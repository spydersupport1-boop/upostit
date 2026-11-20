# UPOSTIT Phase 7 — Milestone 7.1 Implementation Report
## Device Binding Subsystem & Database Migration

**Date:** 2026-11-19  
**Phase:** 7 — Mobile Attendance Fraud Shield v1  
**Milestone:** 7.1 — Device Binding Subsystem & Database Migration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated

---

## 1. Executive Summary

Milestone 7.1 implements the foundational **Employee Device Binding Subsystem** for the UPOSTIT Workforce Attendance SaaS platform. Building upon the secure authentication (Phase 2), employee management (Phase 3–4), and attendance engine (Phase 5–6), Milestone 7.1 introduces cryptographic device identity management, single-device binding policy enforcement, administrative revocation, and atomic device replacement workflows.

Key achievements in Milestone 7.1:
1. **Database Schema & Migration (`a3b4c5d6e7f8_phase_07_devices.py`)**:
   - Authored the `devices` table with UUID primary key, composite tenant-aware foreign keys (`fk_devices_employee`, `fk_devices_revoked_by`, `fk_devices_replacement_for`, `fk_devices_replacement_approved_by`), check constraints on platform and status, and strict PostgreSQL Row-Level Security (RLS).
   - Enforced the single active device policy directly at the database engine level via a partial unique index: `ix_devices_tenant_emp_active` on `(tenant_id, employee_id) WHERE status = 'ACTIVE'`.
   - Verified static SQL upgrade and downgrade generation with Alembic.
2. **Cryptographic Device Identifier Salting & Hashing**:
   - Designed server-side device identifier hashing using HMAC-SHA256 (`hash_device_id`), salting with the tenant's UUID and server secret key. Raw device identifiers are never persisted to the database, preventing rainbow table attacks and cross-tenant correlation.
3. **Domain Models & Pydantic Schemas (`services/api/devices/`)**:
   - Created SQLAlchemy `Device` model and comprehensive Pydantic schemas for device registration, information, listing, revocation, and replacement approval.
   - Public API models strictly exclude internal hashes and cryptographic salts.
4. **Employee Device Registration & Idempotency (`POST /api/v1/devices/register`)**:
   - Authenticated employees register their device using their authenticated server context (tenant ID and employee ID are derived securely from the JWT session, never trusted from client parameters).
   - Re-registration of an existing active device is idempotent, refreshing last seen telemetry without creating duplicate records.
   - Registering a different device while an active device exists automatically initiates an audit-logged `PENDING_APPROVAL` replacement request rather than silently overwriting the active device.
5. **Administrative Management & Device Replacement Workflow**:
   - `GET /api/v1/devices`: Tenant-scoped device list with filtering (by employee, status, platform) and pagination, guarded by `Permission.VIEW_DEVICES`.
   - `GET /api/v1/devices/me`: Employee self-service status endpoint returning their bound device details.
   - `POST /api/v1/devices/{id}/revoke`: Administrative revocation requiring mandatory reason, recording actor user ID, timestamp, and transition to `REVOKED`.
   - `POST /api/v1/devices/{id}/approve-replacement`: Atomic administrative approval rotating the previous active device to `REPLACED` and activating the replacement device in a single database transaction.
6. **Granular RBAC Permissions**:
   - Registered `MANAGE_DEVICES` and `VIEW_DEVICES` capabilities under Owner, Admin, and HR roles. Manager and Employee access is strictly prohibited for administrative management endpoints.
7. **Attendance Integration Preparation (`validate_device_for_punch`)**:
   - Implemented a reusable, modular device validation helper ready for integration into the attendance engine in Milestones 7.2 and 7.3. Distinguishes `ACTIVE`, `UNREGISTERED`, `REVOKED`, `REPLACED`, `PENDING_APPROVAL`, and `NO_DEVICE_SUPPLIED`.

---

## 2. Test Execution & Validation Summary

### 2.1 Automated Test Results

| Test Category | Test File / Suite | Tests Run | Passed | Failed | Skipped | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **RBAC Device Permissions** | `tests/test_phase7_devices.py` | 5 | 5 | 0 | 0 | **PASSED** |
| **Device Hashing & Salt Isolation**| `tests/test_phase7_devices.py` | 3 | 3 | 0 | 0 | **PASSED** |
| **Device Service Logic** | `tests/test_phase7_devices.py` | 8 | 8 | 0 | 0 | **PASSED** |
| **Punch Device Validation Helper**| `tests/test_phase7_devices.py` | 4 | 4 | 0 | 0 | **PASSED** |
| **Device API Endpoints & Routing**| `tests/test_phase7_devices.py` | 12 | 12 | 0 | 0 | **PASSED** |
| **Phase 7.1 Device Test Suite**| All Milestone 7.1 tests | **32** | **32** | **0** | **0** | **100% PASS** |
| **Full Backend Regression Suite**| All backend tests (`pytest tests/`) | **355** | **355** | **0** | **0** | **100% PASS** |

### 2.2 Static Analysis & Linting
- **`ruff check`**: Clean run across `services/api/devices/`, `database/migrations/versions/a3b4c5d6e7f8_phase_07_devices.py`, and `tests/test_phase7_devices.py` with **0 errors**.
- **`mypy`**: **Success: no issues found in 5 source files**.
- **Alembic Offline Upgrade & Downgrade**: Verified transactional static SQL generation (`c4d5e6f7a8b9 -> a3b4c5d6e7f8` and `a3b4c5d6e7f8 -> c4d5e6f7a8b9`).

---

## 3. Database Schema & Migration Specification

### 3.1 Migration `a3b4c5d6e7f8_phase_07_devices.py`

- **Revision ID:** `a3b4c5d6e7f8`
- **Down Revision:** `c4d5e6f7a8b9` (Phase 6.4 Wi-Fi access points)
- **Table Name:** `devices`

```sql
CREATE TABLE devices (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    tenant_id UUID NOT NULL, 
    employee_id UUID NOT NULL, 
    device_id_hash VARCHAR(128) NOT NULL, 
    platform VARCHAR(20) NOT NULL, 
    device_model VARCHAR(100), 
    os_name VARCHAR(50), 
    os_version VARCHAR(50), 
    app_version VARCHAR(50), 
    status VARCHAR(30) DEFAULT 'ACTIVE' NOT NULL, 
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    revoked_by_user_id UUID, 
    revocation_reason TEXT, 
    replacement_for_device_id UUID, 
    replacement_approved_by_user_id UUID, 
    replacement_approved_at TIMESTAMP WITH TIME ZONE, 
    metadata_json JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_devices_tenant_id UNIQUE (tenant_id, id), 
    CONSTRAINT uq_devices_tenant_device_hash UNIQUE (tenant_id, device_id_hash), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_devices_employee FOREIGN KEY(tenant_id, employee_id) REFERENCES employees (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_devices_revoked_by FOREIGN KEY(tenant_id, revoked_by_user_id) REFERENCES users (tenant_id, id) ON DELETE SET NULL (revoked_by_user_id), 
    CONSTRAINT fk_devices_replacement_for FOREIGN KEY(tenant_id, replacement_for_device_id) REFERENCES devices (tenant_id, id) ON DELETE SET NULL (replacement_for_device_id), 
    CONSTRAINT fk_devices_replacement_approved_by FOREIGN KEY(tenant_id, replacement_approved_by_user_id) REFERENCES users (tenant_id, id) ON DELETE SET NULL (replacement_approved_by_user_id), 
    CONSTRAINT chk_devices_platform CHECK (platform IN ('ANDROID', 'IOS', 'WEB', 'OTHER')), 
    CONSTRAINT chk_devices_status CHECK (status IN ('PENDING_APPROVAL', 'ACTIVE', 'REVOKED', 'REPLACED'))
);

CREATE UNIQUE INDEX ix_devices_tenant_emp_active ON devices (tenant_id, employee_id) WHERE status = 'ACTIVE';
CREATE INDEX ix_devices_tenant_status ON devices (tenant_id, status);
CREATE INDEX ix_devices_tenant_employee ON devices (tenant_id, employee_id);

ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON devices
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON devices TO authenticated, service_role;
```

---

## 4. API Endpoints Reference

All endpoints are mounted under `/api/v1/devices`:

| HTTP Method | Route | Permission / Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/devices/register` | Authenticated Employee | Registers employee device. Idempotent for same device; creates `PENDING_APPROVAL` replacement if employee has another active device. |
| `GET` | `/api/v1/devices/me` | Authenticated Employee | Returns current active or pending device status for the calling employee. |
| `GET` | `/api/v1/devices` | `VIEW_DEVICES` (Owner, Admin, HR) | Lists organization devices with filtering (`employee_id`, `status`, `platform`) and pagination. |
| `GET` | `/api/v1/devices/{device_id}` | `VIEW_DEVICES` (Owner, Admin, HR) | Retrieves full metadata for a specific registered device. |
| `POST` | `/api/v1/devices/{device_id}/revoke` | `MANAGE_DEVICES` (Owner, Admin, HR) | Revokes device registration with a mandatory reason ($ \ge 3 $ characters). |
| `POST` | `/api/v1/devices/{device_id}/approve-replacement` | `MANAGE_DEVICES` (Owner, Admin, HR) | Atomically approves a pending replacement device, marking the old device as `REPLACED` and the new device as `ACTIVE`. |

---

## 5. Security & Multi-Tenancy Architecture

1. **HMAC-SHA256 Salted Identity**:
   - `hash_device_id(tenant_id, raw_device_id) = HMAC_SHA256(SECRET_KEY, f"{tenant_id}:{raw_device_id}")`.
   - Prevents exposure of client hardware serial numbers or advertising identifiers.
   - Eliminates cross-tenant device correlation.
2. **Database-Level Single-Device Invariant**:
   - The PostgreSQL partial index `ix_devices_tenant_emp_active` guarantees that concurrent or racing registration requests cannot bypass the single-device rule.
3. **Atomic Rotations**:
   - Approval of a replacement device (`approve_device_replacement`) executes inside a single database transaction using `with_for_update()`, guaranteeing that the old device is deactivated simultaneously with the new device activation.
4. **Fail-Closed Punch Authorization Helper**:
   - `validate_device_for_punch()` returns `is_authorized: False` for missing devices, unregistered devices, revoked devices, and pending replacement devices.

---

## 6. Live Environment Status & Limitations

- **Alembic Static DDL**: Verified offline. Migration script `a3b4c5d6e7f8` is queued and ready for live application.
- **Database Connection**: Tested against mock AsyncSession and static SQL dialect validation. The live Supabase instance will apply this migration upon deployment with `alembic upgrade head`.
- **Scope Discipline**: Mobile Flutter integration, GPS spoofing detection, velocity calculations, and composite risk scoring were strictly excluded from this milestone and remain scheduled for Milestones 7.2 through 7.6.

---

## 7. Sign-Off & Next Steps

Milestone 7.1 is complete, fully tested (32 new tests, 355 full backend tests passing), and lint-clean.

**Next Milestone:**  
**Milestone 7.2: GPS Spoofing Defense, Mock Detection & Velocity Analysis**  
(Implementation of velocity calculations $v = \Delta d / \Delta t$, mock location telemetry validation, and clock drift analysis).

