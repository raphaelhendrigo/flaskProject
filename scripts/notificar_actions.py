"""Envia notificacao de execucao de GitHub Actions usando Gmail SMTP e Secrets."""
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

user = os.environ.get("SMTP_USER", "").strip()
password = os.environ.get("SMTP_APP_PASSWORD", "").replace(" ", "").strip()
if not user or not password:
    raise SystemExit(
        "Envio nao configurado: crie os Secrets SMTP_USER e SMTP_APP_PASSWORD "
        "em Settings > Secrets and variables > Actions. "
        "Nao use sua senha normal do Gmail."
    )

now = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S %Z")
event = os.environ.get("GITHUB_EVENT_NAME", "desconhecido")
repository = os.environ.get("GITHUB_REPOSITORY", "desconhecido")
run_id = os.environ.get("GITHUB_RUN_ID", "")
run_url = f"https://github.com/{repository}/actions/runs/{run_id}"

msg = EmailMessage()
msg["From"] = user
msg["To"] = "raphael.hendrigo@gmail.com, aiwamoto8@hotmail.com"
msg["Subject"] = f"[GitHub Actions] Execucao {event} - {now}"
msg.set_content(
    f"Diagnostico do GitHub Actions iniciado.\n\n"
    f"Data/hora de envio em Brasilia: {now}\n"
    f"Evento: {event}\n"
    f"Repositorio: {repository}\n"
    f"Log da execucao: {run_url}\n\n"
    "Esta mensagem confirma que o passo de envio de e-mail foi executado. "
    "O resultado completo do workflow deve ser conferido no link acima.\n"
)

with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
    server.login(user, password)
    server.send_message(msg)
print("E-mail entregue ao servidor SMTP para os dois destinatarios.")
