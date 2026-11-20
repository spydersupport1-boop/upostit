# UPOSTIT Phase 9 — Milestone 9.5 Implementation Report
## Next.js Web Console — Leave & Overtime Administration

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.5 — Next.js Web Console: Leave & Overtime Administration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.5 delivers the comprehensive Next.js web application console for workforce leave management, holiday calendar administration, and overtime adjudication. Building directly on the completed and verified backend APIs from Milestones 9.1 through 9.4, Milestone 9.5 introduces dedicated enterprise interfaces for employees, managers, HR personnel, and tenant administrators without introducing separate design systems, duplicating backend calculations in TypeScript, or computing premature monetary/payroll amounts.

### Key Deliverables:
1. **API Client & TypeScript DTO Extensions ([`apps/web/src/lib/api.ts`](../../apps/web/src/lib/api.ts))**:
   - Added complete type definitions for `LeaveTypeDto`, `HolidayCalendarDto`, `HolidayDto`, `LeaveBalanceDto`, `LeaveRequestDto`, `OvertimeRuleDto`, `OvertimeRecordDto`, and their associated pagination and mutation payloads.
   - Implemented `leaveApi`: full CRUD on leave types, employee balances inquiry (`/leave/balances/my`), leave application (`/leave/requests`), personal requests (`/leave/requests/my`), supervisor review queue (`/leave/requests`), decision adjudication (`/leave/requests/{id}/decision`), and cancellation (`/leave/requests/{id}/cancel`).
   - Implemented `holidayApi`: calendar list and CRUD (`/holidays/calendars`), holiday entry management (`/holidays/calendars/{id}/entries`), and upcoming holidays inquiry with three-tier resolution metadata (`/holidays/upcoming`).
   - Implemented `overtimeApi`: overtime rules CRUD (`/overtime/rules`), supervisor overtime review queue (`/overtime/records`), personal overtime inquiry (`/overtime/records/my`), and decision adjudication (`/overtime/records/{id}/decision`).
2. **Employee Leave Dashboard ([`apps/web/src/app/leave/page.tsx`](../../apps/web/src/app/leave/page.tsx))**:
   - Route: `/leave`
   - Real-time leave balance cards displaying server-calculated annual allocation, carried forward, accrued, used, pending approval, and available balance for each active category.
   - Modal-based leave application supporting full-day and half-day (`FIRST_HALF`, `SECOND_HALF`) requests, single-day and date-range picker, mandatory reason input, and automated holiday-awareness preview.
   - Comprehensive request history table with status badges (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `CANCELLED`), reviewer feedback, and cancellation capability for eligible requests (`PENDING_APPROVAL` or future `APPROVED`).
   - Upcoming holidays sidebar showing resolved statutory holidays and resolution source (`LOCATION`, `DEPARTMENT`, or `TENANT_DEFAULT`).
3. **Supervisor Leave Review & Approvals Console ([`apps/web/src/app/leave/approvals/page.tsx`](../../apps/web/src/app/leave/approvals/page.tsx))**:
   - Route: `/leave/approvals`
   - Access-controlled: Restricted to Managers, HR, Admins, and Owners (standard employees receive a clear 403 access-denied view).
   - Scoped review queue: Managers see only direct reports; HR/Admin see tenant-wide queue.
   - Interactive review modal presenting full employee statement, deductible days, date range, and current balance context.
   - Anti-self-approval enforcement: Disables approval/rejection actions and alerts reviewers attempting to adjudicate their own requests.
   - Mandatory rejection reason: Enforces minimum 3 non-whitespace characters for `REJECT` actions.
4. **Leave Policy Configuration ([`apps/web/src/app/organization/leave-types/page.tsx`](../../apps/web/src/app/organization/leave-types/page.tsx))**:
   - Route: `/organization/leave-types`
   - HR/Admin console for configuring leave categories.
   - Modals for creating and editing leave categories (code, name, description, paid vs unpaid, approval requirements, half-day allowances, max consecutive days, and annual carry-forward rollover limits).
   - Active/Inactive policy toggle.
   - Conflict-safe deletion: Catches 409 Conflict responses when historical balances or request records exist and surfaces actionable feedback.
5. **Annual Holiday Calendar Administration ([`apps/web/src/app/organization/holidays/page.tsx`](../../apps/web/src/app/organization/holidays/page.tsx))**:
   - Route: `/organization/holidays`
   - Year selector and two-column layout: Calendar listing on left, selected calendar holiday schedule on right.
   - Create calendar modal with Location and Department dropdown overrides or Tenant Default fallback.
   - Inline holiday entry management: Add, edit, and delete holidays (`PUBLIC`, `COMPANY`, `OPTIONAL` / floating).
   - Preserves backend's three-tier resolution without duplicating precedence logic in the browser.
6. **Overtime Administration & Approvals Console ([`apps/web/src/app/attendance/overtime/page.tsx`](../../apps/web/src/app/attendance/overtime/page.tsx))**:
   - Route: `/attendance/overtime`
   - Role-adaptive interface: Employees see personal overtime records (`/records/my`); Managers see direct reports review queue; HR/Admin see tenant-wide review queue and policy rules tab.
   - Overtime records table displaying raw overtime, multiplier rate ($1.5\times$, $2.0\times$), payable overtime duration, category (`WORKDAY`, `WEEK_OFF`, `HOLIDAY`), and approval status.
   - Review dialog: Allows approving (with optional adjusted minutes) or rejecting (with mandatory explanation), guarded by anti-self-approval checks.
   - Overtime rules tab: Configure workday, rest-day, and holiday multipliers, daily thresholds, daily caps, pre-approval requirements, and default rule flags.
   - Zero payroll or currency display: Preserves clear separation between time tracking and future payroll stages.
7. **Cross-Console Navigation**:
   - Updated navigation bars in `apps/web/src/app/page.tsx`, `apps/web/src/app/attendance/page.tsx`, and `apps/web/src/app/organization/page.tsx` with role-aware links to `/leave`, `/leave/approvals`, `/organization/leave-types`, `/organization/holidays`, and `/attendance/overtime`.

---

## 2. API Endpoints Integrated

| Module | Method | Endpoint | Frontend Consumer |
| :--- | :--- | :--- | :--- |
| **Leave Types** | `GET` | `/api/v1/leave/types` | `/leave`, `/organization/leave-types` |
| | `POST` | `/api/v1/leave/types` | `/organization/leave-types` |
| | `PUT` | `/api/v1/leave/types/{id}` | `/organization/leave-types` |
| | `DELETE` | `/api/v1/leave/types/{id}` | `/organization/leave-types` |
| **Balances** | `GET` | `/api/v1/leave/balances/my` | `/leave` |
| **Leave Requests** | `POST` | `/api/v1/leave/requests` | `/leave` |
| | `GET` | `/api/v1/leave/requests/my` | `/leave` |
| | `GET` | `/api/v1/leave/requests` | `/leave/approvals` |
| | `POST` | `/api/v1/leave/requests/{id}/decision` | `/leave/approvals` |
| | `POST` | `/api/v1/leave/requests/{id}/cancel` | `/leave` |
| **Holidays** | `GET` | `/api/v1/holidays/calendars` | `/organization/holidays` |
| | `POST` | `/api/v1/holidays/calendars` | `/organization/holidays` |
| | `DELETE` | `/api/v1/holidays/calendars/{id}` | `/organization/holidays` |
| | `GET` | `/api/v1/holidays/calendars/{id}/entries` | `/organization/holidays` |
| | `POST` | `/api/v1/holidays/calendars/{id}/entries` | `/organization/holidays` |
| | `PUT` | `/api/v1/holidays/calendars/{id}/entries/{hid}` | `/organization/holidays` |
| | `DELETE` | `/api/v1/holidays/calendars/{id}/entries/{hid}` | `/organization/holidays` |
| | `GET` | `/api/v1/holidays/upcoming` | `/leave` |
| **Overtime** | `GET` | `/api/v1/overtime/rules` | `/attendance/overtime` |
| | `POST` | `/api/v1/overtime/rules` | `/attendance/overtime` |
| | `PUT` | `/api/v1/overtime/rules/{id}` | `/attendance/overtime` |
| | `DELETE` | `/api/v1/overtime/rules/{id}` | `/attendance/overtime` |
| | `GET` | `/api/v1/overtime/records` | `/attendance/overtime` |
| | `GET` | `/api/v1/overtime/records/my` | `/attendance/overtime` |
| | `POST` | `/api/v1/overtime/records/{id}/decision` | `/attendance/overtime` |

---

## 3. Role-Based Access Control (RBAC) Matrix

| Route | Minimum Role Required | Behavior for Unauthorized Users |
| :--- | :--- | :--- |
| `/leave` | `employee` | Inline authentication prompt if unauthenticated. |
| `/leave/approvals` | `manager` | Shield card display with `403 Access Denied` and link back to `/leave`. |
| `/organization/leave-types` | `hr` / `admin` / `owner` | Shield card display with `403 Access Denied` and link back to `/leave`. |
| `/organization/holidays` | `hr` / `admin` / `owner` | Shield card display with `403 Access Denied` and link back to `/leave`. |
| `/attendance/overtime` | `employee` | Role-adaptive: Employees see personal history; Managers see direct-report review queue; HR/Admin see tenant queue and policies tab. |

---

## 4. Verification and Automated Test Results

A comprehensive unit and integration test suite was created in [`apps/web/src/lib/leave-and-overtime-api.test.ts`](../../apps/web/src/lib/leave-and-overtime-api.test.ts) containing 26 focused tests:

1. `should fetch leave types list with active filter`: Validates query serialization and response parsing.
2. `should create a new leave type with POST payload`: Validates payload construction and response handling.
3. `should update an existing leave type with PUT payload`: Validates update mechanics.
4. `should handle 409 Conflict when deleting a referenced leave type`: Verifies graceful error capture.
5. `should fetch holiday calendars by year`: Validates year filter and default fallback status.
6. `should create a holiday entry inside a calendar`: Validates date and type parameters.
7. `should fetch upcoming holidays with resolved calendar source`: Verifies three-tier resolution metadata.
8. `should fetch authenticated employee leave balances`: Verifies available balance and quota display.
9. `should submit a full-day leave request`: Validates start and end date serialization.
10. `should submit a half-day leave request with FIRST_HALF session`: Validates session period and 0.5 day deduction.
11. `should cancel a pending leave request`: Validates cancellation endpoint call.
12. `should fetch supervisor review queue with pending filter`: Validates queue filtering.
13. `should adjudicate leave request with APPROVE action`: Validates approval payload.
14. `should adjudicate leave request with REJECT action and mandatory reason`: Validates rejection explanation requirement.
15. `should throw 403 Forbidden on anti-self-approval attempt`: Verifies anti-self-approval error handling.
16. `should throw 422 Unprocessable Content if rejection reason is missing or short`: Verifies validation error handling.
17. `should fetch overtime rules list`: Validates multipliers and threshold retrieval.
18. `should create a new overtime rule with default flag`: Validates rule creation and pre-approval setting.
19. `should fetch supervisor overtime review queue`: Validates worked and payable minutes display.
20. `should fetch employee personal overtime records via /overtime/records/my`: Validates personal endpoint call.
21. `should adjudicate overtime record with APPROVE action and adjusted minutes`: Validates adjusted minutes payload.
22. `should throw 403 Forbidden on anti-self-approval of overtime`: Verifies anti-self-approval security.
23. `should verify available balance mathematical invariant`: Confirms available balance formula.
24. `should verify overtime payable minutes formula`: Confirms multiplication formula.
25. `should verify holiday overtime payable minutes formula with 2.0x multiplier`: Confirms rest-day/holiday rate formula.
26. `should validate rejection reason minimum length requirement`: Validates $\ge 3$ non-whitespace characters rule.

### Test Suite Execution Summary:
- **Next.js Web Unit & Integration Tests**: **96 passed (100%)** across 29 test suites with 0 failures (duration: 400ms).
- **Next.js Production Build**: **14/14 static pages generated successfully** with `next build`.
- **Next.js Linter**: **0 warnings, 0 errors** with `next lint`.
- **Backend Test Suite**: **629 passed (100%)** (including all 95 Phase 9 backend tests).
- **Total Monorepo Tests**: **1,073 tests passing across backend, web, and mobile**.

---

## 5. Known Limitations & Remaining Mobile Work

1. **Frontend-Only Testing**: Web tests utilize mocked API responses with `node:test` as per standard project testing patterns; live backend integration is verified in Milestone 9.7 chaos and simulation suites.
2. **Mobile Leave Application**: Leave application, balance display cards, and holiday viewing on native iOS and Android devices are deferred to **Milestone 9.6: Flutter Mobile: Leave Application, Balances & Holiday Hub**.
3. **No Payroll Calculations**: All overtime screens display time durations (raw and payable minutes) and multiplier rates only; currency and wage calculations are strictly deferred to future payroll phases.

