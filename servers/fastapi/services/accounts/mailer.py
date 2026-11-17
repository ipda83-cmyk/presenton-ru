"""E-mail through the deployment's own SMTP box (confirmation, password reset).

SMTP_HOST, SMTP_PORT (465), SMTP_SECURITY (ssl | starttls | auto | none) or
SMTP_SECURE (true | false), SMTP_USERNAME or SMTP_USER, SMTP_PASSWORD or
SMTP_PASS, SMTP_FROM ("Name <address>" works), SMTP_FROM_NAME. Links in the letters
use PRESENTON_PUBLIC_URL, never the request's Host header (a forged Host
would otherwise put someone else's site into a password-reset letter).
"""

import asyncio
import html
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from utils.get_env import get_presenton_public_url

LOGGER = logging.getLogger(__name__)
TIMEOUT_SECONDS = 20
BRAND = "Kvant AI Studio"


class MailError(Exception):
    pass


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    security: str
    username: str
    password: str
    sender: str
    sender_name: str


def _env(*names: str) -> str:
    """The first of these variables that is set: both SMTP_USERNAME/SMTP_PASSWORD
    and the common SMTP_USER/SMTP_PASS (nodemailer style) work."""
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


TRUE = ("1", "true", "yes", "on", "ssl", "tls")


def _security(port_value: str) -> str:
    """ssl, starttls, none, or auto (STARTTLS when the server offers it).

    SMTP_SECURITY wins; SMTP_SECURE=true means SSL and false a plain start
    that upgrades if it can; otherwise port 465 is SSL."""
    explicit = _env("SMTP_SECURITY").lower()
    if explicit in ("ssl", "starttls", "none", "auto"):
        return explicit
    secure = _env("SMTP_SECURE").lower()
    if secure:
        return "ssl" if secure in TRUE else "auto"
    return "ssl" if port_value in ("", "465") else "auto"


def mail_settings() -> MailSettings | None:
    host = _env("SMTP_HOST")
    name, sender = parseaddr(_env("SMTP_FROM", "SMTP_USERNAME", "SMTP_USER"))
    if not host or "@" not in sender:
        return None
    port_value = _env("SMTP_PORT")
    security = _security(port_value)
    try:
        port = int(port_value or (465 if security == "ssl" else 587))
    except ValueError:
        port = 465
    return MailSettings(
        host=host,
        port=port,
        security=security,
        username=_env("SMTP_USERNAME", "SMTP_USER", "SMTP_LOGIN"),
        password=os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS") or "",
        sender=sender,
        sender_name=_env("SMTP_FROM_NAME") or name or BRAND,
    )


def missing_settings() -> list[str]:
    """What still has to be set for letters with working links."""
    missing = []
    if not _env("SMTP_HOST"):
        missing.append("SMTP_HOST")
    if "@" not in parseaddr(_env("SMTP_FROM", "SMTP_USERNAME", "SMTP_USER"))[1]:
        missing.append("SMTP_FROM")
    if get_presenton_public_url() is None:
        missing.append("PRESENTON_PUBLIC_URL")
    return missing


def configured() -> bool:
    return not missing_settings()


def link(path: str) -> str:
    base = get_presenton_public_url()
    if base is None:
        raise MailError("PRESENTON_PUBLIC_URL is not set")
    return f"{base}{path}"


def _send_sync(settings: MailSettings, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.security == "ssl":
        client = smtplib.SMTP_SSL(settings.host, settings.port, timeout=TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(settings.host, settings.port, timeout=TIMEOUT_SECONDS)
    with client:
        if settings.security == "starttls":
            client.starttls(context=context)
        elif settings.security == "auto":
            client.ehlo()
            if client.has_extn("starttls"):
                client.starttls(context=context)
        if settings.username and settings.password:
            client.login(settings.username, settings.password)
        client.send_message(message)


async def send(to: str, subject: str, text: str, body_html: str) -> None:
    settings = mail_settings()
    if settings is None:
        raise MailError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.sender_name, settings.sender))
    message["To"] = to
    message["Message-ID"] = make_msgid(domain=settings.sender.rsplit("@", 1)[-1])
    message.set_content(text)
    message.add_alternative(body_html, subtype="html")
    try:
        await asyncio.to_thread(_send_sync, settings, message)
    except (OSError, smtplib.SMTPException) as error:
        LOGGER.warning("Could not send the letter %r: %s", subject, error)
        raise MailError(str(error)) from error


LETTERS = {
    "ru": {
        "verify": {
            "subject": "Подтвердите e-mail в Kvant AI Studio",
            "lead": "Вы зарегистрировались в Kvant AI Studio. Подтвердите адрес — после этого на счёт поступит стартовый бонус.",
            "button": "Подтвердить e-mail",
            "note": "Ссылка действует 48 часов. Если вы не регистрировались, просто удалите это письмо.",
        },
        "reset": {
            "subject": "Новый пароль для Kvant AI Studio",
            "lead": "Кто-то (надеемся, вы) попросил сменить пароль. Задайте новый по кнопке ниже.",
            "button": "Задать новый пароль",
            "note": "Ссылка действует 1 час и сработает один раз. Если вы не просили сменить пароль, ничего делать не нужно.",
        },
        "test": {
            "subject": "Проверка почты Kvant AI Studio",
            "lead": "Это тестовое письмо: почта для подтверждений и сброса паролей настроена.",
            "button": "Открыть Kvant AI Studio",
            "note": "Письмо отправлено из «Админка → Регистрация».",
        },
        "fallback": "Если кнопка не работает, откройте ссылку:",
    },
    "en": {
        "verify": {
            "subject": "Confirm your e-mail for Kvant AI Studio",
            "lead": "You signed up for Kvant AI Studio. Confirm the address and the starting bonus goes to your balance.",
            "button": "Confirm e-mail",
            "note": "The link works for 48 hours. If you did not sign up, just delete this letter.",
        },
        "reset": {
            "subject": "New password for Kvant AI Studio",
            "lead": "Someone (hopefully you) asked to change the password. Set a new one with the button below.",
            "button": "Set a new password",
            "note": "The link works for 1 hour and only once. If you did not ask for it, nothing needs to be done.",
        },
        "test": {
            "subject": "Kvant AI Studio mail check",
            "lead": "This is a test letter: mail for confirmations and password resets is set up.",
            "button": "Open Kvant AI Studio",
            "note": "Sent from Admin → Sign-up.",
        },
        "fallback": "If the button does not work, open the link:",
    },
}


def letter(kind: str, locale: str, url: str) -> tuple[str, str, str]:
    """Subject, plain text and HTML of a letter in the user's language."""
    texts = LETTERS["en" if locale == "en" else "ru"]
    words = texts[kind]
    safe_url = html.escape(url, quote=True)
    text = f"{words['lead']}\n\n{words['button']}: {url}\n\n{words['note']}\n\n— {BRAND}"
    body = f"""<!doctype html><html><body style="margin:0;background:#F6F6F9;font-family:Arial,Helvetica,sans-serif;color:#101323">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#FFFFFF;border:1px solid #EDEEEF;border-radius:16px;padding:32px">
<tr><td style="font-size:13px;font-weight:bold;letter-spacing:.08em;text-transform:uppercase;color:#03B015">{BRAND}</td></tr>
<tr><td style="padding-top:16px;font-size:16px;line-height:24px">{html.escape(words['lead'])}</td></tr>
<tr><td style="padding:24px 0"><a href="{safe_url}" style="display:inline-block;background:#03B015;color:#FFFFFF;text-decoration:none;font-weight:bold;font-size:14px;padding:12px 24px;border-radius:999px">{html.escape(words['button'])}</a></td></tr>
<tr><td style="font-size:13px;line-height:20px;color:#667085">{html.escape(words['note'])}</td></tr>
<tr><td style="padding-top:16px;font-size:12px;line-height:18px;color:#98A2B3">{html.escape(texts['fallback'])}<br><a href="{safe_url}" style="color:#027A0E;word-break:break-all">{safe_url}</a></td></tr>
</table></td></tr></table></body></html>"""
    return words["subject"], text, body
