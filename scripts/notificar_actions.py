"""Consulta o Painel de Negócios do DOC de São Paulo e envia o relatório."""
import csv
import io
import json
from html import unescape
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ORIGEM = "https://diariooficial.prefeitura.sp.gov.br/"
DIARIO = ORIGEM + "md_epubli_controlador.php?acao=diario_aberto&formato=A"
FUSO = ZoneInfo("America/Sao_Paulo")
LICITACAO = re.compile(
    r"\bpreg[ãâa]o\b|\bconcorr[êe]ncia\s+(?:p[úu]blica|eletr[ôo]nica|n[º°o.]|\d)|"
    r"\b(?:aviso|ata|edital|abertura|resultado|reabertura)\s+d[ae]\s+licita[çc][ãa]o|"
    r"\bcarta[ -]convite|\bdi[áa]logo competitivo|\btomada de pre[çc]os|\bleil[ãa]o\b|\bconcurso de projetos",
    re.I,
)
TEXTO = re.compile(r"<[^>]+>")
DIRETA = re.compile(r"^(?:dispensa|inexigibilidade)", re.I)


def resumo_ato(row):
    texto = " ".join(unescape(TEXTO.sub(" ", row["conteudo"] or "")).split())
    tipo = (row["serie"] or "").strip()
    modalidade = re.search(r"\bModalidade\s*:?\s*(.{1,100})", texto, re.I)
    if modalidade and DIRETA.search(modalidade[1]):
        return None
    achado = LICITACAO.search(texto) or LICITACAO.search(tipo)
    if not achado and not (modalidade and re.match(r"concorr[êe]ncia\b", modalidade[1], re.I)):
        return None
    link = urlsplit(row["link"])
    if link.hostname != "diariooficial.prefeitura.sp.gov.br" or not row["documento"]:
        raise ValueError("Ato sem documento ou link oficial")
    objeto = re.search(r"\bObjeto(?:\s+(?:da licitação|do contrato|da contratação))?\s*:?\s+(.{8,})", texto, re.I)
    if objeto:
        trecho = re.split(r"\s+(?:Processo|Modalidade|Número do processo|Data de publicação|Nome do contratado|Arquivo)\s*:", objeto[1], maxsplit=1, flags=re.I)[0]
    else:
        pos = max(0, achado.start() - 40) if achado and achado.string == texto else 0
        trecho = texto[pos:]
    return (row["processo"] or "Sem número indicado", tipo, row["orgao"] or "", str(row["documento"]), trecho[:320], link._replace(scheme="https").geturl())


def consultar():
    registros = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(locale="pt-BR", timezone_id="America/Sao_Paulo")
        resp = page.goto(DIARIO, wait_until="domcontentloaded", timeout=45000)
        if not resp or not resp.ok:
            raise RuntimeError(f"Diário Aberto respondeu HTTP {resp.status if resp else 'desconhecido'}")
        botao = page.get_by_role("link", name="JSON", exact=True)
        botao.first.wait_for(timeout=20000)
        links = list(dict.fromkeys(botao.evaluate_all("links => links.map(a=>a.href)")))
        datas = set()
        lidos = 0
        for link in links:
            url = urlsplit(link)
            if url.hostname != urlsplit(DIARIO).hostname:
                raise ValueError("Exportação fora do portal municipal")
            data = parse_qs(url.query)["dta"][0]
            datetime.strptime(data, "%d/%m/%Y")
            datas.add(data)
            texto = page.evaluate("""async url => {
                const r = await fetch(url, {signal: AbortSignal.timeout(90000)});
                if (!r.ok) throw Error('Exportação HTTP ' + r.status);
                return r.text();
            }""", link)
            # O portal acrescenta um ponto e vírgula após o objeto JSON.
            edicao = json.loads(texto.lstrip("\ufeff").rstrip().removesuffix(";"))["edicao"]
            if not isinstance(edicao, list) or not edicao:
                raise ValueError("A exportação da edição veio vazia ou mudou de formato")
            lidos += len(edicao)
            for row in edicao:
                registro = resumo_ato(row)
                if registro:
                    registros[row["documento"]] = registro
        if len(datas) != 1:
            raise ValueError("Datas divergentes nas exportações do Diário")
        data = datas.pop()
        print(f"Edição {data}: {lidos} publicações examinadas, {len(registros)} atos selecionados.", flush=True)
        return data, sorted(registros.values(), key=lambda r: ("abertura" not in r[1].lower(), r[2], r[0], r[3]))


def enviar(assunto, corpo, registros):
    user = os.environ["SMTP_USER"].strip()
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = "raphael.hendrigo@gmail.com, aiwamoto8@hotmail.com"
    msg["Subject"] = assunto
    msg.set_content(corpo)
    if registros:
        arquivo = io.StringIO()
        csv.writer(arquivo, delimiter=";").writerows([("Processo", "Ato", "Órgão", "Documento SEI", "Trecho da publicação", "Link oficial"), *registros])
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
               f"Não foi possível verificar os atos nesta rodada.\n\nDiário Aberto: {DIARIO}", [])
        raise
    resumo = "\n\n".join(f"{evento} — {orgao}\nProcesso {processo} · Documento {doc}\n{trecho}\n{link}" for processo, evento, orgao, doc, trecho, link in registros[:8])
    enviar(f"[DOC São Paulo] {len(registros)} atos de licitação · {agora}",
           f"Consulta em {agora} (São Paulo). Data da edição consultada: {data}.\n"
           f"Atos de licitação identificados: {len(registros)}. "
           f"A seleção usa termos de licitação no tipo ou no texto das publicações da edição. O mesmo ato pode aparecer em consultas sucessivas.\n\n{resumo}\n\n"
           f"{'A relação completa está no CSV anexo. ' if registros else ''}Diário Aberto: {DIARIO}", registros)
