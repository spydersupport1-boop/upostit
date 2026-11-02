"""Email delivery service abstraction supporting SMTP, development preview, and in-memory test queue."""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from services.api.config import settings

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    """Masks an email address for PII-safe logging (e.g. jo***e@example.com)."""
    if not email or "@" not in email:
        return "***"
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 2:
        masked_local = f"{local_part[0]}***"
    else:
        masked_local = f"{local_part[0]}***{local_part[-1]}"
    return f"{masked_local}@{domain}"


@dataclass
class DeliveryResult:
    """Outcome of an email delivery attempt."""

    success: bool
    status: str  # "sent", "failed"
    error_message: str | None = None
    preview_url: str | None = None
    recipient: str = ""


class EmailDeliveryService:
    """Abstracts email dispatch across SMTP, development console preview, and testing backends."""

    def __init__(self) -> None:
        self.outbox: list[dict[str, Any]] = []

    def clear_outbox(self) -> None:
        """Clears the in-memory outbox (useful between test cases)."""
        self.outbox.clear()

    def get_outbox(self) -> list[dict[str, Any]]:
        """Returns captured messages in memory for test assertions."""
        return list(self.outbox)

    def _render_invitation_templates(
        self,
        recipient_name: str,
        company_name: str,
        activation_url: str,
        expire_hours: int,
    ) -> tuple[str, str, str]:
        """Renders subject, plain-text body, and HTML body for an invitation email."""
        subject = f"Invitation to join {company_name} on Attendance SaaS"

        text_content = (
            f"Hello {recipient_name},\n\n"
            f"You have been invited to join {company_name} on Attendance SaaS.\n\n"
            f"To activate your account and set your secure password, please visit:\n"
            f"{activation_url}\n\n"
            f"This activation link will expire in {expire_hours} hours and can only be used once.\n\n"
            f"If you did not anticipate this invitation, please notify your organization administrator.\n"
        )

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f9; color: #1e293b; margin: 0; padding: 24px; }}
    .container {{ max-width: 580px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px; }}
    .header {{ margin-bottom: 24px; }}
    .header h2 {{ margin: 0; color: #0f172a; font-size: 22px; }}
    .company {{ color: #2563eb; font-weight: 600; }}
    .content p {{ font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 16px 0; }}
    .btn-container {{ margin: 28px 0; text-align: center; }}
    .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px; }}
    .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #64748b; line-height: 1.5; }}
    .break {{ word-break: break-all; color: #64748b; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>Welcome to <span class="company">{company_name}</span></h2>
    </div>
    <div class="content">
      <p>Hello {recipient_name},</p>
      <p>You have been invited to activate your employee profile and establish your account credentials on <strong>{company_name}</strong>'s attendance portal.</p>
      <div class="btn-container">
        <a href="{activation_url}" class="btn" target="_blank" rel="noopener noreferrer">Activate Your Account</a>
      </div>
      <p style="font-size: 13px; color: #64748b;">This secure activation link will expire in <strong>{expire_hours} hours</strong> and can only be used once.</p>
    </div>
    <div class="footer">
      <p>If the button above does not work, copy and paste this link into your browser:</p>
      <p class="break">{activation_url}</p>
      <p style="margin-top: 16px;">If you did not expect this invitation, please ignore this email.</p>
    </div>
  </div>
</body>
</html>"""
        return subject, text_content, html_content

    def _send_smtp_sync(
        self,
        recipient_email: str,
        subject: str,
        text_content: str,
        html_content: str,
    ) -> None:
        """Executes synchronous SMTP transport inside a background worker thread."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
        msg["To"] = recipient_email
        msg.set_content(text_content)
        msg.add_alternative(html_content, subtype="html")

        context = ssl.create_default_context()
        if not settings.SMTP_HOST:
            raise RuntimeError("SMTP_HOST is not configured.")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=context)
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

    async def send_invitation_email(
        self,
        recipient_email: str,
        recipient_name: str,
        company_name: str,
        raw_token: str,
        activation_url: str,
    ) -> DeliveryResult:
        """
        Dispatches an employee invitation email.
        In production, raw tokens and full URLs are strictly excluded from logging.
        """
        expire_hours = settings.INVITATION_TOKEN_EXPIRE_HOURS
        subject, text_content, html_content = self._render_invitation_templates(
            recipient_name=recipient_name,
            company_name=company_name,
            activation_url=activation_url,
            expire_hours=expire_hours,
        )

        masked_to = mask_email(recipient_email)
        backend = (settings.EMAIL_BACKEND or "console").lower().strip()

        # 1. Memory / Test backend
        if backend == "memory":
            record = {
                "recipient": recipient_email,
                "recipient_name": recipient_name,
                "company_name": company_name,
                "raw_token": raw_token,
                "activation_url": activation_url,
                "subject": subject,
                "text_content": text_content,
                "html_content": html_content,
            }
            self.outbox.append(record)
            logger.info("Captured invitation email in memory for %s", masked_to)
            return DeliveryResult(
                success=True,
                status="sent",
                preview_url=activation_url if settings.ENVIRONMENT != "production" else None,
                recipient=recipient_email,
            )

        # 2. SMTP backend
        if backend == "smtp":
            try:
                await asyncio.to_thread(
                    self._send_smtp_sync,
                    recipient_email=recipient_email,
                    subject=subject,
                    text_content=text_content,
                    html_content=html_content,
                )
                logger.info("Successfully delivered invitation email via SMTP to %s", masked_to)
                return DeliveryResult(
                    success=True,
                    status="sent",
                    recipient=recipient_email,
                )
            except Exception as e:
                err_msg = f"SMTP dispatch failed: {type(e).__name__}"
                logger.error("Failed to deliver invitation email to %s: %s", masked_to, err_msg)
                return DeliveryResult(
                    success=False,
                    status="failed",
                    error_message=err_msg,
                    recipient=recipient_email,
                )

        # 3. Development / Console Preview fallback
        # If no SMTP provider is configured, safe development-only invitation preview
        if settings.ENVIRONMENT != "production":
            logger.info(
                "[DEV EMAIL PREVIEW] To: %s | Subject: %s | URL: %s",
                masked_to,
                subject,
                activation_url,
            )
            return DeliveryResult(
                success=True,
                status="sent",
                preview_url=activation_url,
                recipient=recipient_email,
            )
        else:
            # Production without SMTP: record as failed delivery safely without leaking token
            logger.warning(
                "Production email dispatch attempted without active SMTP configuration for %s",
                masked_to,
            )
            return DeliveryResult(
                success=False,
                status="failed",
                error_message="Email provider is not configured for production delivery.",
                recipient=recipient_email,
            )


# Global singleton instance
email_service = EmailDeliveryService()
