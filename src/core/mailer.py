"""Отправка служебных писем (код входа в личный кабинет). Поставщик — settings.MAIL_BACKEND:
log — письмо в лог (разработка, тесты), smtp — ящик домена в Яндексе (SMTP_SSL).
Смена поставщика — новая ветка здесь, вызывающий код не меняется."""

import logging
import smtplib
from email.message import EmailMessage

from src.config import settings

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    """petr@mail.ru -> p***@mail.ru"""
    local, at, domain = (email or "").partition("@")
    return f"{local[:1]}***{at}{domain}"


def send_mail(to: str, subject: str, text: str, html: str) -> None:
    """Блокирующая отправка; ошибки поставщика пробрасываются вызывающему."""
    if settings.MAIL_BACKEND != "smtp":
        logger.info("MAIL (log) to=%s subject=%s\n%s", mask_email(to), subject, text)
        return
    msg = EmailMessage()
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
