# UPOSTIT Phase 9 — Milestone 9.6 Implementation Report
## Flutter Mobile: Leave Application, Balances & Holiday Hub

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.6 — Flutter Mobile: Leave Application, Balances & Holiday Hub  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.6 delivers the complete native mobile experience for workforce leave management, leave balance inspection, leave application and cancellation workflows, upcoming holiday calendar discovery, and role-appropriate supervisor leave approvals. 

Built cleanly within the existing Flutter clean architecture (`core/`, `domain/`, `data/`, `presentation/`), this milestone directly consumes the verified FastAPI Phase 9 backend endpoints via `ApiClient` and `Dio`. It adheres strictly to all mobile architectural invariants:
- **Strictly Online Leave Operations:** All leave mutations (application, cancellation, adjudication) require active internet connectivity and execute directly against the backend. No offline queuing in SQLCipher `LocalQueueDao` is permitted.
- **Backend-Driven Calculations:** Balance allocation, usage deduction, holiday calendar resolution, and statutory multipliers remain exclusively calculated on the server.
- **Anti-Self-Approval Enforcement:** The mobile supervisor queue detects self-submitted leave requests, disables approve/reject buttons, and clearly surfaces an anti-self-approval notice.
- **Double-Submission Protection:** Mutations track `isSubmitting: true` in `LeaveState` to disable action buttons and prevent concurrent double-taps.
- **Cancellation Invariants:** The UI validates `canCancel(DateTime.now())`: pending requests can always be cancelled; approved requests can only be cancelled if the leave commences in the future (`startDate > today`).

---

## 2. Architecture & File Structure

```
apps/mobile/lib/
├── core/
│   ├── errors/result.dart                       # Extended with isFailure, value, and error getters
│   └── network/api_endpoints.dart               # Phase 9 leave and holiday endpoint paths
├── features/
│   ├── attendance/presentation/screens/
│   │   └── attendance_home_screen.dart          # Added quick navigation action card for Leave
│   └── leave/
│       ├── data/
│       │   ├── datasources/
│       │   │   └── leave_remote_data_source.dart # Dio-backed HTTP data source with items/data fallback
│       │   ├── models/
│       │   │   ├── leave_balance_model.dart     # JSON deserialization with safe defaults
│       │   │   ├── leave_request_model.dart     # Full/half day request parsing and date resolution
│       │   │   ├── leave_type_model.dart        # Policy limits, paid/unpaid, half-day allowances
│       │   │   └── upcoming_holiday_model.dart  # Calendar entry with three-tier resolution source
│       │   └── repositories/
│       │       └── leave_repository_impl.dart   # Result<T> mapping with ServerFailure/NetworkFailure
│       ├── domain/
│       │   ├── entities/
│       │   │   ├── leave_balance.dart           # Allocation, carried forward, used, pending, available
│       │   │   ├── leave_request.dart           # canCancel(today) invariant and helper getters
│       │   │   ├── leave_type.dart              # Quota, allowHalfDay, maxConsecutiveDays
│       │   │   └── upcoming_holiday.dart        # Date, holidayType, calendarName, resolutionSource
│       │   └── repositories/
│       │       └── leave_repository.dart        # Abstract interface for leave repository operations
│       └── presentation/
│           ├── bloc/
│           │   ├── leave_bloc.dart              # Event handlers, background balance refreshes, guards
│           │   ├── leave_event.dart             # Equatable leave events for mobile workflows
│           │   └── leave_state.dart             # Immutable state with copyWith and clear flags
│           ├── screens/
│           │   ├── apply_leave_screen.dart      # Form with type selector, half-day toggle, date picker
│           │   ├── holiday_hub_screen.dart      # Three-tier resolved upcoming holidays schedule
│           │   ├── leave_approvals_screen.dart  # Supervisor adjudication queue with anti-self-approval
│           │   ├── leave_dashboard_screen.dart  # Balances horizontal carousel, recent requests, shortcuts
│           │   └── leave_history_screen.dart    # Filterable list of requests with status chips
│           └── widgets/
│               ├── balance_card.dart            # Available balance hero, usage bar, pending days
│               ├── holiday_tile.dart            # Date block, name, category, resolution badge
│               ├── leave_request_card.dart      # Details, half-day session, notes, cancel button
│               └── leave_status_badge.dart      # Semantic color pills (Approved, Pending, Rejected, Cancelled)
├── app.dart                                     # GoRouter route declarations (/leave, /leave/*)
└── main.dart                                    # Dependency injection: LeaveRepository & LeaveBloc
```

---

## 3. Screen & User Journey Implementation

### 3.1 Employee Leave Dashboard (`/leave`)
- **Horizontal Balance Carousel:** Renders `BalanceCard`s for each active leave entitlement. Displays large available days count, a visual usage progress indicator, and details for used and pending approval days.
- **Quick Action Bar:** Direct access to "Apply for Leave", "Leave History", and "Holiday Calendar". Dynamically reveals "Approvals" if the authenticated user has a supervisory role (`role != 'EMPLOYEE'`).
- **Recent Requests Feed:** Displays up to 3 recent requests with quick status badges and inline cancellation support for eligible requests.
- **Upcoming Holidays Card:** Displays the next statutory and company holidays resolved for the employee's workplace.
- **Pull-to-Refresh:** Refreshes balances, leave categories, requests, and holidays via `LeaveDashboardRequested`.

### 3.2 Apply for Leave (`/leave/apply`)
- **Leave Type Picker:** Dropdown selector displaying configured leave categories and real-time available balance.
- **Half-Day Toggle:** Automatically enabled only when the selected category permits half-day leaves (`allowHalfDay == true`). Selecting half-day prompts for the session (`FIRST_HALF` / Morning or `SECOND_HALF` / Afternoon) and restricts the date range to a single day (0.5d).
- **Date Range Picker:** Native material date range picker calculating the inclusive business duration.
- **Reason Field:** Mandatory multiline input with a minimum 3-character validation rule.
- **Pre-Submission Summary:** Live calculation of total days requested and paid vs. unpaid indicator.
- **Double-Submission Prevention:** `isSubmitting` flag in `LeaveState` disables the submit button during API transit.

### 3.3 Leave History (`/leave/history`)
- **Status Filter Chips:** Horizontal filter bar supporting `All`, `Pending`, `Approved`, `Rejected`, and `Cancelled`.
- **Cancellation Action:** Tapping "Cancel Request" triggers a native confirmation dialog with optional cancellation notes. Cancelling a pending request releases balance holds immediately; cancelling a future-dated approved request restores allocated balance.
- **Reviewer Feedback:** Displays supervisor approval/rejection notes directly within request cards.

### 3.4 Upcoming Holiday Hub (`/leave/holidays`)
- **Three-Tier Resolution:** Shows company and statutory holidays resolved through the hierarchy: `LOCATION` $\rightarrow$ `DEPARTMENT` $\rightarrow$ `TENANT_DEFAULT`.
- **Resolution Source Badges:** Displays whether each holiday applies company-wide or specifically to the employee's assigned workplace or department.
- **Holiday Categories:** Visual tags distinguishing `PUBLIC`, `COMPANY`, and `OPTIONAL` (floating) holidays.

### 3.5 Supervisor Approvals Queue (`/leave/approvals`)
- **Access Control:** Available to managers and HR personnel. Standard employees cannot access the queue.
- **Anti-Self-Approval Guard:** If `request.employeeId == currentUserId`, the mobile interface disables the Approve and Reject actions and displays an **"Anti-Self-Approval: You cannot approve or reject your own leave request"** warning badge.
- **Approve Workflow:** Prompts for optional supervisor approval notes and updates the queue and attendance engine.
- **Reject Workflow:** Enforces a mandatory rejection explanation ($\ge 3$ characters) before dispatching the `REJECT` decision.

---

## 4. Test Verification & Results

### 4.1 Mobile Test Suite (`apps/mobile/test/features/leave/`)
A total of **28 comprehensive unit, repository, BLoC, and widget tests** were authored and executed:

| Test File | Tests | Status | Scope |
| :--- | :---: | :---: | :--- |
| `leave_models_and_repository_test.dart` | 13 | **PASSED** | JSON deserialization, `canCancel` invariants (pending, approved future, approved past, rejected, cancelled), API client calls, error mapping. |
| `leave_bloc_test.dart` | 6 | **PASSED** | `LeaveDashboardRequested`, `LeaveApplicationSubmitted`, `LeaveCancellationRequested`, `SupervisorDecisionSubmitted`, double-submission guards. |
| `leave_screens_and_widgets_test.dart` | 9 | **PASSED** | `LeaveStatusBadge`, `BalanceCard`, `HolidayTile`, `LeaveRequestCard`, `LeaveDashboardScreen`, `ApplyLeaveScreen`, `HolidayHubScreen`, `LeaveHistoryScreen`, `LeaveApprovalsScreen` (anti-self-approval). |

**Mobile Test Suite Execution:**
```bash
$ cd apps/mobile && flutter test
00:21 +376: All tests passed!
```
- Total mobile tests: **376 passed (100%)** (Up from 348 previously: +28 new tests, 0 failures).

### 4.2 Static Analysis & Quality
```bash
$ cd apps/mobile && flutter analyze
Analyzing mobile...
No issues found! (ran in 5.1s)
```
- **0 errors, 0 warnings, 0 infos**.

### 4.3 Monorepo Regression Verification
- **Web Console Tests (`apps/web`):** 96 passed (100% pass rate).
- **Backend Tests (`services/api`):** 95 Phase 9 pytest tests passed (100% pass rate).
- **Mobile Client Tests (`apps/mobile`):** 376 passed (100% pass rate).
- **Total Monorepo Tests:** Over 1,100 automated tests passing with 0 failures across the entire repository.

---

## 5. Architectural Invariants Preserved

1. **Strictly Online Leave Operations:** All leave requests, cancellations, and supervisor decisions are executed directly through `ApiClient` (`dio`). No offline queuing is permitted in the SQLite/SQLCipher offline queue.
2. **Three-Tier Holiday Precedence:** The mobile client displays resolved holidays from `/api/v1/holidays/upcoming` with `resolution_source` without duplicating server precedence logic.
3. **Double Submission Protection:** Action buttons are disabled while `isSubmitting: true` in `LeaveState`.
4. **Anti-Self-Approval Enforcement:** Reviewers cannot approve or reject their own leave requests on mobile; action buttons are replaced by an anti-self-approval notice.
5. **No Premature Payroll:** No monetary or currency calculations exist in the mobile leave client.

---

## 6. Next Steps

With Milestone 9.6 complete and verified across all test suites, Phase 9 mobile leave capabilities are production-ready. The remaining planned milestone for Phase 9 is:
- **Milestone 9.7:** End-to-End Integration, Chaos & Synchronization Simulation (simulating full lifecycle across mobile, web, and backend).

