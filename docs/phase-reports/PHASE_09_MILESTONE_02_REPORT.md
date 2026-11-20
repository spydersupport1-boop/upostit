# UPOSTIT Phase 9 — Milestone 9.2 Implementation Report
## Holiday Calendars & Leave Type Configuration

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.2 — Holiday Calendars & Leave Type Configuration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.2 delivers the core administrative and employee-facing configuration subsystem for **Leave Types** and **Holiday Calendars** in the UPOSTIT Workforce Attendance SaaS platform. Building upon the verified database architecture established in Milestone 9.1, Milestone 9.2 implements full business logic, validation rules, role-based access control, and a dedicated 3-tier hierarchical holiday resolution engine.

### Key Deliverables:
1. **Leave Type Management Subsystem ([`services/api/leave/leave_type_service.py`](../../services/api/leave/leave_type_service.py))**:
   - Organization-scoped CRUD for leave categories (`CL`, `SL`, `AL`, `LOP`).
   - Case-insensitive unique code enforcement within each tenant (`(tenant_id, UPPER(code))`).
   - Validation of non-negative rollover limits and positive consecutive-day thresholds.
   - Reference integrity guard: blocks destructive deletion with `HTTP 409 Conflict` if the leave type is referenced by employee balances or leave requests, suggesting deactivation instead.
2. **Holiday Calendar & Entry Management Subsystem ([`services/api/leave/holiday_service.py`](../../services/api/leave/holiday_service.py))**:
   - Annual calendar management supporting location-specific overrides, department-specific overrides, and organization default fallbacks.
   - Mutual exclusivity on annual default calendars: setting `is_default=True` automatically demotes any prior default for the same tenant and year.
   - Holiday entry management with duplicate-date prevention per calendar (`HTTP 409 Conflict`) and date-range querying.
3. **Dedicated Hierarchical Calendar Resolution Engine**:
   - Resolves the authoritative holiday calendar for any employee following the strict 3-tier precedence:
     - **Tier 1 (Workplace Location)**: Evaluates employee's active primary workplace location assignment from `EmployeeLocation`. If the workplace location is active, resolves calendar matching `location_id == location.id`. Inactive locations are automatically bypassed.
     - **Tier 2 (Department)**: If no location calendar matches, evaluates `employee.department_id` against calendars where `department_id == employee.department_id` and `location_id IS NULL`.
     - **Tier 3 (Tenant Default)**: If neither location nor department calendar matches, resolves the calendar where `is_default = TRUE`.
     - Returns `(None, "NONE")` if no calendar exists for that year.
4. **Employee Upcoming Holiday Inquiry (`GET /api/v1/holidays/upcoming`)**:
   - Authenticated employee self-scoping derived from server-side JWT context.
   - Strictly prohibits employees from querying peer holiday calendars (`HTTP 403 Forbidden`).
   - Managers, HR, and Admins can query direct reports or tenant defaults.
   - Stable response schema returning holiday entries, calendar metadata, and resolution source provenance.
5. **RBAC & Permissions Registry Update ([`services/api/auth/permissions.py`](../../services/api/auth/permissions.py))**:
   - Registered 6 granular permissions: `MANAGE_POLICIES`, `VIEW_POLICIES`, `MANAGE_LEAVE_TYPES`, `VIEW_LEAVE_TYPES`, `MANAGE_HOLIDAYS`, `VIEW_HOLIDAYS`.
   - Strictly enforced deny-by-default access control across Owner, Admin, HR, Manager, and Employee roles.

---

## 2. API Endpoints Created

All routes are mounted under `/api/v1` in [`services/api/main.py`](../../services/api/main.py) and documented in OpenAPI.

### 2.1 Leave Type Endpoints (`/api/v1/leave/types`)
| Method | Endpoint | Permission Required | Description | Status Code |
| :--- | :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/leave/types` | `MANAGE_LEAVE_TYPES` | Configure new tenant leave type | `201 Created` |
| `GET` | `/api/v1/leave/types` | `VIEW_LEAVE_TYPES` | List paginated tenant leave types with search/filter | `200 OK` |
| `GET` | `/api/v1/leave/types/{id}` | `VIEW_LEAVE_TYPES` | Retrieve leave type by ID | `200 OK` |
| `PATCH` | `/api/v1/leave/types/{id}` | `MANAGE_LEAVE_TYPES` | Update leave type parameters (quota, active status) | `200 OK` |
| `DELETE` | `/api/v1/leave/types/{id}` | `MANAGE_LEAVE_TYPES` | Delete leave type (blocked if balances/requests exist) | `204 No Content` / `409 Conflict` |

### 2.2 Holiday Calendar Endpoints (`/api/v1/holidays/calendars`)
| Method | Endpoint | Permission Required | Description | Status Code |
| :--- | :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/holidays/calendars` | `MANAGE_HOLIDAYS` | Create annual holiday calendar | `201 Created` |
| `GET` | `/api/v1/holidays/calendars` | `VIEW_HOLIDAYS` | List calendars with holiday counts and filters | `200 OK` |
| `GET` | `/api/v1/holidays/calendars/{id}` | `VIEW_HOLIDAYS` | Retrieve calendar with loaded holiday entries | `200 OK` |
| `PATCH` | `/api/v1/holidays/calendars/{id}` | `MANAGE_HOLIDAYS` | Update calendar header details | `200 OK` |
| `DELETE` | `/api/v1/holidays/calendars/{id}` | `MANAGE_HOLIDAYS` | Delete calendar (cascades to holidays) | `204 No Content` |
| `POST` | `/api/v1/holidays/calendars/{id}/holidays` | `MANAGE_HOLIDAYS` | Add holiday entry to calendar | `201 Created` |
| `GET` | `/api/v1/holidays/calendars/{id}/holidays` | `VIEW_HOLIDAYS` | List calendar holidays by date range | `200 OK` |
| `PATCH` | `/api/v1/holidays/calendars/{id}/holidays/{h_id}` | `MANAGE_HOLIDAYS` | Update specific holiday entry | `200 OK` |
| `DELETE` | `/api/v1/holidays/calendars/{id}/holidays/{h_id}` | `MANAGE_HOLIDAYS` | Delete holiday entry | `204 No Content` |

### 2.3 Employee Upcoming Holidays Inquiry (`/api/v1/holidays/upcoming`)
| Method | Endpoint | Permission Required | Description | Status Code |
| :--- | :--- | :--- | :--- | :---: |
| `GET` | `/api/v1/holidays/upcoming` | `VIEW_HOLIDAYS` | Query upcoming holidays via hierarchical resolution | `200 OK` |

---

## 3. Test Execution & Quality Validation

### 3.1 Monorepo Test Summary
All test suites across backend, mobile, and web were executed fresh:

| Component | Test Suite | Tests Run | Passed | Failed | Status |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Milestone 9.2 Suite** | `tests/test_phase9_milestone2_leave_and_holidays.py` | 26 | 26 | 0 | **PASSED (100%)** |
| **Milestone 9.1 Suite** | `tests/test_phase9_database_models_and_migration.py` | 24 | 24 | 0 | **PASSED (100%)** |
| **Total Phase 9 Suite** | `pytest tests/test_phase9*` | 50 | 50 | 0 | **PASSED (100%)** |
| **Full Backend API Suite** | `pytest tests/` (Entire backend test suite) | 584 | 584 | 0 | **PASSED (100%)** |
| **Flutter Mobile Suite** | `flutter test` (in `apps/mobile`) | 348 | 348 | 0 | **PASSED (100%)** |
| **Next.js Web Console Suite** | `npm test` (in `apps/web`) | 70 | 70 | 0 | **PASSED (100%)** |
| **Total Monorepo Suite** | **Full Regression Matrix** | **1,002** | **1,002** | **0** | **PASSED (100%)** |

### 3.2 Static Analysis & Quality Checks
- **Python Linting (`ruff check services/ tests/`)**: 100% clean across all services and tests with **0 errors**.
- **Python Type Checking (`mypy services/api/leave/`)**: `Success: no issues found in 6 source files`.
- **Warning Cleanliness**: Zero `RuntimeWarning` or unhandled coroutine warnings in Milestone 9.2 tests.
- **Cross-Tenant Isolation**: Verified Tenant B receives `404 Not Found` when attempting to access Tenant A's leave types or holiday calendars.
- **Self-Scoping Protection**: Verified employee attempting to query another employee's holidays via `?employee_id=` is blocked with `403 Forbidden`.

---

## 4. Known Limitations & Schema Notes

1. **Holiday Calendar `is_active` Column**:
   - The `holiday_calendars` database table created in Milestone 9.1 does not contain an `is_active` column.
   - Inactive calendar handling is enforced at the location level (`Location.is_active` is verified before adopting a location calendar) and through soft-demotion of defaults. If explicit deactivation of calendars without deletion is required, an optional Alembic column addition may be planned in a subsequent phase.
2. **Department-Level Calendar Support**:
   - As confirmed during inspection, `HolidayCalendar` includes `department_id: UUID | None` with composite foreign key referencing `departments(tenant_id, id)`. Full department calendar precedence (Tier 2) is active and verified.
3. **Host Environment Note**: Docker is not installed and PostgreSQL port 5432 is closed on this macOS host; all integration tests operate against AsyncSession mocks and SQLite test engines.

---

## 5. Next Steps: Milestone 9.3

With Milestone 9.2 complete, validated, and passing 100% of the 1,002 monorepo tests, the platform is ready for:
- **Milestone 9.3 — Leave Application, Balance Tracking & Supervisor Adjudication**:
  - Employee leave submission with balance reservation/hold (`pending_approval += total_days`).
  - Row-level locking on `leave_balances` to prevent race conditions and negative balances.
  - Manager direct-report review queue with anti-self-approval rule.
  - Multi-day, single-day, and half-day (`FIRST_HALF` / `SECOND_HALF`) processing.
  - Balance commit on approval (`pending_approval -> used`) and rollback on rejection/cancellation.

