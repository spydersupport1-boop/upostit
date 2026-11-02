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
  - **Mobile Application**: **Flutter (Android & iOS)** native cross-platform employee app written in Dart for geofenced check-in/out, selfie verification, shift review, and leave requests.
  - **Backend API**: High-performance Python 3.12 + FastAPI modular monolith providing REST APIs, authentication, rule evaluation, and integration endpoints.
  - **Future Integrations**: On-premise biometric hardware terminals (HMAC-signed), BLE/NFC office beacons, and edge CCTV gateway stream processing (Python + OpenCV + GStreamer).
- **Current Stage**: **Stage B: Attendance Core**
- **Current Phase**: **Phase 4 — Employees & Workplaces (Locations, Geofencing, Batch Import & Invites)** (Status: *Phase 4 Fully Complete across all 5 Milestones on branch `phase-04`; Live Supabase database revision `d7a42e88b301`; All frontend interfaces integrated with FastAPI backend without mock data; 172 backend pytest tests passing, 36 frontend tests passing, ESLint 0 warnings/errors, Ruff & Mypy 0 errors in 41 files, production Next.js build succeeding with 7/7 static routes; Awaiting user approval before beginning Phase 5*)

---

## 2. Technology Stack

### 2.1 Discovered Environment & Active Toolchain
- **Operating System**: macOS (Darwin 24.3.0)
- **Node.js**: `v24.21.0` (Active on host)
- **npm**: `11.19.0` (Active on host)
- **Python**: `3.13.15` (Host Python runtime) / Target container runtime: `Python 3.12`
- **Git**: `2.39.5` (Apple Git-154)
- **Flutter SDK**: Installable via `brew install --cask flutter` or direct download; Dart 3.x runtime.
- **Docker / Docker Compose**: Used for local Redis and MinIO (host-dependent; local or CI container runner).

### 2.2 Stack Component Matrix

| Layer | Selected Technology | Specification & Version | Current Repository Status |
| :--- | :--- | :--- | :--- |
| **Web Frontend** | Next.js | Next.js 14+ (App Router, TypeScript) | **Implemented** (Starter shell created) |
| **Mobile App** | **Flutter** | Flutter 3.x+ (Dart, Feature-based architecture) | **Implemented** (Starter shell created) |
| **Backend API** | FastAPI | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 | **Implemented** (FastAPI app & health endpoints created) |
| **Database** | Supabase PostgreSQL + PostGIS | PostgreSQL 16 with PostGIS extension (hosted on Supabase) | **Implemented** (Verification script created; connection pending live credentials) |
| **Database Migrations**| Alembic | Alembic 1.13+ async migrations targeting Supabase | **Implemented** (Alembic configuration initialized) |
| **Caching & Rate Limit**| Redis | Redis 7+ (per-tenant rate limiting & entitlement cache) | **Implemented** (Docker Compose definition ready) |
| **Background Jobs** | Celery | Celery 5.3+ with Redis broker for reports & notifications | **Implemented** (Worker skeleton & smoke test created) |
| **Object Storage** | MinIO / S3-Compatible | MinIO locally, Supabase Storage / AWS S3 in production | **Implemented** (Docker Compose definition ready) |
| **Testing** | pytest, Vitest | pytest, pytest-asyncio, httpx, Vitest | **Implemented** (Test suite scaffolding active) |
| **CI/CD** | GitHub Actions | Automated linting, type-checking, cross-tenant test suite | **Implemented** (GitHub Actions workflow created) |
| **Monitoring** | Sentry & OpenTelemetry | Error logging, performance traces, database connection alerts | **Planned** (Phase 13) |

---

## 3. Architecture

### 3.1 Repository Structure
```text
/Users/apple/Upostit/
├── apps/
│   ├── web/                # Next.js 14+ administrative dashboard (Owners, HR, Managers)
│   └── mobile/             # Flutter (Dart) mobile app for Android & iOS (Welcome screen, configurable API)
├── services/
│   ├── api/                # FastAPI modular monolith (Health, Readiness, DB connection verification)
│   ├── workers/            # Celery asynchronous worker tasks & smoke test
│   └── edge/               # On-premise CCTV / Biometric hardware edge gateway (Phase 16 placeholder)
├── packages/
│   └── contracts/          # Shared Pydantic / OpenAPI schema definitions
├── database/
│   └── migrations/         # Alembic database migration revisions
├── infra/                  # Docker Compose (Redis & MinIO only; no local Postgres), PgBouncer, Nginx
├── tests/                  # Cross-cutting integration, security, and cross-tenant tests
├── docs/                   # System documentation (RULES.md, ARCHITECTURE.md, PHASE_01.md)
├── PROJECT_CONTEXT.md      # Master project documentation & phase tracker (Single Source of Truth)
├── README.md               # Quickstart guide, Flutter setup, and architectural overview
├── Makefile                # Developer workflow commands (make up, make test, make lint)
├── .env.example            # Environment variable template with safe placeholders
└── .gitignore              # Strict ignore rules for secrets, virtual environments, and build artifacts
```

### 3.2 Component Communication Flows
- **Flutter & Web to FastAPI**:
  - Standard REST/JSON over HTTPS.
  - Flutter app reads API base URL via `--dart-define=API_BASE_URL=...` or defaults to `http://localhost:8000`.
  - State mutation calls (e.g. `POST /punches`) require `Authorization: Bearer <JWT>` and an `X-Client-Event-Id` UUID header for idempotency.
- **FastAPI to Supabase PostgreSQL**:
  - Asynchronous connection pool using SQLAlchemy 2 with `asyncpg`.
  - Reads `DATABASE_URL` strictly from the local environment (`.env`).
  - Every connection transaction sets `SET LOCAL app.tenant_id = :tenant_id`.
  - Connects using a non-superuser database role without `BYPASSRLS`.
- **Redis Responsibilities**:
  - Sub-second caching of tenant subscription entitlements (`tenant:{tenant_id}:features`).
  - Sliding-window rate limiting per IP and per tenant.
  - Celery task message broker and result storage.
- **Celery Responsibilities**:
  - Processing long-running bulk employee CSV/XLSX imports.
  - Multi-channel notification delivery (FCM/APNs push notifications, email, SMS).
  - Nightly attendance session recomputations and payroll batch calculations.
- **MinIO / S3 Storage Responsibilities**:
  - Tenant-isolated object paths: `/{tenant_id}/selfies/...`, `/{tenant_id}/exports/...`, `/{tenant_id}/payslips/...`.

### 3.3 Architecture Diagrams

```mermaid
graph TD
    subgraph Clients ["Client Applications"]
        Web["Web Dashboard (Next.js 14+)"]
        Mobile["Mobile App (Flutter - Android & iOS)"]
        Edge["Edge Gateway (Biometric/CCTV)"]
    end

    subgraph API_Layer ["API Layer"]
        FastAPI["FastAPI Modular Monolith"]
        RLS_MW["Tenant Context Middleware"]
    end

    subgraph Async_Tier ["Async & Cache Tier (Docker Compose)"]
        Redis["Redis (Rate Limit, Cache, Queue)"]
        Celery["Celery Task Workers"]
    end

    subgraph Storage_Tier ["Persistence & Storage Tier"]
        DB["Supabase PostgreSQL 16 + PostGIS (RLS Enforced)"]
        MinIO["MinIO / S3 Storage (Tenant-Prefixed Storage)"]
    end

    Web -->|HTTPS REST| FastAPI
    Mobile -->|HTTPS REST + Idempotency UUID| FastAPI
    Edge -->|HMAC Signed REST| FastAPI

    FastAPI --> RLS_MW
    RLS_MW -->|SQLAlchemy 2 Async + asyncpg + SET LOCAL app.tenant_id| DB
    FastAPI -->|Check Entitlements & Rate Limit| Redis
    FastAPI -->|Enqueue Tasks| Redis
    Redis --> Celery
    Celery -->|Read/Write Data| DB
    Celery -->|Store Export Files & Payslips| MinIO
    FastAPI -->|Upload Selfies| MinIO
```

---

## 4. Database Documentation

- **Database Provider**: Supabase PostgreSQL 16.
- **Connection Method**: Asynchronous connection via `asyncpg` with transaction-scoped tenant context (`SET LOCAL app.tenant_id`).
- **Connection Status**:
  - **Supabase Project Endpoint**: **VERIFIED & ACTIVE** (Probed project `qnkgndfzuhrjuopzlcxy` via REST API; returned HTTP 200 OK with clean public schema).
  - **Direct PostgreSQL Connection**: **TESTED & VERIFIED** (Connected successfully via SQLAlchemy 2 async engine with `asyncpg`; safe `SELECT 1` executed and passed).
  - **PostGIS Capability**: **VERIFIED & ACTIVE** (`SELECT postgis_full_version();` executed and confirmed available for spatial geofencing).
  - Diagnostic test script: [`services/api/verify_db.py`](file:///Users/apple/Upostit/services/api/verify_db.py) (Executed via `make verify-db`, exited code 0).
- **PostGIS Extension**: Enabled and verified in Supabase PostgreSQL instance.
- **Existing Schemas & Tables in Remote DB**: Preserved completely. Zero modifications, drops, or table creations performed in Phase 1.
- **Mandatory RLS Policy Template**:
  ```sql
  ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;
  ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;

  CREATE POLICY tenant_isolation ON <table_name>
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
  ```

---

## 5. Features and Implementation Status

### 5.1 Completed & Verified
- [x] Repository Git initialization (`main` branch).
- [x] Master Project Documentation ([`PROJECT_CONTEXT.md`](file:///Users/apple/Upostit/PROJECT_CONTEXT.md)) with all 12 mandatory sections.
- [x] Strict engineering rules documented ([`docs/RULES.md`](file:///Users/apple/Upostit/docs/RULES.md)).
- [x] System architecture & data model documented ([`docs/ARCHITECTURE.md`](file:///Users/apple/Upostit/docs/ARCHITECTURE.md)).
- [x] Phase 1 specification and tracker updated ([`docs/PHASE_01.md`](file:///Users/apple/Upostit/docs/PHASE_01.md)).
- [x] Comprehensive [`README.md`](file:///Users/apple/Upostit/README.md) with Flutter setup instructions.
- [x] `.gitignore` established protecting `.env`, `.venv`, and build artifacts.
- [x] Monorepo directory structure established.
- [x] Backend FastAPI application created with `/health` and `/ready` endpoints.
- [x] Safe Supabase connectivity verification utility (`services/api/verify_db.py`).
- [x] Next.js 14+ responsive web starter shell (`apps/web/`).
- [x] Flutter mobile starter shell (`apps/mobile/`) with responsive welcome screen, accessible controls, and configurable API base URL.
- [x] Docker Compose configured for Redis and MinIO only (`infra/docker-compose.yml`).
- [x] Celery worker task module and smoke test (`services/workers/`).
- [x] Alembic migration configuration initialized (`database/migrations/`).
- [x] Standardized `Makefile` and `.env.example`.
- [x] GitHub Actions CI workflow (`.github/workflows/ci.yml`).
- [x] Supabase Project REST API connectivity verified (HTTP 200 OK for `qnkgndfzuhrjuopzlcxy`).
- [x] Direct Supabase PostgreSQL connection verified via `asyncpg` (`SELECT 1` passed).
- [x] PostGIS extension enabled and capability verified (`SELECT postgis_full_version();` passed).

### 5.2 Implemented but Not Yet Verified
- None. (All Phase 1 foundational features and connection probes verified with test evidence).

### 5.3 In Progress
- **Phase 1 — Project Setup & Monorepo Foundation**: Completing acceptance runs and awaiting project owner review.

### 5.4 Planned for Future Phases
- Phase 2: Auth and Tenants (Argon2, JWT, RLS middleware, RBAC roles).
- Phase 3: Platform Basics (Audit log service, tenant settings, UTC helpers, Redis rate limiter).
- Phase 4: Employees & Workplaces (PostGIS geofences, CSV import worker, invites).
- Phase 5: Shifts & Punch Engine (Append-only events, pure rule engine, idempotency).
- Phase 6: Mobile Check-in (Flutter geofence check, offline queue, retry jitter).
- Phase 7: Fraud Shield v1 (Device binding, selfie capture, mock GPS detection, risk score).
- Phase 8: Corrections and Reports (Correction approvals, async CSV/XLSX exports).
- Phase 9: Leave and Overtime (Leave balances, holiday calendars, overtime thresholds).
- Phase 10: Notifications (Push alerts via FCM/APNs, email, SMS, Celery retries).
- Phase 11: Plans and Billing (Subscription tiers, feature gating, Stripe/Razorpay webhooks).
- Phase 12: Admin & Onboarding (Setup wizard, super-admin console, support impersonation, API keys).
- Phase 13: Load Test & Launch Prep (k6 load testing, PgBouncer, Sentry, restore drills).
- Phase 14: Payroll (Salary structures, statutory tax configs, PDF payslips).
- Phase 15: Face & Devices (Biometric hardware credentials, HMAC signing, face templates).
- Phase 16: CCTV Edge Pilot (Edge gateway, OpenCV/GStreamer, local buffer, RTSP).
- Phases 17–22: Advanced enterprise presence challenges, BLE/NFC proximity, anomaly ML, enterprise SSO/SCIM, external HRIS integrations, and multi-region high availability.

### 5.5 Known Bugs, Limitations & Technical Debt
- *Database Credentials*: The live Supabase instance has not yet been connected because `.env` is absent on the host. When `.env` is created, `python services/api/verify_db.py` will test and confirm connectivity.

---

## 6. API Documentation

### 6.1 Implemented Endpoints
- `GET /health`
  - **Purpose**: Lightweight liveness probe for load balancers and orchestrators.
  - **Auth**: None (Public).
  - **Response (200 OK)**:
    ```json
    {
      "status": "ok",
      "timestamp": "2026-10-30T02:00:00Z",
      "service": "attendance-api",
      "version": "0.1.0"
    }
    ```
- `GET /ready`
  - **Purpose**: Deep readiness probe verifying database and cache subsystem connectivity.
  - **Auth**: None (Public).
  - **Response (200 OK / 503 Service Unavailable)**:
    ```json
    {
      "status": "ready",
      "checks": {
        "database": "connected",
        "postgis": "available",
        "redis": "connected"
      }
    }
    ```
- `GET /docs` & `GET /redoc`
  - **Purpose**: Interactive OpenAPI specification and documentation.
  - **Auth**: None (Public).

---

## 7. Security and Reliability

- **Authentication & Authorization**: Planned for Phase 2 using Argon2id password hashing, 15-minute JWTs with rotating database-backed refresh tokens, and server-side RBAC decorators.
- **Multi-Tenant Isolation**: Enforced via PostgreSQL `FORCE ROW LEVEL SECURITY`. Every tenant query is scoped to `app.tenant_id`.
- **Secret Management**: Zero secrets committed to version control. Configuration managed strictly via environment variables.
- **Audit Logging**: Every mutating action writes an immutable record to `audit_log` detailing `user_id`, `tenant_id`, `entity_type`, `entity_id`, before/after JSON diffs, client IP, and UTC timestamp.
- **Rate Limiting**: Tiered rate limits enforced by Redis token buckets.

---

## 8. Environment and Setup

### 8.1 Prerequisites
- **Node.js**: `>= 20.0.0` (Host: `v24.21.0`)
- **Python**: `>= 3.12` (Host: `3.13.15`)
- **Flutter SDK**: `>= 3.19.0` (Dart `>= 3.3.0`)
- **Git**: Installed
- **Docker & Docker Compose**: Used for local Redis and MinIO

### 8.2 Standard Commands (Makefile Targets)
```bash
# Start Redis and MinIO local infrastructure
make up

# Stop running containers
make down

# Execute automated test suites (pytest)
make test

# Run linter and type-checker across backend
make lint
```

### 8.3 Safe Environment Configuration Template ([`.env.example`](file:///Users/apple/Upostit/.env.example))
```bash
# --- Application Environment ---
ENVIRONMENT=development
LOG_LEVEL=info
SECRET_KEY=change-this-insecure-default-key-32-chars-min
API_PORT=8000

# --- Supabase PostgreSQL Connection ---
# Replace with your actual Supabase connection string in local .env (never commit .env)
DATABASE_URL=postgresql+asyncpg://postgres:placeholder_password@db.placeholder-ref.supabase.co:5432/postgres
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5

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

# --- Mobile & Web Client Configuration ---
API_BASE_URL=http://localhost:8000
```

---

## 9. Testing and Quality

### 9.1 Test Execution Record
| Date | Test Suite / Command | Scope | Actual Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **2026-10-30** | `git status --short`, `git log -5` | Git repository & baseline state | **Passed** | Clean repository baseline; untracked `.env` strictly ignored. |
| **2026-10-30** | `git ls-files --error-unmatch .env` | Secret isolation & git tracking | **Passed (Exit code 1)** | Confirmed `.env` is completely untracked by Git; zero secrets exposed. |
| **2026-10-30** | `make verify-db` (Step 1) | Supabase Project REST API | **Passed (HTTP 200)** | Probed endpoint `https://qnkgndfzuhrjuopzlcxy.supabase.co`; verified project active. |
| **2026-10-30** | `make verify-db` (Step 2) | Direct PostgreSQL connection | **Passed (SELECT 1)** | Safe query executed via SQLAlchemy 2 async engine with `asyncpg`. |
| **2026-10-30** | `make verify-db` (Step 3) | PostGIS spatial capability | **Passed (Operational)**| `SELECT postgis_full_version();` executed and confirmed available. |
| **2026-10-30** | `make test` (`pytest tests/ -v`) | Backend API health & readiness unit tests | **Passed (4/4)** | 4 passed in 5.70s (0 failed, 0 skipped). |
| **2026-10-30** | `make lint` (`ruff check`) | Backend Python code linter | **Passed (Clean)** | All checks passed across `services/`, `packages/`, `tests/`. |
| **2026-10-30** | `make lint` (`mypy services/api/`) | Backend static type checker | **Passed (Clean)** | Success: no issues found in 5 source files. |
| **2026-10-30** | Live ASGI probe `/health` & `/ready` | FastAPI live endpoint verification | **Passed (HTTP 200)** | `/health` returned 200 OK; `/ready` returned 200 OK (`database: connected`, `postgis: PostGIS available`). |
| **2026-10-30** | `make celery-smoke` | Celery configuration smoke test | **Passed** | Task `attendance.ping` registered; direct invocation returned `'pong'`. |
| **2026-10-30** | Celery live broker connection | Redis task queue consumer | **Blocked** | Local Redis container not running; Docker is not installed on host machine. |
| **2026-10-30** | `npm run build` in `apps/web/` | Next.js production build | **Passed** | Next.js 14.2.5 compiled successfully; static pages generated (4/4). |
| **2026-10-30** | `npm run lint` in `apps/web/` | Web ESLint validation | **Passed** | `✔ No ESLint warnings or errors`. |
| **2026-10-30** | `npx tsc --noEmit` in `apps/web/` | Web TypeScript compilation | **Passed** | Exited code 0 with zero type errors. |
| **2026-10-30** | `.venv/bin/alembic current` & `heads`| Alembic migration loader | **Passed** | Loaded root `alembic.ini` and PostgreSQL migration environment cleanly (`PostgresqlImpl`). |
| **2026-10-30** | Flutter host binary check | `which flutter`, `which dart` | **Blocked** | `flutter` and `dart` not installed on host macOS (`brew install --cask flutter` needed). |
| **2026-10-30** | Flutter mobile code inspection | Mobile app architecture & security | **Passed** | Valid entrypoint, welcome screen, compile-time `--dart-define=API_BASE_URL`, real widget test. |
| **2026-10-30** | Docker host binary check | `which docker`, `which docker-compose` | **Blocked** | `docker` not installed on host macOS; container execution blocked locally. |
| **2026-10-30** | `make lint` (`ruff check` & `mypy`) | Phase 2 Auth & Multi-Tenancy code quality | **Passed (Clean)** | Ruff & Mypy clean across all 17 source files. |
| **2026-10-30** | `make test` (`pytest tests/ -v`) | Phase 2 Auth, RBAC, Schemas, Security & Isolation | **Passed (34/34)** | 34 passed in 6.92s (0 failed, 0 skipped). |
| **2026-10-30** | `alembic upgrade head` | Live Supabase migration execution | **Passed** | Revision `4f61a7dd311e` applied; created `tenants`, `users`, `refresh_tokens`, RLS policies, bootstrap function. |
| **2026-10-30** | Live RLS isolation probe | Real PostgreSQL RLS enforcement with `SET LOCAL ROLE authenticated` | **Passed (100%)** | Tenant A cannot see Tenant B users; illegal cross-tenant insert strictly rejected by RLS policy violation. |
| **2026-10-30** | Live bootstrap probe | `register_tenant_bootstrap(...)` function execution on Supabase | **Passed (100%)** | Atomic tenant, owner, and refresh session token created; verified returned JSON. |
| **2026-10-30** | E2E HTTP API Journey Verification | Full HTTP API flow via FastAPI against live Supabase DB | **Passed (100%)** | Verified registration (201), login (200), `/me` (200), `/tenants/current` (200), refresh rotation & reuse detection (401), logout (200), logout-all (200), cross-tenant isolation, and complete DB cleanup. |
| **2026-10-31** | `alembic upgrade head --sql` | Phase 3 migration offline validation | **Passed** | Revision `e6331816d336` generated & validated offline with composite tenant foreign keys on departments, designations, employees, and users. |
| **2026-10-31** | `make test` (`pytest tests/ -v`) | Phase 3 Remediation: Self-access, Deactivation cascade, RBAC, Schemas | **Passed (65/65)** | 65 passed in 6.58s (0 failed, 0 skipped). 31 Phase 3 tests added/hardened. |
| **2026-10-31** | `make lint` (`ruff check` & `mypy`) | Phase 3 Organization & Employee code quality | **Passed (Clean)** | Ruff clean across `services/`, `packages/`, `tests/`; Mypy clean across 27 source files. |
| **2026-10-31** | `npm run lint` & `npm run build` | Next.js Organization & Employee dashboard + API client foundation | **Passed** | Next.js 14.2.5 compiled successfully; `/organization` static route (11.9 kB) created. 0 ESLint errors. |
| **2026-11-01** | `alembic upgrade head` | Live Supabase Phase 3 migration execution | **Passed** | Revision `e6331816d336` applied live. Created `departments`, `designations`, `employees`, 5 composite FKs, composite unique constraints, forced RLS. Pre-migration records preserved. |
| **2026-11-01** | Live Schema & Constraint Probe | Direct PostgreSQL system catalog query on Supabase | **Passed (100%)** | Verified `departments`, `designations`, `employees` exist, composite foreign keys active, `RLS_ENABLED=True, FORCE_RLS=True` active, isolation policies active. |
| **2026-11-01** | Live Functional & Cross-Tenant Probe | Synthetic test tenants on live Supabase | **Passed (100%)** | Verified same-tenant relationships, circular dept-manager FK, nullable relationships, cross-tenant FK blocked (`IntegrityError`), RLS cross-tenant isolation verified. Clean cleanup confirmed. |
| **2026-11-01** | Live E2E Phase 2 & Phase 3 Regression | Full FastAPI HTTP API flows against live Supabase | **Passed (100%)** | Registration (201), login (200), `/me` (200), refresh rotation & reuse detection (401), logout (200), Phase 3 department/designation/employee CRUD (201/200), clean cleanup verified. |
| **2026-11-01** | Phase 3.3 HttpOnly Cookie Migration & Concurrency Lock | Live E2E API tests & frontend unit tests | **Passed (100%)** | Zero localStorage tokens; refresh token in HttpOnly cookie (`Path=/api/v1/auth`, `SameSite=lax`); access token in React memory; reload rehydration verified; active promise concurrency lock; 10/10 live checks passed, 19/19 web tests passed. |
| **2026-11-02** | `alembic upgrade b7d41a89c204` | Phase 4 Milestone 1 live Supabase migration | **Passed** | Applied `b7d41a89c204` to live Supabase; verified `locations` and `employee_locations`, PostGIS generated coordinates, `excl_emp_primary_workplace_overlap` exclusion constraint (`btree_gist`), forced RLS, 96 backend tests passed. |
| **2026-11-02** | Phase 4 Milestone 2 Workplace Assignments | Workplace assignment CRUD & self-access | **Passed** | Implemented workplace assignments, employee self-access endpoint, roster listings, single primary workplace constraint with historical preservation, 122 backend tests passed. |
| **2026-11-02** | Phase 4 Milestone 3 Bulk Employee Import | CSV/XLSX parsing, Celery task, storage service, chunking & retry idempotency | **Passed (100%)** | Implemented `import_jobs` table, composite tenant FK `(tenant_id, created_by_user_id) -> users(tenant_id, id)` with column-specific `ON DELETE SET NULL (created_by_user_id)` (PostgreSQL 17 compliant), forced RLS, unapplied migration `c8e52a91f034` (offline verified). Storage service with tenant-isolated S3/MinIO paths and strict production durability (`STORAGE_ALLOW_MEMORY_FALLBACK=False`); CSV & XLSX parser; 100-row chunk processing in Celery worker task; chunk transaction rollback protection; checkpoint bookmarking `last_processed_row_index`; `with_for_update()` concurrency locking; safe broker failure recovery (HTTP 503); spreadsheet formula injection sanitization; failure CSV generation. 151 backend tests passed (100%), 19 frontend tests passed, Ruff clean, Mypy clean. |
| **2026-11-02** | `alembic upgrade c8e52a91f034` | Phase 4 Milestone 3 live Supabase migration & verification | **Passed (100%)** | Applied `c8e52a91f034` to live Supabase; verified `import_jobs` table, 18 columns, 4 indexes, forced RLS, tenant isolation policy, cross-tenant isolation, composite FK `ON DELETE SET NULL (created_by_user_id)` preserving `tenant_id` on user deletion, 151 backend tests (100%), 19 frontend tests (100%), Ruff clean, Mypy clean. |

---

## 10. Phase Tracker (22 Phases)

| Phase | Stage | Name & Core Objective | Status | Completion Criteria & Evidence |
| :---: | :--- | :--- | :--- | :--- |
| **01** | Stage A | **Project Setup & Monorepo Foundation** | **Audited** | Monorepo layout, Next.js web build (passed), Flutter starter (ready), FastAPI (`/health`, `/ready` passed), Supabase PostgreSQL + PostGIS verified, Alembic loader verified, CI workflow (4 jobs). Docker & Flutter CLI blocked on host tooling. Conditionally ready for Phase 2. |
| **02** | Stage A | **Auth and Tenants** | **Complete** | Tenant registration, Argon2id, JWT access & refresh tokens with rotation and reuse detection, RBAC permissions (5 roles), transaction-scoped `app.tenant_id`, RLS migration `4f61a7dd311e` executed on Supabase, 34 automated unit/API tests passing, live PostgreSQL RLS isolation verified 100%. |
| **03** | Stage A | **Organization Structure & Employee Management** | **Complete** | Departments, Designations, Employee profiles & lifecycle (CRUD, search, filtering, pagination), RBAC matrix, `GET /employees/me` self-access, directory denial for employee role, synchronized user deactivation & session revocation, composite tenant foreign keys, typed API client, Next.js `/organization` dashboard, Phase 3.3 secure HttpOnly cookie migration (zero localStorage tokens, memory access tokens, in-flight promise lock), 65 backend tests, 19 web tests passing. Migration `e6331816d336` applied and verified live on Supabase. |
| **04** | Stage B | **Employees & Workplaces** | **In Progress** | Milestone 1 (`b7d41a89c204` live), Milestone 2 (workplace assignments), and Milestone 3 (`c8e52a91f034` live, bulk employee import, Celery chunks) complete. 151 backend tests and 19 frontend tests passing. Awaiting owner authorization to begin Milestone 4. |
| **05** | Stage B | **Shifts and Punch Engine** | **Not Started** | Shift templates, append-only `attendance_events`, pure calculation engine deriving `attendance_days`, idempotency. |
| **06** | Stage B | **Mobile Check-in (Flutter)** | **Not Started** | Flutter mobile app, geofence verification, offline queue, randomized jitter retry, status screen. |
| **07** | Stage B | **Fraud Shield v1** | **Not Started** | Device binding, check-in selfie capture, mock GPS detection, clock drift check, risk score calculation. |
| **08** | Stage B | **Corrections and Reports** | **Not Started** | Missed punch correction workflow, approval hierarchy, async CSV/XLSX export, pre-aggregated summaries. |
| **09** | Stage C | **Leave and Overtime** | **Not Started** | Leave balances, accrual rules, holiday calendars, overtime rate multipliers. |
| **10** | Stage C | **Notifications** | **Not Started** | Mobile push alerts (FCM/APNs), transactional email, SMS/WhatsApp channel dispatching, Celery retries, quiet hours. |
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

### [2026-11-02] — Phase 4 — Milestone 4: Employee Invitations & Account Activation
- **Phase**: Phase 4 Milestone 4 (Employee Invitations & Account Activation)
- **Summary**:
  - Implemented `EmployeeInvitation` SQLAlchemy model and migration `d7a42e88b301_phase_04_employee_invitations.py` (`down_revision = 'c8e52a91f034'`).
  - Enforced tenant-safe composite foreign keys: `fk_invitations_employee` (`(tenant_id, employee_id) -> employees(tenant_id, id) ON DELETE CASCADE`) and `fk_invitations_user` (`(tenant_id, invited_by_user_id) -> users(tenant_id, id) ON DELETE SET NULL (invited_by_user_id)`).
  - Enforced database-level partial unique index: `uq_invitations_active_employee` on `(tenant_id, employee_id) WHERE status = 'pending'`, strictly preventing concurrent or duplicate active invitations per employee.
  - Enforced PostgreSQL Row-Level Security (`ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;`) with tenant isolation policy and role permissions.
  - Built pluggable `EmailDeliveryService` abstraction (`services/api/common/email.py`) supporting SMTP, safe development preview, and in-memory test queue with PII-safe masking (`mask_email`) and zero raw-token logging in production.
  - Implemented full administrative invitation lifecycle API (`POST /api/v1/employees/{id}/invite`, `GET /api/v1/invitations`, `GET /api/v1/invitations/{id}`, `POST /api/v1/invitations/{id}/resend`, `POST /api/v1/invitations/{id}/revoke`), restricted to authorized Owner, Admin, and HR users via `Permission.INVITE_EMPLOYEES`.
  - Implemented secure public account activation API (`GET /api/v1/auth/invitations/validate`, `POST /api/v1/auth/invitations/activate`):
    - Concurrency row-locking via `with_for_update()`.
    - Maximum 5 failed attempts lockout (returns HTTP 429).
    - Single-use token enforcement; token hashes only (SHA-256), never storing raw tokens.
    - Password hashing using enterprise Argon2id implementation (`services/api/auth/security.py`).
    - Atomic transaction: user record creation, `employee.user_id` linkage, invitation status update to `accepted`, and revocation of any other outstanding invitations.
    - Strict cross-tenant isolation and email spoofing prevention.
  - Added 21 automated tests in `tests/test_phase4_invitations.py` covering valid/expired/revoked/reused tokens, lockout, spoofing, concurrent activation, RBAC, and cross-tenant access. All 172 backend tests and 19 frontend tests passing.
  - Validated offline Alembic SQL upgrade and downgrade without applying migration to live Supabase.
- **Affected Files**:
  - `database/migrations/versions/d7a42e88b301_phase_04_employee_invitations.py`
  - `database/migrations/env.py`
  - `services/api/config.py`
  - `services/api/common/email.py`
  - `services/api/common/__init__.py`
  - `services/api/employees/models.py`
  - `services/api/employees/__init__.py`
  - `services/api/employees/invitation_schemas.py`
  - `services/api/employees/invitation_service.py`
  - `services/api/employees/invitation_routes.py`
  - `services/api/employees/routes.py`
  - `services/api/auth/routes.py`
  - `services/api/main.py`
  - `tests/test_phase4_invitations.py`
  - `PROJECT_CONTEXT.md`

### [2026-11-01] — Phase 3.3: Secure Refresh Token Migration to HttpOnly Cookies
- **Phase**: Phase 3.3 (Security Hardening — HttpOnly Cookie Migration)
- **Summary**:
  - Removed all token persistence from browser `localStorage`. Replaced with `tokenStorage.clearLegacyTokens()` to purge historical keys.
  - Migrated refresh token transport exclusively to HttpOnly cookies scoped to `Path=/api/v1/auth` with `SameSite=lax`.
  - Configured dynamic cookie `Secure` flag: enforced `True` in production, controlled by `settings.COOKIE_SECURE` in development for HTTP `localhost` compatibility.
  - Retained access tokens strictly in React memory (`useState` + `useRef` in `AuthContext`), preventing script access to persistent tokens.
  - Enabled automatic session rehydration on page reload via `POST /api/v1/auth/refresh` sending an empty JSON body `{}` with the browser-managed HttpOnly cookie.
  - Implemented transparent 401 interception in `apiFetch` via `setTokenRefreshHandler`: seamlessly refreshes expired access tokens and replays requests without user interruption.
  - Prevented token race conditions and premature reuse detection triggering via an in-flight promise lock (`activeRefreshPromise`).
  - Preserved logout and session revocation behavior: `POST /api/v1/auth/logout` revokes the refresh token family in the database and dispatches `Set-Cookie` with `Max-Age=0` and matching path/attributes to wipe the cookie.
  - Updated CORS configuration in `services/api/config.py` to support `http://127.0.0.1:3000` alongside `localhost` with `allow_credentials=True`.
  - Executed 10/10 live API tests against FastAPI + Supabase PostgreSQL; 19 frontend unit tests; 65 backend tests; verified clean database row counts and Alembic head.
- **Affected Files**:
  - `services/api/auth/routes.py`
  - `services/api/config.py`
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/auth-context.tsx`
  - `apps/web/src/lib/api.test.ts`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-01] — Phase 3.1: Complete Frontend API Integration
- **Phase**: Phase 3.1 (Organization Frontend API Integration)
- **Summary**:
  - Connected the Next.js Organization workspace (`/organization`) to the live FastAPI backend with zero mock data.
  - Implemented multi-tenant session management (`AuthProvider`, `useAuth`) supporting token storage, refresh rotation, and inline authentication with tenant slug.
  - Connected full CRUD operations for Departments (list, create, edit, activate/deactivate, manager appointment).
  - Connected full CRUD operations for Designations (list, create, edit, activate/deactivate).
  - Connected Employee Directory with real backend search, multi-field filtering, pagination, creation, editing, and dedicated status patching.
  - Implemented robust error handling unpacking Pydantic validation errors, unauthorized (401), and forbidden (403) states.
  - Enforced employee self-access security (`VIEW_OWN_PROFILE`): employee-role users are denied access to the full employee directory and automatically routed to their own personal profile via `GET /employees/me`.
  - Added 15 frontend automated tests in `apps/web/src/lib/api.test.ts` (`make web-test`); verified Next.js ESLint (`make web-lint`), Next.js production build (`make web-build`), backend tests (`make test`, 65 passed), and backend lint (`make lint`).
  - Executed end-to-end live HTTP tests against running FastAPI and Supabase database with 100% pass and verified teardown.
- **Affected Files**:
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/auth-context.tsx`
  - `apps/web/src/lib/providers.tsx`
  - `apps/web/src/lib/api.test.ts`
  - `apps/web/src/app/organization/page.tsx`
  - `apps/web/src/app/layout.tsx`
  - `apps/web/src/app/globals.css`
  - `apps/web/package.json`
  - `Makefile`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-01] — Phase 3: Live Supabase Database Migration & Verification
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Successfully executed approved live migration `e6331816d336_phase_03_org_structure_and_employees.py` against live Supabase PostgreSQL.
  - Verified live schema: tables `departments`, `designations`, and `employees` created with composite unique constraints and composite tenant foreign keys.
  - Confirmed `RLS_ENABLED=True` and `FORCE_RLS=True` active on all 3 tables with parametric isolation policies.
  - Verified same-tenant relationships, circular department manager FK, nullable relationships, and cross-tenant FK blocking (`IntegrityError`) directly against Supabase.
  - Verified Phase 2 and Phase 3 HTTP API regression journeys with 100% pass rate.
  - Cleaned up all synthetic verification data cleanly; confirmed pre-migration row counts (`tenants`: 2, `users`: 2, `refresh_tokens`: 4) 100% preserved.
- **Affected Files**:
  - `database/migrations/versions/e6331816d336_phase_03_org_structure_and_employees.py`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-10-31] — Phase 3: Audit Findings Remediation
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Remediated employee self-access: Introduced `VIEW_OWN_PROFILE`, removed `VIEW_EMPLOYEES` from default `employee` role, implemented `GET /api/v1/employees/me` returning authenticated worker profile only, blocked employee URL ID manipulation (`/employees/{id}` returns 403 Forbidden).
  - Remediated employee deactivation & account access: Synchronized deactivation in `update_employee_status` to set linked `users.status = 'inactive'` and revoke all active refresh tokens in `refresh_tokens` transactionally. Subsequent login and token refresh attempts return HTTP 401. Reactivation restores `users.status = 'active'`.
  - Implemented composite tenant-aware foreign keys: Added `(tenant_id, id)` composite foreign keys and unique constraints across `departments.manager_id`, `employees.department_id`, `employees.designation_id`, `employees.reporting_manager_id`, and `employees.user_id`. Added `uq_employees_tenant_user_id` constraint. Verified offline migration SQL via Alembic.
  - Implemented frontend API client foundation in `apps/web/src/lib/api.ts` with centralized URL config (`NEXT_PUBLIC_API_URL`), bearer authorization, strongly-typed DTOs, and error handling.
  - Expanded automated test suite from 57 to 62 tests; all passing. Ruff, Mypy, Next.js lint, and Next.js production build clean.
- **Affected Files**:
  - `services/api/auth/permissions.py`
  - `services/api/auth/models.py`
  - `services/api/employees/models.py`
  - `services/api/employees/service.py`
  - `services/api/employees/routes.py`
  - `services/api/organization/models.py`
  - `database/migrations/versions/e6331816d336_phase_03_org_structure_and_employees.py`
  - `apps/web/src/lib/api.ts`
  - `tests/test_phase3_rbac.py`
  - `tests/test_phase3_api.py`
  - `tests/test_phase3_business_rules.py`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-10-30] — Phase 3: Organization Structure & Employee Management
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Implemented multi-tenant domain models for `Department`, `Designation`, and `Employee` with tenant scoping, unique codes/names, and foreign key relations.
  - Implemented Department and Designation management with activation/deactivation toggles and department manager references.
  - Implemented comprehensive Employee profiles (`employee_id`, `first_name`, `last_name`, `work_email`, `phone_number`, `department_id`, `designation_id`, `reporting_manager_id`, `employment_type`, `joining_date`, `status`, `work_location`).
  - Implemented Employee lifecycle management: creation, retrieval, updates, status transitions (`active`, `inactive`, `on_leave`, `terminated`), and soft deactivation.
  - Implemented employee search across name, ID, and email with multi-criteria filtering and pagination.
  - Expanded RBAC system with 6 new permissions (`manage_organization`, `view_organization`, `create_employees`, `view_employees`, `update_employees`, `deactivate_employees`) across 5 roles (`owner`, `admin`, `hr`, `manager`, `employee`).
  - Created Alembic migration `e6331816d336_phase_03_org_structure_and_employees.py` including DDL for `departments`, `designations`, `employees`, table-level RLS policies, and grants to `authenticated, service_role`.
  - Offline-validated migration SQL via `alembic upgrade head --sql`.
  - Implemented modern Next.js 14+ UI under `/organization` with Overview statistics, searchable and filterable Employee Directory, Department Management, Designation Management, and modal dialogs.
  - Added 18 new automated tests (52 total) covering schemas, RBAC permissions, and API endpoints; Ruff clean; Mypy clean; Next.js production build clean.
  - Reconciled Phase 3 scope differences with roadmap documentation in `docs/PHASE_03.md`.
- **Affected Files**:
  - `services/api/auth/permissions.py`
  - `services/api/organization/__init__.py`
  - `services/api/organization/models.py`
  - `services/api/organization/schemas.py`
  - `services/api/organization/service.py`
  - `services/api/organization/routes.py`
  - `services/api/employees/__init__.py`
  - `services/api/employees/models.py`
  - `services/api/employees/schemas.py`
  - `services/api/employees/service.py`
  - `services/api/employees/routes.py`
  - `services/api/main.py`
  - `database/migrations/env.py`
  - `database/migrations/versions/e6331816d336_phase_03_org_structure_and_employees.py`
  - `tests/test_phase3_schemas.py`
  - `tests/test_phase3_rbac.py`
  - `tests/test_phase3_api.py`
  - `apps/web/src/app/organization/page.tsx`
  - `apps/web/src/app/globals.css`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-10-30] — Phase 2: Authentication & Multi-Tenant Foundation
- **Phase**: Phase 2 (Auth and Tenants)
- **Summary**:
  - Implemented multi-tenant domain models for `Tenant`, `User`, and `RefreshToken` with UUID primary keys and UTC timestamps.
  - Implemented Argon2id password hashing and validation with RFC 9106 parameters.
  - Implemented short-lived JWT access tokens (15-min) with verified claims (`sub`, `tenant_id`, `role`, `jti`, `iss`, `aud`).
  - Implemented rotating refresh tokens (7-day) with family-based reuse detection and session revocation.
  - Implemented centralized RBAC with 5 roles (`owner`, `admin`, `hr`, `manager`, `employee`) and deny-by-default capabilities.
  - Implemented transaction-scoped tenant context injection (`SELECT set_config('app.tenant_id', :tenant_id, true)`) and `SET LOCAL ROLE authenticated`.
  - Created Alembic migration `4f61a7dd311e_phase_02_auth_and_multitenancy.py` containing table DDL, RLS policies, and `SECURITY DEFINER` registration bootstrap function `register_tenant_bootstrap`.
  - Added comprehensive automated test suite (34 passed tests) covering security, schemas, RBAC, API routes, and cross-tenant isolation.
  - Updated documentation (`docs/PHASE_02.md`, `PROJECT_CONTEXT.md`, `.env.example`).
- **Affected Files**:
  - `services/api/config.py`
  - `services/api/database.py`
  - `services/api/requirements.txt`
  - `services/api/auth/__init__.py`
  - `services/api/auth/models.py`
  - `services/api/auth/permissions.py`
  - `services/api/auth/schemas.py`
  - `services/api/auth/security.py`
  - `services/api/auth/service.py`
  - `services/api/auth/dependencies.py`
  - `services/api/auth/routes.py`
  - `services/api/tenants/__init__.py`
  - `services/api/tenants/models.py`
  - `services/api/tenants/schemas.py`
  - `services/api/tenants/routes.py`
  - `services/api/main.py`
  - `database/migrations/env.py`
  - `database/migrations/versions/4f61a7dd311e_phase_02_auth_and_multitenancy.py`
  - `tests/test_auth_security.py`
  - `tests/test_auth_schemas.py`
  - `tests/test_rbac.py`
  - `tests/test_auth_api.py`
  - `tests/test_cross_tenant_isolation.py`
  - `.env.example`
  - `docs/PHASE_02.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-02] — Phase 4 Milestone 2: Employee Workplace Assignments Complete
- **Phase**: Phase 4 (Employees & Workplaces)
- **Summary**:
  - Implemented complete employee workplace assignment backend architecture without requiring new database migrations or schema alterations.
  - Endpoints delivered:
    - `POST /api/v1/employees/{employee_id}/workplaces`: Assigns a workplace to an active employee with primary status, date validity checks, duplicate prevention, and overlapping primary conflict checks.
    - `GET /api/v1/employees/{employee_id}/workplaces`: Lists paginated workplace assignments for an employee with current-effectiveness filtering.
    - `GET /api/v1/employees/me/workplaces`: Employee self-access endpoint strictly resolving calling user context (`VIEW_OWN_PROFILE`), rejecting client-supplied IDs.
    - `PUT /api/v1/employees/{employee_id}/workplaces/{assignment_id}`: Updates primary status or assignment dates; checks for conflicting primary assignments without silently modifying other assignments.
    - `DELETE /api/v1/employees/{employee_id}/workplaces/{assignment_id}`: Safely ends an assignment by updating `effective_to` (defaults to today or specified date), preserving historical audit logs without hard deleting records.
    - `GET /api/v1/locations/{location_id}/employees`: Lists employees assigned to a workplace location with search, pagination, and primary/current filtering.
  - Security & RBAC:
    - OWNER, ADMIN, and HR authorized to mutate assignments via `Permission.UPDATE_EMPLOYEES`.
    - MANAGER restricted to read-only access (`Permission.VIEW_EMPLOYEES`, `Permission.VIEW_LOCATIONS`).
    - EMPLOYEE restricted to own workplaces via `/employees/me/workplaces` (`Permission.VIEW_OWN_PROFILE`).
    - Strict tenant isolation enforced in all queries.
  - Error Handling:
    - Application-level and database-level constraint handling translating `excl_emp_primary_workplace_overlap`, `uq_emp_loc_assignment`, and `chk_emp_loc_dates` to clean HTTP 409/400 errors.
  - Quality & Regression:
    - Added 26 unit and integration tests (`tests/test_phase4_workplace_assignments.py`); verified 122 backend tests pass, clean Ruff, clean Mypy (33 files), 19 frontend tests pass, and clean ESLint.
- **Affected Files**:
  - `services/api/locations/schemas.py`
  - `services/api/locations/assignment_service.py`
  - `services/api/employees/routes.py`
  - `services/api/locations/routes.py`
  - `tests/test_phase4_workplace_assignments.py`
  - `docs/PHASE_04_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-02] — Phase 4 Milestone 1: Live Supabase Migration Applied & Verified (b7d41a89c204)
- **Phase**: Phase 4 (Employees & Workplaces)
- **Summary**:
  - Pre-migration validation: Confirmed branch `phase-04`, working tree clean, live Alembic revision `e6331816d336`, tables `locations` and `employee_locations` absent, baseline records intact (2 tenants, 2 users, 4 tokens, 0 depts/designations/employees). PostGIS 3.3.7 verified installed and `btree_gist` 1.7 verified available.
  - Applied migration `b7d41a89c204_phase_04_workplace_locations_and_geofences` to live Supabase PostgreSQL via `alembic upgrade b7d41a89c204`. Alembic current verified at `b7d41a89c204 (head)`.
  - Verified live schema:
    - Tables: `locations` and `employee_locations` created.
    - Security: PostgreSQL RLS enabled and forced (`relrowsecurity=True`, `relforcerowsecurity=True`) with `tenant_isolation` policies on both tables.
    - Foreign keys: Composite tenant-aware FKs `(tenant_id, employee_id) -> employees(tenant_id, id)` and `(tenant_id, location_id) -> locations(tenant_id, id)` with `ON DELETE CASCADE`.
    - Check constraints: Lat [-90, 90], Lon [-180, 180], Radius [10, 50000], and date sequence (`effective_to >= effective_from`).
    - Spatial & PostGIS: Generated column `coordinates geography(Point, 4326) GENERATED ALWAYS AS (st_setsrid(st_makepoint(longitude, latitude), 4326)::geography) STORED` with GiST spatial index `ix_locations_spatial`.
    - Exclusion constraint: `excl_emp_primary_workplace_overlap` on `(tenant_id WITH =, employee_id WITH =, daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]'::text) WITH &&)` where `is_primary = true` using `btree_gist`.
  - Executed comprehensive live functional tests inside rolled back transactions:
    - Workplace location created, automatically generating PostGIS point `POINT(77.6744 12.9249)`.
    - Cross-tenant isolation verified under RLS `authenticated` role (cross-tenant select returned 0 rows).
    - Database check constraints rejected invalid coordinates (lat 95.0, lon 195.0) and invalid radius (5m).
    - Geofence distance verification confirmed inside point (11m, within geofence) vs outside point (1117m, outside geofence).
    - Assignment overlap tests: Non-overlapping primary workplaces accepted; overlapping primary workplaces rejected with `ExclusionViolation`; non-primary overlapping workplaces accepted; multiple open-ended primary workplaces rejected.
    - All temporary rows rolled back; verified 0 remaining rows in `locations`, `employee_locations`, and `employees`.
  - Executed full regression suite: 96 backend tests passed, Ruff clean, Mypy clean (32 files), 19 frontend tests passed, Next.js ESLint clean.
- **Affected Files**:
  - `docs/PHASE_04_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-02] — Phase 4: Milestone 1 Complete (Database Foundation & Workplace Locations)
- **Phase**: Phase 4 (Employees & Workplaces)
- **Summary**:
  - Implemented `Location` and `EmployeeLocation` SQLAlchemy models with composite tenant foreign keys, lat/long/radius check constraints, JSONB Wi-Fi BSSID/IP lists, temporal exclusion constraint (`excl_emp_primary_workplace_overlap` using `btree_gist` and `daterange`) preventing overlapping primary workplace assignments across all dates, and partial unique index (`uq_emp_active_primary_location`) for active primary lookups.
  - Generated unapplied Alembic migration `b7d41a89c204_phase_04_workplace_locations_and_geofences.py` chaining from `e6331816d336`. Includes generated `coordinates geography(Point, 4326)` column with spatial GiST index (`ix_locations_spatial`), `btree_gist` exclusion constraint, forced RLS policies, and role grants.
  - Implemented Location CRUD APIs with strict RBAC (`MANAGE_LOCATIONS`, `VIEW_LOCATIONS`), ISO 3166-1 country code validation, IANA timezone validation (`zoneinfo`), and geofence coordinate verification probe (`POST /locations/verify-coordinates`) using PostGIS `ST_DWithin` / `ST_Distance` with spherical Haversine fallback and explicit threat boundary notice.
  - Added 31 new automated unit/integration tests across schemas, RBAC, business rules (including date range intersection logic), and API routes; verified all 96 backend tests and 19 frontend tests pass with zero warnings, clean Ruff, and clean Mypy.
- **Affected Files**:
  - `services/api/auth/permissions.py`
  - `services/api/locations/__init__.py`
  - `services/api/locations/models.py`
  - `services/api/locations/schemas.py`
  - `services/api/locations/service.py`
  - `services/api/locations/routes.py`
  - `services/api/main.py`
  - `database/migrations/env.py`
  - `database/migrations/versions/b7d41a89c204_phase_04_workplace_locations_and_geofences.py`
  - `tests/test_phase4_schemas.py`
  - `tests/test_phase4_rbac.py`
  - `tests/test_phase4_business_rules.py`
  - `tests/test_phase4_locations_api.py`
  - `docs/PHASE_04_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-01] — Phase 3.3: HttpOnly Cookie Refresh Token Migration
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Migrated frontend refresh token handling from `localStorage` to HttpOnly secure cookies.
  - Updated `apiFetch` in `apps/web/src/lib/api.ts` to enforce `credentials: "include"`, memory-only access tokens, and automatic single-flight retry on 401 using the backend cookie transport.
  - Added legacy token cleaner `clearLegacyTokens()` to purge historical localStorage artifacts.
  - Expanded frontend tests to 19 passing tests covering HttpOnly transport and token recovery.
- **Affected Files**:
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/auth-context.tsx`
  - `apps/web/src/lib/api.test.ts`
  - `PROJECT_CONTEXT.md`

### [2026-11-01] — Phase 3.2: Final Security, UX and Production Readiness Audit
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Conducted focused final audit across authentication/token security, API scalability, frontend UX behavior, and cross-tenant regressions.
  - Identified and remediated a critical frontend race condition in `apps/web/src/lib/auth-context.tsx` where concurrent 401s could dispatch simultaneous refresh requests with the same token, tripping backend token reuse detection. Added `activeRefreshPromise` deduplication lock.
  - Inspected backend HttpOnly cookie architecture: confirmed FastAPI backend already issues HttpOnly cookies on `/auth/login` and `/auth/refresh` and supports cookie-based refresh. Outlined safe non-breaking roadmap for eliminating `localStorage` fallback.
  - Evaluated API scalability: verified backend-driven employee pagination, identified frontend limitation for enterprise tenants with >100 departments/designations lacking UI pagination controls.
  - Reported explicit browser automation status: automated Playwright testing was not performed due to sandbox offline driver download restriction; documented full limitation report in scratchpad.
  - Executed automated live security verification against running FastAPI + Supabase: confirmed employee users receive HTTP 403 on directory and organization creation endpoints, employee self-access `/employees/me` works, cross-tenant isolation is intact, token rotation & reuse detection function, and pre-migration database counts remain pristine (`e6331816d336`).
- **Affected Files**:
  - `apps/web/src/lib/auth-context.tsx` (Fixed concurrent refresh race condition)
  - `docs/PHASE_03.md` (Added Section 13 Final Security, UX & Readiness Audit)
  - `PROJECT_CONTEXT.md` (Updated status, change log, and next actions)

### [2026-10-31] — Phase 3.1: Complete Frontend API Integration
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Integrated Next.js administrative organization workspace (`apps/web/src/app/organization/page.tsx`) with live FastAPI backend and live Supabase PostgreSQL database.
  - Removed all mock/sample data from production organization screens.
  - Implemented centralized `AuthProvider` (`apps/web/src/lib/auth-context.tsx`) with multi-tenant workspace login, persistent session recovery, and refresh token rotation.
  - Connected department CRUD, designation CRUD, employee directory with backend pagination, status toggles, and employee self-service view (`/employees/me`).
  - Added 15 frontend unit/integration tests (`apps/web/src/lib/api.test.ts`), passing with clean ESLint and Next.js 14 production build.
- **Affected Files**:
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/api.test.ts`
  - `apps/web/src/lib/auth-context.tsx`
  - `apps/web/src/lib/providers.tsx`
  - `apps/web/src/app/layout.tsx`
  - `apps/web/src/app/organization/page.tsx`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-10-31] — Phase 3: Approved Live Supabase PostgreSQL Migration
- **Phase**: Phase 3 (Organization Structure & Employee Management)
- **Summary**:
  - Applied migration `e6331816d336_phase_03_org_structure_and_employees` to live Supabase PostgreSQL.
  - Created `departments`, `designations`, and `employees` tables with 5 composite tenant foreign keys, composite unique constraints, and forced PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`).
  - Verified live database state with zero loss or tampering of Phase 2 baseline records.
- **Affected Files**:
  - `database/migrations/versions/e6331816d336_phase_03_org_structure_and_employees.py`
  - `docs/PHASE_03.md`
  - `PROJECT_CONTEXT.md`

### [2026-10-30] — Phase 1 Final Verification & Acceptance Audit
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**:
  - Performed comprehensive, evidence-based final audit across all repository subsystems.
  - Resolved root `alembic.ini` configuration to allow Alembic to load directly from repository root.
  - Configured standard Next.js ESLint configuration (`apps/web/.eslintrc.json`, `package.json`) and verified `npm run build`, `npm run lint`, and `npx tsc --noEmit` pass with zero errors.
  - Added web build and web lint targets to `Makefile`.
  - Expanded GitHub Actions CI workflow (`.github/workflows/ci.yml`) to include `web-checks` and `mobile-checks` alongside `backend-checks` and `security-scans`.
  - Confirmed Git secret isolation (`.env` strictly untracked).
  - Documented blocked status for Docker-dependent services (local Redis/MinIO containers) and Flutter CLI execution due to missing host binaries (`docker`, `flutter`).
- **Affected Files**:
  - `alembic.ini` (Created)
  - `apps/web/.eslintrc.json` (Created)
  - `apps/web/package.json` (Updated)
  - `apps/web/package-lock.json` (Updated)
  - `.gitignore` (Updated to ignore `*.tsbuildinfo`)
  - `.env.example` (Updated with Supabase REST keys)
  - `Makefile` (Added `web-build` and `web-lint`)
  - `.github/workflows/ci.yml` (Added `web-checks` and `mobile-checks`)
  - `docs/PHASE_01.md` (Updated with audit table)
  - `PROJECT_CONTEXT.md` (Updated with audit table and change history)

### [2026-10-30] — Supabase PostgreSQL Direct Connection & PostGIS Capability Verified
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**:
  - Owner supplied valid URL-encoded database connection string in local untracked `.env` file.
  - Executed safe direct connection check using SQLAlchemy 2 async engine with `asyncpg` (`SELECT 1`); verified successfully.
  - Enabled and verified PostGIS extension in Supabase PostgreSQL (`SELECT postgis_full_version();`).
  - Validated FastAPI `/ready` probe against live Supabase database returning HTTP 200 OK (`database: connected`, `postgis: PostGIS available`).
- **Affected Files**:
  - `PROJECT_CONTEXT.md` (Updated)
  - `docs/PHASE_01.md` (Updated)

### [2026-10-30] — Supabase Project Credentials Configuration & REST Probe Verification
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**:
  - Configured project credentials in untracked local `.env` file (`SUPABASE_URL`, `SUPABASE_PROJECT_REF`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`).
  - Added Supabase credential handling to `services/api/config.py`.
  - Updated `services/api/verify_db.py` to probe Supabase Project REST API; verified project `qnkgndfzuhrjuopzlcxy` is active and reachable (HTTP 200 OK).

### [2026-10-30] — Phase 1 Update: Flutter Selection & Supabase Architecture Alignment
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**:
  - Owner selected **Flutter** (Dart) as the mobile framework for iOS and Android; removed React Native and Expo references across all documentation and project specs.
  - Aligned database architecture strictly to **Supabase PostgreSQL 16 + PostGIS**; Docker Compose updated to manage Redis and MinIO only (no second local PostgreSQL container).
  - Implemented monorepo layout, Next.js web shell, Flutter mobile starter, FastAPI health probes, Alembic, Celery, and CI workflow (Commit `b64d49d`).

### [2026-10-30] — Phase 1: Repository & Master Documentation Inception
- **Phase**: Phase 1 (Project Setup & Monorepo Foundation)
- **Summary**: Initialized git repository, created initial `PROJECT_CONTEXT.md`, `docs/RULES.md`, `docs/ARCHITECTURE.md`, and `docs/PHASE_01.md` baseline (Commit `8e1a2e9`).

### [2026-11-03] — Phase 4 Milestone 4: Employee Invitations Live Supabase Migration & Verification (Revision d7a42e88b301)
- **Phase**: Phase 4 (Employees & Workplaces — Milestone 4)
- **Summary**:
  - Confirmed pre-migration state on branch `phase-04` at live revision `c8e52a91f034`.
  - Applied Alembic migration `d7a42e88b301` (`d7a42e88b301_phase_04_employee_invitations.py`) directly to live Supabase PostgreSQL database.
  - Live verified `employee_invitations` table in public schema, all 15 expected columns, data types, nullability constraints, and indexes.
  - Verified partial unique index `uq_invitations_active_employee` (`WHERE status = 'pending'`), rejecting duplicate active invitations for the same employee.
  - Verified composite foreign keys: `fk_invitations_employee` (`CASCADE`) and `fk_invitations_user` (`ON DELETE SET NULL (invited_by_user_id)`).
  - Verified user deletion sets `invited_by_user_id = NULL` while preserving `tenant_id` intact.
  - Verified Row-Level Security (`ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`), `tenant_isolation` policy, and cross-tenant isolation under `SET LOCAL ROLE authenticated`.
  - Executed all functional tests within an isolated transaction and cleanly rolled back all synthetic test records without modifying business data.
  - Ran full regression test suite: 172 backend pytest tests passing (100%), Ruff linting passing with 0 errors, Mypy type-checking passing with 0 issues in 41 files, and 19 frontend tests passing with 0 ESLint warnings or errors.
- **Affected Files**:
  - `database/migrations/versions/d7a42e88b301_phase_04_employee_invitations.py` (Migrated live)
  - `PROJECT_CONTEXT.md` (Updated)
  - `docs/PHASE_04_PLAN.md` (Updated)

### [2026-11-03] — Phase 4 Milestone 5: Frontend Integration & Final Phase 4 Verification Complete
- **Phase**: Phase 4 (Employees & Workplaces — Milestone 5)
- **Summary**:
  - Completed complete frontend integration for all Phase 4 features in Next.js 14 App Router, TypeScript, and Tailwind/Vanilla CSS design system:
    1. *Employee Workplace Management*: Interactive modal (`WorkplaceAssignmentModal`), historical assignment visibility, multi-workplace assignment, primary designation with temporal dates, non-destructive assignment end, and employee self-service card (`MyWorkplacesCard`).
    2. *Workplace Location Management*: Comprehensive location dashboard and standalone page (`/locations`, `LocationsTab`), create/edit modals, coordinate & geofence inputs, interactive Leaflet map component (`GeofenceMap`) with dynamic draggable marker and circular geofence overlay (`L.circle`), interactive coordinate test probe with PostGIS distance feedback, and location employee roster modal (`LocationRosterModal`).
    3. *Bulk Employee Import Wizard*: 7-step wizard modal (`ImportWizardModal`) with CSV/XLSX template download, drag-and-drop file upload (<=5MB), client-side preview, pre-validation checks, Celery progress bar polling, metrics grid, and downloadable failure CSV error report.
    4. *Employee Invitation Management*: Directory invitation action (`InviteEmployeeModal`), invitations status table (`InvitationsTab`) with filters (all, pending, accepted, expired, revoked), resend invitation, revoke invitation, and delivery failure diagnostic popover.
    5. *Public Account Activation Page*: Dedicated `/activate?token=...` page with token validation, safe employee and company display, real-time password strength meter, password confirmation validation, Argon2id activation submission, and success redirect to login.
  - Verified security and data integrity: access tokens remain strictly in memory, HttpOnly cookie refresh preserved, zero mock data introduced, and zero internal tenant IDs or token hashes leaked to public pages.
  - Added 17 new frontend unit/integration tests in `apps/web/src/lib/api.test.ts` (36 total tests, 9 suites, 100% pass rate).
  - Executed full test and verification suite:
    - Frontend Tests: `npm --prefix apps/web test` (36 tests passed, 0 failures).
    - Frontend Linting: `npm --prefix apps/web run lint` (0 errors, 0 warnings).
    - Production Next.js Build: `npm --prefix apps/web run build` (7/7 static routes compiled and optimized cleanly).
    - Backend Tests: `make test` (172 pytest tests passed, 100%).
    - Backend Linting: `make lint` (Ruff passed, Mypy passed across 41 source files with 0 issues).
- **Affected Files**:
  - `apps/web/src/app/organization/page.tsx`
  - `apps/web/src/app/locations/page.tsx`
  - `apps/web/src/app/activate/page.tsx`
  - `apps/web/src/components/GeofenceMap.tsx`
  - `apps/web/src/components/WorkplaceAssignmentModal.tsx`
  - `apps/web/src/components/LocationRosterModal.tsx`
  - `apps/web/src/components/ImportWizardModal.tsx`
  - `apps/web/src/components/InviteEmployeeModal.tsx`
  - `apps/web/src/components/InvitationsTab.tsx`
  - `apps/web/src/components/LocationsTab.tsx`
  - `apps/web/src/components/MyWorkplacesCard.tsx`
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/api.test.ts`
  - `apps/web/package.json` & `apps/web/package-lock.json`
  - `apps/web/tsconfig.json`
  - `PROJECT_CONTEXT.md`
  - `docs/PHASE_04_PLAN.md`

---

## 12. Next Actions

1. **Immediate Task**: STOP after Phase 4 Milestone 5 Frontend Integration & Final Verification. Phase 4 is FULLY COMPLETE across all 5 milestones. 172 backend tests & 36 frontend tests passing. Zero lint errors. Production build verified. Await project owner authorization before starting Phase 5 (Attendance Engine & Ledger).
2. **Phase 4 Execution Roadmap**:
   - [x] **Milestone 1 — Database Foundation & Workplace Locations**: Models, applied live Alembic migration `b7d41a89c204`, PostGIS generated coordinates, GiST index, `btree_gist` temporal primary exclusion constraint, forced RLS, CRUD APIs, `POST /locations/verify-coordinates` probe, 31 new tests (96 total backend, 19 frontend). **COMPLETE & LIVE MIGRATION VERIFIED**.
   - [x] **Milestone 2 — Employee Workplace Assignments**: Assignment CRUD, primary workplace management, date validation, employee self-access endpoint (`GET /api/v1/employees/me/workplaces`), location roster (`GET /locations/{id}/employees`), 26 new tests (122 total backend, 19 frontend). **COMPLETE**.
   - [x] **Milestone 3 — Bulk Employee Import**: Asynchronous Celery CSV/XLSX pipeline, shared MinIO/S3 storage, 2,000-row limit, downloadable failure CSV, PostgreSQL 17 column-specific composite FK syntax, formula injection sanitization, concurrency locking, and chunk rollback protection. Migration `c8e52a91f034` applied and verified live on Supabase. 29 new tests (151 total backend, 19 frontend). **COMPLETE & LIVE MIGRATION VERIFIED**.
   - [x] **Milestone 4 — Employee Invitations & Activation**: Complete invitation lifecycle, Argon2id passwords, single-use acceptance, 5-attempt lockout, PII-safe email service, composite foreign keys (CASCADE on employee, SET NULL (invited_by_user_id) on user), partial unique index on pending invitations, forced RLS. Migration `d7a42e88b301` applied and verified live on Supabase. 21 new tests (172 total backend, 19 frontend). **COMPLETE & LIVE MIGRATION VERIFIED**.
   - [x] **Milestone 5 — Frontend Integration & Verification**: Leaflet maps, assignment UI, import wizard, invitation manager, public activation page, 36 frontend tests, production build, full regression audit. **COMPLETE**.
3. **Strict Boundaries**: STOP execution after Milestone 5. Do NOT begin Phase 5 without explicit owner authorization.
