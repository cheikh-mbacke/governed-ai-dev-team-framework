"""Small stdlib SMTP transport; credentials are never logged or returned."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from governed_ai.notifications.config import SmtpSettings


def send_email(
    settings: SmtpSettings,
    *,
    recipients: tuple[str, ...],
    subject: str,
    body: str,
) -> None:
    if not recipients:
        raise ValueError("at least one recipient is required")
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=settings.sender.partition("@")[2] or None)
    message.set_content(body)

    context = ssl.create_default_context()
    if settings.security == "ssl":
        with smtplib.SMTP_SSL(
            settings.host,
            settings.port,
            timeout=settings.connect_timeout_seconds,
            context=context,
        ) as client:
            if settings.username:
                client.login(settings.username, settings.password)
            client.send_message(message)
        return

    with smtplib.SMTP(
        settings.host,
        settings.port,
        timeout=settings.connect_timeout_seconds,
    ) as client:
        client.ehlo()
        if settings.security == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if settings.username:
            client.login(settings.username, settings.password)
        client.send_message(message)
