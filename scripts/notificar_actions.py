"""Consulta o Painel de Negócios do DOC de São Paulo e envia o relatório."""
import csv
import io
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

PAINEL = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php?acao=negocios_pesquisar"
FUSO = ZoneInfo("America/Sao_Paulo")
MODALIDADE = re.compile(r"preg[ãâa]o|concorr[êe]ncia|licita[çc][ãa]o|di[áa]logo competitivo|leil[ãa]o|tomada de pre[çc]os|concurso de projetos|convite", re.I)

# O painel agrupa por processo e inclui também eventos históricos de outras datas.
LER_PAGINA = """() => Array.from(document.querySelectorAll('#sumarioNegocio .dadosDocumentoNegocio'), item => {
    const grupo = item.closest('li')?.parentElement?.closest('li');
    const processo = grupo?.querySelector('.detalhesUnidade');
    const ato = item.querySelector('a[href*=md_epubli_visualizar]') || item.querySelector('a.nroSei');
    return {
        processo: processo?.querySelector('a')?.textContent.trim() || '',
        modalidade: processo?.textContent.trim() || '',
        evento: ato?.textContent.trim() || '',
        link: ato?.href || '',
        detalhes: item.textContent.replace(/\\s+/g,' ').trim(),
        orgao: [...item.querySelectorAll('[title]')].map(el=>el.title).filter(Boolean).join(' / ')
    };
})"""


def consultar():
    registros = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(locale="pt-BR", timezone_id="America/Sao_Paulo")
        response = page.goto(PAINEL, wait_until="domcontentloaded", timeout=45000)
        if response is None or not response.ok:
            raise RuntimeError(f"Painel respondeu HTTP {response.status if response else 'desconhecido'}")
        date_input = page.locator('input[placeholder="__/__/____"]:visible').first
        data = date_input.input_value(timeout=12000)
        datetime.strptime(data, "%d/%m/%Y")
        contagem = re.compile(r"Exibindo\s+([\d.]+)\s*-\s*([\d.]+)\s+de\s+([\d.]+)", re.I)
        esperado = 1
        while True:
            indicador = page.get_by_text(contagem).first
            inicio, fim, total = [int(n.replace(".", "")) for n in contagem.search(indicador.inner_text(timeout=15000)).groups()]
            if inicio != esperado or not inicio <= fim <= total:
                raise RuntimeError("Paginação do painel inconsistente")
            eventos = page.evaluate(LER_PAGINA)
            if not eventos:
                raise RuntimeError(f"Página de resultados {inicio} a {fim} sem eventos legíveis")
            print(f"Página {inicio} a {fim} de {total}: {len(eventos)} eventos", flush=True)
            for row in eventos:
                if not row["modalidade"]:
                    raise RuntimeError(f"Processo sem modalidade na página {inicio}: {row['detalhes'][:120]}")
                if f"Publicado em {data}" not in row["detalhes"] or not MODALIDADE.search(row["modalidade"]):
                    continue
                if not row["evento"] or not row["link"]:
                    raise RuntimeError(f"Ato incompleto no processo {row['processo']}: {row['detalhes'][:160]}")
                link = urlsplit(urljoin(PAINEL, row["link"]))
                if link.hostname != "diariooficial.prefeitura.sp.gov.br" or not row["processo"]:
                    raise RuntimeError("Documento sem identificação ou link oficial")
                url = link._replace(scheme="https").geturl()
                registros[(row["processo"], row["evento"])] = (row["processo"], row["evento"], row["orgao"], url)
            if fim == total:
                break
            esperado = fim + 1
            page.get_by_role("link", name="Próximo", exact=True).click()
            page.get_by_text(re.compile(rf"Exibindo\s+{esperado}\s*-")).first.wait_for(timeout=20000)
        return data, list(registros.values())


def enviar(assunto, corpo, registros):
    user = os.environ["SMTP_USER"].strip()
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = "raphael.hendrigo@gmail.com, aiwamoto8@hotmail.com"
    msg["Subject"] = assunto
    msg.set_content(corpo)
    if registros:
        arquivo = io.StringIO()
        csv.writer(arquivo, delimiter=";").writerows([("Processo", "Ato", "Órgão", "Documento"), *registros])
        msg.add_attachment(arquivo.getvalue().encode("utf-8-sig"), maintype="text", subtype="csv", filename="licitacoes.csv")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ssl.create_default_context()) as servidor:
        servidor.login(user, os.environ["SMTP_APP_PASSWORD"].replace(" ", ""))
        recusados = servidor.send_message(msg)
        if recusados:
            raise RuntimeError(f"SMTP recusou {len(recusados)} destinatário(s)")
    print("Mensagem aceita pelo SMTP para os dois destinatários.", flush=True)


if __name__ == "__main__":
    agora = datetime.now(FUSO).strftime("%d/%m/%Y %H:%M")
    try:
        data, registros = consultar()
    except Exception as erro:
        print(f"Consulta indisponível: {erro}", flush=True)
        enviar(f"[DOC São Paulo] Consulta indisponível · {agora}",
               f"O monitor tentou consultar o Diário Oficial às {agora} (São Paulo). "
               f"Não foi possível verificar os atos nesta rodada.\n\nPainel oficial: {PAINEL}", [])
        raise
    resumo = "\n\n".join(f"{evento} — {orgao}\nProcesso {processo}\n{link}" for processo, evento, orgao, link in registros[:8])
    enviar(f"[DOC São Paulo] {len(registros)} atos de licitação · {agora}",
           f"Consulta em {agora} (São Paulo). Data exibida pelo painel: {data}.\n"
           f"Atos de licitação identificados: {len(registros)}. "
           f"O total é da edição e pode se repetir entre consultas.\n\n{resumo}\n\n"
           f"{'A relação completa está no CSV anexo. ' if registros else ''}Painel oficial: {PAINEL}", registros)
