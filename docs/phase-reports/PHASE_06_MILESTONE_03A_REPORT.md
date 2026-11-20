# PHASE 06 MILESTONE 6.3.A REPORT — Backend Attendance Policy Engine & GPS Geofence Enforcement

**Stage**: Stage B — Attendance Core  
**Phase**: Phase 6 — Mobile Attendance Application  
**Milestone**: Milestone 6.3.A — Backend Attendance Policy Engine & GPS Geofence Enforcement  
**Status**: ✅ COMPLETED & VERIFIED  
**Repository**: `/Users/apple/Upostit`  
**Active Branch**: `phase-06`  
**Live Supabase Head Revision**: `b3c4d5e6f7a8 (head)` (Down: `a2b3c4d5e6f7`)  
**Timestamp**: 2026-11-05  

---

## 1. Executive Summary & Objective

In Phase 6 Milestone 6.3.A, we delivered the server-authoritative **Company Attendance Policy Engine** and **PostGIS GPS Geofence Enforcement** for the UPOSTIT platform.

This milestone ensures that:
1. Attendance verification rules are tenant-configurable (`MANUAL`, `GPS_ONLY`, `WIFI_ONLY`, `BIOMETRIC_ONLY`, `FACE_RECOGNITION`, `COMBINED`, `PRIMARY_WITH_FALLBACK`).
2. Companies who do not require GPS verification remain on the default `MANUAL` policy, where punches require zero location coordinates, ensuring 100% backward compatibility for existing web and mobile attendance.
3. When GPS is required by company policy, the backend authoritatively enforces PostGIS `ST_DWithin` spatial containment, accuracy bounds ($\le 100\text{m}$), and timestamp freshness ($\le 30\text{s}$), either rejecting out-of-geofence punches (`HTTP 400`) or flagging them for supervisor review (`PENDING_REVIEW`) per policy.
4. Future verification methods (`WIFI`, `BIOMETRIC`, `FACE_RECOGNITION`) are clearly marked as future integrations. If configured and required, the engine fails safely with a descriptive `HTTP 422 Unprocessable Content` response rather than silently downgrading to manual punching.
5. Mobile and web employees access only their active assigned workplaces via `GET /api/v1/employees/me/workplaces` (now extended with `latitude`, `longitude`, and `radius_meters`) and can probe their proximity via `POST /api/v1/employees/me/workplaces/verify-coordinates` without receiving broad tenant-wide location directory access.
6. Policy changes are immutable and versioned; historical punches retain traceability via `AttendanceEvent.applied_policy_version`, and idempotency replays preserve original results regardless of subsequent policy modifications.

---

## 2. Policy Data Model & Immutable Versioning

### Database Migration: `b3c4d5e6f7a8_phase_06_tenant_attendance_policies.py`
Applied cleanly to the live Supabase PostgreSQL database:
- **Table Created**: `tenant_attendance_policies`
- **Isolation & Security**: `ALTER TABLE tenant_attendance_policies ENABLE ROW LEVEL SECURITY;` and `FORCE ROW LEVEL SECURITY`.
- **Policy Seeded**: Every existing tenant in the platform was automatically seeded with an active Version 1 `MANUAL` policy.
- **Ledger Alteration**: Added `applied_policy_version INTEGER` to `attendance_events`.

### Schema Constraints & Indexes
```sql
CREATE TABLE tenant_attendance_policies (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT true,
    default_mode VARCHAR(32) NOT NULL DEFAULT 'MANUAL',
    allowed_methods JSONB NOT NULL DEFAULT '["MANUAL"]',
    required_methods JSONB NOT NULL DEFAULT '["MANUAL"]',
    combination_rule VARCHAR(16) NOT NULL DEFAULT 'OR',
    fallback_policy JSONB NOT NULL DEFAULT '{}',
    gps_config JSONB NOT NULL DEFAULT '{"max_accuracy_meters": 100, "max_location_age_seconds": 30, "enforce_assigned_workplace": true, "out_of_geofence_action": "REJECT"}',
    wifi_config JSONB NOT NULL DEFAULT '{}',
    biometric_config JSONB NOT NULL DEFAULT '{}',
    face_config JSONB NOT NULL DEFAULT '{}',
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenant_attendance_policy_tenant_version UNIQUE (tenant_id, version),
    CONSTRAINT uq_tenant_attendance_policy_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT chk_tenant_policy_version CHECK (version >= 1),
    CONSTRAINT chk_tenant_policy_default_mode CHECK (default_mode IN ('MANUAL', 'GPS_ONLY', 'WIFI_ONLY', 'BIOMETRIC_ONLY', 'FACE_RECOGNITION', 'COMBINED', 'PRIMARY_WITH_FALLBACK')),
    CONSTRAINT chk_tenant_policy_combination_rule CHECK (combination_rule IN ('AND', 'OR', 'PRIMARY_WITH_FALLBACK'))
);

CREATE INDEX ix_tenant_attendance_policies_tenant_active 
    ON tenant_attendance_policies(tenant_id, is_active);

-- Strictly guarantees at most ONE active policy per tenant
CREATE UNIQUE INDEX uq_tenant_attendance_policy_one_active 
    ON tenant_attendance_policies(tenant_id) 
    WHERE is_active = true;
```

### Immutable Versioning Rules
When an administrator modifies attendance policies:
1. The currently active policy row for that tenant is locked with `SELECT ... FOR UPDATE` and deactivated (`is_active = False`).
2. The maximum version number for that tenant is queried: `max_version = MAX(version)`.
3. A brand new row is inserted with `version = max_version + 1` and `is_active = True`.
4. Historical policy configurations are never overwritten or mutated.
5. In case of concurrent policy activations, the partial unique index `uq_tenant_attendance_policy_one_active` guarantees database-level serializability.

---

## 3. Dedicated Policy Evaluation Engine

Implemented in `services/api/attendance/policy_engine.py`:

| Method | Status | Backend Evaluation Behavior |
| :--- | :--- | :--- |
| `MANUAL` | **Operational** | Default mode. Coordinates are optional telemetry. Geofence checks do not gate or reject attendance. |
| `GPS_ONLY` | **Operational** | Strict location evidence required (`location_id`, `latitude`, `longitude`). Evaluates assignment, accuracy ($\le 100\text{m}$), freshness ($\le 30\text{s}$), and PostGIS `ST_DWithin`. |
| `WIFI_ONLY` | *Future Integration* | Fails safely with `HTTP 422 Unprocessable Content`. Explicit error stating Wi-Fi is not yet operational. Never silently downgrades to MANUAL. |
| `BIOMETRIC_ONLY` | *Future Integration* | Fails safely with `HTTP 422 Unprocessable Content`. Requires dedicated biometric device terminal bridge (Phase 15). |
| `FACE_RECOGNITION`| *Future Integration* | Fails safely with `HTTP 422 Unprocessable Content`. Requires Phase 7 biometric liveness shield. |
| `COMBINED` (AND / OR) | **Operational** | Evaluates combination rule; if any required component is unimplemented, fails safely. |
| `PRIMARY_WITH_FALLBACK`| **Operational** | Auditable fallback structure preserved in policy history. |

---

## 4. API Endpoints Implemented & Extended

### 1. `GET /api/v1/attendance/policy/me`
- **Authorization**: `Permission.VIEW_ATTENDANCE_POLICY` or `Permission.RECORD_PUNCH` (accessible by Employee, Manager, HR, Admin, Owner).
- **Behavior**: Retrieves sanitized, employee-safe view of the caller's active policy without exposing internal administrative audit trails or creator IDs.
- **Response Schema (`EmployeeAttendancePolicyResponse`)**:
  ```json
  {
    "tenant_id": "30ad42c9-1b15-4e4b-8896-f3d91677ff26",
    "version": 1,
    "default_mode": "MANUAL",
    "allowed_methods": ["MANUAL"],
    "required_methods": ["MANUAL"],
    "combination_rule": "OR",
    "requires_gps": false,
    "requires_wifi": false,
    "requires_biometric": false,
    "requires_face": false,
    "max_accuracy_meters": 100,
    "max_location_age_seconds": 30
  }
  ```

### 2. `GET /api/v1/attendance/policy` & `POST /api/v1/attendance/policy`
- **Authorization**: `Permission.MANAGE_ATTENDANCE_POLICY` (Owner/Admin only; Employees and Managers receive `HTTP 403 Forbidden`).
- **Behavior**: Lists full immutable policy version history, and creates new versions with automatic deactivation of previous versions.

### 3. Extended `GET /api/v1/employees/me/workplaces`
- **Authorization**: `Permission.VIEW_OWN_PROFILE` (Employee self-access).
- **Behavior**: Returns only workplaces actively assigned to the authenticated employee for the query date.
- **Fields Added**:
  - `latitude: Decimal | None`
  - `longitude: Decimal | None`
  - `radius_meters: int | None`

### 4. `POST /api/v1/employees/me/workplaces/verify-coordinates`
- **Authorization**: `Permission.RECORD_PUNCH`.
- **Purpose**: Server-authoritative probe endpoint for mobile/web UI to preview geofence proximity prior to punching.
- **Validations Enforced**:
  1. Authenticated user has an active linked `Employee` profile.
  2. Employee is actively assigned to the requested `location_id` for today's date.
  3. Location exists, belongs to the caller's tenant, and is active.
  4. Accuracy is within active policy threshold (`<= max_accuracy_meters`).
  5. Timestamp is fresh (`<= max_location_age_seconds`).
  6. PostGIS spatial calculation: `ST_Distance(...)` and `ST_DWithin(...)`.
- **Response Schema (`EmployeeGeofenceVerifyResponse`)**:
  ```json
  {
    "location_id": "9f1039b1-bff5-4db5-b4cc-4fe46230ef1a",
    "location_name": "Headquarters",
    "location_code": "HQ-MAIN",
    "radius_meters": 100,
    "reported_latitude": "12.9715987",
    "reported_longitude": "77.5945627",
    "accuracy_meters": "12.0",
    "distance_meters": 18.5,
    "within_geofence": true,
    "accuracy_acceptable": true,
    "location_freshness_acceptable": true,
    "freshness_acceptable": true,
    "is_inside": true,
    "can_punch": true,
    "message": "Inside 'Headquarters' geofence (18.5m). Verification successful.",
    "threat_boundary_notice": "ST_DWithin verifies geometric spherical proximity against the workplace perimeter. Anti-spoofing and biometric liveness are enforced in Phase 7 Fraud Shield."
  }
  ```

---

## 5. Punch Ingestion Integration (`POST /api/v1/attendance/punch`)

The punch workflow was updated transactionally in `services/api/attendance/service.py`:
1. **Idempotency Replay Check**: If the idempotency key already completed, the cached response is returned immediately with `idempotent_replay = True`. A subsequent policy change does NOT re-evaluate or modify the historical punch.
2. **Policy Resolution**: Active policy is fetched using `get_active_tenant_policy(session, tenant_id)`.
3. **Evidence Evaluation**:
   - Under `MANUAL`: GPS coordinates (if optionally provided) are captured purely as telemetry (`metadata_json["spatial_evidence"]["telemetry_only"] = True`).
   - Under `GPS_ONLY` or required `GPS`: Missing coordinates return `HTTP 400`. Poor accuracy returns `HTTP 400`. Stale fixes return `HTTP 400`. Unassigned locations return `HTTP 403`.
   - PostGIS `ST_DWithin` is evaluated. If outside geofence:
     - `out_of_geofence_action == "REJECT"`: Aborts transaction with `HTTP 400 Bad Request` with exact distance and allowed radius.
     - `out_of_geofence_action == "FLAG_PENDING_REVIEW"`: Flags event with `review_status = "PENDING_REVIEW"` and `verification_flags = ["OUT_OF_GEOFENCE"]`.
4. **Policy Version Traceability**: Sets `AttendanceEvent.applied_policy_version = policy_outcome.policy_version`.
5. **Atomic Projection Recalculation**: Runs inside the same database transaction.

---

## 6. Verification Results

### 1. Dedicated Phase 6.3.A Test Suite (`tests/test_phase6_attendance_policy.py`)
```bash
.venv/bin/pytest tests/test_phase6_attendance_policy.py -v
```
**Results**:
- `test_policy_defaults_to_manual_when_no_active_row` ✅ PASSED
- `test_policy_create_new_version_increments_and_deactivates_previous` ✅ PASSED
- `test_unsupported_future_method_wifi_fails_safely` ✅ PASSED
- `test_unsupported_future_method_biometric_fails_safely` ✅ PASSED
- `test_manual_policy_punch_without_coordinates_succeeds` ✅ PASSED
- `test_manual_policy_optional_coordinates_do_not_gate_or_reject` ✅ PASSED
- `test_gps_policy_missing_coordinates_rejected_400` ✅ PASSED
- `test_gps_policy_insufficient_accuracy_rejected_400` ✅ PASSED
- `test_gps_policy_stale_coordinates_rejected_400` ✅ PASSED
- `test_gps_policy_unassigned_workplace_forbidden_403` ✅ PASSED
- `test_gps_policy_outside_geofence_reject_action_400` ✅ PASSED
- `test_gps_policy_outside_geofence_flag_pending_review` ✅ PASSED
- `test_gps_policy_inside_geofence_succeeds_with_evidence` ✅ PASSED
- `test_verify_employee_coordinates_inside_geofence` ✅ PASSED
- `test_verify_employee_coordinates_outside_geofence` ✅ PASSED
- `test_api_get_my_policy_employee_safe` ✅ PASSED
- `test_api_admin_can_create_policy_version` ✅ PASSED
- `test_api_employee_cannot_manage_policy` ✅ PASSED
- `test_idempotency_replay_preserves_original_policy_version` ✅ PASSED
**19 passed in 2.18s** (100% pass rate).

### 2. Full Backend Regression Suite
```bash
.venv/bin/pytest tests/ -v
```
**Results**: **300 passed, 0 failures** across all test suites:
- `test_auth_api.py`, `test_auth_schemas.py`, `test_auth_security.py` (Authentication & Security)
- `test_cross_tenant_isolation.py`, `test_rbac.py`, `test_health.py` (Tenant Isolation & RBAC)
- `test_phase3_api.py`, `test_phase3_business_rules.py`, `test_phase3_rbac.py`, `test_phase3_schemas.py` (Phase 3 Core)
- `test_phase4_locations_api.py`, `test_phase4_workplace_assignments.py`, `test_phase4_invitations.py`, `test_phase4_import.py` (Phase 4 Workplaces & Onboarding)
- `test_phase5_shifts.py`, `test_phase5_punch_ledger.py`, `test_phase5_corrections.py`, `test_phase5_calculation_engine.py` (Phase 5 Attendance Ledger, Shifts, Corrections, Projections)
- `test_phase6_attendance_policy.py` (Phase 6 Attendance Policy Engine & Geofencing)

### 3. Static Analysis & Linting
```bash
make lint
```
- `ruff check services/ packages/ tests/`: **All checks passed!**
- `mypy services/api/`: **Success: no issues found in 50 source files!**

### 4. Live Supabase PostgreSQL Verification
```bash
make verify-db
```
- Direct Supabase PostgreSQL + PostGIS Connection: **OK (PostGIS available)**.
- `alembic current`: **b3c4d5e6f7a8 (head)**.
- Verified active table `tenant_attendance_policies`, columns, constraints, unique partial index `uq_tenant_attendance_policy_one_active`, and initial seeded records.

---

## 7. Scope Boundaries & Remaining Work

### Implemented in Milestone 6.3.A:
- ✅ Backend Company Attendance Policy Engine with versioning and immutable history.
- ✅ PostGIS `ST_DWithin` spatial verification in punch ingest and geofence probe.
- ✅ Employee-safe policy endpoint `GET /api/v1/attendance/policy/me`.
- ✅ Employee assigned workplace coordinate extensions in `GET /api/v1/employees/me/workplaces`.
- ✅ Dedicated geofence probe endpoint `POST /api/v1/employees/me/workplaces/verify-coordinates`.
- ✅ Unimplemented methods safe failure (`HTTP 422`).
- ✅ Idempotency replay preservation under policy evolution.

### Remaining Work for Milestone 6.3.B (Mobile GPS):
- ⏳ Mobile Flutter location service (`features/location/`).
- ⏳ Foreground location permissions (`geolocator`) on Android & iOS.
- ⏳ Haversine advisory distance and radar geofence status cards.
- ⏳ Integration with mobile punch BLoC.

### Future Phase Integrations:
- ⏳ Milestone 6.4: Wi-Fi BSSID verification.
- ⏳ Milestone 6.5: Offline encrypted SQLite synchronization queue.
- ⏳ Phase 7: Biometric facial liveness and hardware binding.
- ⏳ Phase 15: Hardware biometric terminal network protocol.

---

## 8. Exact Git Status

```text
On branch phase-06
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   PROJECT_CONTEXT.md
	modified:   apps/mobile/analysis_options.yaml
	modified:   apps/mobile/lib/core/config/env_config.dart
	modified:   apps/mobile/lib/core/constants/app_colors.dart
	deleted:    apps/mobile/lib/features/welcome/presentation/welcome_screen.dart
	modified:   apps/mobile/lib/main.dart
	modified:   apps/mobile/pubspec.yaml
	modified:   apps/mobile/test/widget_test.dart
	modified:   services/api/attendance/models.py
	modified:   services/api/attendance/routes.py
	modified:   services/api/attendance/schemas.py
	modified:   services/api/attendance/service.py
	modified:   services/api/auth/permissions.py
	modified:   services/api/employees/routes.py
	modified:   services/api/locations/assignment_service.py
	modified:   services/api/locations/schemas.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	apps/mobile/.gitignore
	apps/mobile/.metadata
	apps/mobile/android/
	apps/mobile/ios/
	apps/mobile/lib/app.dart
	apps/mobile/lib/core/constants/app_spacing.dart
	apps/mobile/lib/core/constants/app_typography.dart
	apps/mobile/lib/core/errors/
	apps/mobile/lib/core/network/
	apps/mobile/lib/core/storage/
	apps/mobile/lib/core/theme/
	apps/mobile/lib/core/utils/
	apps/mobile/lib/features/attendance/
	apps/mobile/lib/features/auth/
	apps/mobile/lib/features/profile/
	apps/mobile/lib/shared/
	apps/mobile/pubspec.lock
	apps/mobile/test/core/
	apps/mobile/test/features/
	database/migrations/versions/b3c4d5e6f7a8_phase_06_tenant_attendance_policies.py
	docs/MOBILE_ATTENDANCE_ARCHITECTURE.md
	docs/PHASE_06_PLAN.md
	docs/phase-reports/PHASE_06_MILESTONE_03A_REPORT.md
	services/api/attendance/policy_engine.py
	tests/test_phase6_attendance_policy.py
```
*(No commits, tags, or pushes made. Stopping strictly after Milestone 6.3.A as mandated).*
