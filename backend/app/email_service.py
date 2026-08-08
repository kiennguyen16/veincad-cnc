from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from app.config import Settings


def password_reset_link(settings: Settings, token: str) -> str:
    query = urlencode({"token": token})
    return f"{settings.frontend_url.rstrip('/')}/reset-password?{query}"


def send_password_reset_email(*, settings: Settings, email: str, reset_link: str) -> bool:
    if not settings.smtp_host or not settings.smtp_from_email:
        log_path = settings.storage_dir / "password_reset_links.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{email}: {reset_link}\n")
        print(f"Password reset link for {email}: {reset_link}")
        return False

    message = EmailMessage()
    message["Subject"] = "Reset your VeinCAD CNC password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "\n".join(
            [
                "We received a request to reset your VeinCAD CNC password.",
                "",
                "Open this link to choose a new password:",
                reset_link,
                "",
                f"This link expires in {settings.password_reset_minutes} minutes.",
                "",
                "If you did not request this, you can ignore this email.",
            ]
        )
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)

    return True
