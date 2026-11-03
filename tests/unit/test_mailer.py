from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from src.core import mailer


def test_log_backend_writes_letter_to_log(caplog):
    with patch.object(mailer.settings, "MAIL_BACKEND", "log"), caplog.at_level("INFO"):
        mailer.send_mail("a@b.ru", "Тема", "Текст 123", "<b>123</b>")
    assert "a***@b.ru" in caplog.text and "a@b.ru" not in caplog.text
    assert "Тема" in caplog.text and "Текст 123" in caplog.text and "<b>" not in caplog.text


def test_mask_email():
    assert mailer.mask_email("petr@mail.ru") == "p***@mail.ru"
    assert mailer.mask_email("P@x.ru") == "P***@x.ru"
    assert mailer.mask_email("broken") == "b***"


def test_smtp_backend_sends_multipart_letter():
    smtp = MagicMock()
    with patch.object(mailer.settings, "MAIL_BACKEND", "smtp"), \
         patch.object(mailer.settings, "SMTP_USER", "noreply@krasmarafon.ru"), \
         patch.object(mailer.settings, "SMTP_PASSWORD", "pw"), \
         patch.object(mailer.settings, "MAIL_FROM", "Красмарафон <noreply@krasmarafon.ru>"), \
         patch("src.core.mailer.smtplib.SMTP_SSL") as cls:
        cls.return_value.__enter__.return_value = smtp
        mailer.send_mail("a@b.ru", "Код для входа: 123 456", "Текст", "<b>HTML</b>")
    cls.assert_called_once_with(mailer.settings.SMTP_HOST, mailer.settings.SMTP_PORT, timeout=15)
    smtp.login.assert_called_once_with("noreply@krasmarafon.ru", "pw")
    msg: EmailMessage = smtp.send_message.call_args[0][0]
    assert msg["To"] == "a@b.ru"
    assert msg["Subject"] == "Код для входа: 123 456"
    assert msg.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]
