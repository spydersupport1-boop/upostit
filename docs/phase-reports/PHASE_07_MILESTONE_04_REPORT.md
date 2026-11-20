# UPOSTIT — Phase 7.4 Implementation Report: HR Fraud Review Queue, Decision Workflows & Audit Ledger

**Project:** UPOSTIT Workforce Attendance SaaS  
**Repository:** `/Users/apple/Upostit`  
**Branch:** `phase-06`  
**Milestone:** 7.4 — HR Fraud Review Queue, Decision Workflows & Audit Ledger  
**Status:** Completed & Validated  
**Date:** November 19, 2026  

---

## 1. Executive Summary

Milestone 7.4 delivers the backend-authoritative Human Resources (HR) and Administrator fraud adjudication subsystem within the UPOSTIT Workforce Attendance SaaS platform.

Building on the foundation of device hardware binding (Milestone 7.1), spatial spoofing and velocity telemetry (Milestone 7.2), and the deterministic risk-scoring engine (Milestone 7.3), Milestone 7.4 provides the operational tools and immutable audit structures required to review, inspect, and adjudicate suspicious attendance punches.

Authorized supervisors can inspect comprehensive forensic evidence (including employee profile, shift context, location coordinates, geofence status, device telemetry, mock indicators, clock drift, velocity, rule flags, and historical decisions), and issue authoritative decisions (`APPROVED` or `REJECTED`) with a mandatory reviewer reason.

Decisions are immutably captured in the newly created `fraud_reviews` audit ledger. Approval reconciles the punch into normal shift calculation, while rejection excludes the fraudulent punch from daily attendance timeline intervals, all without modifying the immutable raw attendance event ledger. Strict self-review prohibitions prevent any employee from adjudicating their own reviews.

---

## 2. Database Schema & Migration Architecture

### 2.1 Database Migration
- **Migration Script:** `database/migrations/versions/d6e7f8a9b0c1_phase_07_fraud_reviews.py`
- **Revision ID:** `d6e7f8a9b0c1`
- **Down Revision:** `c5d6e7f8a9b0` (Phase 7.3 fraud rules and flags)
- **Validation:** Both offline SQL upgrade and downgrade scripts were generated and verified.

### 2.2 Table: `fraud_reviews`
Maintains an immutable, append-only forensic audit ledger of all human administrative review decisions on flagged attendance events:

| Column | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, `gen_random_uuid()` | Unique review decision identifier |
| `tenant_id` | `UUID` | FK `tenants.id` ON DELETE RESTRICT | Multi-tenant organization reference |
| `attendance_event_id` | `UUID` | Composite FK `(tenant_id, attendance_events.id)` ON DELETE CASCADE | Target attendance punch event |
| `reviewer_user_id` | `UUID` | Composite FK `(tenant_id, users.id)` ON DELETE RESTRICT | Authenticated user issuing decision |
| `reviewer_role` | `VARCHAR(32)` | NOT NULL | User role at adjudication time |
| `decision` | `VARCHAR(20)` | NOT NULL, CHECK `IN ('APPROVED', 'REJECTED')` | Adjudication outcome |
| `reason` | `TEXT` | NOT NULL, CHECK `length(trim(reason)) >= 3` | Mandatory rationale provided by reviewer |
| `notes` | `TEXT` | Nullable | Optional secondary notes |
| `metadata_json` | `JSONB` | DEFAULT `'{}'`, NOT NULL | Arbitrary operational audit context |
| `decided_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Exact adjudication timestamp (UTC) |
| `created_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Record creation timestamp (UTC) |

### 2.3 Row-Level Security & Indexes
- **RLS Enabled & Forced:** `ALTER TABLE fraud_reviews FORCE ROW LEVEL SECURITY;`
- **Isolation Policy:** Enforces `tenant_id = current_setting('app.tenant_id', true)::uuid` on all `SELECT`, `INSERT`, `UPDATE`, `DELETE` operations.
- **Indexes:**
  - `ix_fraud_reviews_tenant_event`: `(tenant_id, attendance_event_id)`
  - `ix_fraud_reviews_tenant_reviewer`: `(tenant_id, reviewer_user_id)`
  - `ix_fraud_reviews_tenant_decision`: `(tenant_id, decision)`
  - `ix_fraud_reviews_tenant_decided`: `(tenant_id, decided_at)`

---

## 3. RBAC & Organizational Hierarchy Permissions

In accordance with UPOSTIT security architecture, granular permissions were introduced in `services/api/auth/permissions.py`:

- `Permission.REVIEW_FRAUD_EVENTS = "review_fraud_events"`: Permission to approve or reject flagged attendance punches.
- `Permission.VIEW_FRAUD_REVIEWS = "view_fraud_reviews"`: Permission to inspect fraud evidence details and decision histories.

### Role Authorization Matrix:

| Role | `VIEW_FRAUD_FLAGS` | `VIEW_FRAUD_REVIEWS` | `REVIEW_FRAUD_EVENTS` | Scope of Visibility |
| :--- | :---: | :---: | :---: | :--- |
| **Owner** | Yes | Yes | Yes | Entire tenant organization |
| **Admin** | Yes | Yes | Yes | Entire tenant organization |
| **HR** | Yes | Yes | Yes | Entire tenant organization |
| **Manager** | Yes | Yes | **No** (403 Forbidden) | Limited to direct reports & same department |
| **Employee**| **No** (403) | **No** (403) | **No** (403) | Denied by default |

### Manager Visibility & Self-Review Controls:
1. **Manager Visibility Enforcement:** When a `MANAGER` attempts `GET /api/v1/fraud/events/{id}/review`, the service resolves the manager's employee profile and confirms that the event's employee is either a direct report (`reporting_manager_id == manager.id`) or shares the same department (`department_id == manager.department_id`). Unrelated employees return `HTTP 403 Forbidden`.
2. **Strict Self-Review Prohibition:** Reviewers cannot adjudicate their own attendance records. If the reviewer's authenticated user account is linked to the employee whose attendance was flagged (`reviewer_emp.id == event.employee_id`), the decision endpoint rejects the request with `HTTP 403 Forbidden` ("Self-review prohibited: Users cannot adjudicate their own attendance fraud reviews").

---

## 4. Business Logic & Recalculation Integration

### 4.1 Review Detail Aggregation (`review_service.get_fraud_event_review_detail`)
Constructs an exhaustive inspection payload combining:
- **Employee Identity:** Name, employee code, department name.
- **Event Metadata:** Timestamp, event type (`CHECK_IN`, `CHECK_OUT`), source (`MOBILE`), verification status.
- **Location Evidence:** Workplace geofence match, distance in meters, GPS accuracy, mock location sensor indicator.
- **Device Telemetry:** Platform, device model, OS version, application version, binding status.
- **Shift Details:** Assigned shift template name and scheduled effective range.
- **Forensic Signals:** Ordered list of all immutable `FraudFlag` records triggered by the punch.
- **Review History:** Complete chronology of prior human decisions, reviewer identities, and reasons.

### 4.2 Atomic Decision & Attendance Recalculation (`review_service.adjudicate_fraud_event`)
Adjudication operates within an atomic database transaction:
1. **Row Locking:** Locks the target `AttendanceEvent` record with `with_for_update()` to prevent race conditions.
2. **Immutable Audit Insertion:** Inserts a new `FraudReview` record. Re-adjudications are appended to the ledger, guaranteeing complete non-destructive audit history.
3. **Status Update:** Updates `AttendanceEvent.review_status` to `"APPROVED"` or `"REJECTED"`.
4. **Deterministic Daily Recalculation:** Resolves shift start date using `determine_shift_date_for_punch` and triggers `recalculate_attendance_day`:
   - When **`APPROVED`**: Event is accepted into active timeline; suspicious anomalies are cleared from derived day projections.
   - When **`REJECTED`**: `resolve_active_timeline` (`if event.review_status == "REJECTED": continue`) automatically omits the punch, immediately recalculating total working minutes and marking incomplete/missing punches where applicable.

---

## 5. API Endpoints Reference

### 5.1 `GET /api/v1/fraud/flags` (Review Queue Filtering)
Retrieves forensic fraud flags with expanded filtering capabilities:
- `review_status`: Filters by event review status (`PENDING_REVIEW`, `APPROVED`, `REJECTED`).
- `risk_category`: Filters by deterministic risk classification (`NORMAL`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `REQUIRES_REVIEW`).
- `min_risk_score` / `max_risk_score`: Numeric range filtering ($0 \dots 100$).
- `department_id`: Filters flags by employee departmental affiliation.
- `severity`, `signal_code`, `employee_id`, `attendance_event_id`, `start_date`, `end_date`, `limit`, `offset`.

### 5.2 `GET /api/v1/fraud/events/{event_id}/review`
Returns comprehensive forensic inspection data for an attendance event.
- **Permissions:** `VIEW_FRAUD_REVIEWS` (Owner, Admin, HR, Manager with reporting-line check).

### 5.3 `POST /api/v1/fraud/events/{event_id}/decision`
Submits an administrative adjudication decision.
- **Permissions:** `REVIEW_FRAUD_EVENTS` (Owner, Admin, HR).
- **Request Body:**
  ```json
  {
    "decision": "APPROVED",
    "reason": "Verified off-site client visit with field supervisor.",
    "notes": "Remote punch authorized via phone verification.",
    "metadata": {"field_call_verified": true}
  }
  ```
- **Responses:**
  - `200 OK`: Decision applied, audit record created, and attendance day recalculated.
  - `403 Forbidden`: Insufficient role permissions or self-review violation.
  - `404 Not Found`: Event does not exist in tenant scope.
  - `422 Unprocessable Content`: Reason $<3$ characters or decision invalid.

---

## 6. Automated Verification & Test Results

A comprehensive automated test suite (`tests/test_phase7_fraud_review_workflow.py`) was created, covering all service and API route workflows:

1. **Review Detail Retrieval:** Admin/HR access, 404 for missing events, manager direct report access, manager departmental access, manager forbidden access for unrelated employees, manager without profile check.
2. **Adjudication Decisions:** Admin/HR approval, Admin/HR rejection, self-review prohibition, manager rejection (403), short reason validation (422), invalid decision validation (422), non-existent event (404), repeat re-adjudication audit preservation.
3. **Queue Filters:** Review status, risk category, risk score boundaries, departmental filtering.
4. **Cross-Tenant Security:** Cross-tenant review detail access rejection (404), cross-tenant decision submission rejection (404).

### Test Suite Execution Summary:
- **Phase 7.4 Dedicated Suite:** `pytest tests/test_phase7_fraud_review_workflow.py` -> **20 passed in 2.39s**.
- **All Phase 7 Suites Combined:** `pytest tests/test_phase7_*.py` -> **102 passed in 2.56s**.
- **Complete Monolith Regression:** `pytest tests/` -> **425 passed in 105.06s** (0 regressions).
- **Static Analysis & Formatting:**
  - `ruff check services/api tests/` -> **Clean (0 errors)**.
  - `mypy services/api/fraud` -> **Clean (Success: no issues found in 8 source files)**.
  - `alembic upgrade head --sql` -> **Clean static DDL generation**.

---

## 7. Deliverables & Modified Artifacts

| File | Change Type | Purpose |
| :--- | :--- | :--- |
| `database/migrations/versions/d6e7f8a9b0c1_phase_07_fraud_reviews.py` | New | Alembic migration for `fraud_reviews` table and RLS policies |
| `database/migrations/env.py` | Modified | Registered `FraudReview` model with Alembic metadata |
| `services/api/auth/permissions.py` | Modified | Added `REVIEW_FRAUD_EVENTS` and `VIEW_FRAUD_REVIEWS` permissions and role mappings |
| `services/api/fraud/models.py` | Modified | Added `FraudReview` SQLAlchemy model with composite foreign keys |
| `services/api/fraud/schemas.py` | Modified | Added Pydantic schemas for decision request, response, history, and review detail |
| `services/api/fraud/review_service.py` | New | Core business logic for review detail retrieval and atomic adjudication |
| `services/api/fraud/rules_service.py` | Modified | Extended `list_fraud_flags` with review status, risk category, and department filters |
| `services/api/fraud/routes.py` | Modified | Added `GET .../review` and `POST .../decision` endpoints and updated flags filters |
| `services/api/attendance/models.py` | Modified | Added hybrid properties for `risk_score` and `risk_category` |
| `tests/test_phase7_fraud_review_workflow.py` | New | Automated test suite with 20 comprehensive unit and API tests |
| `docs/phase-reports/PHASE_07_MILESTONE_04_REPORT.md` | New | Formal Phase 7.4 milestone completion report |
| `PROJECT_CONTEXT.md` | Modified | Updated milestone status and roadmap progress |

---

## 8. Next Milestone: Phase 7.5

**Next Step:** Phase 7.5 — Flutter Mobile Device Binding & Fraud Telemetry.
- Secure hardware/install identifier generation and storage in Keychain / Keystore via `flutter_secure_storage`.
- Geolocator sensor mock detection (`isMocked`) propagation into mobile `PunchRequestModel`.
- Device status and binding review card in the Mobile UI.
- Local user feedback for revoked device status or pending administrative approvals.

