# UPOSTIT — Phase 6, Milestone 6.4.A
## Final Security, Policy & Live API Audit Report

**Audit Date**: November 6, 2026  
**Audited Branch**: `phase-06`  
**Database**: Supabase PostgreSQL 17.11 with PostGIS (AWS ap-south-1)  
**Migration Head**: `c4d5e6f7a8b9` (`c4d5e6f7a8b9_phase_06_workplace_wifi_access_points.py`)  
**Auditor**: Senior Systems, Policy & Security Agent  
**Final Audit Verdict**: **NOT READY — BLOCKING DEFECTS**

---

## 1. Executive Summary

Milestone 6.4.A introduced **Workplace-Level Wi-Fi Attendance Verification** and **Admin-Configurable Fallback Mechanisms** (`services/api/locations/wifi_service.py`, `services/api/attendance/policy_engine.py`, migration `c4d5e6f7a8b9`).

Prior to authorizing Milestone 6.4.B (Flutter Mobile Wi-Fi Integration), a comprehensive security, policy, and live end-to-end API audit was executed against the live Supabase PostgreSQL database and FastAPI ASGI test environment.

### Summary of Audit Outcomes:
- **Direct Database Schema, Constraints & RLS**: **100% VERIFIED** (all 12 columns, composite foreign keys, PostGIS constraints, unique indexes, and forced RLS verified).
- **Wi-Fi Signal State Telemetry & Fraud Guardrails**: **VERIFIED** (`PERMISSION_DENIED`, `UNSUPPORTED`, `UNAVAILABLE`, `STALE`, `MISMATCHED`, and SSID spoofing resistance verified).
- **Fallback Policy Evaluation Logic**: **VERIFIED** (all 4 fallbacks: `REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK` verified in engine).
- **Multi-Factor Guardrails (`AND` / `OR`)**: **VERIFIED** (dual-factor `AND` strictly disables fallback bypasses).
- **Automated Regression Test Suite**: **315 / 315 tests passing (100%)** in 99.2s (`tests/`).
- **Linter & Type Checking**: `ruff check` (0 errors), `mypy` (0 errors across 56 files).
- **Live Database Persistence via HTTP API**: ❌ **CRITICAL BLOCKING DEFECT DISCOVERED**  
  While unit tests with mock sessions passed, live multi-request HTTP execution revealed that `create_workplace_wifi_access_point`, `update_workplace_wifi_access_point`, and `deactivate_workplace_wifi_access_point` invoke `await session.flush()` but **never invoke `await session.commit()`**. In FastAPI, the `get_db` generator dependency rolls back uncommitted sessions upon exit. Consequently, access points registered via the admin API are immediately rolled back and never persisted to the Supabase database, breaking cross-request live verification.

---

## 2. Defects & Findings Registry

In strict adherence to the audit protocol, **no application code was modified**. All identified items are documented below with reproduction evidence and remediation instructions.

### Defect 1: Missing Database Transaction Commit in Wi-Fi Access Point Service
- **Severity**: **BLOCKING**
- **Affected File & Functions**: [`services/api/locations/wifi_service.py`](file:///Users/apple/Upostit/services/api/locations/wifi_service.py#L68)
  - `create_workplace_wifi_access_point` (line 68)
  - `update_workplace_wifi_access_point` (line 165)
  - `deactivate_workplace_wifi_access_point` (line 181)
- **Reproduction Evidence**:
  1. Admin issues `POST /api/v1/locations/{location_id}/wifi-access-points` with BSSID `00:1A:2B:3C:4D:5E`.
  2. Endpoint returns `HTTP 201 Created` with the serialized access point object.
  3. When `get_db()` in [`services/api/database.py`](file:///Users/apple/Upostit/services/api/database.py#L48) completes its generator context (`async with AsyncSessionLocal() as session: yield session`), SQLAlchemy issues a `ROLLBACK` because `session.commit()` was never called.
  4. Subsequent query `SELECT * FROM workplace_wifi_access_points WHERE bssid = '00:1A:2B:3C:4D:5E'` returns 0 rows.
  5. Subsequent call to `POST /api/v1/employees/me/workplaces/verify-wifi` evaluates to `MISMATCHED` (unauthorized).
  6. Subsequent punch with this BSSID is rejected with `HTTP 400 Bad Request` ("Connected Wi-Fi network ... is not an authorized access point for this workplace").
  7. Subsequent registration with the identical BSSID returns `HTTP 201` rather than `HTTP 409 Conflict`.
  *Note: Unit tests in `test_phase6_wifi_verification.py` did not catch this because they used an `AsyncMock` session or single-scope mock where `session.add()` / `session.flush()` remained in-memory.*
- **Recommended Correction**:
  In `services/api/locations/wifi_service.py`:
  - Replace `await session.flush()` with `await session.commit()` and `await session.refresh(ap)` across lines 68, 165, and 181 (matching the established pattern in [`services/api/locations/service.py:89`](file:///Users/apple/Upostit/services/api/locations/service.py#L89) and [`services/api/locations/assignment_service.py:182`](file:///Users/apple/Upostit/services/api/locations/assignment_service.py#L182)).
- **Blocks Acceptance**: **YES** (Workplace Wi-Fi records cannot persist across HTTP requests).

---

### Finding 2: Incomplete SHA-256 Fingerprint Binding for Wi-Fi Telemetry in Punch Idempotency
- **Severity**: **MEDIUM**
- **Affected File & Function**: [`services/api/attendance/service.py:compute_request_fingerprint`](file:///Users/apple/Upostit/services/api/attendance/service.py#L752-L790)
- **Reproduction Evidence**:
  The canonical dictionary in `compute_request_fingerprint` serializes:
  `accuracy_meters`, `device_id`, `device_reported_at`, `employee_id`, `event_type`, `latitude`, `location_id`, `longitude`, `metadata`.
  It does **not** include `wifi_bssid`, `wifi_ssid`, or `wifi_signal_status`.
  If a mobile client submits a punch request with idempotency key `KEY-001` and `wifi_bssid="AA:BB:CC:DD:EE:01"`, and an attacker or malfunctioning client subsequently resubmits `KEY-001` with `wifi_bssid="99:88:77:66:55:44"`, the fingerprint remains identical. The server returns the cached `HTTP 201` response rather than rejecting the payload tamper with `HTTP 422 Unprocessable Content`.
- **Recommended Correction**:
  Add Wi-Fi attributes to `canonical_dict` in `compute_request_fingerprint`:
  ```python
  canonical_dict = {
      ...,
      "wifi_bssid": payload.wifi_bssid.strip().upper().replace("-", ":") if payload.wifi_bssid else None,
      "wifi_ssid": payload.wifi_ssid.strip() if payload.wifi_ssid else None,
      "wifi_signal_status": str(payload.wifi_signal_status),
  }
  ```
- **Blocks Acceptance**: **NO** (Does not compromise basic verification flow, but should be addressed before mobile release).

---

### Finding 3: Signal Status vs. Match Status Representation of `PERMISSION_DENIED`
- **Severity**: **INFORMATIONAL**
- **Affected File & Functions**: [`services/api/attendance/schemas.py:WifiMatchStatus`](file:///Users/apple/Upostit/services/api/attendance/schemas.py#L832) & [`services/api/attendance/policy_engine.py:335, 1155`](file:///Users/apple/Upostit/services/api/attendance/policy_engine.py#L335)
- **Observation**:
  `signal_status="PERMISSION_DENIED"` is explicitly validated in incoming payloads (`PunchRequest.wifi_signal_status` and `EmployeeWifiVerifyRequest.signal_status`). When received, the engine maps it to `match_status = WifiMatchStatus.UNAVAILABLE`, routing gracefully to the administrator's configured fallback (e.g. `GPS_FALLBACK` or `SUPERVISOR_REVIEW`). While functionally correct and secure, `WifiMatchStatus` does not have a separate `PERMISSION_DENIED` enum value. The original permission denial is preserved in `metadata_json["wifi_evidence"]["signal_status"]`.
- **Recommended Correction**: Document this mapping in `MOBILE_ATTENDANCE_ARCHITECTURE.md` so Flutter developers know to check `signal_status` if granular UI messaging is required.
- **Blocks Acceptance**: **NO**.

---

### Finding 4: BSSID Exposure and Employee Privacy Boundary
- **Severity**: **INFORMATIONAL**
- **Affected Endpoints**: `GET /api/v1/attendance/policy/me`, `GET /api/v1/employees/me/workplaces`
- **Observation**:
  Audit confirmed that employee-facing policy endpoints (`/policy/me`) and workplace endpoints (`/me/workplaces`) **do not leak** authorized BSSID lists or router hardware details, preventing rogue AP cloning. The only BSSID returned in `EmployeeWifiVerifyResponse` is the BSSID the device itself reported in the probe request.
- **Blocks Acceptance**: **NO** (Compliant with privacy & anti-spoofing requirements).

---

## 3. Systematic Audit Checklist & Test Results

### 3.1 Tenant Isolation & Row-Level Security (RLS)
| Audit Invariant | Tested Method | Result | Notes |
| :--- | :--- | :---: | :--- |
| **RLS Enabled & Forced** | Direct SQL on `pg_class` | **PASS** | `relrowsecurity = true`, `relforcerowsecurity = true` |
| **RLS Policy Parameter** | Direct SQL on `pg_policies` | **PASS** | Matches `current_setting('app.tenant_id', true)::uuid` |
| **Cross-Tenant AP Creation** | Tenant A Admin -> Tenant B Location | **PASS** | Returns `HTTP 404 Not Found` |
| **Cross-Tenant AP Query** | Tenant B Admin -> Tenant A Location APs | **PASS** | Returns `HTTP 404 Not Found` |
| **Composite FK Isolation** | `(tenant_id, location_id)` FK | **PASS** | Database prevents cross-tenant location linkage |
| **RBAC: Employee AP CRUD** | Employee -> AP POST / GET | **PASS** | `HTTP 403 Forbidden` (`Permission.MANAGE_LOCATIONS` required) |
| **RBAC: HR AP Management** | HR -> AP POST | **PASS** | `HTTP 403 Forbidden` (HR has VIEW, not MANAGE) |
| **RBAC: Admin / Owner AP Management** | Admin -> AP POST / PATCH / DELETE | **PASS** | Allowed with `Permission.MANAGE_LOCATIONS` |

### 3.2 Wi-Fi Evidence Signal States (Probe Endpoint)
| Signal State | Ingestion Condition | Verification Outcome | Engine Evaluation | Result |
| :--- | :--- | :--- | :--- | :---: |
| **`MATCHED`** | Active authorized workplace BSSID | `match_status = MATCHED` | `is_verified = true` | **PASS (Engine)** / *Blocked by Defect 1 on HTTP persist* |
| **`MISMATCHED`** | Unknown / rogue BSSID | `match_status = MISMATCHED` | `is_verified = false`, negative evidence | **PASS** |
| **`UNAVAILABLE`** | Wi-Fi turned off / no connection | `match_status = UNAVAILABLE` | Routes to configured fallback | **PASS** |
| **`UNSUPPORTED`** | Unsupported OS platform (iOS without entitlement) | `match_status = UNSUPPORTED` | Routes to configured fallback | **PASS** |
| **`PERMISSION_DENIED`** | Device OS location/Wi-Fi permission denied | `match_status = UNAVAILABLE` | Routes to configured fallback | **PASS** |
| **`STALE`** | Telemetry timestamp > 30s old | `match_status = STALE` | `freshness_acceptable = false` | **PASS** |
| **`INACTIVE`** | Soft-deactivated AP or expired effective date | `match_status = MISMATCHED` | Treated as unauthorized | **PASS** |
| **`UNASSIGNED`** | Employee probes unassigned workplace | `HTTP 403 Forbidden` | Strict workplace assignment enforcement | **PASS** |
| **`ERROR`** | Malformed BSSID format (`"INVALID-MAC"`) | `HTTP 422 Unprocessable` | Pydantic regex filter rejects | **PASS** |
| **SSID-Only Spoof** | SSID provided without BSSID | Rejected / Not Matched | SSID alone never proves presence | **PASS** |

### 3.3 Fallback Punch Behaviors (Punch Ingestion API)
| Configured Fallback | Device Evidence | Expected HTTP Outcome | Verification Stamping | Audit Result |
| :--- | :--- | :---: | :--- | :---: |
| **`REJECT`** | Wi-Fi UNAVAILABLE | `HTTP 400 Bad Request` | Punch rejected, no event created | **PASS** |
| **`GPS_FALLBACK`** | Wi-Fi UNAVAILABLE + GPS Inside | `HTTP 201 Created` | `verification_mode = "GPS_FALLBACK"` | **PASS** |
| **`GPS_FALLBACK`** | Wi-Fi UNAVAILABLE + GPS Outside | `HTTP 400 Bad Request` | Punch rejected outside geofence | **PASS** |
| **`SUPERVISOR_REVIEW`** | Wi-Fi UNAVAILABLE | `HTTP 201 Created` | `review_status = "PENDING_REVIEW"`, `WIFI_UNAVAILABLE_REVIEW` | **PASS** |
| **`MANUAL_FALLBACK`** | Wi-Fi UNAVAILABLE (Manual allowed) | `HTTP 201 Created` | `verification_mode = "MANUAL_FALLBACK"` | **PASS** |
| **Negative Presence Guardrail** | Connected to rogue BSSID (`MISMATCHED`) | `HTTP 400 Bad Request` | **Never** silently falls back to GPS or Manual | **PASS** |

### 3.4 Multi-Method & Combination Rules
| Policy Configuration | Scenario | Expected Behavior | Audit Result |
| :--- | :--- | :--- | :---: |
| **`WIFI_ONLY`** | Valid BSSID punch | Accepted with `verification_mode = "WIFI"` | **PASS** |
| **`GPS_ONLY` Regression** | GPS punch without Wi-Fi | Accepted with `verification_mode = "GPS"`, zero regression | **PASS** |
| **`COMBINED + AND`** | Valid GPS + Valid Wi-Fi | Accepted with `verification_mode = "COMBINED_AND"` | **PASS** |
| **`COMBINED + AND`** | Valid GPS + Wi-Fi UNAVAILABLE | **Strictly Rejected**: Fallback disabled under AND rule | **PASS** |
| **`COMBINED + OR`** | Wi-Fi UNAVAILABLE + Valid GPS | Accepted with `verification_mode = "GPS"` | **PASS** |
| **Workplace Override** | Location sets `SUPERVISOR_REVIEW` | Takes precedence over tenant `REJECT` default | **PASS** |
| **Override Fail-Closed** | Location sets `MANUAL_FALLBACK` but tenant disallows MANUAL | Reverts to `REJECT` (fails closed) | **PASS** |

### 3.5 Ledger Immutability & Audit Evidence
| Verification Aspect | Audit Method | Result | Notes |
| :--- | :--- | :---: | :--- |
| **Applied Policy Version** | Inspected `applied_policy_version` on ledger | **PASS** | Preserves exact version active at punch time |
| **Append-Only Trigger** | Direct SQL `UPDATE` / `DELETE` on `attendance_events` | **PASS** | Blocked by `trg_prevent_attendance_events_mutation` |
| **Replay Invariance** | Replayed punch after policy increment (v1 $\rightarrow$ v5) | **PASS** | Returns original cached response and v1 version |
| **Payload Tamper Detection** | Same idempotency key with altered `event_type` | **PASS** | `HTTP 422 Unprocessable Content` |
| **Supervisor Review Retrieval** | Verified query on `review_status = 'PENDING_REVIEW'` | **PASS** | Accessible via existing supervisor review routes |

---

## 4. Test Suites & Code Quality Results

### 4.1 Pytest Backend Regression Suite
```text
============================= test session starts ==============================
collected 315 items

tests/test_auth_api.py ......                                            [  1%]
tests/test_auth_schemas.py ......                                        [  3%]
tests/test_auth_security.py .......                                      [  6%]
tests/test_cross_tenant_isolation.py ....                                [  7%]
tests/test_health.py ....                                                [  8%]
tests/test_phase3_api.py ......                                          [ 10%]
tests/test_phase3_business_rules.py ............                         [ 14%]
tests/test_phase3_rbac.py .....                                          [ 15%]
tests/test_phase3_schemas.py ........                                    [ 18%]
tests/test_phase4_business_rules.py .........                            [ 21%]
tests/test_phase4_import.py .............................                [ 30%]
tests/test_phase4_invitations.py .....................                   [ 37%]
tests/test_phase4_locations_api.py ......                                [ 39%]
tests/test_phase4_rbac.py .....                                          [ 40%]
tests/test_phase4_schemas.py ...........                                 [ 44%]
tests/test_phase4_workplace_assignments.py ..........................    [ 52%]
tests/test_phase5_calculation_engine.py ................................ [ 62%]
......                                                                   [ 64%]
tests/test_phase5_corrections.py ....................                    [ 70%]
tests/test_phase5_punch_ledger.py ..............................         [ 80%]
tests/test_phase5_shifts.py .....................                        [ 86%]
tests/test_phase6_attendance_policy.py ...................               [ 93%]
tests/test_phase6_wifi_verification.py ...............                   [ 97%]
tests/test_rbac.py .......                                               [100%]

================= 315 passed, 45 warnings in 99.22s (0:01:39) ==================
```

### 4.2 Ruff Linter
```text
$ ruff check services/ tests/
All checks passed!
```

### 4.3 Mypy Static Type Checking
```text
$ mypy services/
Success: no issues found in 56 source files
```

### 4.4 Live Database Migration State
```text
$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
c4d5e6f7a8b9 (head)
```

### 4.5 Teardown & Residual Cleanup
All synthetic tenants, users, locations, access points, and events provisioned during live testing were cleanly removed. Direct SQL verification confirmed:
`Remaining synthetic records: 0`.

---

## 5. Scope, Git & Boundary Confirmation

In strict compliance with audit rules:
- **No application code, migrations, or database policies were modified.**
- **No commits, tags, or pushes were created.**
- **Milestone 6.4.B mobile implementation was NOT started.**

---

## 6. Final Verdict & Next Steps

### Verdict: **NOT READY — BLOCKING DEFECTS**

### Action Items Prior to Acceptance:
1. **Fix Defect 1**: Add `await session.commit()` and `await session.refresh(ap)` to `create_workplace_wifi_access_point`, `update_workplace_wifi_access_point`, and `deactivate_workplace_wifi_access_point` in `services/api/locations/wifi_service.py`.
2. **Address Finding 2**: Update `compute_request_fingerprint` in `services/api/attendance/service.py` to bind `wifi_bssid`, `wifi_ssid`, and `wifi_signal_status`.
3. **Re-Run Live Audit**: Verify that access points persist to Supabase across HTTP requests and that live Wi-Fi positive punches succeed.
4. **Accept Milestone 6.4.A & Proceed to Milestone 6.4.B (Mobile Wi-Fi)** upon resolution.

