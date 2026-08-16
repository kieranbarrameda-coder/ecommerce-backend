import logging

import sib_api_v3_sdk
from fastapi.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key["api-key"] = settings.BREVO_API_KEY
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email}],
        sender={"email": settings.BREVO_FROM_EMAIL},
        subject="Reset your password",
        html_content=f'<p>Click the link below to reset your password. This link expires in 30 minutes.</p><p><a href="{reset_url}">Reset password</a></p>',
        text_content=f"Reset your password by visiting: {reset_url}\n\nThis link expires in 30 minutes.",
    )
    await run_in_threadpool(api_instance.send_transac_email, send_smtp_email)
