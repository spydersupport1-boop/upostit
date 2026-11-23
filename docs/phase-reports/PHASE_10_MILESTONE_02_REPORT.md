# UPOSTIT Phase 10 — Milestone 10.2 Implementation Report
## Core Notification Dispatch Engine, Repository & Provider Abstraction

**Date:** 2026-11-21  
**Phase:** 10 — Notifications (Outbound Alerts)  
**Milestone:** 10.2 — Core Notification Dispatch Engine, Repository & Provider Abstraction  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 10.2 delivers the core business logic, asynchronous data repository, safe template rendering engine, preference resolution engine, quiet-hours evaluation service, and provider abstraction architecture for **Phase 10: Notifications (Outbound Alerts)**.

Building on the Phase 10.1 database foundation (`notification_templates`, `notification_preferences`, `notifications`, `device_push_tokens`), this engine provides a unified, reusable notification backend for all UPOSTIT domain modules (such as attendance anomalies, overtime approvals, leave status updates, and geofence alerts).

In strict adherence to milestone boundaries:
- **No external production credentials configured**: Mock provider adapters simulate realistic delivery outcomes without external network requests.
- **Asynchronous Celery tasks deferred**: The dispatcher provides pure asynchronous domain orchestration; background queue bindings (Celery workers, scheduled poller tasks) are deferred to Milestone 10.3.
- **Zero UI/API routes introduced**: HTTP endpoints and web/mobile screens remain deferred to subsequent milestones.

---

## 2. Notification Package Architecture

The notification engine is organized under [`services/api/notifications/`](../../services/api/notifications/):

```
services/api/notifications/
├── __init__.py               # Public API exports
├── models.py                 # Phase 10.1 SQLAlchemy 2.0 mapped models
├── schemas.py                # Typed Pydantic request/response/provider schemas & enums
├── exceptions.py             # Granular domain exceptions (TemplateNotFoundError, etc.)
├── template_renderer.py      # Safe sandboxed parameter substitution engine
├── preference_resolver.py    # Hierarchical preference resolution (User -> Tenant -> System)
├── quiet_hours.py            # Timezone-aware quiet hours & DST evaluator
├── provider.py               # Base provider interface, normalized result models & mock adapters
├── repository.py             # Async SQLAlchemy repository with atomic conditional transitions
├── service.py                # Creation service resolving recipients & templates
└── dispatcher.py             # Dispatch orchestrator managing atomic claims, retries & backoff
```

---

## 3. Core Engine Components & Technical Design

### 3.1 Safe Sandboxed Template Rendering ([`template_renderer.py`](../../services/api/notifications/template_renderer.py))
- **SSTI & Code Execution Prevention**: Deliberately avoids Python `eval()`, `exec()`, or unrestricted AST evaluation. Matches placeholders `{var}` and `{{ var }}` strictly with alphanumeric identifier regex `[a-zA-Z_][a-zA-Z0-9_]*`.
- **Prohibited Tokens Check**: Rejects any template containing dunder tokens (`__class__`, `__mro__`), import statements, or reflection constructs.
- **Variable Validation**: Inspects all required placeholders. If any required variable is missing from `variables`, raises `TemplateRenderError` with the specific missing variable name.
- **Context-Aware Escaping**:
  - `escape_html_entities=True` (for HTML emails): Escapes all dynamic parameters via `html.escape(quote=True)` to prevent script/HTML injection.
  - `is_subject=True` (for email subjects): Strips CRLF characters (`\r`, `\n`) and collapses whitespace to prevent email header injection attacks.

### 3.2 Hierarchical Preference Resolution ([`preference_resolver.py`](../../services/api/notifications/preference_resolver.py))
- **Precedence Order**:
  1. **User Override** (`NotificationPreference` where `user_id == recipient_user_id`)
  2. **Tenant Default** (`NotificationPreference` where `user_id IS NULL`)
  3. **Approved System Fallback**:
     - `PUSH`: `True`
     - `EMAIL`: `True`
     - `SMS`: `False` (disabled by default to prevent unexpected telecommunication costs)
     - `quiet_hours_enabled`: `False`
     - `timezone`: `"UTC"`
- **Audit Logging of Skips**: Explicitly records whether a channel was skipped due to `OPT_OUT_USER` or `DISABLED_TENANT_POLICY`.

### 3.3 Quiet-Hours Evaluation ([`quiet_hours.py`](../../services/api/notifications/quiet_hours.py))
- **Timezone Awareness**: Evaluates recipient time using Python's `zoneinfo.ZoneInfo(timezone)` to account for daylight-saving transitions (DST).
- **Interval Processing**:
  - **Daytime intervals** (e.g. `13:00` to `15:00`): Active if `start <= current_time < end`.
  - **Overnight intervals** (e.g. `22:00` to `07:00` crossing midnight): Active if `current_time >= start` OR `current_time < end`.
- **Exact Boundary Testing**: Exact start time (`22:00:00`) is active; exact end time (`07:00:00`) is inactive (eligible for immediate dispatch).
- **Priority Rules**: `URGENT` priority notifications bypass quiet hours deferral (`should_defer = False`). Non-urgent notifications (`LOW`, `NORMAL`, `HIGH`) are deferred to `next_eligible_dispatch_time` (the UTC equivalent of the quiet-hours end time).

### 3.4 Provider Abstraction & Mock Adapters ([`provider.py`](../../services/api/notifications/provider.py))
- **`BaseNotificationProvider` Interface**: Defines asynchronous `send(recipient, subject, body, payload) -> ProviderResult`.
- **Normalized `ProviderResult`**:
  - `success: bool`
  - `status: ProviderStatus` (`ACCEPTED`, `FAILED`, `UNKNOWN`)
  - `provider_name: str`
  - `provider_message_id: str | None`
  - `is_retryable: bool`
  - `error_message: str | None`
  - `raw_response: dict[str, Any] | None`
- **Delivery Invariant (`SENT != DELIVERED`)**: Immediate provider acceptance marks status as `SENT`. Final end-user delivery (`DELIVERED`) requires asynchronous delivery receipt webhooks (Milestone 10.3+).
- **Mock Adapters**:
  - `MockPushProvider`: Simulates FCM/APNs responses (`SUCCESS`, `TRANSIENT_FAILURE` [503, retryable], `PERMANENT_FAILURE` [403, unretryable], `INVALID_TOKEN` [404/400, unretryable], `TIMEOUT`).
  - `MockEmailProvider`: Simulates SMTP/SES responses (`SUCCESS`, `TRANSIENT_FAILURE` [451 greylisted], `INVALID_RECIPIENT` [550 mailbox unknown], `PERMANENT_FAILURE`, `TIMEOUT`).
  - `MockSmsProvider`: Simulates Twilio/SMS responses (`SUCCESS`, `TRANSIENT_FAILURE` [429 rate limit], `INVALID_RECIPIENT` [21211 invalid phone number], `PERMANENT_FAILURE`, `TIMEOUT`).

### 3.5 FCM Token Storage Security Assessment
- **Dual Representation**:
  - `token_hash`: Deterministic SHA-256 hash used for unique active token indexing (`uq_device_push_tokens_active_token`) and rapid lookups without token exposure.
  - `token`: Stored encrypted at rest using `encrypt_token_at_rest()` (HMAC/AES-derived key using `SECRET_KEY`).
  - `mask_token_for_display()`: Never exposes raw FCM tokens in logs or API schemas; returns preview format (e.g. `abcd...1234`).
  - Production readiness: Designed to swap cipher backend to AWS KMS / Google Cloud KMS envelope encryption without schema modifications.

### 3.6 Asynchronous Repository ([`repository.py`](../../services/api/notifications/repository.py))
- **Idempotency**: `create_notification()` inspects `(tenant_id, idempotency_key)`. If a duplicate request arrives, returns the existing notification without creating duplicate rows.
- **Atomic State Transitions**: `claim_for_processing()` uses a conditional SQL update:
  ```sql
  UPDATE notifications
  SET status = 'PROCESSING', updated_at = now()
  WHERE id = :id AND tenant_id = :tenant_id AND status IN ('PENDING', 'RETRY_SCHEDULED')
  RETURNING *;
  ```
  Prevents race conditions between concurrent worker threads claiming the same notification.
- **Priority Queue Index**: `get_pending_notifications()` queries `status IN ('PENDING', 'RETRY_SCHEDULED') AND scheduled_for <= now`, ordering by `priority DESC` (URGENT -> HIGH -> NORMAL -> LOW) and `scheduled_for ASC`.
- **Tenant Isolation**: Every query, update, and deletion is scoped strictly by `tenant_id`.

### 3.7 Dispatcher & Retry Policy ([`dispatcher.py`](../../services/api/notifications/dispatcher.py))
- **Lifecycle Flow**:
  1. Claims notification atomically (`PENDING` / `RETRY_SCHEDULED` $\to$ `PROCESSING`).
  2. Evaluates quiet hours at time of dispatch; if deferred, resets status to `RETRY_SCHEDULED` with `next_eligible_at`.
  3. Invokes channel provider adapter.
  4. On acceptance: updates to `SENT`, records `provider_message_id` and `sent_at`.
  5. On retryable failure (`is_retryable = True` and `attempt_count + 1 < max_attempts`):
     - Calculates exponential backoff: $\text{delay} = \min(\text{base} \times 2^{\text{attempt\_count}}, \text{max})$.
     - Schedules future retry: `attempt 0 -> 60s`, `attempt 1 -> 120s`, `attempt 2 -> 240s`.
     - Sets status to `RETRY_SCHEDULED` and records error message.
  6. On permanent failure (or exceeded attempts):
     - Sets status to `FAILED` and records `failed_at` and safe redacted error message.
- **At-Least-Once Risk Documentation**: If a provider accepts a message but the process crashes before the database commit, a subsequent worker retry could deliver a duplicate. Downstream provider idempotency keys mitigate this risk.

---

## 4. Automated Test Suite Execution ([`tests/test_phase10_milestone2_dispatch_engine.py`](../../tests/test_phase10_milestone2_dispatch_engine.py))

37 dedicated unit and contract tests were executed with a **100% pass rate**:

| Test Class | Focus Area | Assertions | Status |
| :--- | :--- | :--- | :---: |
| `TestSafeTemplateRenderer` | Parameter substitution & sandboxing | Curly brace syntax, missing variables, HTML entity escaping, subject CRLF stripping, SSTI dunder prevention | **PASSED** |
| `TestPreferenceResolver` | Hierarchy & channel toggles | User override, tenant fallback, system default, user opt-out enforcement, SMS disabled by default | **PASSED** |
| `TestQuietHoursEvaluator` | Timezone & interval logic | Daytime interval, overnight midnight crossover, exact boundaries, urgent priority bypass, timezone offset calculation | **PASSED** |
| `TestProvidersAndTokenSecurity` | Provider abstraction & crypto | Mock push/email/sms success, transient failure, invalid recipient, timeout, SHA-256 hash, at-rest encryption/decryption, token masking | **PASSED** |
| `TestNotificationRepository` | Database repository operations | Idempotency duplicate check, atomic conditional claim, success record, retryable failure, permanent failure, template hierarchy lookup | **PASSED** |
| `TestNotificationService` | Destination & creation workflow | User email resolution, employee phone resolution, channel opt-out enforcement, template not found check | **PASSED** |
| `TestNotificationDispatcher` | Dispatch orchestration & retry | Full delivery lifecycle to SENT, quiet-hours deferral, retryable failure backoff, permanent failure, exponential backoff progression | **PASSED** |

**Execution Result**: 37 passed in 2.62s.

### Full Regression Verification
```bash
pytest tests/test_phase10*.py tests/test_phase9_database_models_and_migration.py tests/test_health.py
# Result: 85 passed in 11.24s (100% pass rate)
```

### Static Analysis & Type Checking
- **`ruff check services/api/notifications/ tests/test_phase10*.py`**: All checks passed (0 errors, 0 warnings).
- **`mypy services/api/notifications/ tests/test_phase10_milestone2_dispatch_engine.py`**: Success: no issues found in 12 source files.

---

## 5. Security & Multi-Tenancy Compliance

1. **Strict Multi-Tenant Scoping**: All repository queries require `tenant_id`. No cross-tenant access is permitted.
2. **Template Code Execution Neutralized**: No Python `eval`, `exec`, or unrestricted Jinja template code evaluation is possible. Placeholders are validated against strict alphanumeric identifier rules.
3. **Token At-Rest Encryption**: Device push tokens are stored encrypted and masked in API outputs. Raw tokens are never logged.
4. **Idempotency Protection**: Duplicate submissions with identical `idempotency_key` within a tenant return the existing notification without creating duplicate records or dispatching duplicate alerts.
5. **PII Sanitization**: Recipient email and phone numbers are logged only in masked format (`jo***e@example.com`, `+12***890`).

---

## 6. Monorepo Verification Summary

- **Total Automated Tests**: Increased to **1,192 tests passing (100% pass rate)**:
  - Backend: 712 tests (57 Phase 10 [20 in 10.1, 37 in 10.2])
  - Flutter Mobile: 376 tests
  - Next.js Web: 104 tests
- **Git Working Tree**: Preserved. No commits, tags, or pushes. Branch remains `phase-06`.

---

## 7. Next Actions

Milestone 10.2 is complete and verified. Work has paused awaiting review and explicit authorization before proceeding to **Milestone 10.3: Push Notification Provider (FCM Adapter, Mobile Token Registration API & Celery Dispatch Worker)**.

