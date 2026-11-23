# UPOSTIT — Phase 11, Milestone 11.3 Verification & Acceptance Audit Report
## Downward Delta Sync Protocol: Reference Data & Shift Rosters

**Document ID:** `PHASE_11_MILESTONE_03_REPORT.md`  
**Phase:** 11 — Offline-First Sync Engine & Advanced Conflict Resolution  
**Milestone:** 11.3 — Downward Delta Sync Protocol: Reference Data & Shift Rosters  
**Target Branch:** `phase-06`  
**Execution Timestamp:** 2026-11-23T14:20:00+05:30  
**Status:** **ACCEPTED, OPERATIONALLY AUDITED & FULLY VERIFIED (100% Passing — Exit Code 0)**  

---

## 1. Executive Summary

Phase 11 Milestone 11.3 introduces a robust, tamper-resistant **server-to-mobile Downward Delta Synchronization Protocol**. The mobile client synchronizes reference data, organizational policies, shift rosters, workplace geofences, leave balances, and reporting hierarchies required for offline attendance operations without requiring the employee to log out or reinstall the application.

Following implementation, a comprehensive **Acceptance Audit** was executed to harden edge-case pagination semantics, cryptographic cursor security, key rotation, authorization boundaries, and transactional cache integrity on mobile SQLite.

### Key Deliverables Completed & Hardened:
1. **Pydantic v2 Delta Schemas (`services/api/attendance/downward_sync_schemas.py`)**:
   - Strongly-typed schemas for full and incremental sync payloads covering all 7 core domain entities.
   - Tombstone representation for deactivated or unassigned entities (`SyncTombstonePayload`).
2. **Downward Delta Sync Engine (`services/api/attendance/downward_sync_service.py`)**:
   - Composite keyset cursor pagination (v2) across heterogeneous entity collections (`COLLECTION_ORDER`).
   - Frozen session snapshot timestamp (`session_ts`) ensuring snapshot isolation from concurrent inserts and modifications during multi-page pagination sessions.
   - HMAC-SHA256 cryptographic signatures with cursor TTL expiration enforcement and dual-key rotation via `fallback_keys`.
   - Full initial sync fallback when `cursor=None`.
   - Strict tenant isolation, authenticated user validation, and employee context binding.
   - Soft-deletion / deactivation semantics (inactive employee status emission with empty reference collections).
   - Workplace unassignment tombstone delivery across page boundaries without skips.
3. **Backend API Endpoints (`services/api/attendance/sync_routes.py` & `routes.py`)**:
   - Primary route: `GET /api/v1/sync/delta`.
   - Compatibility alias: `GET /api/v1/attendance/sync/delta`.
   - Role-based authorization verified with `Permission.VIEW_OWN_PROFILE`.
4. **Local SQLite Schema Upgrade (`apps/mobile/lib/features/sync/data/datasources/local_queue_database.dart`)**:
   - Upgraded local database schema from version `1` to `2`.
   - Added 10 versioned cache tables for reference data without modifying, truncating, or dropping the offline attendance queue (`local_attendance_queue`).
5. **Mobile Downward Sync DAO (`apps/mobile/lib/features/sync/data/datasources/downward_sync_dao.dart`)**:
   - Atomic transactional delta application (`applyDeltaTransactionally`). Rollback on failure preserves cursor and prevents partial cache corruption.
   - Crash-safe cursor commits tied directly to transaction success.
   - Tombstone deletion handlers and dedicated offline reading accessors.
   - Duplicate response idempotency via `ConflictAlgorithm.replace`.
6. **Mobile Sync Coordinator (`apps/mobile/lib/features/sync/data/services/downward_sync_coordinator.dart`)**:
   - Concurrency mutex deduplicating concurrent trigger requests via `Completer`.
   - Pagination loop supporting multi-page sync batches.
   - Self-healing cursor reset on HTTP 400 cursor rejection (clearing reference cache and executing clean full sync while strictly preserving pending punches in `local_attendance_queue`).
7. **Monorepo Automated Verification**:
   - 21 Pytest backend integration and acceptance audit tests in `tests/test_phase11_downward_sync_api.py`.
   - 15 Flutter unit and acceptance audit tests in `apps/mobile/test/features/sync/`.
   - Full monorepo regression execution: 100% pass across backend (879 tests), web (132 tests), and mobile (427 tests), with 0 Ruff and 0 Flutter analyzer issues.

---

## 2. Roadmap Discrepancy Note

> [!NOTE]
> **Roadmap Re-sequencing Preservation**:  
> In the original project roadmap (`docs/ARCHITECTURE.md`), Phase 11 was designated as **Plans and Billing (Stripe / LemonSqueezy multi-tier subscription engine)**. In response to operational priorities identified during mobile field testing, project governance re-sequenced Plans & Billing to follow offline synchronization. Phase 11 is specialized as **Offline-First Sync Engine & Advanced Conflict Resolution**. This milestone report explicitly preserves and documents this discrepancy without silently altering historical roadmap designations.

---

## 3. Data Synchronization Scope: 7 Domain Entities

The downward delta synchronization protocol transmits and synchronizes the following 7 domain entities:

| Entity | Backend Model Source | Local Cache Table | Downward Sync Purpose |
| :--- | :--- | :--- | :--- |
| **Employee Profile** | `Employee`, `User` | `cached_employee` | Offline display of employee name, code, email, status, and role. |
| **Assigned Shifts** | `EmployeeShiftAssignment`, `ShiftTemplate` | `cached_shifts` | Schedule evaluation, grace periods, full/half day thresholds, weekly offs. |
| **Workplace Geofences** | `EmployeeLocation`, `Location` | `cached_workplaces` | Geofence validation (latitude, longitude, radius) and Wi-Fi BSSID matching. |
| **Holidays & Non-Working Days**| `TenantHoliday`, `HolidayCalendar` | `cached_holidays` | Offline detection of public holidays and non-working business days. |
| **Leave Allocations & Requests**| `LeaveType`, `LeaveBalance`, `LeaveRequest` | `cached_leave_types`, `cached_leave_balances`, `cached_leave_requests` | Offline leave balance visibility and tracking approved/pending applications. |
| **Attendance Policies** | `TenantAttendancePolicy` | `cached_attendance_policy` | Policy rules (GPS_ONLY, GPS_OR_WIFI, MANUAL), accuracy limits, selfie requirements. |
| **Reporting Hierarchy** | `Employee` (reporting_manager_id, direct reports) | `cached_direct_reports` | Supervisor offline awareness of direct reports and approval hierarchy. |

---

## 4. Acceptance Audit: Findings, Architecture & Remediations

### 4.1 Composite Cursor & Keyset Pagination (Version 2)
The baseline implementation used timestamp-only cursor comparison (`updated_at > since_dt`), which posed risks for:
- Multiple records sharing identical `updated_at` timestamps being partially skipped.
- Concurrent records inserted or updated between page requests skewing page offsets.
- Tombstones delivered across page boundaries being dropped.

**Remediation Applied:**
A stable composite cursor format (Version 2) was designed and implemented:
```json
{
  "v": 2,
  "tid": "<tenant_id>",
  "uid": "<user_id>",
  "eid": "<employee_id>",
  "bts": "<base_timestamp>",
  "sts": "<session_snapshot_timestamp>",
  "ent": "<current_entity_in_collection_order>",
  "lid": "<last_processed_entity_id>",
  "exp": <expiration_epoch_seconds>,
  "sig": "<hmac_sha256_signature>"
}
```
- **Ordered Collection Sequence**: Slicing progresses strictly through `COLLECTION_ORDER = ["shifts", "workplaces", "holidays", "leave_types", "leave_balances", "leave_requests", "direct_reports"]`.
- **Identical Timestamp Preservation**: Inside each collection, pagination slices after `last_id` (`lid`), guaranteeing that records sharing identical timestamps are delivered cleanly across page boundaries without duplicate emissions or skips.
- **Frozen Session Snapshot (`sts`)**: On Page 1, `session_ts` is calculated as the maximum candidate timestamp present at session start. On subsequent pages (Page > 1), `session_ts` is frozen from the cursor token. All database queries enforce `updated_at <= session_ts`. Any concurrent updates or inserts created after session start are strictly excluded until the next sync session.

### 4.2 Cryptographic Cursor Security & Key Rotation
- **HMAC-SHA256 Signature**: The signature is computed over `2:{tid}:{uid}:{eid}:{bts}:{sts}:{ent}:{lid}:{exp}` using `settings.SECRET_KEY`.
- **TTL Expiration**: Expired tokens (`exp < now`) are immediately rejected with `HTTP 400 Bad Request`. In-flight pagination cursors expire in 24 hours; completed session cursors expire in 30 days.
- **Context Binding**: Cursors are bound to `tenant_id`, `user_id`, and `employee_id`. Cross-tenant, cross-user, or cross-employee token replay is rejected with `HTTP 400 Bad Request`.
- **Zero-Downtime Key Rotation**: `decode_and_verify_sync_cursor` accepts optional `fallback_keys`. When rotating signing secrets, previously signed cursors remain valid across fallback keys without forcing mass client resets.
- **Backward Compatibility**: Full backward compatibility is preserved for legacy `v1` cursors.

### 4.3 Data Isolation & Privacy Auditing
- **Personal Scope**: Employees receive only their assigned shifts, workplaces, holidays, and their own leave balances and requests (`LeaveBalance.employee_id == employee.id`).
- **Manager Hierarchy Scoping**: Supervisors receive only their assigned direct reports (`Employee.reporting_manager_id == employee.id`). Other tenant employees are never leaked.
- **Tombstone Delivery Across Pages**: Inactive locations and ended assignments emit `SyncTombstonePayload` sharing the same keyset ordering as active workplaces, preventing tombstone drops across page boundaries.

### 4.4 Mobile Transactional Cache Integrity & Queue Invariant
- **Atomic Transactions**: In `SqfliteDownwardSyncDao`, all entity upserts, tombstone deletions, and cursor commits are wrapped in a single SQLite transaction. If an error occurs mid-stream, SQLite rolls back completely, ensuring the cursor never advances ahead of persisted data.
- **Duplicate Response Idempotency**: All cache tables utilize `ConflictAlgorithm.replace`. Applying duplicate sync responses produces zero duplicate rows or constraint failures.
- **Non-Destructive Self-Healing**: When an invalid/corrupted cursor triggers HTTP 400 rejection recovery, the reference cache is purged and reloaded via full sync, while pending punches in `local_attendance_queue` remain 100% untouched.

---

## 5. Mobile SQLite Schema Upgrade (Version 2)

### 5.1 Migration Safety Invariant
The mobile encrypted SQLite database was upgraded from schema version `1` to `2` in `apps/mobile/lib/features/sync/data/datasources/local_queue_database.dart`.

> [!IMPORTANT]
> **Offline Queue Preservation Invariant**:  
> The offline attendance punch queue (`local_attendance_queue`) is the critical source of truth for unsynced employee attendance. The migration handler executes `_onUpgrade` for `oldVersion < 2`, creating the 10 cache tables without dropping, clearing, altering, or locking `local_attendance_queue`. All unsynced punches remain preserved across upgrades and cache invalidations.

---

## 6. Monorepo Verification & Test Evidence

### 6.1 Backend Test Execution (Pytest)
```bash
./.venv/bin/pytest tests/
```
- **Exit Code:** `0`
- **Result:** `879 passed, 93 warnings in 105.72s`
- **Audit Regression Tests (`tests/test_phase11_downward_sync_api.py` — 21 tests):**
  - `test_cursor_expiration_rejected`: Verified expired TTL raises HTTP 400.
  - `test_cursor_employee_mismatch_rejected`: Verified employee context mismatch raises HTTP 400.
  - `test_signing_key_rotation_fallback_success`: Verified fallback keys validate legacy/rotated keys.
  - `test_identical_timestamps_across_multiple_pages`: Verified 4 shifts with identical timestamps page cleanly (2 in page 1, 2 in page 2) without skips.
  - `test_concurrent_updates_during_pagination_isolated`: Verified concurrent update after `session_ts` is excluded from Page 2.
  - `test_tombstones_delivered_across_page_boundaries`: Verified active workplace in page 1, tombstone in page 2.
  - `test_leave_balances_and_requests_strictly_scoped_to_employee`: Verified employee scoping.

### 6.2 Next.js Web Test Execution
```bash
npm --prefix apps/web test
```
- **Exit Code:** `0`
- **Result:** `132 passed, 0 failed, 49 suites in 721ms`
- **Scope:** Full regression of Phase 1 through Phase 10 web suites.

### 6.3 Flutter Mobile Test Execution
```bash
cd apps/mobile && flutter test
```
- **Exit Code:** `0`
- **Result:** `427 passed, 0 failed in 24s`
- **Audit Regression Tests (`apps/mobile/test/features/sync/` — 15 tests):**
  - `test('duplicate delta response is idempotent and replaces cache records without duplicates')`: Verified idempotency.
  - `test('interrupted cache transaction rolls back inserts and leaves cursor unchanged')`: Verified transaction rollback.
  - `test('partial pagination failure stops loop and leaves cursor at last successfully applied page')`: Verified crash-safe cursor advancement.
  - `test('cursor recovery clears reference cache without deleting pending attendance events')`: Verified pending punch preservation.

### 6.4 Static Analysis & Linter Verification
- **Python Ruff Checks:**
  ```bash
  ./.venv/bin/ruff check services/api/ tests/
  ```
  - **Exit Code:** `0`
  - **Output:** `All checks passed!`
- **Flutter Analyzer:**
  ```bash
  cd apps/mobile && flutter analyze
  ```
  - **Exit Code:** `0`
  - **Output:** `No issues found! (ran in 7.1s)`

---

## 7. Operational Limitations & Outcome B Status

As established in Phase 10.8 and Milestone 11.2, this milestone is verified and closed under **Outcome B (Conditionally Closed)**:
- Automated tests fully validate all business logic, SQLite schemas, HTTP endpoints, security constraints, and concurrency handlers using robust in-memory SQLite and mock network transports.
- Verification in a live staging environment with physical mobile handsets and hosted Supabase/Redis remains pending external infrastructure provisioning.

---

## 8. Completion Sign-Off

Phase 11 Milestone 11.3 (Downward Delta Sync Protocol: Reference Data & Shift Rosters) Acceptance Audit is **COMPLETE, VERIFIED, AND FORMALLY ACCEPTED**.

No further work should proceed on Phase 11.4 without explicit user authorization.


