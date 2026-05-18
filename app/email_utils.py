import mimetypes
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from flask import current_app


@dataclass
class EmailDeliveryResult:
    sent: bool
    fallback_used: bool
    message: str


def _print_fallback(subject, recipient, text_body):
    separator = "=" * 72
    print(separator)
    print("YourSeat email fallback")
    print(f"To: {recipient}")
    print(f"Subject: {subject}")
    print()
    print(text_body)
    print(separator)


def send_email(recipient, subject, html_body, text_body, inline_images=None):
    host = current_app.config.get("SMTP_HOST", "")
    port = int(current_app.config.get("SMTP_PORT", 587))
    username = current_app.config.get("SMTP_USERNAME", "")
    password = current_app.config.get("SMTP_PASSWORD", "")
    use_tls = bool(current_app.config.get("SMTP_USE_TLS", True))
    use_ssl = bool(current_app.config.get("SMTP_USE_SSL", False))
    sender = current_app.config.get("MAIL_FROM", "noreply@yourseat.local")

    if not host:
        _print_fallback(subject, recipient, text_body)
        return EmailDeliveryResult(
            sent=False,
            fallback_used=True,
            message="SMTP не налаштовано. Посилання для тесту виведено в консоль.",
        )

    if username and not password:
        _print_fallback(subject, recipient, text_body)
        return EmailDeliveryResult(
            sent=False,
            fallback_used=True,
            message="Не задано SMTP_PASSWORD. Додайте app password Gmail у .env, і тоді лист піде реально на пошту.",
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    html_part = message.get_payload()[-1]
    for image in inline_images or []:
        try:
            image_path = Path(image["path"])
            mime_type = image.get("mime_type") or mimetypes.guess_type(str(image_path))[0] or "image/png"
            maintype, subtype = mime_type.split("/", 1)
            html_part.add_related(
                image_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                cid=f"<{image['cid']}>",
                disposition="inline",
            )
        except Exception:
            current_app.logger.exception("Не вдалося підготувати inline image для email: %s", image)

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as server:
            if not use_ssl and use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(message)
    except Exception as error:
        current_app.logger.exception("Не вдалося відправити email ресторану.")
        _print_fallback(subject, recipient, text_body)
        return EmailDeliveryResult(
            sent=False,
            fallback_used=True,
            message=f"SMTP недоступний ({error}). Посилання для тесту виведено в консоль.",
        )

    return EmailDeliveryResult(
        sent=True,
        fallback_used=False,
        message="Email ресторану успішно відправлено.",
    )
