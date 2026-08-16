import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": "Reset your password",
        "html": f'<p>Click the link below to reset your password. This link expires in 30 minutes.</p><p><a href="{reset_url}">Reset password</a></p>',
        "text": f"Reset your password by visiting: {reset_url}\n\nThis link expires in 30 minutes.",
    }
    await resend.Emails.send_async(params)
