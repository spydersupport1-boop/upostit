# UPOSTIT Phase 9 — Milestone 9.4 Implementation Report
## Overtime Rules Engine & Attendance Calculation Integration

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.4 — Overtime Rules Engine & Attendance Calculation Integration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.4 delivers the overtime rules engine, pure functional calculation extensions, and supervisor overtime adjudication workflow for the UPOSTIT Workforce Attendance SaaS platform. Building directly on the verified Phase 9.1–9.3 foundations and the Phase 5 pure functional attendance engine, Milestone 9.4 establishes a deterministic, multi-tier overtime computation system without modifying the immutable event ledger (`attendance_events`) or introducing premature payroll/monetary calculations.

### Key Deliverables:
1. **Alembic Migration (`database/migrations/versions/a4b5c6d7e8f9_phase_09_overtime_enhancements.py`)**:
   - Single clean head upgrade from `f2a3b4c5d6e7`.
   - Added `is_default` (boolean) and `requires_pre_approval` (boolean) columns and composite index `ix_overtime_rules_tenant_default` to `overtime_rules`.
   - Added `overtime_rule_id` foreign key column, composite foreign key (`["tenant_id", "overtime_rule_id"] -> ["overtime_rules.tenant_id", "overtime_rules.id"]`), and index `ix_overtime_records_rule` to `overtime_records`.
   - Complete, reversible upgrade and downgrade paths tested against SQLite and PostgreSQL schemas.
2. **SQLAlchemy Models Update ([`services/api/leave/models.py`](../../services/api/leave/models.py))**:
   - Enhanced `OvertimeRule` with `requires_pre_approval` and `is_default` attributes.
   - Enhanced `OvertimeRecord` with `overtime_rule_id` foreign key and bi-directional relationship to `OvertimeRule` with `overlaps="overtime_records,rule"` annotations to eliminate mapper collision warnings.
3. **Pure Functional Calculation Engine ([`services/api/attendance/engine.py`](../../services/api/attendance/engine.py))**:
   - Extended `calculate_attendance_day()` with zero DB dependencies.
   - Accepts parameters: `target_date`, `shift_version`, `resolved_timeline`, `tenant_timezone`, `now_dt`, `is_holiday`, `is_on_leave`, `leave_type_code`, `is_half_day_leave`, `half_day_period`, `overtime_rule`.
   - Implemented `OvertimeCalculationDetails` dataclass returning:
     - `raw_overtime_minutes`
     - `eligible_overtime_minutes`
     - `capped_overtime_minutes`
     - `multiplier`
     - `payable_overtime_minutes`
     - `overtime_type` (`WORKDAY`, `WEEK_OFF`, `HOLIDAY`)
     - `status` (`AUTO_APPROVED`, `PENDING_APPROVAL`, `REJECTED`)
     - `rule_id`
   - **Deterministic Precedence**: Statutory Holiday takes absolute precedence over Weekly Off (no double counting).
   - **Thresholds & Daily Caps**: Enforces `daily_overtime_threshold_minutes` eligibility gate and `max_daily_overtime_minutes` ceiling.
   - **Absence & Incomplete Safety**: Incomplete sessions and full-day approved leaves yield zero overtime.
   - **Half-Day Boundary Overtime**: Correctly accounts for worked duration beyond half-day scheduled net window.
4. **Tenant-Scoped Overtime Rule Service & APIs ([`services/api/leave/overtime_service.py`](../../services/api/leave/overtime_service.py), [`services/api/leave/routes.py`](../../services/api/leave/routes.py))**:
   - Full CRUD endpoints under `/api/v1/overtime/rules`: create, list, retrieve, update, delete.
   - Single default rule per tenant with automatic demotion of previous default rule.
   - Multiplier validation: $\ge 1.00$ and $\le 5.00$ (`workday_multiplier`, `weekly_off_multiplier`, `holiday_multiplier`).
   - Daily cap validation: $0 \le \text{daily\_threshold} \le \text{max\_daily} \le 1440$.
   - Conflict-safe deletion: Deleting a rule referenced by existing `OvertimeRecord` rows is blocked (`HTTP 409 Conflict`).
5. **Supervisor Overtime Adjudication Workflow ([`services/api/leave/routes.py`](../../services/api/leave/routes.py))**:
   - `GET /api/v1/overtime/records`: Supervisor review queue. Direct-report filtering for managers; tenant-wide queue for HR/Admins; forbidden for standard employees (`HTTP 403 Forbidden`).
   - `GET /api/v1/overtime/records/my`: Authenticated employee self-service view of own overtime records.
   - `GET /api/v1/overtime/records/{id}`: Detailed record view scoped to applicant, manager hierarchy, or HR/Admin.
   - `POST /api/v1/overtime/records/{id}/decision`: Adjudication endpoint (`APPROVE` or `REJECT`) with row-level locking (`with_for_update()`).
   - **Anti-Self-Approval**: Managers and admins cannot adjudicate their own overtime (`HTTP 403 Forbidden`).
   - **Mandatory Rejection Reason**: Rejections enforce non-whitespace reason of at least 3 characters (`HTTP 422 Unprocessable Content`).
   - **Ledger Invariant**: Approval sets `approved_overtime_minutes` and updates `AttendanceDay.overtime_minutes`; rejection sets `approved_overtime_minutes = 0` and `AttendanceDay.overtime_minutes = 0`.
6. **Attendance Recalculation Integration ([`services/api/attendance/service.py`](../../services/api/attendance/service.py))**:
   - Automatically queries applicable holiday, leave, and overtime rule during `recalculate_attendance_day()`.
   - Upserts `OvertimeRecord` idempotently linked via `attendance_day_id` and unique `(tenant_id, employee_id, attendance_date)`.
   - **Decision Preservation**: Existing `APPROVED` records preserve approved status (capped to raw overtime if raw was reduced); existing `REJECTED` records remain rejected.
   - **Audit Guarantee**: Never modifies or inserts synthetic events in `attendance_events`.
7. **RBAC & Permissions Registry Update ([`services/api/auth/permissions.py`](../../services/api/auth/permissions.py))**:
   - Registered `Permission.MANAGE_OVERTIME_RULES = "manage_overtime_rules"` (`OWNER`, `ADMIN`, `HR`).
   - Registered `Permission.VIEW_OVERTIME_RULES = "view_overtime_rules"` (All roles).
   - Registered `Permission.APPROVE_OVERTIME = "approve_overtime"` (`OWNER`, `ADMIN`, `HR`, `MANAGER`).
   - Registered `Permission.VIEW_OVERTIME_RECORDS = "view_overtime_records"` (All roles, scoped by hierarchy).

---

## 2. API Endpoints Created

All routes are registered under the `/api/v1/overtime` router prefix and mounted in `services/api/main.py`:

| Method | Endpoint | Required Permission | Description | Status Code |
| :--- | :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/overtime/rules` | `MANAGE_OVERTIME_RULES` | Create tenant overtime rule (with default demotion) | `201 Created` |
| `GET` | `/api/v1/overtime/rules` | `VIEW_OVERTIME_RULES` | List tenant overtime rules | `200 OK` |
| `GET` | `/api/v1/overtime/rules/{id}` | `VIEW_OVERTIME_RULES` | Get overtime rule by ID | `200 OK` |
| `PUT` | `/api/v1/overtime/rules/{id}` | `MANAGE_OVERTIME_RULES` | Update overtime rule | `200 OK` |
| `DELETE` | `/api/v1/overtime/rules/{id}` | `MANAGE_OVERTIME_RULES` | Delete overtime rule (prevented if in use) | `200 OK` |
| `GET` | `/api/v1/overtime/records` | `APPROVE_OVERTIME` | List overtime records in supervisor queue | `200 OK` |
| `GET` | `/api/v1/overtime/records/my` | `VIEW_OVERTIME_RECORDS` | List authenticated employee's overtime records | `200 OK` |
| `GET` | `/api/v1/overtime/records/{id}` | `VIEW_OVERTIME_RECORDS` | Get overtime record details (scoped) | `200 OK` |
| `POST` | `/api/v1/overtime/records/{id}/decision` | `APPROVE_OVERTIME` | Adjudicate (Approve/Reject) overtime record | `200 OK` |

---

## 3. Mathematical & Deterministic Engine Formats

### 3.1 Workday Overtime
$$\text{Scheduled Net} = \text{Shift End} - \text{Shift Start} - \text{Scheduled Breaks}$$
$$\text{Actual Net} = \text{Completed Working Minutes} - \text{Completed Break Minutes}$$
$$\text{Raw OT} = \max(0, \text{Actual Net} - \text{Scheduled Net})$$

- If $\text{Raw OT} < \text{daily\_overtime\_threshold\_minutes}$, then $\text{Eligible OT} = 0$.
- If $\text{Raw OT} \ge \text{daily\_overtime\_threshold\_minutes}$, then $\text{Eligible OT} = \min(\text{Raw OT}, \text{max\_daily\_overtime\_minutes})$.
- $\text{Payable Minutes} = \text{round}(\text{Eligible OT} \times \text{workday\_multiplier})$.

### 3.2 Non-Working Day Overtime & Category Precedence
- **Rest Day (Weekly Off)**:
  - $\text{Raw OT} = \text{Actual Net}$
  - Category: `WEEK_OFF`
  - Multiplier: `weekly_off_multiplier` (default $2.00$)
- **Statutory Public Holiday**:
  - $\text{Raw OT} = \text{Actual Net}$
  - Category: `HOLIDAY`
  - Multiplier: `holiday_multiplier` (default $2.00$)
- **Deterministic Overlap Resolution**:
  $$\text{When } \text{is\_holiday} = \text{True} \text{ and } \text{is\_weekly\_off} = \text{True} \implies \text{Category} = \text{HOLIDAY}$$
  Holiday multiplier is applied; rest day multiplier is discarded to prevent double counting.

### 3.3 Approval Lifecycle
$$\text{Requires Approval} = \text{requires\_manager\_approval} \lor \text{requires\_pre\_approval}$$
- If $\text{Requires Approval} = \text{False} \implies \text{Status} = \text{AUTO\_APPROVED}, \text{Approved OT} = \text{Eligible OT}$.
- If $\text{Requires Approval} = \text{True} \implies \text{Status} = \text{PENDING\_APPROVAL}, \text{Approved OT} = 0$.

---

## 4. Verification and Test Results

A dedicated test suite was implemented in [`tests/test_phase9_milestone4_overtime_engine.py`](../../tests/test_phase9_milestone4_overtime_engine.py) containing 25 comprehensive tests covering all functional components:

1. `test_workday_overtime_below_threshold_yields_zero_eligible`: Confirms that worked overtime below threshold yields 0 eligible minutes.
2. `test_workday_overtime_above_threshold_with_break_deductions`: Confirms accurate net calculation and multiplier application.
3. `test_workday_overtime_capped_by_daily_maximum`: Confirms capping at maximum daily minutes.
4. `test_weekly_off_overtime_multiplier_and_rest_day_work`: Validates rest-day overtime with 2.0x multiplier.
5. `test_holiday_overtime_statutory_multiplier`: Validates holiday overtime with statutory multiplier.
6. `test_holiday_and_weekly_off_overlap_precedence_no_double_count`: Confirms statutory holiday takes precedence over weekly off.
7. `test_overnight_shift_overtime_calculation`: Validates overtime calculation across day boundaries.
8. `test_incomplete_attendance_session_yields_zero_overtime`: Verifies unclosed punches never yield overtime.
9. `test_full_day_approved_leave_yields_zero_overtime`: Verifies leave days do not generate overtime.
10. `test_half_day_approved_leave_scheduled_boundary_overtime`: Verifies half-day leave scheduled duration threshold.
11. `test_pre_approval_required_flags_pending_approval_not_auto_approved`: Verifies `requires_pre_approval` forces review.
12. `test_auto_approval_when_neither_manager_nor_pre_approval_required`: Verifies auto-approval when neither flag is set.
13. `test_create_overtime_rule_success_and_default_demotion`: Verifies rule creation and default demotion.
14. `test_create_overtime_rule_invalid_multiplier_raises_400`: Verifies boundary validation on multipliers.
15. `test_create_overtime_rule_invalid_daily_cap_raises_400`: Verifies threshold $\le$ max cap validation.
16. `test_delete_overtime_rule_blocked_when_referenced_raises_409`: Verifies FK reference conflict protection.
17. `test_anti_self_approval_raises_403`: Verifies supervisors cannot approve their own overtime.
18. `test_manager_cannot_adjudicate_non_direct_report_raises_403`: Verifies manager direct-report boundaries.
19. `test_successful_approval_updates_record_and_attendance_day_overtime`: Verifies ledger and projection update.
20. `test_rejection_without_mandatory_reason_raises_422`: Rejects whitespace or missing rejection reasons.
21. `test_recalculation_preserves_already_approved_decision`: Verifies existing supervisor approvals survive attendance recalculations.
22. `test_admin_can_create_and_list_overtime_rules_200_201`: Verifies administrative HTTP route access.
23. `test_employee_cannot_create_overtime_rule_raises_403`: Verifies employee RBAC boundary on rules.
24. `test_employee_cannot_access_supervisor_overtime_queue_raises_403`: Verifies employee RBAC boundary on queue.
25. `test_cross_tenant_isolation_on_overtime_records_raises_404`: Verifies tenant RLS isolation.

### Monorepo Regression Test Matrix:
- **Backend Test Suite**: **629 passed** (including all 95 Phase 9 tests and 38 Phase 5 calculation engine tests) with 0 failures.
- **Next.js Web Test Suite**: **70 passed** with 0 failures.
- **Flutter Mobile Test Suite**: **348 passed** with 0 failures.
- **Total Monorepo Tests**: **1,047 passed** with 0 failures.
- **Linter & Static Analysis**: `ruff check` (0 errors), `ruff format` (clean), `mypy` (0 issues across all 10 source files).

