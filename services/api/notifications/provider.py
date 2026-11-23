"""Provider abstraction, normalized result models, and mock channel adapters.

Important architectural rule:
A provider's immediate response reflects ACCEPTANCE into its pipeline, never confirmed
end-user delivery. Confirmed delivery requires asynchronous provider delivery receipts (webhooks).
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from services.api.notifications.crypto import (
    decrypt_push_token as decrypt_token_at_rest,
)
from services.api.notifications.crypto import (
    encrypt_push_token as encrypt_token_at_rest,
)
from services.api.notifications.crypto import (
    hash_push_token,
    mask_token_for_display,
)
from services.api.notifications.exceptions import (
    ProviderPermanentError,
    ProviderTimeoutError,
)
from services.api.notifications.schemas import (
    NotificationChannel,
    ProviderResult,
    ProviderStatus,
)


class BaseNotificationProvider(ABC):
    """Abstract interface for multi-channel notification dispatch providers."""

    def __init__(self, name: str, channel: NotificationChannel) -> None:
        self.name = name
        self.channel = channel

    @abstractmethod
    async def send(
        self,
        recipient_destination: str,
        subject: str | None,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Dispatches a notification to the destination.

        Returns:
            ProviderResult indicating acceptance or failure classification.
        """
        pass


class MockPushProvider(BaseNotificationProvider):
    """Mock push notification provider simulating FCM/APNs."""

    def __init__(self, mode: str = "SUCCESS") -> None:
        super().__init__(name="mock_fcm", channel=NotificationChannel.PUSH)
        self.mode = mode  # "SUCCESS", "TRANSIENT_FAILURE", "PERMANENT_FAILURE", "INVALID_TOKEN", "TIMEOUT"
        self.sent_messages: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.sent_messages.clear()

    async def send(
        self,
        recipient_destination: str,
        subject: str | None,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        self.sent_messages.append({
            "recipient": recipient_destination,
            "subject": subject,
            "body": body,
            "payload": payload,
            "mode": self.mode,
        })

        if self.mode == "TIMEOUT":
            raise ProviderTimeoutError(self.name, "Mock FCM service connection timed out")

        if self.mode == "TRANSIENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=True,
                error_message="FCM server unavailable (503 Service Unavailable)",
                raw_response={"error": "Unavailable", "code": 503},
            )

        if self.mode == "INVALID_TOKEN":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="Registration token has been unregistered or expired (UNREGISTERED)",
                raw_response={"error": "UNREGISTERED", "code": 404},
            )

        if self.mode == "PERMANENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="Invalid FCM credentials or project quota exceeded (403)",
                raw_response={"error": "SenderIdMismatch", "code": 403},
            )

        # Successful acceptance
        msg_id = f"projects/upostit/messages/{uuid.uuid4()}"
        return ProviderResult(
            success=True,
            status=ProviderStatus.ACCEPTED,
            provider_name=self.name,
            provider_message_id=msg_id,
            is_retryable=False,
            raw_response={"name": msg_id, "status": "ACCEPTED"},
        )


class MockEmailProvider(BaseNotificationProvider):
    """Mock email provider simulating SMTP / SES."""

    def __init__(self, mode: str = "SUCCESS") -> None:
        super().__init__(name="mock_email", channel=NotificationChannel.EMAIL)
        self.mode = mode
        self.sent_messages: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.sent_messages.clear()

    async def send(
        self,
        recipient_destination: str,
        subject: str | None,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        self.sent_messages.append({
            "recipient": recipient_destination,
            "subject": subject,
            "body": body,
            "payload": payload,
            "mode": self.mode,
        })

        if self.mode == "TIMEOUT":
            raise ProviderTimeoutError(self.name, "Mock SMTP socket timed out")

        if self.mode == "TRANSIENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=True,
                error_message="Greylisted: recipient server asked to try again later (451)",
                raw_response={"smtp_code": 451},
            )

        if self.mode == "INVALID_RECIPIENT":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="Mailbox does not exist (550 5.1.1 User unknown)",
                raw_response={"smtp_code": 550},
            )

        if self.mode == "PERMANENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="SPF/DKIM alignment failure or recipient blocked (554)",
                raw_response={"smtp_code": 554},
            )

        msg_id = f"<{uuid.uuid4()}@mail.upostit.local>"
        return ProviderResult(
            success=True,
            status=ProviderStatus.ACCEPTED,
            provider_name=self.name,
            provider_message_id=msg_id,
            is_retryable=False,
            raw_response={"id": msg_id, "status": "QUEUED"},
        )


class MockSmsProvider(BaseNotificationProvider):
    """Mock SMS provider simulating Twilio / AWS SNS."""

    def __init__(self, mode: str = "SUCCESS") -> None:
        super().__init__(name="mock_sms", channel=NotificationChannel.SMS)
        self.mode = mode
        self.sent_messages: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.sent_messages.clear()

    async def send(
        self,
        recipient_destination: str,
        subject: str | None,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        self.sent_messages.append({
            "recipient": recipient_destination,
            "subject": subject,
            "body": body,
            "payload": payload,
            "mode": self.mode,
        })

        if self.mode == "TIMEOUT":
            raise ProviderTimeoutError(self.name, "Mock SMS gateway timed out")

        if self.mode == "TRANSIENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=True,
                error_message="Rate limit exceeded on shortcode (429)",
                raw_response={"error_code": 429},
            )

        if self.mode == "INVALID_RECIPIENT":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="Invalid phone number format or unreachable landline (21211)",
                raw_response={"error_code": 21211},
            )

        if self.mode == "PERMANENT_FAILURE":
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message="Carrier blocked message due to content filtering (30007)",
                raw_response={"error_code": 30007},
            )

        msg_id = f"SM{uuid.uuid4().hex}"
        return ProviderResult(
            success=True,
            status=ProviderStatus.ACCEPTED,
            provider_name=self.name,
            provider_message_id=msg_id,
            is_retryable=False,
            raw_response={"sid": msg_id, "status": "QUEUED"},
        )


class ProviderRegistry:
    """Registry routing channels to their active provider adapter."""

    def __init__(self, use_live_fcm: bool | None = None) -> None:
        from services.api.config import settings

        live_fcm = use_live_fcm if use_live_fcm is not None else settings.FCM_ENABLED
        push_provider: BaseNotificationProvider
        if live_fcm:
            from services.api.notifications.fcm_provider import FirebasePushProvider

            push_provider = FirebasePushProvider()
        else:
            push_provider = MockPushProvider()

        self._providers: dict[NotificationChannel, BaseNotificationProvider] = {
            NotificationChannel.PUSH: push_provider,
            NotificationChannel.EMAIL: MockEmailProvider(),
            NotificationChannel.SMS: MockSmsProvider(),
        }

    def register(self, channel: NotificationChannel, provider: BaseNotificationProvider) -> None:
        self._providers[channel] = provider

    def get_provider(self, channel: NotificationChannel | str) -> BaseNotificationProvider:
        ch = NotificationChannel(channel) if isinstance(channel, str) else channel
        provider = self._providers.get(ch)
        if not provider:
            raise ProviderPermanentError(
                provider_name="unknown",
                message=f"No provider registered for channel {ch.value}",
            )
        return provider


__all__ = [
    "BaseNotificationProvider",
    "MockEmailProvider",
    "MockPushProvider",
    "MockSmsProvider",
    "ProviderRegistry",
    "decrypt_token_at_rest",
    "encrypt_token_at_rest",
    "hash_push_token",
    "mask_token_for_display",
]
