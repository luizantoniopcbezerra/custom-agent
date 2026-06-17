import smtplib
from email.mime.text import MIMEText

from rich.console import Console

console = Console()


class EmailClient:
    """Sends emails via Gmail SMTP using an App Password."""

    def __init__(self, from_addr: str, app_password: str, to_addr: str) -> None:
        self._from = from_addr
        self._password = app_password
        self._to = to_addr

    def send(self, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = self._to
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.starttls()
                smtp.login(self._from, self._password)
                smtp.send_message(msg)
            console.print(f"[Email] Sent: {subject}")
        except Exception as exc:
            console.print(f"[Email] Failed to send '{subject}': {exc}")
