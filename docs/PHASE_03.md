# PHASE 03 — Organization Structure & Employee Management

**Stage**: Stage A — Foundation  
**Branch**: `phase-03`  
**Current Status**: Complete, Migrated to Live Supabase, and Fully Verified (Alembic migration `e6331816d336` applied, composite foreign keys active, RLS enforced, 65 automated tests passing, live API & regression verified).

---

## 1. Goal & Functional Scope

Phase 3 builds the core organizational structure and employee management foundation for multi-tenant companies. It enables businesses—ranging from small offices and retail shops to large multi-branch enterprises and manufacturing factories—to model their hierarchy, departments, job titles, and workforce records within strictly isolated tenant boundaries.

### Functional Scope
1. **Organization Structure**:
   - **Departments**: Code, name, description, manager assignment, active/inactive status.
   - **Designations**: Code, title, description, active/inactive status.
   - Tenant scoping: Unique department codes and designation codes within each tenant.
2. **Employee Management**:
   - Tenant-scoped employee profiles with company-specific `employee_id`, `first_name`, `last_name`, `work_email`, `phone_number`, `department_id`, `designation_id`, `reporting_manager_id`, `employment_type` (`full_time`, `part_time`, `contract`, `intern`), `joining_date`, `status` (`active`, `inactive`, `on_leave`, `terminated`), `work_location`, and timestamps.
   - Self-referencing reporting hierarchy (`reporting_manager_id -> employees.id`).
3. **Employee Lifecycle**:
   - Employee creation, profile updates, and status transitions.
   - Soft deactivation and lifecycle states (`active`, `inactive`, `on_leave`, `terminated`) without physical record deletion.
   - Search across name, employee ID, and email with multi-criteria filtering (department, designation, status, employment type) and offset/limit pagination.
4. **Tenant Isolation & Security**:
   - Every table includes `tenant_id UUID REFERENCES tenants(id)`.
   - PostgreSQL Row-Level Security (RLS) enabled and forced (`FORCE ROW LEVEL SECURITY`).
   - Cross-tenant foreign key references prevented at both service layer and RLS engine layer.
5. **Role-Based Access Control (RBAC)**:
   - Backend enforcement for 5 roles: `owner`, `admin`, `hr`, `manager`, `employee`.
6. **Frontend Dashboard**:
   - Next.js 14+ TypeScript dashboard with Organization Overview, Employee Directory, Department Management, Designation Management, and modal forms.

---

## 2. Database Schema & Relationships

```mermaid
erDiagram
    tenants ||--o{ departments : owns
    tenants ||--o{ designations : owns
    tenants ||--o{ employees : employs
    departments ||--o{ employees : assigns
    designations ||--o{ employees : assigns
    employees ||--o{ employees : manages

    tenants {
        uuid id PK
        string name
        string slug
    }

    departments {
        uuid id PK
        uuid tenant_id FK
        string name
        string code
        string description
        uuid manager_id FK
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    designations {
        uuid id PK
        uuid tenant_id FK
        string title
        string code
        string description
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    employees {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string employee_id
        string first_name
        string last_name
        string work_email
        string phone_number
        uuid department_id FK
        uuid designation_id FK
        uuid reporting_manager_id FK
        string employment_type
        date joining_date
        string status
        string work_location
        timestamptz created_at
        timestamptz updated_at
    }
```

### 2.1 `departments` Table
- `id`: UUID (Primary Key, default `gen_random_uuid()`)
- `tenant_id`: UUID NOT NULL REFERENCES `tenants(id)` ON DELETE CASCADE
- `name`: VARCHAR(100) NOT NULL
- `code`: VARCHAR(50) NOT NULL
- `description`: TEXT NULL
- `manager_id`: UUID NULL REFERENCES `employees(id)` ON DELETE SET NULL
- `is_active`: BOOLEAN NOT NULL DEFAULT TRUE
- `created_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- `updated_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- **Constraints**:
  - `uq_departments_tenant_code`: UNIQUE (`tenant_id`, `code`)
  - `uq_departments_tenant_name`: UNIQUE (`tenant_id`, `name`)
- **Indexes**:
  - `ix_departments_tenant_id`: (`tenant_id`)
  - `ix_departments_code`: (`code`)

### 2.2 `designations` Table
- `id`: UUID (Primary Key, default `gen_random_uuid()`)
- `tenant_id`: UUID NOT NULL REFERENCES `tenants(id)` ON DELETE CASCADE
- `title`: VARCHAR(100) NOT NULL
- `code`: VARCHAR(50) NOT NULL
- `description`: TEXT NULL
- `is_active`: BOOLEAN NOT NULL DEFAULT TRUE
- `created_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- `updated_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- **Constraints**:
  - `uq_designations_tenant_code`: UNIQUE (`tenant_id`, `code`)
  - `uq_designations_tenant_title`: UNIQUE (`tenant_id`, `title`)
- **Indexes**:
  - `ix_designations_tenant_id`: (`tenant_id`)
  - `ix_designations_code`: (`code`)

### 2.3 `employees` Table
- `id`: UUID (Primary Key, default `gen_random_uuid()`)
- `tenant_id`: UUID NOT NULL REFERENCES `tenants(id)` ON DELETE CASCADE
- `user_id`: UUID NULL REFERENCES `users(id)` ON DELETE SET NULL
- `employee_id`: VARCHAR(50) NOT NULL (Company-specific badge/employee code)
- `first_name`: VARCHAR(100) NOT NULL
- `last_name`: VARCHAR(100) NOT NULL
- `work_email`: VARCHAR(255) NOT NULL
- `phone_number`: VARCHAR(50) NULL
- `department_id`: UUID NULL REFERENCES `departments(id)` ON DELETE SET NULL
- `designation_id`: UUID NULL REFERENCES `designations(id)` ON DELETE SET NULL
- `reporting_manager_id`: UUID NULL REFERENCES `employees(id)` ON DELETE SET NULL
- `employment_type`: VARCHAR(20) NOT NULL DEFAULT 'full_time' (`full_time`, `part_time`, `contract`, `intern`)
- `joining_date`: DATE NOT NULL
- `status`: VARCHAR(20) NOT NULL DEFAULT 'active' (`active`, `inactive`, `on_leave`, `terminated`)
- `work_location`: VARCHAR(150) NULL
- `created_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- `updated_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- **Constraints**:
  - `uq_employees_tenant_emp_id`: UNIQUE (`tenant_id`, `employee_id`)
  - `uq_employees_tenant_email`: UNIQUE (`tenant_id`, `work_email`)
- **Indexes**:
  - `ix_employees_tenant_id`: (`tenant_id`)
  - `ix_employees_employee_id`: (`employee_id`)
  - `ix_employees_work_email`: (`work_email`)
  - `ix_employees_department_id`: (`department_id`)
  - `ix_employees_designation_id`: (`designation_id`)
  - `ix_employees_reporting_manager_id`: (`reporting_manager_id`)
  - `ix_employees_status`: (`status`)

---

## 3. Row-Level Security (RLS) & Multi-Tenant Isolation

All Phase 3 tables enforce PostgreSQL Row-Level Security:
- `ALTER TABLE departments ENABLE ROW LEVEL SECURITY;`
- `ALTER TABLE departments FORCE ROW LEVEL SECURITY;`
- `ALTER TABLE designations ENABLE ROW LEVEL SECURITY;`
- `ALTER TABLE designations FORCE ROW LEVEL SECURITY;`
- `ALTER TABLE employees ENABLE ROW LEVEL SECURITY;`
- `ALTER TABLE employees FORCE ROW LEVEL SECURITY;`

### Isolation Policies
Every query issued by the application API sets `SET LOCAL ROLE authenticated` and `SELECT set_config('app.tenant_id', :tenant_id, true)`.
Each table has an isolated tenant policy:
```sql
CREATE POLICY tenant_isolation_departments ON departments
    AS PERMISSIVE FOR ALL
    TO authenticated
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```
Identical policies protect `designations` and `employees`. Table permissions (`SELECT, INSERT, UPDATE, DELETE`) are granted to `authenticated` and `service_role`.

---

## 4. Alembic Migration

- **Revision ID**: `e6331816d336`
- **Down Revision**: `4f61a7dd311e` (Phase 2 authentication migration)
- **File**: `database/migrations/versions/e6331816d336_phase_03_org_structure_and_employees.py`
- **Verification**: Verified offline using static SQL generation:
  ```bash
  .venv/bin/alembic upgrade head --sql
  ```
- **Live Status**: Prepared and validated. **Not yet applied to live Supabase** awaiting explicit user approval.

---

## 5. Role-Based Access Control (RBAC) Matrix

Phase 3 introduces granular permissions for organization structure and workforce management:

| Permission | Description |
| :--- | :--- |
| `manage_organization` | Create, update, and deactivate departments and designations |
| `view_organization` | View departments and designations |
| `create_employees` | Register new employee profiles |
| `view_employees` | View employee directory and details |
| `update_employees` | Edit employee profile records |
| `deactivate_employees` | Soft deactivate or update employee employment status |

### Role Permissions Assignment

| Role | `manage_organization` | `view_organization` | `create_employees` | `view_employees` | `update_employees` | `deactivate_employees` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Owner** | Yes | Yes | Yes | Yes | Yes | Yes |
| **Admin** | Yes | Yes | Yes | Yes | Yes | Yes |
| **HR** | No | Yes | Yes | Yes | Yes | Yes |
| **Manager** | No | Yes | No | Yes | No | No |
| **Employee** | No | Yes | No | Self / Permitted | No | No |

---

## 6. API Endpoints

### 6.1 Departments API (`/api/v1/departments`)
- `POST /api/v1/departments`: Create department (`manage_organization` required)
- `GET /api/v1/departments`: List departments with optional `is_active` filter and pagination (`view_organization` required)
- `GET /api/v1/departments/{department_id}`: Retrieve department details (`view_organization` required)
- `PUT /api/v1/departments/{department_id}`: Update department (`manage_organization` required)
- `DELETE /api/v1/departments/{department_id}`: Soft deactivate department (`manage_organization` required)

### 6.2 Designations API (`/api/v1/designations`)
- `POST /api/v1/designations`: Create designation (`manage_organization` required)
- `GET /api/v1/designations`: List designations with optional `is_active` filter and pagination (`view_organization` required)
- `GET /api/v1/designations/{designation_id}`: Retrieve designation details (`view_organization` required)
- `PUT /api/v1/designations/{designation_id}`: Update designation (`manage_organization` required)
- `DELETE /api/v1/designations/{designation_id}`: Soft deactivate designation (`manage_organization` required)

### 6.3 Employees API (`/api/v1/employees`)
- `POST /api/v1/employees`: Create employee record (`create_employees` required)
- `GET /api/v1/employees`: List employees with search (`q`), filters (`department_id`, `designation_id`, `status`, `employment_type`), and pagination (`limit`, `offset`) (`view_employees` required)
- `GET /api/v1/employees/{employee_id}`: Retrieve employee details (`view_employees` required)
- `PUT /api/v1/employees/{employee_id}`: Update employee profile (`update_employees` required)
- `PATCH /api/v1/employees/{employee_id}/status`: Transition employee status (`deactivate_employees` required)

---

## 7. Frontend Interface

Implemented under `apps/web/src/app/organization/page.tsx` with modern enterprise UI styles in `apps/web/src/app/globals.css`:
1. **Overview Tab**:
   - High-level metric cards: Total Employees, Active Workforce, Total Departments, Job Titles.
   - Quick action shortcuts to register employees or add departments/designations.
2. **Employees Directory Tab**:
   - Real-time search by name, badge ID, or email.
   - Filters for department, designation, and employment status.
   - Detailed employee table with badge codes, departments, job titles, joining dates, and status pills.
   - Slide-over profile inspection drawer with reporting manager details and contact information.
   - Status toggle action (`Active` vs. `Inactive`).
3. **Departments Tab**:
   - Department directory table displaying department code, description, and status.
   - Add Department modal dialog with validation.
4. **Designations Tab**:
   - Designation directory table displaying job title code, title, and status.
   - Add Designation modal dialog with validation.

---

## 8. Verification & Test Execution

- **Total Automated Tests**: 65 passed in 6.58s.
  - Phase 3 Schema Tests: 8 passed (`test_phase3_schemas.py`)
  - Phase 3 RBAC Tests: 5 passed (`test_phase3_rbac.py`)
  - Phase 3 API Authorization & Validation Tests: 6 passed (`test_phase3_api.py`)
  - Phase 3 Business Rules & Validations Tests: 12 passed (`test_phase3_business_rules.py`)
  - Existing Phase 1 & Phase 2 Tests: 34 passed
- **Linter & Type Checker**:
  - `ruff check`: 0 warnings, 0 errors.
  - `mypy services/api/`: Clean across 27 source files.
- **Frontend Quality**:
  - `next lint`: 0 warnings, 0 errors.
  - `next build`: Successfully compiled and generated production static bundle with 0 errors.

---

## 9. Technical Audit & Pre-Migration Verification Findings

### 9.1 Frontend and Backend Integration Audit
- **Integration State**: **Mock data only** (`apps/web/src/app/organization/page.tsx`).
- **Audit Findings**:
  - The UI uses hardcoded arrays (`SAMPLE_DEPARTMENTS`, `SAMPLE_DESIGNATIONS`, `SAMPLE_EMPLOYEES`).
  - Employee creation, department creation, designation creation, and status toggles update local React state only without invoking `fetch()` or calling FastAPI endpoints.
  - Search and department/status filtering execute purely in-memory.
  - Pagination, loading skeletons, and HTTP error handling are not yet integrated into the frontend.

### 9.2 Employee Account and Onboarding Design
- **`employees.user_id` Nullability**: `user_id` is nullable. An employee can exist without a login account.
- **Login Access Provisioning**: Not automated in Phase 3. Invitation workflows, token generation, and employee password onboarding are scheduled for Phase 4.
- **Deactivation Cascade**: Prior to remediation, deactivating an employee profile (`employees.status = 'inactive'`) did not cascade to deactivate the linked `users` account in Phase 2.
- **User-Employee Uniqueness**: Service layer and database schema hardened to enforce that a `user_id` cannot be linked to multiple employee profiles within a tenant (`uq_employees_tenant_user_id`).

### 9.3 Database Schema & Migration Audit
- **Circular Foreign Key Issue & Fix**:
  - `departments.manager_id` references `employees.id`, while `employees.department_id` references `departments.id`.
  - In `e6331816d336`, `sa.ForeignKeyConstraint(..., use_alter=True)` inside `op.create_table` did not emit the foreign key DDL in offline SQL mode.
  - **Fix Applied**: Updated migration to explicitly execute `op.create_foreign_key('fk_departments_manager_id', ...)` after `employees` table creation, and `op.drop_constraint(...)` on downgrade before dropping `employees`.
- **Tenant Isolation & RLS**:
  - `departments`, `designations`, and `employees` have RLS enabled and forced (`FORCE ROW LEVEL SECURITY`).
  - Tenant isolation policy enforces `tenant_id = current_setting('app.tenant_id', true)::uuid`.
  - Database grants applied to `authenticated, service_role`.

### 9.4 Business Rules & Validation Hardening
- **Hierarchy Cycle Prevention**: Added cycle detection in `update_employee` to traverse manager ancestry and reject circular reporting loops.
- **Active State Validation**: Enforced that inactive departments or designations cannot be assigned to employees, and inactive/terminated employees cannot be assigned as reporting managers.
- **Status Transition Machine**: Added `ALLOWED_STATUS_TRANSITIONS` to reject invalid state transitions (e.g. `terminated` directly to `on_leave`).

---

## 10. Audit Findings Remediation Implementation

Following the Phase 3 technical audit review, all identified gaps were remediated without applying live database migrations or modifying live Supabase data:

### 10.1 Task 1 — Employee Self-Access and Permissions
1. **Dedicated Permission**: Introduced `Permission.VIEW_OWN_PROFILE = "view_own_profile"`.
2. **Directory Access Denial**: Removed unrestricted `VIEW_EMPLOYEES` from `UserRole.EMPLOYEE`. Workers in the `employee` role can only view organization metadata (`VIEW_ORGANIZATION`) and their own profile (`VIEW_OWN_PROFILE`).
3. **Endpoint Creation**: Added `GET /api/v1/employees/me` requiring `VIEW_OWN_PROFILE`.
4. **Self-Profile Isolation**: Resolves the employee profile strictly via `session.execute(select(Employee).where(Employee.tenant_id == tenant_id, Employee.user_id == user_id))`.
5. **ID Manipulation Prevention**: Attempts by employees to access `GET /api/v1/employees/{id}` or `GET /api/v1/employees` fail immediately with HTTP 403 Forbidden.
6. **No Profile Linked Handling**: If an authenticated user has no linked employee profile, returns HTTP 404 (`"No employee profile found for the authenticated user"`) without leaking other employee records.
7. **Higher Roles Preserved**: Owner, Admin, HR, and Manager continue to access employee directories and management endpoints per their defined RBAC scopes.

### 10.2 Task 2 — Employee Deactivation and Session Revocation
1. **Synchronized Account Deactivation**: When an employee's status is changed to `inactive` or `terminated` in `update_employee_status`, the linked `users` account has its `status` set to `"inactive"` within the same database transaction.
2. **Immediate Session Revocation**: In the same transaction, all active refresh tokens in `refresh_tokens` for the user (`revoked_at IS NULL`) are immediately revoked by setting `revoked_at = datetime.now(UTC)`.
3. **Login Rejection**: Subsequent login attempts for deactivated users fail with HTTP 401 (`"Invalid credentials or inactive account"`).
4. **Refresh-Token Rotation Rejection**: Subsequent `/auth/refresh` attempts with existing refresh tokens fail with HTTP 401 (`"User or tenant account is inactive"`).
5. **Reactivation Behavior**: Changing an employee status back to `active` restores `linked_user.status = "active"`.
6. **Accidental Deactivation Protection**: General employee profile updates (`PUT /api/v1/employees/{id}`) do not accept status changes; status transitions must be executed explicitly via `PATCH /api/v1/employees/{id}/status`.
7. **Historical Reference Preservation**: The employee record, its history, audits, and foreign key references remain intact.

### 10.3 Task 3 — Tenant-Aware Composite Foreign Keys
Implemented composite foreign key constraints referencing `(tenant_id, id)` across all tenant relationships in models and migration `e6331816d336`:
- `departments(tenant_id, manager_id)` references `employees(tenant_id, id)` ON DELETE SET NULL.
- `employees(tenant_id, department_id)` references `departments(tenant_id, id)` ON DELETE SET NULL.
- `employees(tenant_id, designation_id)` references `designations(tenant_id, id)` ON DELETE SET NULL.
- `employees(tenant_id, reporting_manager_id)` references `employees(tenant_id, id)` ON DELETE SET NULL.
- `employees(tenant_id, user_id)` references `users(tenant_id, id)` ON DELETE SET NULL.
- Added unique constraints `uq_users_tenant_id` on `users(tenant_id, id)`, `uq_departments_tenant_id` on `departments(tenant_id, id)`, `uq_designations_tenant_id` on `designations(tenant_id, id)`, and `uq_employees_tenant_id` on `employees(tenant_id, id)`.
- Added unique constraint `uq_employees_tenant_user_id` on `employees(tenant_id, user_id)` to ensure one-to-one user-to-employee mapping per tenant.
- Verified offline upgrade and downgrade SQL via `alembic upgrade head --sql`. Live Supabase migration held pending approval.

### 10.4 Task 4 — Frontend/Backend Integration Foundation
Created a centralized, secure API client foundation in `apps/web/src/lib/api.ts`:
- **Centralized Configuration**: `NEXT_PUBLIC_API_URL` environment configuration defaulting to `http://localhost:8000/api/v1`.
- **Authenticated Requests**: Type-safe helper functions accepting bearer tokens.
- **Zero Embedded Secrets**: Uses only public configuration without storing secrets or exposing backend credentials.
- **Typed DTOs**: Exported interfaces matching FastAPI schemas for departments, designations, and employees.
- **Standard Error Handling**: `ApiError` class with HTTP status code and structured detail parsing.
- **UI Rewrite Avoidance**: Mock UI retained; production build passes cleanly (`next build` succeeded).

### 10.5 Task 5 — Testing & Quality Verification
- **Total Tests**: 65 passed in 6.58s.
- **Ruff**: Clean across `services/`, `packages/`, `tests/`.
- **Mypy**: Clean across 27 source files.
- **Web Lint**: Clean (0 ESLint errors).
- **Web Build**: Successfully compiled (Next.js 14.2.5).
- **Alembic Migration**: Applied and verified live on Supabase (`e6331816d336`).

---

## 11. Live Supabase Database Migration & Verification

Following explicit project owner authorization, migration `e6331816d336` was applied to the live Supabase PostgreSQL database (`db.qnkgndfzuhrjuopzlcxy.supabase.co`).

### 11.1 Pre-Migration Preconditions
1. **Target Database**: `postgresql://***:***@db.qnkgndfzuhrjuopzlcxy.supabase.co:5432/postgres` (credentials masked).
2. **Current Revision Checked**: Verified `alembic_version` was exactly `4f61a7dd311e`.
3. **Existing Records Checked**: Verified `tenants`: 2, `users`: 2, `refresh_tokens`: 4.
4. **Backup Confirmation**: User explicitly confirmed automated platform daily backup / recovery point is active.

### 11.2 Migration Execution
- **Command**: `.venv/bin/alembic upgrade head`
- **Result**: Exited code 0 with transactional DDL:
  ```
  INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
  INFO  [alembic.runtime.migration] Will assume transactional DDL.
  INFO  [alembic.runtime.migration] Running upgrade 4f61a7dd311e -> e6331816d336, phase_03_org_structure_and_employees
  ```
- **New Alembic Revision**: `e6331816d336`.

### 11.3 Live Schema Verification
Verified directly via PostgreSQL system catalogs:
- **Tables**: `departments`, `designations`, and `employees` exist in schema `public`.
- **Composite Unique Constraints**:
  - `departments`: `uq_departments_tenant_code`, `uq_departments_tenant_id`, `uq_departments_tenant_name`
  - `designations`: `uq_designations_tenant_code`, `uq_designations_tenant_id`, `uq_designations_tenant_title`
  - `employees`: `uq_employees_tenant_employee_id`, `uq_employees_tenant_id`, `uq_employees_tenant_user_id`, `uq_employees_tenant_work_email`
  - `users`: `uq_users_tenant_email`, `uq_users_tenant_id`
- **Composite Foreign Keys**:
  - `departments.fk_departments_tenant_manager_id`: `(tenant_id, manager_id)` references `employees(tenant_id, id)` ON DELETE SET NULL.
  - `employees.fk_employees_tenant_department_id`: `(tenant_id, department_id)` references `departments(tenant_id, id)` ON DELETE SET NULL.
  - `employees.fk_employees_tenant_designation_id`: `(tenant_id, designation_id)` references `designations(tenant_id, id)` ON DELETE SET NULL.
  - `employees.fk_employees_tenant_reporting_manager_id`: `(tenant_id, reporting_manager_id)` references `employees(tenant_id, id)` ON DELETE SET NULL.
  - `employees.fk_employees_tenant_user_id`: `(tenant_id, user_id)` references `users(tenant_id, id)` ON DELETE SET NULL.
- **Row-Level Security**:
  - `RLS_ENABLED=True` and `FORCE_RLS=True` confirmed on `departments`, `designations`, and `employees`.
  - Isolation policies `tenant_isolation_departments`, `tenant_isolation_designations`, and `tenant_isolation_employees` active with `USING` and `WITH CHECK` clauses.
- **Grants**: `authenticated` and `service_role` granted CRUD privileges.

### 11.4 Safe Functional Verification
Executed against Supabase using synthetic test data:
- **Same-Tenant Linking**: Departments, designations, employees, manager hierarchy, and circular department-manager relationships created and verified successfully.
- **Nullable Relationships**: Employees with NULL department, designation, manager, and user successfully created and verified.
- **Cross-Tenant FK Rejection**: Cross-tenant foreign key assignment (Tenant B employee assigned to Tenant A department) strictly rejected by PostgreSQL with `IntegrityError` (code 23503).
- **RLS Cross-Tenant Isolation**: Tenant B context confirmed 0 rows visible from Tenant A; cross-tenant insert strictly rejected by RLS `WITH CHECK` (`ProgrammingError`).
- **Cleanup**: All synthetic test records cleaned up cleanly. Pre-migration counts (`tenants`: 2, `users`: 2, `refresh_tokens`: 4) verified 100% untouched.

### 11.5 Phase 2 & Phase 3 Live API Journey Verification
Executed full HTTP API flows via FastAPI against the migrated live database:
- Company registration (HTTP 201).
- Owner login (HTTP 200).
- User profile retrieval `/api/v1/auth/me` (HTTP 200).
- Tenant context `/api/v1/tenants/current` (HTTP 200).
- Refresh token rotation and reuse detection (HTTP 200 / 401).
- Logout session revocation (HTTP 200).
- Phase 3 Department, Designation, and Employee creation (HTTP 201).
- Employee list with joined names (HTTP 200).
- Employee self-access `/employees/me` unlinked handling (HTTP 404).
- Synthetic API records cleaned up; 0 test records remaining.

---

## 12. Phase 3.1 — Complete Frontend API Integration

Following successful live Supabase database migration, the production Organization Management web screens in Next.js (`apps/web/src/app/organization/page.tsx`) were completely integrated with the live FastAPI backend, removing all mock and sample data.

### 12.1 Authentication & Session Integration
- **Centralized Session Context**: Created `apps/web/src/lib/auth-context.tsx` and wrapped the application inside `AuthProvider` (`apps/web/src/lib/providers.tsx` $\to$ `apps/web/src/app/layout.tsx`).
- **Multi-Tenant Authentication**: Updated `LoginRequestDto` with mandatory `tenant_slug`. Inline sign-in form provides workspace slug, work email, and password authentication against `POST /api/v1/auth/login`.
- **Token Management**: Integrated `tokenStorage` with `localStorage` persistence, automatic session recovery on client mount, and refresh token rotation with `POST /api/v1/auth/refresh`.
- **User Identity Display**: Organization navbar displays tenant name, authenticated user's name, role badge (`owner`, `admin`, `hr`, `manager`, `employee`), and sign out trigger.

### 12.2 Department Management Integration
- **Fetch**: `GET /api/v1/departments` with pagination and status filtering.
- **Create**: Modal triggers `POST /api/v1/departments` with `{ name, code, description, manager_id }`.
- **Edit**: Modal triggers `PUT /api/v1/departments/{id}` with `{ name, code, description, manager_id }`.
- **Deactivate / Activate**: Inline action button calls `PUT /api/v1/departments/{id}` with `{ is_active: !dept.is_active }`.
- **Manager Appointment**: Dropdown allows selecting active employees as department managers.
- **States**: Handled loading spinner, empty state, and modal error alerts.

### 12.3 Designation Management Integration
- **Fetch**: `GET /api/v1/designations` with pagination.
- **Create**: Modal triggers `POST /api/v1/designations` with `{ title, code, description }`.
- **Edit**: Modal triggers `PUT /api/v1/designations/{id}` with `{ title, code, description }`.
- **Deactivate / Activate**: Inline action button calls `PUT /api/v1/designations/{id}` with `{ is_active: !desig.is_active }`.
- **States**: Handled loading spinner, empty state, and modal error alerts.

### 12.4 Employee Directory & Lifecycle Integration
- **Fetch**: `GET /api/v1/employees` with dynamic backend query parameters (`search`, `department_id`, `designation_id`, `status`, `page`, `page_size`).
- **Pagination**: Real backend pagination with total record count and page controls.
- **Create**: Modal triggers `POST /api/v1/employees` with department, designation, and reporting manager selections.
- **Edit**: Modal triggers `PUT /api/v1/employees/{id}` for profile modifications.
- **Status Transition**: Status toggle and profile actions call dedicated `PATCH /api/v1/employees/{id}/status`.
- **Joined Relationships**: Table displays joined department name, designation title, and reporting manager name directly from backend DTOs.

### 12.5 Employee Self-Access Security Enforcement
- **Directory Denial**: For users with role `employee`, the directory table and modification buttons are suppressed. If an employee attempts direct access, `GET /api/v1/employees` returns `HTTP 403 Forbidden`.
- **Self-Service View**: Automatically loads `GET /api/v1/employees/me` under the `VIEW_OWN_PROFILE` permission.
- **Empty Linkage**: If an employee user account has no associated employee record, renders an informative alert prompt to contact HR.

### 12.6 Verification Results
- **Frontend Unit & Integration Tests**: 15 tests passed in `apps/web/src/lib/api.test.ts` (`make web-test`).
- **ESLint**: 0 warnings or errors (`make web-lint`).
- **Next.js Production Build**: Compiled successfully (`make web-build`, `/organization` 17.2 kB).
- **Backend Tests**: 65 passed in 6.82s (`make test`).
- **Backend Lint & Types**: 0 issues in 27 files (`make lint`).
- **Live HTTP Integration Tests**: 100% passed against live FastAPI server and Supabase PostgreSQL with clean teardown.

---

## 13. Phase 3.2 — Final Security, UX and Production Readiness Audit

### 13.1 Authentication and Token Security Evaluation

| Audit Item | Current Implementation | Security Assessment | Remediation & Production Recommendation |
| :--- | :--- | :--- | :--- |
| **Access Token Storage** | Stored in browser `localStorage` (`attendance_access_token`) and React auth state | **Medium Risk**: Accessible to client-side JavaScript. If an XSS vulnerability occurs, access token can be exfiltrated. Mitigated by short TTL (15 minutes). | Keep access token in-memory only (React Context / state) or deliver via short-lived HttpOnly cookie. |
| **Refresh Token Storage** | Stored in `localStorage` (`attendance_refresh_token`) and also issued as HttpOnly cookie by backend | **High Risk**: Storing the 7-day refresh token in `localStorage` allows rogue JavaScript or malicious dependencies to steal persistent session credentials. | Remove `attendance_refresh_token` from `localStorage`. Rely exclusively on the backend's existing HttpOnly cookie. |
| **JavaScript Token Access** | JS has full synchronous read/write access to `localStorage` tokens | **High Risk**: Defeats HttpOnly cookie protection if token is also stored in `localStorage`. | Eliminate `localStorage` fallback once CORS and cookie transport credentials are wired end-to-end. |
| **Refresh Token Rotation** | Backend strictly verifies SHA-256 hash, expires old token, links `replaced_by_token_id`, and issues new cryptographic pair | **Verified Secure**: Preserves `family_id`, updates `last_used_at`, and rotates both access and refresh tokens. | No backend changes required; rotation functions as designed. |
| **Token Reuse Detection** | If a revoked token is presented to `/api/v1/auth/refresh`, backend immediately revokes all tokens sharing the same `family_id` | **Verified Secure**: Successfully detects replay/theft attacks and terminates the compromised session tree. | Preserved. Frontend race condition fixed (see below). |
| **Simultaneous Refresh Requests** | Previously un-mutexed in `auth-context.tsx`. Concurrent 401s could send identical refresh tokens, triggering false-positive reuse revocation. | **Defect Identified & Resolved**: Added `activeRefreshPromise` deduplication lock in `apps/web/src/lib/auth-context.tsx`. Concurrent callers now share a single in-flight refresh request. | **Fixed**. Verified: Concurrent refreshes no longer trigger premature session termination. |
| **Session Revocation upon Logout** | `POST /api/v1/auth/logout` sets `revoked_at = now`, clears HttpOnly cookie, and frontend clears `tokenStorage` | **Verified Secure**: Refresh token is immediately rejected (HTTP 401) on subsequent attempts. | Preserved. Verified in live test suite. |
| **Expired & Inactive Sessions** | Backend rejects expired JWTs (HTTP 401) and inactive user/tenant accounts (HTTP 401) | **Verified Secure**: Frontend catches 401, clears tokens, and transitions user to login state. | Preserved. |

#### Backend HttpOnly Cookie Transition Analysis
The FastAPI backend *already* implements HttpOnly cookie issuing:
1. `_set_refresh_cookie(response, tokens.refresh_token)` in `services/api/auth/routes.py` sets an HttpOnly, Path-scoped (`path="/api/v1/auth"`) cookie.
2. `refresh_token` and `logout` endpoints accept:
   `raw_token = body.refresh_token if (body and body.refresh_token) else cookie_token`
3. `CORSMiddleware` in `services/api/main.py` is already configured with `allow_credentials=True`.

**Changes required for full HttpOnly transition (without breaking architecture)**:
1. **Frontend Fetch**: Set `credentials: "include"` on `apiFetch` in `apps/web/src/lib/api.ts`.
2. **Frontend Storage**: Delete `REFRESH_TOKEN_KEY` and associated getters/setters in `tokenStorage`. Call `authApi.refresh()` with empty body so browser supplies the cookie.
3. **In-Memory Access Tokens**: Maintain `access_token` strictly in React state or memory closure, rehydrated on page reload via `/auth/refresh`.

---

### 13.2 API Scalability & Enterprise Verification

1. **Department & Designation List Endpoints**:
   - **Pagination**: Backend `GET /api/v1/departments` and `GET /api/v1/designations` support `limit` (max 100) and `offset` with total record counts.
   - **Inactive Filtering**: Supported via `is_active: bool | None` query parameter.
   - **Scalability Limitation (Medium Risk)**: The backend hardcodes `limit: Annotated[int, Query(ge=1, le=100)] = 50`. In the frontend UI, both tabs fetch `{ limit: 100 }` with no pagination controls or search inputs. Enterprise tenants with $>100$ departments or job titles will not see or be able to assign records beyond the first 100 in dropdowns.
   - **Recommendation**: In Phase 5/UI polish, add pagination controls and search inputs to Department and Designation tabs, and increase backend max limit to 500 for taxonomy endpoints or implement asynchronous searchable comboboxes.
2. **Employee Pagination**:
   - **Genuinely Backend-Driven**: Verified. `GET /api/v1/employees` takes `page` and `page_size`, computing SQL `LIMIT :page_size OFFSET (:page - 1) * :page_size` alongside an exact `SELECT COUNT(*)` query.
   - **UI Integration**: Frontend `page.tsx` binds search, status, department, and designation filters to the API call, with pagination controls (`Previous`, `Next`, `Page X of Y`).

---

### 13.3 Frontend Behavior & Browser Testing Limitations Report

> [!IMPORTANT]
> **Explicit Browser Testing Report**:
> In compliance with project guidelines (*"Use browser-based tests if an appropriate browser automation setup is already available. Otherwise clearly report that browser testing was not performed. Do not claim it was tested based only on a successful build"*), automated browser testing using Playwright was **explicitly not performed**.
> - **Technical Limitation**: The execution sandbox is isolated from external internet access; when the browser subagent attempted to initialize Playwright, driver binary download from Azure CDN failed with HTTP 404 / connection refusal.
> - **Alternative Verification**: Verified via end-to-end HTTP integration scripts testing real FastAPI endpoints, Next.js production build analysis (`npm run build`), ESLint type checks, and simulated token refresh/auth cycle tests.
> - **Visual & Responsive Inspection**: Reviewed `apps/web/src/app/organization/page.tsx` CSS styles. The layout includes responsive media queries (`@media (max-width: 768px)`), collapsible table overflow wrappers (`overflow-x: auto`), and grid-to-block adaptations for mobile and tablet form factors.

---

### 13.4 Security & Regression Verification Results

An automated end-to-end security test suite was executed against the running FastAPI application and live Supabase PostgreSQL database (`scratch/verify_security_audit.py`). All 17 verification points passed:

| Test ID | Security Verification Check | Result | Evidence |
| :--- | :--- | :--- | :--- |
| **SEC-01** | Multi-tenant tenant registration (Tenant A & B) | **PASS** | HTTP 201 Created for both isolated tenants |
| **SEC-02** | Department creation in respective tenants | **PASS** | HTTP 201 Created with tenant-scoped UUIDs |
| **SEC-03** | Cross-tenant department retrieval (`GET /departments/{id}`) | **PASS** | HTTP 404 Not Found (zero data leakage) |
| **SEC-04** | Cross-tenant foreign key injection in employee creation | **PASS** | HTTP 400 Bad Request ("Selected department does not exist or does not belong to your organization") |
| **SEC-05** | Employee user authentication with role `employee` | **PASS** | HTTP 200 OK with valid JWT access & refresh tokens |
| **SEC-06** | **Employee Directory Denial**: Employee requests `GET /employees` | **PASS** | **HTTP 403 Forbidden** (strictly enforced by backend dependency `require_permission(Permission.VIEW_EMPLOYEES)`) |
| **SEC-07** | **Employee Creation Denial**: Employee requests `POST /departments` | **PASS** | **HTTP 403 Forbidden** (enforced by `require_permission(Permission.MANAGE_ORGANIZATION)`) |
| **SEC-08** | **Employee Self-Access**: Employee requests `GET /employees/me` | **PASS** | **HTTP 200 OK** (returns authenticated employee profile only) |
| **SEC-09** | Refresh token rotation (`POST /auth/refresh`) | **PASS** | HTTP 200 OK, new access and refresh token issued |
| **SEC-10** | **Refresh Token Reuse Detection**: Replay of old refresh token | **PASS** | **HTTP 401 Unauthorized** ("Refresh token reuse detected. All sessions in this family have been revoked.") |
| **SEC-11** | Token family termination upon reuse detection | **PASS** | HTTP 401 Unauthorized when attempting to use rotated token |
| **SEC-12** | User session logout (`POST /auth/logout`) | **PASS** | HTTP 200 OK, refresh token marked `revoked_at` |
| **SEC-13** | Post-logout refresh token rejection | **PASS** | HTTP 401 Unauthorized |
| **SEC-14** | Zero credentials or secrets exposed in frontend code | **PASS** | Grep scan of `apps/web/src` confirmed 0 secrets (only `NEXT_PUBLIC_API_URL`) |
| **SEC-15** | Phase 2 authentication remains functional | **PASS** | Full login, registration, and session flows intact |
| **SEC-16** | Database migration revision stability | **PASS** | Alembic current confirmed at `e6331816d336 (head)` |
| **SEC-17** | Complete synthetic test data teardown | **PASS** | Pre-migration database row counts verified unchanged (`tenants: 2, users: 2, refresh_tokens: 4, departments: 0, designations: 0, employees: 0`) |

---

### 13.5 Production Readiness Evaluation & Defect Remediation

1. **Defects Found & Remediated**:
   - **Concurrent Token Refresh Race Condition**: Identified that simultaneous 401 responses in the frontend could fire multiple concurrent refresh requests with the same refresh token, tripping backend reuse detection and prematurely killing the user session. **Remediation**: Implemented `activeRefreshPromise` deduplication in `apps/web/src/lib/auth-context.tsx`.
   - **Unlinked Employee User Profile Handling**: Ensured that an employee user without a linked employee record receives a clear 404 prompt to contact HR rather than a blank screen or unhandled exception.
   - **`localStorage` Refresh Token Security Exposure**: Identified that storing refresh tokens in browser `localStorage` created an XSS exposure vector. **Remediation**: Completed full migration to HttpOnly cookies in Phase 3.3.
2. **Remaining Production Considerations**:
   - **Enterprise Taxonomy UI Limits**: Department and Designation tabs currently fetch with `{ limit: 100 }` without dedicated client pagination controls. Recommend adding pagination controls and search filters in Phase 5/UI polish.
3. **Final Recommendation**:
   - **READY FOR PHASE 4**. Phase 3 backend, database migrations, frontend integration, and Phase 3.3 secure HttpOnly cookie migration meet all enterprise security, isolation, and stability criteria.

---

## 14. Phase 3.3 — Secure Refresh Token Migration to HttpOnly Cookies

### 14.1 Objective & Architecture Overview

Phase 3.2 identified that while the FastAPI backend already supported HttpOnly refresh cookies, the frontend was still persisting both access tokens and refresh tokens in `localStorage`. 

In Phase 3.3, we completed the full migration to enterprise-grade cookie authentication:
1. **Zero JavaScript Access to Refresh Tokens**: The refresh token is transmitted strictly via a `Set-Cookie` header with the `HttpOnly` flag. Browser JavaScript cannot read, inspect, or exfiltrate the refresh token.
2. **Strict Cookie Path Scoping**: The cookie `Path` is locked down to `/api/v1/auth`. Business API endpoints (such as `/departments`, `/employees`, `/attendance`) never receive the cookie header in requests, reducing unnecessary token exposure.
3. **In-Memory Access Tokens**: Access tokens are kept strictly in React memory state (`useState` + `useRef` in `AuthContext`). They are never persisted to `localStorage` or `sessionStorage`.
4. **Session Rehydration**: On initial page load or hard refresh, `AuthContext` calls `POST /api/v1/auth/refresh` with an empty JSON body `{}`. The browser automatically includes the HttpOnly cookie, restoring the user's session and in-memory access token seamlessly.
5. **Transparent 401 Re-Authentication & Concurrency Lock**: When an access token expires during active user activity, `apiFetch` catches the 401 response and invokes the registered refresh handler. In-flight refresh requests are deduplicated by an active promise lock (`activeRefreshPromise`), ensuring that concurrent requests never trigger multiple refresh operations or trip reuse detection.
6. **Clean Legacy Token Purge**: An automatic migration utility (`tokenStorage.clearLegacyTokens()`) clears any preexisting tokens from `localStorage` upon page load or login.

---

### 14.2 Backend Cookie & CORS Implementation

#### Cookie Flag Configuration
In `services/api/auth/routes.py`:
- **`HttpOnly=True`**: Prevents document script access via `document.cookie`.
- **`Path=/api/v1/auth`**: Scopes the cookie exclusively to authentication endpoints (`/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/register`).
- **`SameSite=Lax`**: Protects against cross-site request forgery (CSRF) for state-changing cross-site POST requests while allowing top-level navigation.
- **Dynamic `Secure` Flag**:
  ```python
  def _is_cookie_secure() -> bool:
      if settings.ENVIRONMENT == "production":
          return True
      return settings.COOKIE_SECURE
  ```
  - **Development (`ENVIRONMENT="development"`)**: `COOKIE_SECURE=False` is used because local development occurs over plain HTTP (`http://localhost:3000` / `http://127.0.0.1:3000`). Browsers drop cookies configured with `Secure=True` on non-HTTPS origins.
  - **Production (`ENVIRONMENT="production"`)**: Strictly forced to `Secure=True`, guaranteeing tokens are only transmitted over TLS/HTTPS connections.

#### CORS Credential Configuration
In `services/api/main.py` and `services/api/config.py`:
- `CORSMiddleware` is configured with `allow_credentials=True`.
- `CORS_ALLOWED_ORIGINS` includes:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
  - `http://localhost:8000`
  - `http://127.0.0.1:8000`
  - Production origin: `https://app.upostit.com`
- Wildcards (`"*"`) are strictly disallowed when `allow_credentials=True`, satisfying browser CORS specifications.

#### Cookie Clearance on Logout
`_clear_refresh_cookie` in `services/api/auth/routes.py` deletes the cookie with exact matching attributes:
```python
response.delete_cookie(
    key=REFRESH_COOKIE_NAME,
    path="/api/v1/auth",
    httponly=True,
    secure=_is_cookie_secure(),
    samesite=settings.COOKIE_SAMESITE,
)
```

---

### 14.3 Frontend In-Memory & Cookie Integration

#### `apps/web/src/lib/api.ts`
- **Default `credentials: "include"`**: Configured on all `apiFetch` requests so cookies are automatically sent with same-origin and cross-origin CORS requests to the API backend.
- **Removed Storage Methods**: Removed `getAccessToken()`, `setAccessToken()`, `getRefreshToken()`, `setRefreshToken()`, and `clearTokens()`. Added `clearLegacyTokens()` which deletes `attendance_access_token` and `attendance_refresh_token` from `localStorage`.
- **Global 401 Interceptor**:
  - Registered via `setTokenRefreshHandler(handler)`.
  - When a request with an `Authorization` header receives a 401, `apiFetch` attempts a refresh via the handler, updates the header, and retries the request once.
- **Auth API Updates**:
  - `authApi.refresh()` sends `{}` body, letting the browser attach the HttpOnly cookie.
  - `authApi.logout(token)` sends `{}` body with `Authorization: Bearer <token>` and cookie.

#### `apps/web/src/lib/auth-context.tsx`
- **In-Memory State**: Access token stored in `useState<string | null>` and `useRef<string | null>`.
- **De-duplicated Refresh Lock**:
  ```typescript
  let activeRefreshPromise: Promise<string | null> | null = null;
  ```
  Guarantees that multiple concurrent 401s or calls to `executeRefresh()` share a single HTTP request to `/api/v1/auth/refresh`.
- **Mount Initialization (`initAuth`)**: Calls `executeRefresh()` directly to restore the session from the HttpOnly cookie. If no cookie exists, state gracefully resolves to unauthenticated (`token: null`, `user: null`, `isLoading: false`).

---

### 14.4 Verification & Test Results

#### 1. Live End-to-End API Test (`scratch/test_cookie_auth_live.py`)
Executed against live FastAPI and Supabase PostgreSQL with real HTTP cookies:
1. Registration issued `Set-Cookie` with `HttpOnly`, `Path=/api/v1/auth`, `SameSite=lax`.
2. Login issued `Set-Cookie` with `HttpOnly`, `Path=/api/v1/auth`, `SameSite=lax`.
3. Session restoration via `POST /api/v1/auth/refresh` succeeded with empty JSON body.
4. Token rotation issued new HttpOnly cookie and rotated access token.
5. Rotated access token authorized `GET /api/v1/auth/me`.
6. Subsequent cookie refresh succeeded.
7. Logout revoked session in database and sent `Set-Cookie` clearing cookie (`Max-Age=0`).
8. Post-logout refresh rejected with HTTP 401.
9. Database row counts verified unchanged (`tenants: 2, users: 2, refresh_tokens: 4`).
10. Synthetic tenant cleaned up completely.

#### 2. Frontend Unit Test Suite (`apps/web/src/lib/api.test.ts`)
19 tests passing (`make web-test`):
- `credentials: "include"` verified on all requests.
- Cookie-based refresh verified with empty body `{}`.
- Cookie-based logout verified with empty body `{}` and bearer header.
- `clearLegacyTokens` purges legacy keys without error.
- Automatic 401 retry verified on token expiration.

#### 3. Backend & Type Check Verification
- `make test`: 65 passed in pytest.
- `make lint`: Ruff clean, Mypy clean (27 source files).
- `make web-lint`: Clean (0 warnings, 0 errors).
- `make web-build`: Clean production Next.js build.
