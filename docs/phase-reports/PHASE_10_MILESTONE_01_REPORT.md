# UPOSTIT Phase 10 — Milestone 10.1 Implementation Report
## Notification Database Architecture, Models & Alembic Migration

**Date:** 2026-11-21  
**Phase:** 10 — Notifications (Outbound Alerts)  
**Milestone:** 10.1 — Notification Database Architecture, Models & Alembic Migration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 10.1 establishes the foundational database architecture for **Phase 10: Notifications (Outbound Alerts)** of the UPOSTIT Workforce Attendance SaaS platform. Following the authorized Phase 10 scope ([`docs/phase-reports/PHASE_10_SCOPE_VERIFICATION_REPORT.md`](PHASE_10_SCOPE_VERIFICATION_REPORT.md)), the four approved database entities have been authored using SQLAlchemy 2.0 mapped declarative syntax, registered in `Base.metadata`, incorporated into a linear Alembic migration (`b5c6d7e8f9a0`), and verified via automated contract and unit tests.

In strict adherence to milestone requirements:
- **Scope is database-only**: No Celery workers, FCM/SMS/SMTP provider dispatch adapters, FastAPI endpoints, Next.js web consoles, or Flutter mobile screens have been introduced in this milestone.
- **External account credentials deferred**: Per user instruction, Firebase and SMS external configurations are deferred to subsequent implementation stages.
- **Linear migration chain preserved**: Alembic migration `b5c6d7e8f9a0` branches cleanly from the existing head `a4b5c6d7e8f9` (Phase 9.4 overtime enhancements).

---

## 2. Key Deliverables

### 2.1 Four Core Database Entities & SQLAlchemy Models ([`services/api/notifications/models.py`](../../services/api/notifications/models.py))

1. **`notification_templates` (`NotificationTemplate`)**:
   - Stores system-defined default templates (`tenant_id IS NULL`, `is_system=True`) and tenant-customizable template overrides (`tenant_id=<uuid>`, `is_system=False`).
   - Fields: `id`, `tenant_id`, `template_key`, `name`, `description`, `event_type`, `channel`, `subject_template`, `body_template`, `locale`, `is_active`, `is_system`, `created_by_user_id`, `updated_by_user_id`, `created_at`, `updated_at`.
   - Constraints:
     - `chk_notification_templates_channel`: `channel IN ('PUSH', 'EMAIL', 'SMS')`.
     - `chk_notification_templates_system_tenant`: `(is_system = true AND tenant_id IS NULL) OR (is_system = false AND tenant_id IS NOT NULL)`.
   - Partial unique indexes:
     - `uq_notification_templates_tenant`: Unique on `(tenant_id, template_key, channel, locale)` where `tenant_id IS NOT NULL`.
     - `uq_notification_templates_system`: Unique on `(template_key, channel, locale)` where `tenant_id IS NULL`.
   - Composite lookup index: `ix_notification_templates_lookup` on `(tenant_id, event_type, channel, is_active)`.

2. **`notification_preferences` (`NotificationPreference`)**:
   - Stores tenant-wide fallback defaults (`user_id IS NULL`) and employee/user-level preference overrides (`user_id=<uuid>`).
   - Fields: `id`, `tenant_id`, `user_id`, `is_push_enabled`, `is_email_enabled`, `is_sms_enabled`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`, `timezone`, `category_preferences`, `created_at`, `updated_at`.
   - Partial unique indexes:
     - `uq_notification_preferences_user`: Unique on `(tenant_id, user_id)` where `user_id IS NOT NULL`.
     - `uq_notification_preferences_tenant_default`: Unique on `tenant_id` where `user_id IS NULL`.
   - Supports 24-hour quiet-hours formatting (`HH:MM`) and tenant timezone alignment.

3. **`notifications` (`Notification`)**:
   - Persists asynchronous outbound dispatch requests and serves as a permanent, legally auditable delivery ledger.
   - Fields: `id`, `tenant_id`, `recipient_user_id`, `recipient_employee_id`, `event_type`, `channel`, `template_id`, `template_key`, `recipient_destination`, `subject`, `body`, `payload_json`, `status`, `priority`, `scheduled_for`, `attempt_count`, `max_attempts`, `next_retry_at`, `provider_name`, `provider_message_id`, `provider_response`, `error_message`, `idempotency_key`, `related_entity_type`, `related_entity_id`, `sent_at`, `delivered_at`, `failed_at`, `created_at`, `updated_at`.
   - Constraints:
     - `chk_notifications_channel`: `channel IN ('PUSH', 'EMAIL', 'SMS')`.
     - `chk_notifications_status`: `status IN ('PENDING', 'PROCESSING', 'RETRY_SCHEDULED', 'SENT', 'DELIVERED', 'FAILED', 'CANCELLED')`.
     - `chk_notifications_priority`: `priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')`.
     - `chk_notifications_attempt_count`: `attempt_count >= 0`.
     - `chk_notifications_max_attempts`: `max_attempts > 0`.
   - Indexes:
     - `uq_notifications_tenant_idempotency`: Partial unique index on `(tenant_id, idempotency_key)` where `idempotency_key IS NOT NULL`.
     - `ix_notifications_worker_queue`: Composite index on `(status, scheduled_for, priority)` for high-throughput background worker polling.
     - `ix_notifications_recipient_user`, `ix_notifications_recipient_employee`, `ix_notifications_related_entity` for fast administrative lookup.
   - **Audit Preservation Invariant**: `recipient_user_id` and `recipient_employee_id` foreign keys enforce `ondelete="SET NULL"`. If a user or employee record is deleted or deactivated, historical notification logs, rendered content, provider message IDs, and delivery timestamps are permanently retained for audit compliance.

4. **`device_push_tokens` (`DevicePushToken`)**:
   - Manages FCM device tokens for mobile push notifications with token rotation and revocation.
   - Fields: `id`, `tenant_id`, `user_id`, `employee_id`, `device_id`, `platform`, `token`, `token_hash`, `device_model`, `os_version`, `app_version`, `status`, `last_seen_at`, `created_at`, `updated_at`.
   - Constraints:
     - `chk_device_push_tokens_platform`: `platform IN ('ANDROID', 'IOS', 'WEB')`.
     - `chk_device_push_tokens_status`: `status IN ('ACTIVE', 'REVOKED', 'EXPIRED')`.
   - Partial unique index:
     - `uq_device_push_tokens_active_token`: Unique on `token_hash` where `status = 'ACTIVE'` to prevent active duplicate token registration across devices while allowing historical token records upon rotation.
   - Security: Tokens are hashed with SHA-256 in `token_hash` for fast lookups without exposing raw tokens in logs.

---

### 2.2 Alembic Migration ([`database/migrations/versions/b5c6d7e8f9a0_phase_10_notifications.py`](../../database/migrations/versions/b5c6d7e8f9a0_phase_10_notifications.py))

- **Revision ID**: `b5c6d7e8f9a0`
- **Revises**: `a4b5c6d7e8f9`
- **Status**: Single head (`alembic heads` -> `b5c6d7e8f9a0 (head)`)
- **DDL Implementation**:
  - Full creation of all 4 tables with check constraints, foreign keys, and indexes.
  - Enables and forces PostgreSQL Row Level Security (RLS) on all 4 tables.
  - Multi-tenant RLS policies:
    - `notification_templates`: Dual-policy configuration:
      - `tenant_isolation_read`: Allows selecting system templates (`tenant_id IS NULL`) OR tenant-owned templates (`tenant_id = current_setting('app.tenant_id', true)::uuid`).
      - `tenant_isolation_write`: Permits INSERT, UPDATE, DELETE only for rows where `tenant_id = current_setting('app.tenant_id', true)::uuid`. Protects system templates from tenant modification.
    - `notification_preferences`, `notifications`, `device_push_tokens`: Standard strict tenant isolation policy enforcing `tenant_id = current_setting('app.tenant_id', true)::uuid`.
  - Permissions: Grants `ALL` to `authenticated` and `service_role`.
  - Reversible: Full `downgrade()` script drops all RLS policies, tables, and constraints in exact reverse dependency order.

### 2.3 Metadata Configuration ([`database/migrations/env.py`](../../database/migrations/env.py))

All four Phase 10 models are imported and registered on `Base.metadata`:
```python
from services.api.notifications.models import (  # noqa: F401
    DevicePushToken,
    Notification,
    NotificationPreference,
    NotificationTemplate,
)
```

---

## 3. Automated Test Execution & Quality Validation

### 3.1 Test Suite Summary ([`tests/test_phase10_database_models_and_migration.py`](../../tests/test_phase10_database_models_and_migration.py))

20 dedicated contract and unit tests were created and executed:

| Test Class | Test Target | Assertions | Status |
| :--- | :--- | :--- | :---: |
| `TestAlembicMigrationIntegrity` | `test_migration_revision_and_down_revision` | Verifies revision `b5c6d7e8f9a0` branches from `a4b5c6d7e8f9` | **PASSED** |
| `TestAlembicMigrationIntegrity` | `test_upgrade_and_downgrade_callables_exist` | Verifies callable upgrade and downgrade functions | **PASSED** |
| `TestModelMetadataRegistration` | `test_all_tables_registered_in_metadata` | Verifies all 4 tables registered on `Base.metadata` | **PASSED** |
| `TestNotificationTemplateModel` | `test_instantiate_tenant_template_success` | Verifies tenant-specific template instantiation | **PASSED** |
| `TestNotificationTemplateModel` | `test_instantiate_system_template_success` | Verifies system template instantiation (`tenant_id=None`) | **PASSED** |
| `TestNotificationTemplateModel` | `test_template_table_constraints` | Validates channel and system/tenant check constraints | **PASSED** |
| `TestNotificationTemplateModel` | `test_template_partial_indexes` | Validates dual partial unique indexes for tenant vs. system | **PASSED** |
| `TestNotificationPreferenceModel` | `test_instantiate_tenant_default_preferences` | Verifies tenant fallback default creation (`user_id=None`) | **PASSED** |
| `TestNotificationPreferenceModel` | `test_instantiate_user_override_preferences_with_quiet_hours` | Verifies user override with quiet-hours configuration | **PASSED** |
| `TestNotificationPreferenceModel` | `test_preference_table_indexes` | Validates tenant-default and user-override partial unique indexes | **PASSED** |
| `TestNotificationModel` | `test_instantiate_notification_record_success` | Verifies outbound notification record construction | **PASSED** |
| `TestNotificationModel` | `test_notification_status_and_priority_constraints` | Validates status, priority, and attempt constraints | **PASSED** |
| `TestNotificationModel` | `test_notification_audit_preservation_foreign_keys` | Verifies `ondelete="SET NULL"` for audit preservation | **PASSED** |
| `TestNotificationModel` | `test_notification_indexes_for_dispatch_and_audit` | Validates worker queue index and tenant idempotency index | **PASSED** |
| `TestDevicePushTokenModel` | `test_instantiate_device_push_token_success` | Verifies device token instantiation with SHA-256 hash | **PASSED** |
| `TestDevicePushTokenModel` | `test_device_push_token_constraints` | Validates platform and status check constraints | **PASSED** |
| `TestDevicePushTokenModel` | `test_device_push_token_active_uniqueness_index` | Validates active-status uniqueness partial index | **PASSED** |
| `TestMigrationRLSPoliciesScriptVerification` | `test_migration_enables_rls_on_all_four_tables` | Verifies DDL enables RLS on all 4 tables | **PASSED** |
| `TestMigrationRLSPoliciesScriptVerification` | `test_migration_template_read_and_write_policy_distinction` | Verifies read vs. write policy separation on templates | **PASSED** |
| `TestMigrationRLSPoliciesScriptVerification` | `test_migration_grants_permissions` | Verifies permission grants to authenticated and service roles | **PASSED** |

**Execution Result**: 20 passed in 0.94s (100% pass rate).

### 3.2 Regression Verification

Running regression across Phase 10, Phase 9, and health checks:
```bash
pytest tests/test_phase10_database_models_and_migration.py tests/test_phase9_database_models_and_migration.py tests/test_health.py
# Result: 48 passed in 16.28s (100% pass rate)
```

### 3.3 Static Analysis & Formatting
- **Linter (`ruff check services/api/notifications/ tests/test_phase10_database_models_and_migration.py`)**: All checks passed (0 errors, 0 warnings).
- **Type Checker (`mypy services/api/notifications/`)**: `Success: no issues found in 2 source files`.

---

## 4. PostgreSQL Staging & Environment Notes

- PostgreSQL-specific constructs (partial indexes with `postgresql_where`, RLS policies with `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `current_setting('app.tenant_id', true)`) were validated via contract assertions and AST/DDL script inspection.
- Live database execution of migration `b5c6d7e8f9a0` requires PostgreSQL 15+ (configured in Supabase or CI runner environment). SQLite in-memory engines are excluded from asserting RLS enforcement per standard testing guidelines.

---

## 5. Summary of Milestones Ahead in Phase 10

Following the approved Phase 10 Scope Roadmap:
- **Milestone 10.2**: Core Dispatch Engine & Notification Repository (dispatch routing, quiet-hours evaluation, template rendering, provider abstraction interface).
- **Milestone 10.3**: Push Notification Provider (FCM adapter, token registration API, invalid token handling).
- **Milestone 10.4**: Email & SMS Notification Providers (SMTP/SendGrid/SES fallback, SMS gateway adapter, template interpolation).
- **Milestone 10.5**: Domain Event Integrations (attendance anomaly triggers, geofence violations, shift reminders, leave status changes).
- **Milestone 10.6**: Web Console Management UI (notification template editor, tenant preference configuration, dispatch audit logs).
- **Milestone 10.7**: Mobile Push Reception & Notification Center (FCM Flutter setup, background handler, in-app notification list).

---

## 6. Verification Status & Readiness

Milestone 10.1 is complete, verified, and adheres to all project architecture constraints. In accordance with strict instructions, no commits, tags, or pushes have been made, and work has paused for review and authorization before proceeding to Milestone 10.2.

