"""Firebase Cloud Messaging (FCM) push notification provider adapter.

Adheres strictly to Phase 10 provider abstraction:
- Uses official Google Firebase Admin SDK (firebase-admin).
- Configures platform-specific message structures for Android and iOS (APNs).
- Classifies provider errors into retryable (5xx, rate limits, timeouts) vs permanent (unregistered tokens, invalid sender).
- Safely initializes service-account credentials from environment (file path or inline JSON) without hardcoded secrets.
- Invariant: Provider acceptance maps to status ACCEPTED (SENT in database); device delivery confirmation is unconfirmed.
"""

import asyncio
import json
import logging
import os
from typing import Any

import firebase_admin
from firebase_admin import credentials, exceptions, messaging

from services.api.config import settings
from services.api.notifications.crypto import mask_token_for_display
from services.api.notifications.exceptions import (
    ProviderPermanentError,
    ProviderTimeoutError,
)
from services.api.notifications.provider import BaseNotificationProvider
from services.api.notifications.schemas import (
    NotificationChannel,
    ProviderResult,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class FirebasePushProvider(BaseNotificationProvider):
    """Production Firebase Cloud Messaging adapter supporting Android and iOS push delivery."""

    def __init__(
        self,
        app_name: str = "upostit_fcm",
        credentials_path: str | None = None,
        credentials_json: str | None = None,
        project_id: str | None = None,
    ) -> None:
        super().__init__(name="fcm", channel=NotificationChannel.PUSH)
        self.app_name = app_name
        self._app: firebase_admin.App | None = None
        self._is_configured: bool = False

        self._initialize_app(
            credentials_path=credentials_path,
            credentials_json=credentials_json,
            project_id=project_id,
        )

    def _initialize_app(
        self,
        credentials_path: str | None,
        credentials_json: str | None,
        project_id: str | None,
    ) -> None:
        """Initializes the firebase_admin app using environment or supplied credentials."""
        # Check if app already initialized in firebase_admin registry
        try:
            self._app = firebase_admin.get_app(self.app_name)
            self._is_configured = True
            return
        except ValueError:
            pass  # Not yet initialized

        cred_path = credentials_path or settings.FIREBASE_CREDENTIALS_PATH
        cred_json = credentials_json or settings.FIREBASE_CREDENTIALS_JSON
        proj_id = project_id or settings.FIREBASE_PROJECT_ID

        cred: credentials.Base | None = None

        if cred_path and os.path.exists(cred_path):
            try:
                cred = credentials.Certificate(cred_path)
                logger.info("Initializing Firebase Admin SDK from certificate path: %s", cred_path)
            except Exception as exc:
                logger.error("Failed loading Firebase credentials file: %s", exc)
                self._is_configured = False
                return

        elif cred_json and cred_json.strip():
            try:
                parsed_json = json.loads(cred_json.strip())
                cred = credentials.Certificate(parsed_json)
                logger.info("Initializing Firebase Admin SDK from inline JSON configuration")
            except Exception as exc:
                logger.error("Failed parsing Firebase credentials JSON: %s", type(exc).__name__)
                self._is_configured = False
                return

        if cred:
            options: dict[str, Any] = {}
            if proj_id:
                options["projectId"] = proj_id
            try:
                self._app = firebase_admin.initialize_app(cred, options=options, name=self.app_name)
                self._is_configured = True
            except Exception as exc:
                logger.error("Failed initializing Firebase Admin app: %s", exc)
                self._is_configured = False
        else:
            self._is_configured = False

    @property
    def is_configured(self) -> bool:
        """Returns True if valid Firebase credentials are loaded and active."""
        return self._is_configured

    async def send(
        self,
        recipient_destination: str,
        subject: str | None,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Dispatches an FCM push notification to the recipient token.

        Args:
            recipient_destination: Plaintext decrypted FCM registration token.
            subject: Notification title.
            body: Notification body text.
            payload: Optional dictionary of string key-values.

        Returns:
            ProviderResult indicating provider acceptance or failure classification.
        """
        masked = mask_token_for_display(recipient_destination)

        if not self._is_configured or self._app is None:
            raise ProviderPermanentError(
                provider_name=self.name,
                message=(
                    "FCM provider credentials unconfigured: specify FIREBASE_CREDENTIALS_PATH "
                    "or FIREBASE_CREDENTIALS_JSON in environment."
                ),
            )

        # Basic token sanity check
        clean_token = recipient_destination.strip()
        if not clean_token or clean_token.startswith("user:") or len(clean_token) < 16:
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message=f"Invalid or placeholder destination token ({masked})",
                raw_response={"error": "InvalidDestinationToken"},
            )

        # Build string-only data payload
        safe_data: dict[str, str] = {}
        if payload:
            for k, v in payload.items():
                if v is not None:
                    safe_data[str(k)] = str(v)

        # Android specific configuration
        android_config = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                title=subject or "UPOSTIT Alert",
                body=body,
                channel_id="upostit_alerts",
                click_action="FLUTTER_NOTIFICATION_CLICK",
                sound="default",
            ),
        )

        # iOS APNs specific configuration
        apns_config = messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(
                        title=subject or "UPOSTIT Alert",
                        body=body,
                    ),
                    sound="default",
                    badge=1,
                )
            ),
        )

        message = messaging.Message(
            token=clean_token,
            notification=messaging.Notification(
                title=subject or "UPOSTIT Alert",
                body=body,
            ),
            data=safe_data,
            android=android_config,
            apns=apns_config,
        )

        try:
            # Delegate blocking synchronous network call to worker thread
            message_id: str = await asyncio.to_thread(
                messaging.send, message, False, self._app
            )
            logger.info("FCM accepted message for %s with message_id: %s", masked, message_id)
            return ProviderResult(
                success=True,
                status=ProviderStatus.ACCEPTED,
                provider_name=self.name,
                provider_message_id=message_id,
                is_retryable=False,
                raw_response={"name": message_id, "status": "ACCEPTED"},
            )

        except (
            messaging.UnregisteredError,
            messaging.SenderIdMismatchError,
            exceptions.NotFoundError,
        ) as exc:
            logger.warning("FCM registration token is invalid or expired for %s: %s", masked, exc)
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message=f"FCM token unregistered or expired: {type(exc).__name__}",
                raw_response={"error": type(exc).__name__, "reason": "UNREGISTERED"},
            )

        except (
            messaging.QuotaExceededError,
            exceptions.UnavailableError,
            exceptions.DeadlineExceededError,
            exceptions.ResourceExhaustedError,
        ) as exc:
            logger.warning("FCM service temporarily unavailable for %s: %s", masked, exc)
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=True,
                error_message=f"FCM service throttled or unavailable: {type(exc).__name__}",
                raw_response={"error": type(exc).__name__, "is_retryable": True},
            )

        except exceptions.InvalidArgumentError as exc:
            logger.error("Invalid FCM argument when dispatching to %s: %s", masked, exc)
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=False,
                error_message=f"Invalid FCM argument or payload: {type(exc).__name__}",
                raw_response={"error": "InvalidArgument"},
            )

        except TimeoutError as exc:
            logger.warning("FCM network socket timed out for %s", masked)
            raise ProviderTimeoutError(self.name, "Firebase Cloud Messaging socket timed out") from exc

        except Exception as exc:
            logger.exception("Unexpected FCM failure for %s: %s", masked, type(exc).__name__)
            return ProviderResult(
                success=False,
                status=ProviderStatus.FAILED,
                provider_name=self.name,
                is_retryable=True,
                error_message=f"FCM unexpected failure: {type(exc).__name__}",
                raw_response={"error": type(exc).__name__},
            )
