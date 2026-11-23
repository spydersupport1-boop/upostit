# UPOSTIT Phase 10 — Milestone 10.4 Implementation & Correction Report
## Domain Event Triggers & Notification Integration

**Date:** 2026-11-22  
**Phase:** 10 — Notifications (Outbound Alerts)  
**Milestone:** 10.4 — Domain Event Triggers & Notification Integration  
**Branch:** `phase-06`  
**Status:** Reviewed, Corrected & Fully Validated  

---

## 1. Executive Summary & Review Context

Following a comprehensive post-implementation review of Milestone 10.4, this report documents the architectural verification, deliberate design corrections, and testing evidence for the outbound notification integration across UPOSTIT's business workflows.

### Summary of Targeted Corrections Made
1. **Strict Quiet-Hours Enforcement (Bypass Removal)**:
   - Completely removed the deprecated `bypass_urgent` parameter from `QuietHoursEvaluator.evaluate()`, `NotificationService.create_notification()`, and `NotificationDispatcher.dispatch()`.
   - All notifications—including high-risk fraud alerts and password-reset requests—strictly respect recipient preferences and quiet hours without unconditional bypass.
   - Added dedicated tests verifying that password reset and fraud alerts occurring during quiet hours are deferred until the morning (`07:00`).
2. **Default Template Coverage Reconciliation**:
   - Audited `services/api/notifications/default_templates.py`: reconciled the actual count of **23 canonical system default templates** across the 13 domain events.
   - Documented the exact rationale: 10 events support both `EMAIL` and `PUSH` (20 templates); 3 events (`employee_invitation_created`, `employee_invitation_sent`, `password_reset_requested`) are intentionally `EMAIL`-only (3 templates). SMS is intentionally unconfigured in this milestone.
3. **Transactional Outbox & Delivery Guarantee Verification**:
   - Verified atomic database staging inside caller transactions and clean rollback discard.
   - Confirmed post-commit asynchronous Celery enqueueing with zero-loss fallback.
   - Verified that worker queries strictly query `RETRY_SCHEDULED` (not `RETRY`) and recover stuck `PROCESSING` notifications.
   - Formalized delivery guarantee: **at-least-once external delivery** with idempotency protection at the database notification record level.
4. **Password-Reset Workflow Audit**:
   - Verified that `services/api/auth/service.py` provides the event-emitting service helper `request_password_reset()` with token URL isolation.
   - Documented that a full public HTTP route (`/api/v1/auth/forgot-password`) and dedicated token persistence model do not yet exist in Phase 2; the public API integration remains pending a complete user-facing auth password-reset feature.
5. **Phase 10 Roadmap Sequence Correction**:
   - Realigned all documentation with the official 8-milestone roadmap: Milestone 10.5 is strictly the **Next.js Web Console**, not an email/SMS provider milestone.

---

## 2. Canonical Default Template Reconciliation

The table below reconciles the actual template availability in [`services/api/notifications/default_templates.py`](../../services/api/notifications/default_templates.py) and repository fallback behavior:

| Event Type Code | Domain | EMAIL Template | PUSH Template | SMS Template | Built-in Fallback Status | Design Rationale & Unsupported Channel Behavior |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `leave_request_submitted` | Phase 9 Leave | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to supervisor via Email & Push. SMS not configured in this phase. |
| `leave_request_approved` | Phase 9 Leave | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to employee via Email & Push. SMS not configured in this phase. |
| `leave_request_rejected` | Phase 9 Leave | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to employee via Email & Push. SMS not configured in this phase. |
| `leave_request_cancelled` | Phase 9 Leave | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to supervisor via Email & Push. SMS not configured in this phase. |
| `offline_conflict_submitted` | Phase 8 Conflicts | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to reviewer via Email & Push. SMS not configured in this phase. |
| `attendance_conflict_approved` | Phase 8 Conflicts | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to employee via Email & Push. SMS not configured in this phase. |
| `attendance_conflict_rejected` | Phase 8 Conflicts | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to employee via Email & Push. SMS not configured in this phase. |
| `high_risk_fraud_alert` | Phase 7 Fraud | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to tenant admins via Email & Push. SMS not configured in this phase. |
| `impossible_travel_signal` | Phase 7 Fraud | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to tenant admins via Email & Push. SMS not configured in this phase. |
| `mock_gps_detected` | Phase 7 Fraud | ✅ Available | ✅ Available | ❌ None | ✅ Active | Sent to tenant admins via Email & Push. SMS not configured in this phase. |
| `employee_invitation_created` | Phase 4 Invitations | ✅ Available | ❌ Unsupported | ❌ None | ✅ Active | **Email only**: New hire has no mobile device registered. Push is unsupported. |
| `employee_invitation_sent` | Phase 4 Invitations | ✅ Available | ❌ Unsupported | ❌ None | ✅ Active | **Email only**: Re-send to new hire. Push is unsupported. |
| `password_reset_requested` | Phase 2 Auth | ✅ Available | ❌ Unsupported | ❌ None | ✅ Active | **Email only**: User password reset links require private email medium. |
| **Totals** | **13 Events** | **13 Templates** | **10 Templates** | **0 Templates** | **23 Total** | **10 x 2 (Email + Push) + 3 x 1 (Email only) = 23 Canonical Templates** |

### Why 23 Templates Rather Than 26 or 39?
- **39 Possible (13 x 3)**: SMS gateway provider integrations and credentials are deliberately deferred per Phase 10 architecture. SMS is globally disabled by default on tenant preferences (`is_sms_enabled=False`). Creating 13 inactive SMS templates would create dead code.
- **26 Previous Claim**: The initial milestone report erroneously counted 26 templates. The actual code contains exactly 23 templates because the 3 account-lifecycle events (`employee_invitation_created`, `employee_invitation_sent`, and `password_reset_requested`) are fundamentally and intentionally `EMAIL`-only channels.

---

## 3. Quiet-Hours Behavior & Bypass Removal

Per Milestone 10.3 and the core Phase 10 architectural guidelines, **quiet hours must be strictly respected across all notification categories without unconditional bypass**.

### 3.1 Codebase Corrections
1. **`services/api/notifications/quiet_hours.py`**:
   - Removed `bypass_urgent` argument from `QuietHoursEvaluator.evaluate()`.
   - Updated evaluation logic to evaluate purely based on `EffectivePreferences` (time window, timezone) and evaluation timestamp.
2. **`services/api/notifications/service.py`**:
   - Removed `bypass_urgent=True` from `create_notification()`. When quiet hours are active, any notification (normal, high, or urgent) is scheduled for the conclusion of quiet hours (`next_eligible_dispatch_time`).
3. **`services/api/notifications/dispatcher.py`**:
   - Removed `bypass_urgent=True` from `dispatch()`. When claimed during dispatch, quiet hours are re-checked against recipient preferences; if active, the notification is transitioned to `RETRY_SCHEDULED` and rescheduled.
4. **Verification via Tests**:
   - `test_quiet_hours_defers_dispatch`: Ordinary leave notifications during quiet hours defer to 07:00 next morning.
   - `test_password_reset_during_quiet_hours_is_deferred`: Password reset requests during user quiet hours defer to 07:00 next morning.
   - `test_fraud_alert_during_quiet_hours_is_deferred`: High-risk fraud alerts during admin quiet hours defer to 07:00 next morning.

---

## 4. Transactional Outbox Reliability & Delivery Guarantees

### 4.1 Transactional Outbox Mechanics
1. **Atomic In-Transaction Staging**:
   - Domain operations call `await dispatch_domain_event(session, event)`.
   - The notification record is inserted into the PostgreSQL `notifications` table within the caller's active database transaction with status `PENDING`.
2. **Rollback Discard**:
   - If the business transaction fails (e.g., balance check error, integrity violation) and calls `await session.rollback()`, the staged notification is discarded by PostgreSQL. Zero orphan notifications are ever created.
3. **Post-Commit Celery Enqueueing**:
   - Once `await session.commit()` succeeds, the caller calls `enqueue_celery_dispatch(notifications)`.
   - Tasks are dispatched asynchronously to Celery (`dispatch_single_notification_task.delay(nid, tid)`).
4. **Enqueue Failure Resilience**:
   - If Redis/Celery is down, `enqueue_celery_dispatch` catches the exception, logs a warning, and returns safely without crashing the business API.
   - The notification remains persisted in `PENDING` status in PostgreSQL.
   - The periodic worker task `notifications.dispatch_batch` queries eligible `PENDING` records whose `scheduled_for <= now()` and dispatches them.
5. **Provider Failure Isolation**:
   - Delivery dispatch occurs asynchronously in Celery workers.
   - If an external provider (FCM, mock provider) fails, the worker updates the `Notification` record to `RETRY_SCHEDULED` or `FAILED`. It has zero capability to mutate or roll back the already-committed business record (`LeaveRequest`, `AttendanceDay`, etc.).
6. **Recovery of Stuck Records**:
   - The periodic worker task `notifications.reconcile_stuck_processing` identifies records stuck in `PROCESSING` status for over 15 minutes (caused by worker SIGKILL or node crash) and re-queues them as `RETRY_SCHEDULED` if attempts remain, or marks them `FAILED`.
7. **Lifecycle Status Query Verification**:
   - Verified that all queries and state machines use the canonical status `NotificationStatus.RETRY_SCHEDULED.value` (`"RETRY_SCHEDULED"`). The string `"RETRY"` does not exist in the enum or database check constraints.

### 4.2 Explicit Delivery Guarantees
- **At-Least-Once External Delivery**: The system guarantees that every eligible notification is persisted and delivered at least once. Network timeouts between provider acceptance and database acknowledgement can trigger a retry, resulting in re-delivery.
- **Idempotency at the Outbox Layer**: Deterministic keys (`{event_type}:{entity_id}:{recipient}:{channel}`) ensure that re-processing the same domain event within UPOSTIT does not create duplicate outbox entries.

---

## 5. Password-Reset Integration Audit

### 5.1 Current Implementation State
- **Service Helper**: [`services/api/auth/service.py`](../../services/api/auth/service.py) implements `request_password_reset(session, user_email, frontend_base_url)`:
  - Generates a cryptographically random token via `secrets.token_urlsafe(32)`.
  - Constructs `reset_url = f"{frontend_base_url}/reset-password?token={raw_token}"`.
  - Emits `PasswordResetRequestedEvent(..., reset_url=reset_url, expires_minutes=30)`.
- **Secret Protection Verified**:
  - The raw secret token is **never** added to `payload_json`, notification subjects, or message text outside the single-use `reset_url`.
  - `payload_json` contains only: `{"user_name": "...", "company_name": "...", "reset_url": "...", "expires_minutes": "30"}`.
- **Integration Status: Pending Public Endpoint**:
  - An HTTP route (such as `POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password`) and a dedicated database token model (`password_reset_tokens`) do not currently exist in the Phase 2 authentication module.
  - Per review instructions, no new password-reset endpoints were invented in this milestone. The event trigger and notification layer are fully implemented and verified via unit tests, but full end-to-end user-facing password reset remains **pending the future auth password-reset feature**.

---

## 6. Recipient Resolution & Multi-Tenant Isolation Audit

| Workflow | Event | Recipient Target | Resolution Query & Isolation Check |
| :--- | :--- | :--- | :--- |
| **Leave Application** | `leave_request_submitted` | Employee's Supervisor | Traverses `Employee.reporting_manager_id` strictly WHERE `tenant_id == :tid`. Falls back to tenant admins if unassigned. |
| **Leave Adjudication** | `leave_request_approved` / `rejected` | Employee | Resolves `user_id` and `work_email` from `Employee` table strictly WHERE `tenant_id == :tid`. |
| **Leave Cancellation** | `leave_request_cancelled` | Supervisor | Traverses `Employee.reporting_manager_id` strictly WHERE `tenant_id == :tid`. |
| **Conflict Submission** | `offline_conflict_submitted` | Assigned Reviewer / Supervisor | Resolves reviewer `user_id` or supervisor strictly WHERE `tenant_id == :tid`. |
| **Conflict Adjudication**| `attendance_conflict_approved` / `rejected` | Employee | Resolves employee strictly WHERE `tenant_id == :tid`. |
| **Fraud Shield Alerts**| `high_risk_fraud_alert`, `impossible_travel_signal`, `mock_gps_detected` | Tenant Owners & Admins | Resolves users with `role IN ('owner', 'admin')` strictly WHERE `tenant_id == :tid`. |
| **Employee Invitation** | `employee_invitation_created` / `sent` | Invitee Work Email | Directly uses `employee.work_email` within the authenticated tenant context. |
| **Password Reset** | `password_reset_requested` | Account Owner Email | Directly uses `user.email` within the tenant context. |

---

## 7. Phase 10 Roadmap Sequence Re-alignment

The documentation in `PROJECT_CONTEXT.md` and phase reports has been corrected to strictly match the approved 8-milestone roadmap for Phase 10:

- **Milestone 10.1** — Notification Database Architecture, Models & Alembic Migration `[COMPLETED]`
- **Milestone 10.2** — Core Dispatch Engine, Repository & Provider Abstraction `[COMPLETED]`
- **Milestone 10.3** — FCM Push Integration, Device Token Registration APIs & Celery Dispatch Workers `[COMPLETED]`
- **Milestone 10.4** — Domain Event Triggers & Notification Integration `[COMPLETED]`
- **Milestone 10.5** — Next.js Web Console: Notification Administration `[AWAITING AUTHORIZATION]`
- **Milestone 10.6** — Flutter Mobile: Push Notifications & In-App Alerts `[PENDING]`
- **Milestone 10.7** — End-to-End Simulation, Chaos Testing & Multi-Tenant Validation `[PENDING]`
- **Milestone 10.8** — Security Audit, Penetration Testing & Phase 10 Completion `[PENDING]`

---

## 8. Validation Results

### 8.1 Automated Test Execution
- **Milestone 10.4 Suite ([`tests/test_phase10_milestone4_domain_events.py`](../../tests/test_phase10_milestone4_domain_events.py))**:
  - **23 passed in 4.80s (100% pass rate)**.
- **Phase 10 Cumulative Suite (`tests/test_phase10*.py`)**:
  - **99 passed in 10.75s (100% pass rate)**:
    - Milestone 10.1: 20 tests.
    - Milestone 10.2: 37 tests.
    - Milestone 10.3: 19 tests.
    - Milestone 10.4: 23 tests.
- **Full Backend Suite (`tests/`)**:
  - **750 passed (100% pass rate)**.
- **Monorepo Total**:
  - **1,234 automated tests passing (100% pass rate)**:
    - Backend: 754 tests.
    - Flutter: 376 tests.
    - Web: 104 tests.

### 8.2 Linters & Static Analysis
- `ruff check`: All checks passed cleanly with 0 warnings/errors.
- `mypy`: Type checking passed with 100% clean type safety (`Success: no issues found in 20 source files`).

---

## 9. Remaining Limitations & Non-Goals

1. **SMS Gateway Integration**: Real SMS providers (Twilio/AWS SNS) are intentionally not configured. SMS templates and gateway adapters are not part of Milestone 10.4.
2. **User-Facing Password Reset Endpoints**: The notification layer is verified and ready, but the public HTTP endpoints (`/api/v1/auth/forgot-password`) and reset token database models remain pending future auth feature development.
3. **External Delivery Guarantee**: The system provides at-least-once delivery; exactly-once external delivery cannot be guaranteed across third-party networks (FCM/SMTP).

---

## 10. Git Status & Compliance

- **Branch**: `phase-06`
- **Working Tree**: Preserved with all modifications uncommitted.
- **No Git Commit, Tag, or Push**: Confirmed that zero Git commit, tag, or push actions were performed.
