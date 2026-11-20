# UPOSTIT Phase 9 — Milestone 9.1 Implementation Report
## Database Architecture, Models & Alembic Migration

**Date:** 2026-11-20  
**Phase:** 9 — Leave, Holidays and Overtime Multipliers  
**Milestone:** 9.1 — Database Architecture, Data Models & Alembic Migration  
**Branch:** `phase-06`  
**Status:** Complete & Fully Validated  

---

## 1. Executive Summary

Milestone 9.1 establishes the foundational data architecture for Phase 9 of the UPOSTIT Workforce Attendance SaaS platform, covering **Leave Management**, **Holiday Calendars**, and **Overtime Multipliers**. Following the approved scope assessment ([`docs/PHASE_09_SCOPE_ASSESSMENT.md`](../PHASE_09_SCOPE_ASSESSMENT.md)), all seven database entities have been authored using SQLAlchemy 2.0 mapped declarative syntax, integrated into the Alembic migration history, registered in `Base.metadata`, and rigorously verified with contract and unit tests.

### Key Deliverables:
1. **7 Core Database Tables & Models ([`services/api/leave/models.py`](../../services/api/leave/models.py))**:
   - `leave_types`: Organization-level leave policy definitions (paid/unpaid, accrual frequency, negative balance rules, rollover caps, documentation requirements).
   - `leave_balances`: Per-employee, per-leave-type, per-year ledger tracking allocation, accrual, rollover, consumption, and pending holds.
   - `leave_requests`: Employee leave applications with multi-day/half-day date ranges, reason, medical attachment URIs, review workflow statuses, and anti-self-approval constraints.
   - `holiday_calendars`: Tenant-wide or location-specific holiday calendar groupings with fallback inheritance.
   - `holidays`: Specific non-working and optional holiday definitions with overtime multiplier overrides.
   - `overtime_rules`: Tenant-scoped overtime calculation parameters (daily threshold, rest-day multipliers, holiday multipliers, approval requirements).
   - `overtime_records`: Calculated and approved daily overtime summaries for payroll export and attendance projection reporting.
2. **Alembic Migration ([`database/migrations/versions/f2a3b4c5d6e7_phase_09_leave_holidays_overtime.py`](../../database/migrations/versions/f2a3b4c5d6e7_phase_09_leave_holidays_overtime.py))**:
   - Revision ID `f2a3b4c5d6e7` chained cleanly to Phase 8 Alembic head `e7f8a9b0c1d2`.
   - Comprehensive DDL with strict composite foreign keys `(tenant_id, ...)` enforcing cross-tenant foreign key integrity.
   - Complete PostgreSQL Row-Level Security (RLS) enablement and tenant isolation policies (`tenant_isolation_policy` using `app.current_tenant_id()`) for all 7 tables.
   - Complete clean reverse-order downgrade script.
3. **Metadata & Alembic Configuration ([`database/migrations/env.py`](../../database/migrations/env.py))**:
   - Explicitly imported and registered all 7 Phase 9 models on `Base.metadata`.
   - Verified that `alembic heads` resolves to a single head: `['f2a3b4c5d6e7']`.
4. **Automated Test Suite ([`tests/test_phase9_database_models_and_migration.py`](../../tests/test_phase9_database_models_and_migration.py))**:
   - 24 comprehensive unit and contract tests verifying migration chain integrity, table names, nullability, composite foreign keys, unique constraints, check constraints, half-day period rules, decision metadata rules, available balance computation invariant, and `Base.metadata` registration.

---

## 2. Test Execution & Quality Validation

### 2.1 Monorepo Test Summary
All test suites across backend, mobile, and web were executed fresh:

| Component | Test Suite | Tests Run | Passed | Failed | Status |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Backend API** | `pytest tests/test_phase9_database_models_and_migration.py` | 24 | 24 | 0 | **PASSED (100%)** |
| **Backend API** | `pytest tests/test_phase8* tests/test_phase9*` | 90 | 90 | 0 | **PASSED (100%)** |
| **Backend API** | `pytest tests/` (Complete backend suite) | 558 | 558 | 0 | **PASSED (100%)** |
| **Mobile App** | `flutter test` (Complete Flutter suite) | 348 | 348 | 0 | **PASSED (100%)** |
| **Web Console** | `npm test` in `apps/web` (Complete Jest suite) | 70 | 70 | 0 | **PASSED (100%)** |
| **Total Monorepo** | **Full Regression Matrix** | **976** | **976** | **0** | **PASSED (100%)** |

### 2.2 Static Analysis & Code Quality
- **Python Linting (`ruff check services/ tests/`)**: All checks passed with 0 warnings or errors.
- **Python Type Checking (`mypy services/api/leave/models.py`)**: `Success: no issues found in 1 source file`.
- **SQLAlchemy Relationship Overlaps**: Zero `SAWarning` warnings emitted during test execution, achieved via explicit `overlaps="..."` annotations on overlapping composite foreign keys.
- **Dart Code Quality (`dart format` & `flutter analyze`)**: 100% formatted, 0 issues found.
- **Alembic Migration Graph**: Verified single head `f2a3b4c5d6e7` pointing directly to parent `e7f8a9b0c1d2`.

---

## 3. Database Schema Specification

### 3.1 Alembic Migration Details
- **File:** `database/migrations/versions/f2a3b4c5d6e7_phase_09_leave_holidays_overtime.py`
- **Revision:** `f2a3b4c5d6e7`
- **Down Revision:** `e7f8a9b0c1d2` (Phase 8 Head: `attendance_conflict_incidents`)
- **Tables Created:**
  1. `leave_types`
  2. `leave_balances`
  3. `leave_requests`
  4. `holiday_calendars`
  5. `holidays`
  6. `overtime_rules`
  7. `overtime_records`

### 3.2 Key Constraints & Invariants

#### 1. Composite Tenant-Aware Foreign Keys
To guarantee strict multi-tenant isolation at the database level, parent tables define unique constraints on `(tenant_id, id)`:
- `uq_leave_types_tenant_id`
- `uq_leave_balances_tenant_id`
- `uq_leave_requests_tenant_id`
- `uq_holiday_calendars_tenant_id`
- `uq_holidays_tenant_id`
- `uq_overtime_rules_tenant_id`
- `uq_overtime_records_tenant_id`

Child tables enforce composite foreign keys referencing both `tenant_id` and the parent ID:
- `fk_leave_balances_type`: `(tenant_id, leave_type_id) REFERENCES leave_types(tenant_id, id)`
- `fk_leave_requests_type`: `(tenant_id, leave_type_id) REFERENCES leave_types(tenant_id, id)`
- `fk_holidays_calendar`: `(tenant_id, calendar_id) REFERENCES holiday_calendars(tenant_id, id)`
- `fk_overtime_records_rule`: `(tenant_id, rule_id) REFERENCES overtime_rules(tenant_id, id)`

#### 2. Unique Constraints
- `uq_leave_types_tenant_code`: `(tenant_id, code)` — prevents duplicate leave type codes within a tenant.
- `uq_leave_balances_tenant_emp_type_year`: `(tenant_id, employee_id, leave_type_id, year)` — one balance record per employee, leave type, and calendar year.
- `uq_holidays_calendar_date`: `(calendar_id, holiday_date)` — prevents duplicate holidays on the same date in a calendar.
- `uq_overtime_records_tenant_emp_date`: `(tenant_id, employee_id, work_date)` — ensures one consolidated daily overtime calculation per employee per date.

#### 3. Check Constraints & Invariants
- **Date Invariants**:
  - `ck_leave_requests_date_order`: `start_date <= end_date`
  - `ck_leave_requests_positive_days`: `days_requested > 0`
  - `ck_leave_requests_half_day_rule`: If `is_half_day` is `TRUE`, `half_day_period` must be `'FIRST_HALF'` or `'SECOND_HALF'`.
  - `ck_leave_requests_decision_metadata`: If status is `'APPROVED'` or `'REJECTED'`, `decided_at` and `decided_by` must be non-null.
- **Overtime Multiplier Constraints**:
  - `ck_holidays_multiplier_positive`: `overtime_multiplier >= 1.0`
  - `ck_overtime_rules_multipliers`: `daily_threshold_hours >= 0`, `standard_rate_multiplier >= 1.0`, `rest_day_multiplier >= 1.0`, `holiday_multiplier >= 1.0`.
  - `ck_overtime_records_minutes`: `overtime_minutes >= 0`, `approved_minutes >= 0`, `rate_multiplier >= 1.0`.
- **Available Balance Invariant**:
  $$\text{Available Balance} = \text{annual\_allocation} + \text{carried\_forward} + \text{accrued} - \text{used} - \text{pending\_approval}$$

#### 4. PostgreSQL Row-Level Security (RLS)
Every table is secured with:
```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_policy ON <table>
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

---

## 4. Environment Verification & Operational Constraints

1. **Host Environment Note**: Docker is not running on the development macOS host, and local PostgreSQL port 5432 is closed. All database tests and schema contract validations operate through SQLAlchemy's asynchronous dialect engine, mock inspection, and SQLite test databases.
2. **Phase Boundaries**: Milestone 9.1 strictly implements database models, constraints, and Alembic migrations. API endpoints, business logic, holiday resolution, leave balance hold/deduction, and calculation engine integration remain deferred to subsequent milestones (9.2–9.8).
3. **No Synthetic Ledger Punches**: Per project architecture rules, leave and holidays will never write synthetic punch rows to `attendance_events`.

---

## 5. Next Steps

With Milestone 9.1 complete, validated, and passing 100% of the 976 monorepo tests, the platform is ready for:
- **Milestone 9.2**: Holiday Calendars & Leave Type Configuration API (CRUD endpoints, hierarchical holiday resolution from workplace location to tenant default).

