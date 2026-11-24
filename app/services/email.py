import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from app.config import settings


logger = logging.getLogger(__name__)


def send_password_reset_email(recipient: str, token: str) -> None:
    if not settings.smtp_host:
        logger.warning("Password reset email not sent because SMTP is not configured.")
        return

    reset_url = f"{settings.app_base_url.rstrip('/')}/reset-password#{quote(token, safe='')}"
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = recipient
    message["Subject"] = "Reset your ClassSwap password"
    message.set_content(
        "Use this link within 15 minutes to reset your ClassSwap password:\n\n"
        f"{reset_url}\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(message)


def dispatch_password_reset_email(recipient: str, token: str) -> None:
    try:
        send_password_reset_email(recipient, token)
    except (OSError, smtplib.SMTPException) as error:
        logger.error(
            "Password reset email delivery failed (%s).",
            type(error).__name__,
        )
