# UPOSTIT Phase 9 — Milestone 9.3 Implementation Report
## Leave Application, Balance Tracking & Supervisor Adjudication

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.3 — Leave Application, Balance Tracking & Supervisor Adjudication  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.3 delivers the core employee self-service leave application, balance tracking, and supervisor adjudication lifecycle for the UPOSTIT Workforce Attendance SaaS platform. Building directly on the verified Phase 9.1 database architecture, Milestone 9.2 hierarchical holiday calendar resolution, and Phase 5 daily attendance projection engine, Milestone 9.3 implements robust balance accounting invariants, anti-self-approval security, manager reporting hierarchy constraints, and transactional attendance recalculation integration.

### Key Deliverables:
1. **Authenticated Employee Leave APIs ([`services/api/leave/routes.py`](../../services/api/leave/routes.py), [`services/api/leave/leave_request_service.py`](../../services/api/leave/leave_request_service.py))**:
   - `GET /api/v1/leave/balances/my`: Authenticated employee views their leave balances with real-time calculated available balance.
   - `POST /api/v1/leave/requests`: Authenticated employee applies for single-day, multi-day, or half-day (`FIRST_HALF`, `SECOND_HALF`) leave.
   - `GET /api/v1/leave/requests/my`: Paginated inquiry of employee's own requests with status filtering.
   - `GET /api/v1/leave/requests/{id}`: Detailed request view scoped to applicant, applicant's manager, or HR/Admin.
   - `POST /api/v1/leave/requests/{id}/cancel`: Cancellation lifecycle (releasing pending reservations or reversing future approved leave).
2. **Balance Reservation & Available Balance Invariant Engine**:
   - Row-level locking with `SELECT ... FOR UPDATE` on `LeaveBalance` during submission, adjudication, and cancellation to eliminate concurrent race conditions.
   - Strict enforcement of the balance invariant:
     $$\text{Available Balance} = \text{annual\_allocation} + \text{carried\_forward} + \text{accrued} - \text{used} - \text{pending\_approval}$$
   - Prevents negative available balances (`HTTP 400 Bad Request`).
   - Automatically reserves requested days: `pending_approval += requested_days`.
3. **Working Days & Calendar Exclusions Calculation**:
   - Integrates with Milestone 9.2's `resolve_applicable_calendar_for_employee()` to exclude non-working public holidays.
   - Integrates with `resolve_employee_shift_version()` to exclude employee weekly-off days.
   - Half-day requests: validated to single working date and assigned `0.50` deductible days.
   - Deductible days $\le 0$ rejected with `HTTP 400 Bad Request`.
4. **Supervisor Adjudication & Anti-Self-Approval Enforcement**:
   - `GET /api/v1/leave/requests`: Supervisor review queue. Managers see only direct reports (`reporting_manager_id == reviewer.id`); HR/Admin see tenant-wide queue; employees cannot access (`HTTP 403 Forbidden`).
   - `POST /api/v1/leave/requests/{id}/decision`: Adjudication endpoint (`APPROVE` or `REJECT`).
   - **Anti-Self-Approval**: Under no circumstance can a manager or admin approve or reject their own leave application (`HTTP 403 Forbidden`).
   - **Mandatory Rejection Reason**: Rejections require non-whitespace reason of at least 3 characters (`HTTP 422 Unprocessable Content`).
5. **Atomic Balance Accounting Transitions**:
   - **On Approval**: `pending_approval -= total_days`, `used += total_days`, status becomes `APPROVED`, `reviewer_user_id` and `decided_at` recorded.
   - **On Rejection**: `pending_approval -= total_days`, `used` unchanged, status becomes `REJECTED`, rejection reason recorded.
   - **On Cancellation**:
     - If `PENDING_APPROVAL`: `pending_approval -= total_days`, status becomes `CANCELLED`.
     - If `APPROVED`: Permitted only for future dates (`start_date > today`), `used -= total_days`, status becomes `CANCELLED`. Cancellation of past/commenced approved leave is blocked (`HTTP 400 Bad Request`).
6. **Attendance Projection Recalculation Integration**:
   - On approval or cancellation of approved leave, the service invokes `recalculate_attendance_day()` for each affected date in the leave window.
   - **Transactional Integrity**: If attendance recalculation fails, the database transaction is rolled back, preventing orphaned or desynchronized state.
   - **Immutable Ledger Guarantee**: No synthetic punches are added or modified in `attendance_events`; leave is represented strictly in projections.
7. **RBAC & Permissions Registry Update ([`services/api/auth/permissions.py`](../../services/api/auth/permissions.py))**:
   - Registered `Permission.APPLY_LEAVE = "apply_leave"` (all authenticated roles).
   - Registered `Permission.VIEW_LEAVE_REQUESTS = "view_leave_requests"` (all roles, scoped by hierarchy).
   - Registered `Permission.APPROVE_LEAVE = "approve_leave"` (`OWNER`, `ADMIN`, `HR`, `MANAGER`; `EMPLOYEE` excluded).

---

## 2. API Endpoints Created

All routes are registered under `/api/v1/leave` and secured via JWT authentication and tenant isolation.

| Method | Endpoint | Required Permission | Description | Status Code |
| :--- | :--- | :--- | :--- | :---: |
| `GET` | `/api/v1/leave/balances/my` | `APPLY_LEAVE` | View authenticated employee's active leave balances | `200 OK` |
| `POST` | `/api/v1/leave/requests` | `APPLY_LEAVE` | Submit a new leave request (reserves balance) | `201 Created` |
| `GET` | `/api/v1/leave/requests/my` | `VIEW_LEAVE_REQUESTS` | List authenticated employee's submitted requests | `200 OK` |
| `GET` | `/api/v1/leave/requests/{id}` | `VIEW_LEAVE_REQUESTS` | Retrieve detail of a leave request (scoped) | `200 OK` |
| `POST` | `/api/v1/leave/requests/{id}/cancel` | `APPLY_LEAVE` | Cancel a pending or future approved leave request | `200 OK` |
| `GET` | `/api/v1/leave/requests` | `APPROVE_LEAVE` | List requests in supervisor's review queue | `200 OK` |
| `POST` | `/api/v1/leave/requests/{id}/decision` | `APPROVE_LEAVE` | Adjudicate (Approve/Reject) a subordinate's leave request | `200 OK` |

---

## 3. Balance Transition & Invariant Verification Matrix

| Transition | Initial State | Action | Final State | `pending_approval` | `used` | `available_balance` | Recalculate Projections |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Submission** | N/A | Submit application | `PENDING_APPROVAL` | $+ \text{total\_days}$ | Unchanged | $- \text{total\_days}$ | No |
| **Approval** | `PENDING_APPROVAL` | Supervisor Approve | `APPROVED` | $- \text{total\_days}$ | $+ \text{total\_days}$ | Unchanged | Yes (each working day) |
| **Rejection** | `PENDING_APPROVAL` | Supervisor Reject | `REJECTED` | $- \text{total\_days}$ | Unchanged | $+ \text{total\_days}$ | No |
| **Cancel (Pending)** | `PENDING_APPROVAL` | Employee Cancel | `CANCELLED` | $- \text{total\_days}$ | Unchanged | $+ \text{total\_days}$ | No |
| **Cancel (Approved)** | `APPROVED` ($> \text{today}$) | Employee Cancel | `CANCELLED` | Unchanged | $- \text{total\_days}$ | $+ \text{total\_days}$ | Yes (reverses projection) |

---

## 4. Verification and Test Results

A dedicated test suite was implemented in [`tests/test_phase9_milestone3_leave_workflow.py`](../../tests/test_phase9_milestone3_leave_workflow.py) containing 20 focused tests covering every business rule, edge case, and security boundary:

1. `test_permission_matrix_for_leave_operations`: Verifies role-based access to `apply_leave`, `view_leave_requests`, and `approve_leave`.
2. `test_single_working_day_calculation`: Confirms 1.0 day deductible for standard working days.
3. `test_multi_day_excluding_weekends_and_holidays`: Validates subtraction of public holidays and shift weekly offs.
4. `test_half_day_returns_half_day_amount`: Confirms 0.50 day calculation for half-day requests.
5. `test_successful_leave_submission_reserves_pending_balance`: Verifies atomic increment of `pending_approval` upon submission.
6. `test_insufficient_balance_raises_400`: Verifies rejection when `total_days > available_balance`.
7. `test_overlapping_active_request_raises_409`: Prevents overlapping date ranges for the same employee.
8. `test_anti_self_approval_raises_403`: Verifies that managers/admins cannot approve/reject their own requests.
9. `test_manager_cannot_adjudicate_non_direct_report_raises_403`: Prevents managers from adjudicating outside their reporting hierarchy.
10. `test_successful_approval_commits_balance_and_triggers_recalculation`: Confirms `pending -> used` transition and attendance recalculation.
11. `test_rejection_releases_pending_hold`: Confirms `pending_approval` release and non-mutation of `used`.
12. `test_rejection_without_mandatory_reason_raises_422`: Rejects missing or whitespace-only rejection reasons.
13. `test_attendance_recalculation_failure_rolls_back_transaction`: Verifies database rollback if `recalculate_attendance_day` raises an exception.
14. `test_pending_request_cancellation_releases_hold`: Verifies pending cancellation releases `pending_approval`.
15. `test_cancellation_of_past_or_commenced_approved_leave_raises_400`: Blocks cancellation of historical/commenced approved leave.
16. `test_get_my_balances_200_ok`: HTTP route test for employee balance inquiry.
17. `test_employee_cannot_access_supervisor_queue_raises_403`: HTTP route test for RBAC denial on supervisor queue.
18. `test_manager_can_access_supervisor_queue_200_ok`: HTTP route test for supervisor queue retrieval.
19. `test_supervisor_decision_endpoint_approve_200_ok`: HTTP route test for supervisor approval workflow.
20. `test_cross_tenant_isolation_on_leave_requests`: HTTP route test ensuring 404 on cross-tenant request access.

### Monorepo Test Suite Verification
- **Milestone 9.3 Suite**: `20 passed` (100%) in 1.75s
- **Phase 9 Cumulative Suite**: `70 passed` (Milestone 9.1 + 9.2 + 9.3) in 2.07s
- **Backend Complete Suite**: `604 passed` (0 failures, 84 warnings) in 85.04s
- **Web Complete Suite**: `70 passed` in 0.35s
- **Flutter Complete Suite**: `348 passed` in 20.0s
- **Total Monorepo Tests Passing**: `1,022 passed` (604 Backend + 70 Web + 348 Mobile)

