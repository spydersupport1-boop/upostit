# PHASE 06 MILESTONE 6.4.A REPORT — Backend Wi-Fi Attendance Verification & Admin-Configurable Fallback

**Stage**: Stage B — Attendance Core  
**Phase**: Phase 6 — Mobile Attendance Application  
**Milestone**: Milestone 6.4.A — Backend Wi-Fi Attendance Verification & Admin-Configurable Fallback  
**Status**: ✅ COMPLETED & VERIFIED  
**Repository**: `/Users/apple/Upostit`  
**Active Branch**: `phase-06`  
**Live Supabase Head Revision**: `c4d5e6f7a8b9 (head)` (Down: `b3c4d5e6f7a8`)  
**Timestamp**: 2026-11-05  

---

## 1. Executive Summary & Objective

In Phase 6 Milestone 6.4.A, we successfully engineered and verified the server-authoritative **Workplace Wi-Fi Attendance Verification** and **Admin-Configurable Fallback Engine** for the UPOSTIT platform.

This milestone operationalizes:
1. **Workplace-Level Wi-Fi Configuration**: Authorized company administrators can register, inspect, update, and soft-deactivate multiple physical Wi-Fi Access Points (BSSIDs / MAC addresses) per workplace location.
2. **Strict Hardware Identification (BSSID vs. SSID)**: Normalized IEEE 802 MAC addresses (`XX:XX:XX:XX:XX:XX`) are authoritatively used as presence credentials. Network SSID is treated as advisory/diagnostic display only, preventing rogue mobile hotspot impersonation.
3. **Signal State Categorization & Fraud Defense**:
   - `MATCHED`: BSSID matches an active, authorized workplace router. Punch verified as `WIFI`.
   - `MISMATCHED`: Device connected to an unauthorized network (e.g. employee home router, personal hotspot, neighbor router). Strictly treated as **negative presence evidence** and rejected (`HTTP 400`) or flagged for review. Never silently falls back.
   - `UNAVAILABLE`: Device disconnected from Wi-Fi or permissions toggled off. Seamlessly transitions to configured admin fallback.
   - `UNSUPPORTED`: Client platform limitation (e.g. iOS without Apple Wi-Fi entitlement). Safely transitions to configured fallback.
   - `STALE`: Wi-Fi telemetry older than `max_wifi_age_seconds` (default 30s) is strictly rejected with `HTTP 400`.
4. **Four Admin-Configurable Fallback Behaviors**:
   - `REJECT`: Mandatory Wi-Fi; punch aborted if Wi-Fi telemetry is unavailable.
   - `GPS_FALLBACK`: Evaluates punch coordinates against workplace PostGIS geofence. Accepted if inside (`GPS_FALLBACK`), rejected if outside.
   - `SUPERVISOR_REVIEW`: Punch accepted into append-only ledger flagged as `PENDING_REVIEW` (`WIFI_UNAVAILABLE_REVIEW`).
   - `MANUAL_FALLBACK`: Punch accepted as unverified manual punch if authorized by tenant `allowed_methods`.
5. **Security Guardrail for Multi-Method Rules (`AND` / `OR`)**:
   - Under dual-factor `AND` rules requiring both GPS and Wi-Fi, the fallback engine strictly disables single-factor bypasses, guaranteeing multi-factor presence.
   - Under `OR` rules, authorized Wi-Fi or valid GPS independently satisfies presence.
6. **Workplace-Level Policy Overrides**: Individual facilities can override tenant fallback actions via `Location.wifi_config_override`, while strictly constrained by tenant `allowed_methods`.
7. **Traceable Append-Only Ledger**: Added `wifi_bssid` and `wifi_ssid` to `attendance_events`. Full BSSID matching evidence and fallback audit trails are preserved in `metadata_json`.

---

## 2. Database Schema & Migration Implementation

### Alembic Migration: `c4d5e6f7a8b9_phase_06_workplace_wifi_access_points.py`
Applied and verified live against the Supabase PostgreSQL database:
- **Table Created**: `workplace_wifi_access_points`
- **Columns Extended on `locations`**: `wifi_config_override JSONB DEFAULT '{}'::jsonb NOT NULL`
- **Columns Extended on `attendance_events`**: `wifi_bssid VARCHAR(17) NULL`, `wifi_ssid VARCHAR(64) NULL`
- **Row-Level Security**: Enabled and forced on `workplace_wifi_access_points` using `tenant_isolation` policy matching `current_setting('app.tenant_id', true)::uuid`.

```sql
CREATE TABLE workplace_wifi_access_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    location_id UUID NOT NULL,
    friendly_name VARCHAR(100) NOT NULL,
    bssid VARCHAR(17) NOT NULL,
    ssid VARCHAR(64) NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to DATE NULL,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_workplace_wifi_location FOREIGN KEY (tenant_id, location_id)
        REFERENCES locations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT uq_workplace_wifi_location_bssid UNIQUE (tenant_id, location_id, bssid),
    CONSTRAINT chk_workplace_wifi_bssid_format CHECK (bssid ~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'),
    CONSTRAINT chk_workplace_wifi_dates CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX ix_workplace_wifi_tenant_location_active 
    ON workplace_wifi_access_points (tenant_id, location_id, is_active);

CREATE INDEX ix_workplace_wifi_tenant_bssid 
    ON workplace_wifi_access_points (tenant_id, bssid);

ALTER TABLE workplace_wifi_access_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE workplace_wifi_access_points FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workplace_wifi_access_points
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

---

## 3. API Contracts & Implemented Endpoints

### 3.1 Admin Workplace Wi-Fi Management APIs
Mounted under `/api/v1/locations/{location_id}/wifi-access-points`:
- `POST /` — Register an authorized Wi-Fi access point (`Permission.MANAGE_LOCATIONS`).
- `GET /` — List authorized access points for a workplace with `is_active` filter (`Permission.VIEW_LOCATIONS`).
- `GET /{ap_id}` — Get single access point details (`Permission.VIEW_LOCATIONS`).
- `PATCH /{ap_id}` — Update friendly name, SSID, active status, or effective dates (`Permission.MANAGE_LOCATIONS`).
- `DELETE /{ap_id}` — Soft-deactivates access point (`is_active = False`) preserving historical attendance integrity (`Permission.MANAGE_LOCATIONS`).

### 3.2 Employee Wi-Fi Probe Endpoint
- `POST /api/v1/employees/me/workplaces/verify-wifi` (`Permission.RECORD_PUNCH`)
  - Evaluates connected Wi-Fi BSSID against assigned workplace access points.
  - Returns `EmployeeWifiVerifyResponse` with `match_status` (`MATCHED`, `MISMATCHED`, `UNAVAILABLE`, `UNSUPPORTED`, `STALE`), `is_verified`, `matched_access_point_name`, and `applicable_fallback`.

### 3.3 Punch Ingestion API
- `POST /api/v1/attendance/punch`
  - Extended `PunchRequest` with `wifi_bssid`, `wifi_ssid`, and `wifi_signal_status`.
  - Authoritatively executes `evaluate_punch_policy` across all verification modes.
  - Enriches `AttendanceEvent.metadata_json` with `wifi_evidence`, `fallback_evidence`, `verification_flags`, and `verification_mode`.

---

## 4. Test Verification & Results

### 4.1 Automated Unit & Integration Tests
File: `tests/test_phase6_wifi_verification.py` (15 dedicated test cases):
- BSSID normalization and regex validation (`aa-bb-cc-dd-ee-ff` $\rightarrow$ `AA:BB:CC:DD:EE:FF`).
- Duplicate BSSID within same workplace rejection (`HTTP 409`).
- Soft deactivation preserving historical rows.
- Employee probe endpoint across `MATCHED`, `MISMATCHED`, `UNAVAILABLE`, `UNSUPPORTED`.
- `WIFI_ONLY` positive punch verification.
- Mismatched BSSID negative presence rejection (`HTTP 400`).
- Seamless `GPS_FALLBACK` execution inside PostGIS geofence.
- `SUPERVISOR_REVIEW` fallback routing to `PENDING_REVIEW`.
- `MANUAL_FALLBACK` authorized presence.
- Dual-factor `AND` guardrail strictly preventing fallback bypasses.
- Workplace-level `Location.wifi_config_override` precedence over tenant defaults.
- Admin access point CRUD and multi-tenant isolation.

### 4.2 Full Regression Suite
- **Full Backend Pytest Suite**: **315 / 315 tests passing (100%)**.
- **Ruff Linter**: `All checks passed! Zero warnings.`
- **Mypy Static Type Analysis**: `Success: no issues found in 79 source files.`

### 4.3 Live Supabase Database Verification & Synthetic E2E Test
Verified against live PostgreSQL + PostGIS on Supabase:
- **Migration Execution**: `alembic upgrade head` applied revision `c4d5e6f7a8b9`.
- **Live Test Execution**:
  - [x] Seeded synthetic Tenant, Users, Employee, Workplace Location & Workplace Assignment.
  - [x] Registered authorized Wi-Fi Access Point (`00:1A:2B:3C:4D:5E`).
  - [x] Activated Policy Version 1 (`mode=WIFI_ONLY`, `fallback=GPS_FALLBACK`).
  - [x] Verified employee Wi-Fi probe `MATCHED` on authorized router.
  - [x] Verified employee Wi-Fi probe `MISMATCHED` on rogue hotspot.
  - [x] Verified employee Wi-Fi probe `UNAVAILABLE` returning `GPS_FALLBACK`.
  - [x] Verified live punch accepted with `WIFI` verification mode and recorded BSSID.
  - [x] Verified rogue BSSID strictly rejected with `HTTP 400`.
  - [x] Verified Wi-Fi unavailable + GPS inside geofence accepted as `GPS_FALLBACK` via live PostGIS `ST_DWithin`.
  - [x] Verified Wi-Fi unavailable + GPS outside geofence strictly rejected with `HTTP 400`.
  - [x] Verified single-use UUID idempotency replay on live database.
  - [x] Executed isolated synthetic cleanup with 0 residual records.

---

## 5. Scope & Git Safety Confirmation

- **Backend-Only Scope**: Only Python backend services, routes, schemas, and migrations were modified.
- **Flutter Code Preserved**: 0 Flutter mobile files touched or modified.
- **Git Safety**: 0 commits, 0 tags, and 0 pushes made. All changes remain staged/unstaged on working branch `phase-06`.
- **Milestone 6.4.B Ready**: The backend API contracts, permissions, and database infrastructure are fully prepared for Flutter mobile integration in Milestone 6.4.B.

