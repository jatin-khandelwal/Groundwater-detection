from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote


class EmailDeliveryError(RuntimeError):
    pass


def _settings() -> dict[str, str]:
    return {
        "host": os.getenv("GW_SMTP_HOST", "").strip(),
        "port": os.getenv("GW_SMTP_PORT", "587").strip(),
        "username": os.getenv("GW_SMTP_USERNAME", "").strip(),
        "password": os.getenv("GW_SMTP_PASSWORD", ""),
        "sender": os.getenv("GW_MAIL_FROM", "").strip(),
        "admin": os.getenv("GW_ADMIN_NOTIFICATION_EMAIL", "").strip(),
        "frontend_url": os.getenv("GW_PUBLIC_FRONTEND_URL", "").strip().rstrip("/"),
    }


def is_configured() -> bool:
    settings = _settings()
    return all(settings.values())


def _send(to: str, subject: str, text: str, html_body: str) -> None:
    settings = _settings()
    if not is_configured():
        raise EmailDeliveryError("Email delivery is not configured.")
    try:
        port = int(settings["port"])
        message = EmailMessage()
        message["From"] = settings["sender"]
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings["host"], port, timeout=20) as server:
            server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(message)
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Email could not be sent. Check the mail settings in Render.") from exc


def send_verification_email(to: str, token: str) -> None:
    settings = _settings()
    link = f"{settings['frontend_url']}/?complete_registration={quote(token, safe='')}"
    safe_link = html.escape(link, quote=True)
    _send(
        to,
        "Verify your Groundwater Intelligence access request",
        f"Open this link to verify your email address: {link}\nThe link expires in 24 hours. After verification, an administrator will review your access request.",
        f"<p>Verify your email address for Groundwater Intelligence.</p>"
        f"<p><a href=\"{safe_link}\">Verify email address</a></p>"
        "<p>This link expires in 24 hours. An administrator will review the request after verification.</p>",
    )


def send_admin_request_notice(email: str) -> None:
    settings = _settings()
    safe_email = html.escape(email)
    _send(
        settings["admin"],
        "Groundwater Intelligence: access request ready for review",
        f"A verified access request from {email} is waiting in the Administrator panel.",
        f"<p>A verified access request from <strong>{safe_email}</strong> is waiting in the "
        f"<a href=\"{html.escape(settings['frontend_url'], quote=True)}\">Administrator panel</a>.</p>",
    )


def send_access_decision(to: str, approved: bool) -> None:
    if approved:
        subject = "Groundwater Intelligence access approved"
        text = "Your access request was approved. You can now sign in using the password you chose when requesting access."
        detail = "Your access request has been approved. You can now sign in with the password you chose."
    else:
        subject = "Groundwater Intelligence access request update"
        text = "Your access request was not approved. Contact the project administrator if you need more information."
        detail = "Your access request was not approved. Contact the project administrator if you need more information."
    _send(
        to,
        subject,
        f"{text}\nSign in: {_settings()['frontend_url']}",
        f"<p>{html.escape(detail)}</p><p><a href=\"{html.escape(_settings()['frontend_url'], quote=True)}\">Open Groundwater Intelligence</a></p>",
    )
