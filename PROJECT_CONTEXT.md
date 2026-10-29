# PROJECT_CONTEXT.md — Attendance SaaS Master Project Documentation

> **CRITICAL NOTICE**: This document is the single source of truth for the current state of the Attendance SaaS platform. Every developer and AI coding agent must read this document prior to making any modifications and must update it immediately after completing any meaningful implementation, configuration change, bug fix, architectural decision, or phase milestone.

---

## 1. Project Overview

- **Project Name**: Attendance SaaS
- **Purpose & Vision**: A modern, enterprise-grade multi-tenant attendance and workforce management platform designed to eliminate time fraud (buddy punching, fake GPS, ghost shifts) and streamline attendance-to-payroll workflows.
- **Target Customers**: Small to medium businesses, retail chains, factories, construction firms, educational institutions, and multi-location field operations requiring provable, tamper-resistant employee presence.
- **Core Problems Solved**:
  1. *Buddy Punching*: Eliminated via selfie capture, facial liveness verification, and strict device hardware binding.
  2. *Location Spoofing*: Blocked through PostGIS spatial geofencing (`ST_DWithin`), OS-level mock-location detection, and impossible-travel velocity analysis.
  3. *Unreliable Network Environments*: Solved via client-side offline queues with cryptographic idempotency keys (`client_event_id`) and randomized exponential backoff retry.
  4. *Multi-Tenant Data Leakage*: Enforced at the database engine level via PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`) with per-transaction tenant isolation.
  5. *Payroll Discrepancies*: Streamlined via deterministic attendance session derivation from an immutable, append-only event ledger.
- **Product Scope**:
  - **Web Dashboard**: Next.js 14+ (TypeScript) administrative console for HR, Managers, Owners, and Billing management.
  - **Mobile Application**: Cross-platform employee app (React Native / Expo / Flutter) for geofenced check-in/out, selfie verification, shift review, and leave requests.
  - **Backend API**: High-performance Python 3.12 + FastAPI modular monolith providing REST APIs, authentication, rule evaluation, and integration endpoints.
  - **Future Integrations**: On-premise biometric hardware terminals (HMAC-signed), BLE/NFC office beacons, and edge CCTV gateway stream processing (Python + OpenCV + GStreamer).
- **Current Stage**: **Stage A: Foundation**
- **Current Phase**: **Phase 1 — Project Setup & Monorepo Foundation** (Status: *In Progress*)

---

## 2. Technology Stack

### 2.1 Discovered Environment & Active Toolchain
- **Operating System**: macOS (Darwin 24.3.0)
- **Node.js**: `v24.21.0` (Active on host)
- **npm**: `11.19.0` (Active on host)
- **Python**: `3.13.15` (Host Python runtime) / Target container runtime: `Python 3.12`
- **Git**: `2.39.5` (Apple Git-154)
- **Docker / Docker Compose**: Not installed / not detected in host path (Planned for container orchestration)
- **Supabase CLI**: Not installed on host (Planned for local/remote database migrations)

### 2.2 Planned Stack vs. Implementation Status

| Layer | Planned Technology | Specification & Version | Current Repository Status |
| :--- | :--- | :--- | :--- |
| **Web Frontend** | Next.js | Next.js 14+ (App Router, TypeScript, TailwindCSS/Vanilla CSS) | **Planned** (Directory scaffold pending) |
| **Mobile App** | React Native (Expo) / Flutter | Expo SDK 51+ or Flutter 3.x with native location & camera | **Planned** (Directory scaffold pending) |
| **Backend API** | FastAPI | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) | **Planned** (Directory scaffold pending) |
| **Database** | PostgreSQL + PostGIS | PostgreSQL 16 with PostGIS extension (hosted on Supabase) | **Planned** (Connection Not Yet Verified) |
| **Database Migrations**| Alembic | Alembic 1.13+ async migrations | **Planned** (Directory scaffold pending) |
| **Caching & Rate Limit**| Redis | Redis 7+ (per-tenant rate limiting & entitlement cache) | **Planned** (Pending Docker setup) |
| **Background Jobs** | Celery | Celery 5.3+ with Redis broker for reports & notifications | **Planned** (Directory scaffold pending) |
| **Object Storage** | S3-Compatible / MinIO | MinIO locally, Supabase Storage / AWS S3 in production | **Planned** (Pending Docker setup) |
| **Testing** | pytest, Vitest | pytest, pytest-asyncio, httpx, Vitest | **Planned** (Test runners pending) |
| **CI/CD** | GitHub Actions | Automated linting, type-checking, cross-tenant test suite | **Planned** (Workflow file pending) |
| **Monitoring** | Sentry & OpenTelemetry | Error logging, performance traces, database connection alerts | **Planned** (Phase 13) |

---

## 3. Architecture

### 3.1 Repository Structure
The repository is structured as a modular monorepo:

```text
/Users/apple/Upostit/
├── apps/
│   ├── web/                # Next.js administrative dashboard (Owners, HR, Managers)
│   └── mobile/             # Cross-platform mobile app for employee punch & selfie capture
├── services/
│   ├── api/                # FastAPI modular monolith (auth, tenants, attendance, fraud, payroll)
│   ├── workers/            # Celery asynchronous worker tasks
│   └── edge/               # On-premise CCTV / Biometric hardware edge gateway (Phase 16)
├── packages/
│   └── contracts/          # Shared Pydantic / OpenAPI schema definitions
├── database/
│   └── migrations/         # Alembic database migration revisions
├── infra/                  # Docker Compose, PgBouncer, Nginx, deployment scripts
├── tests/                  # Cross-cutting integration, security, and cross-tenant tests
├── docs/                   # System documentation (RULES.md, ARCHITECTURE.md, PHASE_*.md)
├── PROJECT_CONTEXT.md      # Master project documentation & phase tracker (Single Source of Truth)
├── Makefile                # Developer workflow commands (make up, make test)
└── .env.example            # Environment variable template with safe placeholders
```

### 3.2 Component Communication Flows
- **Web & Mobile to FastAPI**:
  - Standard REST/JSON over HTTPS.
  - State mutation calls (e.g. `POST /punches`) require `Authorization: Bearer <JWT>` and an `X-Client-Event-Id` UUID header for idempotency.
- **FastAPI to Supabase PostgreSQL**:
  - Asynchronous connection pool using SQLAlchemy 2 with `asyncpg`.
  - Every connection checks out with `SET LOCAL app.tenant_id = :tenant_id` inside an isolated transaction.
  - Connects using a non-superuser database role without `BYPASSRLS`.
- **Redis Responsibilities**:
  - Sub-second caching of tenant subscription entitlements (`tenant:{tenant_id}:features`).
  - Sliding-window rate limiting per IP and per tenant.
  - Celery task message broker and result storage.
- **Celery Responsibilities**:
  - Processing long-running bulk employee CSV/XLSX imports.
  - Multi-channel notification delivery (Expo push, email, SMS).
  - Nightly attendance session recomputations and payroll batch calculations.
- **MinIO / S3 Storage Responsibilities**:
  - Tenant-isolated object paths: `/{tenant_id}/selfies/...`, `/{tenant_id}/exports/...`, `/{tenant_id}/payslips/...`.

### 3.3 Architecture Diagrams

```mermaid
graph TD
    subgraph Clients ["Client Applications"]
        Web["Web Dashboard (Next.js)"]
        Mobile["Mobile App (Expo/Flutter)"]
        Edge["Edge Gateway (Biometric/CCTV)"]
    end

    subgraph API_Layer ["API Layer"]
        FastAPI["FastAPI Modular Monolith"]
        RLS_MW["Tenant Context Middleware"]
    end

    subgraph Async_Tier ["Async & Cache Tier"]
        Redis["Redis (Rate Limit, Cache, Queue)"]
        Celery["Celery Task Workers"]
    end

    subgraph Storage_Tier ["Persistence & Storage Tier"]
        DB["Supabase PostgreSQL 16 + PostGIS (RLS Enforced)"]
        MinIO["MinIO / S3 (Tenant-Prefixed Storage)"]
    end

    Web -->|HTTPS REST| FastAPI
    Mobile -->|HTTPS REST + Idempotency UUID| FastAPI
    Edge -->|HMAC Signed REST| FastAPI

    FastAPI --> RLS_MW
    RLS_MW -->|SET LOCAL app.tenant_id + SQL| DB
    FastAPI -->|Check Entitlements & Rate Limit| Redis
    FastAPI -->|Enqueue Tasks| Redis
    Redis --> Celery
    Celery -->|Read/Write Data| DB
    Celery -->|Store Export Files & Payslips| MinIO
    FastAPI -->|Upload Selfies| MinIO
```

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee Mobile App
    participant API as FastAPI Backend
    participant Redis as Redis Cache
    participant DB as Supabase PostgreSQL (RLS)
    participant S3 as MinIO / S3 Storage

    Employee->>API: POST /punches (JWT, Location, Selfie, client_event_id)
    API->>API: Verify JWT signature & extract tenant_id, user_id
    API->>Redis: Check per-tenant & per-device rate limit
    alt Rate Limit Exceeded
        API-->>Employee: 429 Too Many Requests (Retry-After header)
    end
    API->>S3: Upload check-in selfie to /{tenant_id}/selfies/...
    API->>DB: BEGIN Transaction
    API->>DB: SET LOCAL app.tenant_id = :tenant_id
    API->>DB: Check idempotency (client_event_id)
    alt Already Processed
        API->>DB: COMMIT (Return existing event record)
        API-->>Employee: 200 OK (Idempotent replay)
    else New Event
        API->>DB: Validate PostGIS geofence ST_DWithin(location, workplace.geog)
        API->>DB: Evaluate fraud rules (mock GPS, clock drift, device binding)
        API->>DB: INSERT into attendance_events (Append-Only)
        API->>DB: Execute pure calculation engine -> Upsert attendance_days
        API->>DB: INSERT into audit_log
        API->>DB: COMMIT Transaction
        API-->>Employee: 201 Created (Punch confirmed, derived session status)
    end
```

---

## 4. Database Documentation

- **Database Provider**: Supabase PostgreSQL 16.
- **Connection Method**: Asynchronous connection via `asyncpg` with transaction-scoped tenant context (`SET LOCAL app.tenant_id`).
- **Connection Status**: **NOT YET VERIFIED** (Pending staging/production credentials from repository owner).
- **PostGIS Extension**: **NOT YET VERIFIED** (Required for spatial geofencing in Phase 4).
- **Existing Schemas & Tables in Remote DB**: Unknown / unverified until credentials are provided.
- **Target Schemas & Table Roadmap**:
  - `public.tenants` (Phase 2): Tenant organization record, subdomain slug, status.
  - `public.users` (Phase 2): Global user authentication records, email, password hash (Argon2id).
  - `public.memberships` (Phase 2): Join table mapping users to tenants with specific RBAC roles (`owner`, `admin`, `hr`, `manager`, `employee`).
  - `public.refresh_tokens` (Phase 2): Cryptographically secure rotating session tokens.
  - `public.audit_log` (Phase 3): Append-only audit trail capturing user, action, entity, delta JSON, client IP, timestamp.
  - `public.tenant_settings` (Phase 3): Time zone, week start day, language, date format.
  - `public.feature_flags` (Phase 3): Tenant-specific feature overrides.
  - `public.employees` (Phase 4): Employee profile, employee code, contact info, status.
  - `public.departments` (Phase 4): Organizational departments.
  - `public.locations` (Phase 4): Work locations with PostGIS `geography(Point, 4326)` and geofence radius.
  - `public.employee_locations` (Phase 4): M:N mapping of employees to authorized workplaces.
  - `public.import_jobs` (Phase 4): Background CSV/Excel import tracking.
  - `public.shift_templates` (Phase 5): Shift schedules, grace periods, break rules, overnight flags.
  - `public.shift_assignments` (Phase 5): Employee/team shift calendar assignments.
  - `public.attendance_events` (Phase 5): **Append-only ledger** of punch actions (`IN`, `OUT`, `BREAK_START`, `BREAK_END`).
  - `public.attendance_days` (Phase 5): Deterministically calculated daily attendance summary (present, late, early exit, overtime).
  - `public.devices` (Phase 7): Registered mobile hardware devices bound to employees.
  - `public.fraud_rules` & `public.fraud_flags` (Phase 7): Risk scoring definitions and flagged suspicious punches.
  - `public.selfies` (Phase 7): Check-in selfie metadata and liveness match scores.
  - `public.correction_requests` & `public.approvals` (Phase 8): Correction workflow requests and multi-tier manager approvals.
  - `public.attendance_daily_summary` (Phase 8): Pre-aggregated daily reporting table.
  - `public.leave_types`, `leave_balances`, `leave_requests` (Phase 9): Leave management and holiday schedules.
  - `public.notification_templates` & `notifications` (Phase 10): Notification preferences and dispatch queue.
  - `public.plans`, `subscriptions`, `invoices` (Phase 11): Billing tiers, Stripe/Razorpay customer subscriptions.
  - `public.api_keys` & `webhooks` (Phase 12): Developer API access and external webhook subscriptions.
  - `public.salary_structures`, `payroll_runs`, `payslips` (Phase 14): Payroll calculation runs and PDF payslips.
  - `public.terminal_devices` & `biometric_enrolments` (Phase 15): On-premise biometric hardware registry.
- **Mandatory RLS Policy Template**:
  ```sql
  ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;
  ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;

  CREATE POLICY tenant_isolation ON <table_name>
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
  ```
- **Indexing Rules**:
  - Every tenant-scoped table must feature a composite index beginning with `tenant_id` (e.g. `CREATE INDEX idx_emp_tenant_status ON employees(tenant_id, status)`).
  - Spatial indexes on `locations` must use GiST: `CREATE INDEX idx_locations_geog ON locations USING GIST(geog)`.

---

## 5. Features and Implementation Status

### 5.1 Completed & Verified
- [x] Repository Git initialization.
- [x] Master Project Documentation (`PROJECT_CONTEXT.md`) created with all 12 mandatory sections.
- [x] Core engineering rules documented (`docs/RULES.md`).
- [x] System architecture & data model documented (`docs/ARCHITECTURE.md`).
- [x] Phase 1 specification and acceptance tracker established (`docs/PHASE_01.md`).

### 5.2 Implemented but Not Yet Verified
- None. (Zero code changes will be marked implemented without concrete verification).

### 5.3 In Progress
- **Phase 1 — Project Setup & Monorepo Foundation**:
  - Scaffolding monorepo directory hierarchy (`apps/`, `services/`, `packages/`, `database/`, `infra/`, `tests/`).
  - Containerization setup (`docker-compose.yml` for Postgres+PostGIS, Redis, MinIO).
  - FastAPI skeleton with `/health` endpoint and OpenAPI documentation.
  - Web & Mobile starter shells.
  - Standardized Makefile and safe `.env.example`.

### 5.4 Planned for Future Phases
- Phase 2: Auth and Tenants (Argon2, JWT, RLS middleware, RBAC roles).
- Phase 3: Platform Basics (Audit log service, tenant settings, UTC helpers, Redis rate limiter).
- Phase 4: Employees & Workplaces (PostGIS geofences, CSV import worker, invites).
- Phase 5: Shifts & Punch Engine (Append-only events, pure rule engine, idempotency).
- Phase 6: Mobile Check-in (Offline queue, geofence check, retry jitter).
- Phase 7: Fraud Shield v1 (Device binding, selfie capture, mock GPS detection, risk score).
- Phase 8: Corrections and Reports (Correction approvals, async CSV/XLSX exports).
- Phase 9: Leave and Overtime (Leave balances, holiday calendars, overtime thresholds).
- Phase 10: Notifications (Expo push, email, SMS, Celery retries).
- Phase 11: Plans and Billing (Subscription tiers, feature gating, Stripe/Razorpay webhooks).
- Phase 12: Admin & Onboarding (Setup wizard, super-admin console, support impersonation, API keys).
- Phase 13: Load Test & Launch Prep (k6 load testing, PgBouncer, Sentry, restore drills).
- Phase 14: Payroll (Salary structures, statutory tax configs, PDF payslips).
- Phase 15: Face & Devices (Biometric hardware credentials, HMAC signing, face templates).
- Phase 16: CCTV Edge Pilot (Edge gateway, OpenCV/GStreamer, local buffer, RTSP).
- Phases 17–22: Advanced enterprise presence challenges, BLE/NFC proximity, anomaly ML, enterprise SSO/SCIM, external HRIS integrations, and multi-region high availability.

### 5.5 Known Bugs, Limitations & Technical Debt
- *Toolchain limitation*: Docker is not currently installed on the host macOS machine; containerized local runs will require Docker Desktop or an external cloud development database.
- *Database credentials*: Supabase PostgreSQL connection details have not yet been provided by the project owner.

---

## 6. API Documentation

### 6.1 Implemented Endpoints
*No endpoints are deployed yet. Scaffolding is scheduled in Phase 1.*

### 6.2 Planned Immediate Endpoints (Phase 1)
- `GET /health`
  - **Purpose**: System liveness and dependency readiness probe.
  - **Auth**: None (Public).
  - **Response (200 OK)**:
    ```json
    {
      "status": "healthy",
      "timestamp": "2026-10-30T01:50:00Z",
      "version": "0.1.0",
      "services": {
        "database": "connected",
        "redis": "connected"
      }
    }
    ```
- `GET /docs` & `GET /redoc`
  - **Purpose**: Interactive OpenAPI specification and documentation.
  - **Auth**: None (Public).

### 6.3 Required Environment Variables (Planned)
- `DATABASE_URL`: Connection string for PostgreSQL (e.g. `postgresql+asyncpg://app_user:placeholder@db.supabase.co:5432/postgres`).
- `REDIS_URL`: Connection string for Redis instance (e.g. `redis://localhost:6379/0`).
- `JWT_SECRET_KEY`: High-entropy 256-bit secret string for signing access tokens.
- `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_BUCKET`: Object storage configuration.

---

## 7. Security and Reliability

- **Authentication & Authorization**: Planned for Phase 2 using Argon2id password hashing, 15-minute JWTs with rotating database-backed refresh tokens, and server-side RBAC decorators.
- **Multi-Tenant Isolation**: Enforced via PostgreSQL `FORCE ROW LEVEL SECURITY`. Every tenant query is scoped to `app.tenant_id`. Cross-tenant tests will be built to verify that data access across tenant boundaries is strictly impossible.
- **Secret Management**: Zero secrets committed to version control. Configuration managed strictly via environment variables.
- **Audit Logging**: Every mutating action (create, update, delete) writes an immutable record to `audit_log` detailing `user_id`, `tenant_id`, `entity_type`, `entity_id`, before/after JSON diffs, client IP, and UTC timestamp.
- **Rate Limiting**: Tiered rate limits enforced by Redis token buckets (per IP for public routes, per tenant for authenticated routes).
- **Known Risks & Mitigations**:
  - *Risk*: Database connection pool exhaustion under morning punch spikes.
  - *Mitigation*: Implementation of PgBouncer connection pooling and client-side retry jitter in Phase 13.
  - *Risk*: Loss of offline punch data during device crash.
  - *Mitigation*: Durable on-device SQLite transaction queues with client-generated UUID keys.

---

## 8. Environment and Setup

### 8.1 Prerequisites
- **Node.js**: >= 20.0.0 (Host: v24.21.0)
- **Python**: >= 3.12 (Host: 3.13.15)
- **Git**: Installed
- **Docker & Docker Compose**: Recommended for local dependencies (PostgreSQL, Redis, MinIO)

### 8.2 Standard Commands (Makefile Targets)
```bash
# Start all local infrastructure and application services
make up

# Stop all running containers
make down

# Execute all automated test suites (pytest + Vitest)
make test

# Run linter and type-checker across all monorepo modules
make lint
```

### 8.3 Safe Environment Configuration Template
```bash
# --- Application Environment ---
ENVIRONMENT=development
LOG_LEVEL=info
SECRET_KEY=change-this-insecure-default-key-32-chars-min

# --- Supabase / PostgreSQL ---
DATABASE_URL=postgresql+asyncpg://postgres:placeholder_password@localhost:5432/attendance_saas
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# --- Redis & Celery ---
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# --- Object Storage (MinIO / S3) ---
STORAGE_ENDPOINT=http://localhost:9000
STORAGE_ACCESS_KEY=placeholder_access_key
STORAGE_SECRET_KEY=placeholder_secret_key
STORAGE_BUCKET=attendance-assets
STORAGE_USE_SSL=false
```

---

## 9. Testing and Quality

### 9.1 Test Execution Record
| Date | Test Suite / Command | Scope | Actual Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **2026-10-30** | `git status` | Git repository initialization | **Passed** | Empty repo initialized cleanly. |
| **2026-10-30** | `docs` verification | Consistency check across docs | **Passed** | `RULES.md`, `ARCHITECTURE.md`, `PHASE_01.md`, and `PROJECT_CONTEXT.md` verified consistent. |

### 9.2 Blocked or Skipped Tests
- *Backend & Frontend unit test suites*: Skipped pending code scaffolding in next Phase 1 tasks.
- *Supabase live connection probe*: Blocked awaiting database credentials from owner.

---

## 10. Phase Tracker (22 Phases)

| Phase | Stage | Name & Core Objective | Status | Completion Criteria & Evidence |
| :---: | :--- | :--- | :---: | :--- |
| **01** | Stage A | **Project Setup & Monorepo Foundation** | **In Progress** | Monorepo layout, Docker Compose, FastAPI skeleton (`/health`), Next.js & Expo starters, CI, `PROJECT_CONTEXT.md`. |
| **02** | Stage A | **Auth and Tenants** | **Not Started** | Tenant registration, Argon2, JWT tokens, RBAC permissions, RLS migration helper, cross-tenant leak tests. |
| **03** | Stage A | **Platform Basics** | **Not Started** | Audit logging service, tenant settings, UTC helpers, feature flags, Redis rate limiter middleware. |
| **04** | Stage B | **Employees & Workplaces** | **Not Started** | Employee CRUD, departments, PostGIS locations (`ST_DWithin`), CSV import Celery worker, invite flow. |
| **05** | Stage B | **Shifts and Punch Engine** | **Not Started** | Shift templates, append-only `attendance_events`, pure calculation engine deriving `attendance_days`, idempotency. |
| **06** | Stage B | **Mobile Check-in** | **Not Started** | Expo mobile app, geofence verification, offline queue, randomized jitter retry, status screen. |
| **07** | Stage B | **Fraud Shield v1** | **Not Started** | Device binding, check-in selfie capture, mock GPS detection, clock drift check, risk score calculation. |
| **08** | Stage B | **Corrections and Reports** | **Not Started** | Missed punch correction workflow, approval hierarchy, async CSV/XLSX export, pre-aggregated summaries. |
| **09** | Stage C | **Leave and Overtime** | **Not Started** | Leave balances, accrual rules, holiday calendars, overtime rate multipliers. |
| **10** | Stage C | **Notifications** | **Not Started** | Expo push alerts, transactional email, SMS/WhatsApp channel dispatching, Celery retries, quiet hours. |
| **11** | Stage C | **Plans and Billing** | **Not Started** | Tiered subscription plans (Free/Standard/Pro), employee usage counters, Stripe/Razorpay webhook idempotency. |
| **12** | Stage C | **Admin and Onboarding** | **Not Started** | Self-serve onboarding wizard, super-admin console, audited support 'view-as' sessions, customer API keys. |
| **13** | Stage D | **Load Test and Launch Prep** | **Not Started** | k6 load tests (2,000 punches/min), PgBouncer connection pooling, Sentry/OpenTelemetry, disaster recovery drills. |
| **14** | Stage E | **Payroll Engine** | **Not Started** | Salary structures, statutory tax deductions, payroll run locking, PDF payslip generation. |
| **15** | Stage E | **Face and Biometric Terminals** | **Not Started** | On-premise biometric terminal integration, HMAC signed requests, face template consent and deletion. |
| **16** | Stage E | **CCTV Edge Pilot** | **Not Started** | Standalone edge gateway (`services/edge`), RTSP/ONVIF ingestion, local SQLite buffering, accuracy pilot report. |
| **17** | Stage E | **Random In-Shift Presence Checks** | **Not Started** | Configurable random selfie presence challenges during active shift to prevent phone-left-behind fraud. |
| **18** | Stage E | **Workplace Beacon & NFC Proximity**| **Not Started** | Physical office proximity verification via BLE beacons and NFC touchpoints. |
| **19** | Stage E | **Advanced Anomaly & Risk ML** | **Not Started** | Machine learning risk scoring for abnormal location jumps, repeated coordinates, and punch velocity. |
| **20** | Stage E | **Enterprise SSO & Directory Sync** | **Not Started** | SAML 2.0 / OIDC enterprise Single Sign-On and SCIM directory user synchronization. |
| **21** | Stage E | **HRIS & ERP Integration Hub** | **Not Started** | Pre-built bi-directional connectors for Workday, SAP, BambooHR, and public developer webhooks. |
| **22** | Stage E | **Multi-Region HA & Disaster Recovery**| **Not Started** | Multi-region read replicas, active-passive failover orchestration, and automated annual compliance audit drills. |

---

## 11. Change History

### [2026-10-30] — Phase 1: Repository & Master Documentation Inception
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**:
  - Initialized git repository.
  - Established Master Project Documentation (`PROJECT_CONTEXT.md`) with all 12 mandatory sections.
  - Created strict engineering and multi-tenancy rules (`docs/RULES.md`).
  - Created system architecture, component diagrams, and data models (`docs/ARCHITECTURE.md`).
  - Initialized Phase 1 progress and acceptance tracker (`docs/PHASE_01.md`).
- **Affected Files**:
  - `PROJECT_CONTEXT.md` (Created)
  - `docs/RULES.md` (Created)
  - `docs/ARCHITECTURE.md` (Created)
  - `docs/PHASE_01.md` (Created)
- **Architectural Decisions (ADR)**:
  - *ADR-001*: Multi-tenancy enforced at the database layer using PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`) with `SET LOCAL app.tenant_id = :tenant_id` per-request transaction scoping.
  - *ADR-002*: Attendance events ledger (`attendance_events`) is strictly append-only. Daily attendance statuses (`attendance_days`) are derived deterministically via a pure calculation engine.
  - *ADR-003*: All punch requests must provide client-generated UUIDs (`X-Client-Event-Id`) for idempotency during retries.
- **Database Status**: Supabase PostgreSQL connection recorded as **Not Yet Verified** (awaiting credentials).
- **Tests Executed**: Git workspace verification and documentation consistency audit passed.

---

## 12. Next Actions

1. **Immediate Task**: Await owner review and approval of `PROJECT_CONTEXT.md` and Phase 1 documentation baseline.
2. **Next Implementation Steps (Phase 1)**:
   - Scaffold the monorepo directory skeleton:
     - `apps/web/`
     - `apps/mobile/`
     - `services/api/`
     - `services/workers/`
     - `services/edge/`
     - `packages/contracts/`
     - `database/migrations/`
     - `infra/`
     - `tests/`
   - Create root `Makefile` (`make up`, `make down`, `make test`, `make lint`).
   - Create `.env.example` with sanitized placeholders.
   - Implement initial FastAPI app skeleton in `services/api` with `GET /health` and OpenAPI documentation.
   - Configure GitHub Actions CI workflow in `.github/workflows/ci.yml`.
3. **Decisions & Blockers Requiring Owner Approval**:
   - Provide Supabase development project connection string (or confirm local Docker PostgreSQL preference).
   - Confirm mobile framework preference between React Native (Expo) and Flutter.
