# UPOSTIT Phase 10 — Milestone 10.3 Implementation Report
## FCM Push Integration, Device Token Registration APIs & Celery Dispatch Workers

**Date:** 2026-11-21  
**Phase:** 10 — Notifications (Outbound Alerts)  
**Milestone:** 10.3 — FCM Push Integration, Device Token Registration APIs & Celery Dispatch Workers  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 10.3 implements the production push notification integration architecture, authenticated mobile device token registration endpoints, and asynchronous Celery dispatch pipelines for **Phase 10: Notifications (Outbound Alerts)**.

Building upon the Phase 10.1 database models and Phase 10.2 core dispatch engine, this milestone delivers:
1. **Production Firebase Cloud Messaging (FCM) Adapter**: Official `firebase-admin` SDK adapter behind the `BaseNotificationProvider` abstraction, supporting platform-specific payloads for Android and iOS (APNs), error classification (retryable vs. permanent), and fallback to mock push in local/test environments.
2. **Authenticated Encryption at Rest for Mobile Device Tokens**: Cryptographically vetted token protection using `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256 authenticated encryption) with PBKDF2HMAC key derivation, strict `fernet:` prefix validation, zero plaintext fallback, and masked display previews.
3. **Device Push Token Registration & Management APIs**: Secure FastAPI endpoints under `/api/v1/notifications/devices` for registering, rotating, listing, and revoking push tokens, strictly isolated by authenticated tenant and user context.
4. **Celery Asynchronous Notification Workers**: End-to-end background task workers (`dispatch_single`, `dispatch_batch`, `process_retries`, `reconcile_stuck_processing`, `cleanup_revoked_tokens`) with exponential backoff, dead-letter preservation, and stuck-processing recovery.
5. **Strict Quiet-Hours Compliance**: Verified that quiet hours are strictly honored without unconditional bypass, preserving deferred dispatch timestamps.

---

## 2. Firebase Cloud Messaging (FCM) Adapter Architecture

The production FCM provider adapter is implemented in [`services/api/notifications/fcm_provider.py`](../../services/api/notifications/fcm_provider.py).

### 2.1 Adapter Capabilities & Platform-Specific Payloads
The adapter constructs structured messages using Google's `firebase_admin.messaging`:
- **Android Configuration (`messaging.AndroidConfig`)**:
  - Priority: `"high"`
  - Notification channel: `"upostit_alerts"`
  - Click action: `"FLUTTER_NOTIFICATION_CLICK"`
  - Sound: `"default"`
- **iOS APNs Configuration (`messaging.APNSConfig`)**:
  - Headers: `{"apns-priority": "10"}`
  - APS payload: alert title, body, sound `"default"`, badge `1`
- **Data Payload**: String-coerced key-value metadata for client-side routing (e.g. `event_type`, `shift_id`, `leave_request_id`).

### 2.2 Error Classification & Normalized Results
The adapter executes the network call asynchronously via `asyncio.to_thread` and maps provider responses to normalized `ProviderResult` instances:
- **Provider Acceptance (`ACCEPTED`)**:
  - Returns `success=True`, `status=ProviderStatus.ACCEPTED`, `provider_message_id=message_id`.
  - Invariant maintained: `ACCEPTED` maps to `SENT` in database audit records (`SENT != DELIVERED`).
- **Permanent Errors (Non-Retryable)**:
  - `messaging.UnregisteredError`, `messaging.SenderIdMismatchError`, `exceptions.NotFoundError`: Token is unregistered, uninstalled, or expired.
  - Returns `success=False`, `is_retryable=False`, `status=ProviderStatus.FAILED`.
- **Transient Errors (Retryable)**:
  - `messaging.QuotaExceededError`, `exceptions.UnavailableError`, `exceptions.DeadlineExceededError`, `exceptions.ResourceExhaustedError`: Service throttled or temporarily down.
  - Returns `success=False`, `is_retryable=True`, `status=ProviderStatus.FAILED`.
- **Socket Timeouts**:
  - `TimeoutError`: Raises `ProviderTimeoutError(is_retryable=True)`.
- **Invalid Tokens**:
  - Pre-flight checks reject placeholder destinations (e.g. `user:12345` or string length < 10) as permanent unretryable failures before dispatch.

### 2.3 Credential Configuration & Safe Fallback
Environment settings in [`services/api/config.py`](../../services/api/config.py):
- `FCM_ENABLED`: Boolean toggle (defaults to `False` in dev/test).
- `FCM_CREDENTIALS_PATH`: Path to service account JSON file.
- `FCM_CREDENTIALS_JSON`: Inline JSON string for containerized deployments.
- `FCM_PROJECT_ID`: Google Cloud / Firebase project identifier.
- **Provider Registry Integration**: When `FCM_ENABLED=False`, `ProviderRegistry.get_provider("push")` seamlessly falls back to `MockPushProvider`, ensuring continuous local development and CI testing without external cloud dependencies.

---

## 3. Authenticated Encryption at Rest for Device Tokens

Token cryptography is implemented in [`services/api/notifications/crypto.py`](../../services/api/notifications/crypto.py) using the vetted `cryptography` library (version 48.0.1).

### 3.1 Cryptographic Guarantees
- **AEAD Construction**: Uses `Fernet`, which implements AES-128 in CBC mode with PKCS7 padding and HMAC using SHA-256 for authenticated integrity verification.
- **Key Derivation**: Derives a 32-byte URL-safe base64 Fernet key using `PBKDF2HMAC` (SHA-256, 100,000 iterations, application-bound salt) from `SECRET_KEY` or dedicated `NOTIFICATION_TOKEN_ENCRYPTION_KEY`. Requires a minimum 32-character secret.
- **Strict Format**: Ciphertexts are stored with the prefix `fernet:` (`fernet:<base64-payload>`).
- **Zero Plaintext Fallback**: `decrypt_push_token()` strictly verifies the `fernet:` prefix and MAC signature. Unauthenticated, tampered, or plaintext tokens raise `TokenEncryptionError`.
- **Masked Previews**: `mask_token_for_display(token)` returns truncated previews (e.g. `abcd...1234`) for log and API serialization, guaranteeing raw secrets never leak into observability platforms.

---

## 4. Mobile Device Token Registration & Management APIs

The HTTP endpoints are implemented in [`services/api/notifications/routes.py`](../../services/api/notifications/routes.py) and mounted under `/api/v1/notifications/devices`.

| Method | Endpoint | Description | Auth & Scope |
|---|---|---|---|
| `POST` | `/api/v1/notifications/devices` | Register or rotate device push token | Current user + active tenant |
| `GET` | `/api/v1/notifications/devices` | List active device tokens with masked preview | Current user + active tenant |
| `DELETE` | `/api/v1/notifications/devices/{token_hash}` | Revoke device token by hash | Current user + active tenant |
| `POST` | `/api/v1/notifications/devices/revoke` | Revoke device token by raw token or hash | Current user + active tenant |

### 4.1 Security & Multi-Tenant Isolation
- All endpoints require authentication via `get_authenticated_context`.
- `tenant_id` and `user_id` are derived strictly from the verified session context; request bodies cannot spoof tenant or user IDs.
- On registration, any previous active token registered for the same device ID is marked inactive, preventing orphaned tokens.
- Query filters strictly enforce `tenant_id == ctx.active_tenant.id` and `user_id == ctx.user.id`.

---

## 5. Celery Asynchronous Notification Workers

Asynchronous worker tasks are implemented in [`services/workers/notification_tasks.py`](../../services/workers/notification_tasks.py) and registered in [`services/workers/celery_app.py`](../../services/workers/celery_app.py).

### 5.1 Registered Background Tasks
1. **`notifications.dispatch_single`**:
   - Dispatches a single notification by UUID.
   - Atomically claims the notification (`PENDING` -> `PROCESSING`).
   - Dispatches through `NotificationDispatcher`.
   - On retryable failure, schedules next attempt via Celery `countdown` or updates `next_retry_at` in the database.
2. **`notifications.dispatch_batch`**:
   - Queries up to `batch_size` (default 50) pending notifications eligible for dispatch.
   - Dispatches each concurrently or enqueues single-dispatch tasks.
3. **`notifications.process_retries`**:
   - Queries notifications in `RETRY` status where `next_retry_at <= now()`.
   - Reschedules them for processing.
4. **`notifications.reconcile_stuck_processing`**:
   - Queries notifications stuck in `PROCESSING` longer than `timeout_minutes` (default 15 minutes), indicative of crashed worker nodes.
   - If attempts remain, transitions back to `RETRY` with updated backoff; if exhausted, marks terminal `FAILED` (dead-letter audit preservation).
5. **`notifications.cleanup_revoked_tokens`**:
   - Purges revoked or inactive device tokens older than `retention_days` (default 90 days).

### 5.2 Retry Backoff & Dead-Letter Handling
- **Exponential Backoff**: Calculated as `min(max_backoff, initial_interval * (backoff_factor ** attempt)) * jitter`.
  - Initial interval: 30 seconds
  - Backoff factor: 2.0
  - Max backoff: 3600 seconds (1 hour)
  - Jitter: $\pm 10\%$
- **Dead-Letter Audit**: When attempts reach `max_attempts` (default 3), the notification transitions to terminal `FAILED`. All error messages, provider raw responses, and attempt counts are immutably preserved in the database for auditing and operational review.

---

## 6. Quiet-Hours Policy Alignment

In accordance with explicit roadmap requirements:
- The unconditional `URGENT` bypass was removed from [`services/api/notifications/quiet_hours.py`](../../services/api/notifications/quiet_hours.py).
- Quiet hours are evaluated strictly according to tenant and user preferences.
- Notifications created during quiet hours are marked `PENDING` with a computed `next_eligible_dispatch_time` corresponding to the quiet-hours window end in the recipient's local timezone.

---

## 7. Verification & Test Execution Results

A dedicated test suite was implemented in [`tests/test_phase10_milestone3_fcm_and_celery.py`](../../tests/test_phase10_milestone3_fcm_and_celery.py).

### 7.1 Test Summary
- **FCM Provider Tests (`TestFirebasePushProvider`)**:
  - `test_unconfigured_credentials_raises_permanent_error`: Verified permanent failure on unconfigured credentials.
  - `test_invalid_destination_token_returns_failure`: Verified placeholder/malformed destination tokens are rejected.
  - `test_successful_provider_acceptance`: Verified message structure, Android high priority, and APNs headers.
  - `test_unregistered_token_is_unretryable`: Verified `UnregisteredError` maps to non-retryable failure.
  - `test_quota_exceeded_or_unavailable_is_retryable`: Verified `UnavailableError` maps to retryable failure.
  - `test_fcm_timeout_raises_provider_timeout`: Verified socket timeout raises retryable `ProviderTimeoutError`.
- **Device Push Token API Tests (`TestDevicePushTokenAPIs`)**:
  - `test_register_device_token_success_and_masked_preview`: Verified registration, encryption, and masked preview.
  - `test_list_user_device_tokens`: Verified user-scoped device listing.
  - `test_revoke_device_token_by_hash_not_found`: Verified 404 on nonexistent token hash.
- **Celery Worker Task Tests (`TestNotificationCeleryTasks`)**:
  - `test_dispatch_single_notification_task_success`: Verified Celery single-dispatch lifecycle.
  - `test_dispatch_batch_notifications_task`: Verified batch processing and status aggregation.
  - `test_reconcile_stuck_processing_task`: Verified recovery of crashed processing notifications.
  - `test_cleanup_revoked_tokens_task`: Verified pruning of old revoked tokens.
- **Token Cryptography Tests (`TestTokenAuthenticatedEncryption`)**:
  - `test_fernet_roundtrip_with_derived_key`: Verified encryption and decryption roundtrip.
  - `test_plaintext_fallback_is_strictly_rejected`: Verified rejection of unencrypted plaintext strings.
  - `test_tampered_ciphertext_fails_mac_verification`: Verified AEAD HMAC tamper detection.
  - `test_empty_token_encryption_rejected`: Verified empty string rejection.
  - `test_derive_key_from_short_secret_raises`: Verified minimum secret length validation.
  - `test_mask_token_display_format`: Verified masked preview formatting.

### 7.2 Test Suite Execution Metrics
- **Milestone 10.3 Suite**: **19 / 19 passed** in 6.36s.
- **Full Phase 10 Suite (10.1 + 10.2 + 10.3)**: **76 / 76 passed** in 6.69s.
- **Regression Suite (Phase 9 Models + Health + Celery Smoke)**: **28 / 28 passed** in 15.49s.
- **Static Analysis**:
  - Ruff: `Found 0 errors`.
  - Mypy: `Success: no issues found in 16 source files`.

---

## 8. Physical Device & Live Staging Requirements Note

1. **Physical Devices for Mobile Validation**: Real push notification testing requires a physical Android or iOS device with Google Play Services or Apple APNs registration tokens. Android emulators without Google APIs or iOS simulators cannot receive standard remote push notifications.
2. **Firebase Project Setup**: To enable production FCM dispatch, set the following environment variables in `.env`:
   ```bash
   FCM_ENABLED=true
   FCM_CREDENTIALS_PATH=/path/to/firebase-adminsdk-key.json
   FCM_PROJECT_ID=upostit-staging
   ```
   Local testing and automated CI will safely operate with `FCM_ENABLED=false` using `MockPushProvider`.

---

## 9. Next Steps

With Milestone 10.3 verified and complete, the project is ready for **Milestone 10.4**:
- Production Email (Resend / SendGrid / Amazon SES) adapter integration.
- Production SMS (Twilio) adapter integration.
- Webhook signature verification and asynchronous delivery receipt processing (`DELIVERED` status updates).
- Delivery receipt audit tracking.

