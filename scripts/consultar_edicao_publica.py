"""Prepara uma transferência temporária de uma edição pública para o solicitante."""
import gzip
import json
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from playwright.sync_api import sync_playwright

SITE = "https://diariooficial.prefeitura.sp.gov.br/md_epubli_controlador.php"
pedido = json.loads(Path("monitor-doc/pedido.json").read_text())
data = date.fromisoformat(pedido["data"]).strftime("%d/%m/%Y")
assert re.fullmatch(r"[a-f0-9]{16}", pedido["id"])
pdf_publico = []
with sync_playwright() as pw:
    navegador = pw.chromium.launch(channel="chrome")
    pagina = navegador.new_page(locale="pt-BR", timezone_id="America/Sao_Paulo")
    resposta = pagina.goto(SITE + "?acao=inicio", wait_until="domcontentloaded", timeout=60000)
    if not resposta or not resposta.ok:
        raise RuntimeError("Página inicial do Diário indisponível")
    inicio = pagina.get_by_role("link", name="Diário Aberto", exact=True).first
    url = urlsplit(urljoin(SITE, inicio.get_attribute("href")))
    if url.hostname != urlsplit(SITE).hostname:
        raise ValueError("Origem inesperada")
    campos = {k:v[0] for k,v in parse_qs(url.query).items()}
    campos["dta"] = data
    pagina.goto(url._replace(query=urlencode(campos)).geturl(), wait_until="domcontentloaded", timeout=60000)
    links = pagina.get_by_role("link", name="JSON", exact=True)
    pagina.locator("main").wait_for()
    urls = list(dict.fromkeys(links.evaluate_all("links => links.map(a=>a.href)")))
    for link in urls:
        u = urlsplit(link)
        if u.hostname != urlsplit(SITE).hostname or parse_qs(u.query).get("dta") != [data]:
            continue
        texto = pagina.evaluate("""async u=>{const r=await fetch(u,{signal:AbortSignal.timeout(90000)}); if(!r.ok)throw Error('HTTP '+r.status);return r.text()}""",link)
        docs = json.loads(texto.lstrip("\ufeff").rstrip().removesuffix(";"))["edicao"]
        if not isinstance(docs,list) or not docs:
            raise ValueError("Edição vazia")
        pdf_publico.append({"fonte":link,"atos":docs})
    pagina_texto = pagina.locator("main").inner_text()
    if not pdf_publico and not re.search(r"(sem edi[çc][ãa]o|n[ãa]o (?:h[áa]|houve|existe) (?:publica[çc][ãa]o|edi[çc][ãa]o)|edi[çc][ãa]o n[ãa]o encontrada)",pagina_texto,re.I):
        raise RuntimeError("Não foi possível verificar a edição solicitada")
estado = {"data":data,"id":pedido["id"],"edicoes":pdf_publico}
with tempfile.TemporaryDirectory() as temp:
    raiz = Path(temp)
    cert = raiz / "publico.pem"
    cert.write_text(pedido["certificado_publico"])
    bruto = raiz / "edicao.json.gz"
    bruto.write_bytes(gzip.compress(json.dumps(estado,ensure_ascii=False).encode()))
    subprocess.run(["openssl","cms","-encrypt","-binary","-aes256","-in",str(bruto),"-outform","DER","-out","edicao.p7m",str(cert)], check=True)
print(f"Data solicitada {data}. Edições confirmadas: {len(pdf_publico)}. Publicações: {sum(len(e['atos']) for e in pdf_publico)}")
