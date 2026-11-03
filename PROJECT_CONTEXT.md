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
- **Current Phase**: **Phase 5 — Attendance Engine & Ledger (Shifts and Punch Engine)** (Status: *All Milestones 1–5 Implemented & Fully Verified on branch `phase-05`; Live Supabase revision: `a2b3c4d5e6f7 (head)`; 281/281 backend tests + 52/52 frontend tests passing; Next.js production build succeeded; Live workflow audit and defect correction complete*)

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
| **04** | Stage B | **Employees & Workplaces** | **Complete** | Milestones 1–5 complete. Live migrations b7d41a89c204, c8e52a91f034, d7a42e88b301 applied and verified on Supabase. 172 backend tests & 36 frontend tests passing. Git tag phase-04-complete. |
| **05** | Stage B | **Shifts and Punch Engine** | **Planning** | Architecture Revision 2.0 formulated (docs/ATTENDANCE_ARCHITECTURE.md, docs/PHASE_05_PLAN.md) with shift versions, explicit correction model, and request fingerprinting. Awaiting user review and approval. |
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

### [2026-11-03] — Phase 5 Milestone 1: Shift Templates, Immutable Versions & Employee Assignments Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Milestone 1)
- **Summary**:
  - Implemented complete backend foundation for shift management on branch `phase-05`:
    1. *Shift Templates*: Master entity `shift_templates` with unique tenant code, name, description, and active status.
    2. *Immutable Shift Versions*: Versioned rules in `shift_template_versions` capturing version number, effective date, operational timings (`start_time`, `end_time`), overnight flag, flexible flag, grace periods (start and early exit), allowances (early arrival and late departure), half/full-day thresholds, break duration, and weekly off days. Older versions are preserved without mutation; editing creates a new version.
    3. *Employee Shift Assignments*: Temporal mapping in `shift_assignments` (`effective_from`, `effective_to`) protected by PostgreSQL `btree_gist` exclusion constraint `excl_shift_assignments_overlap` preventing overlapping assignments for the same employee while accepting contiguous date ranges.
    4. *Security & Tenant Isolation*: Composite foreign keys, PostgreSQL 17 column-specific `ON DELETE SET NULL (created_by_user_id)` syntax, and PostgreSQL forced Row-Level Security (`FORCE ROW LEVEL SECURITY`) with `tenant_isolation` policies on all 3 tables.
    5. *Database Migration*: Prepared Alembic migration `e9f63b02a145_phase_05_shift_templates_and_assignments.py` with parent revision `d7a42e88b301`. Verified offline migration SQL script.
    6. *RBAC Protection*: Added `MANAGE_SHIFTS` and `VIEW_SHIFTS` permissions to `services/api/auth/permissions.py`. Authorized Owner, Admin, and HR to manage; Manager and Employee have read-only visibility.
    7. *REST Endpoints*: Delivered `POST/GET/PUT/DELETE /api/v1/shifts`, `POST/GET /api/v1/shifts/{id}/versions`, `POST/GET/PUT /api/v1/shifts/assignments`, and `POST /api/v1/shifts/assignments/{id}/end`.
    8. *Testing & Quality*: Added 21 automated tests in `tests/test_phase5_shifts.py` covering schema validation, shift creation, duplicate rejection, versioning history preservation, historical date resolution, overlap rejection, exclusion constraint error handling, soft deactivation, and RBAC enforcement.
    9. Full regression suite passed: 193 backend tests passed (100%), Ruff clean, Mypy clean across 46 source files.
- **Affected Files**:
  - `services/api/auth/permissions.py`
  - `services/api/attendance/__init__.py`
  - `services/api/attendance/models.py`
  - `services/api/attendance/schemas.py`
  - `services/api/attendance/service.py`
  - `services/api/attendance/routes.py`
  - `services/api/main.py`
  - `database/migrations/env.py`
  - `database/migrations/versions/e9f63b02a145_phase_05_shift_templates_and_assignments.py`
  - `tests/test_phase5_shifts.py`
  - `docs/PHASE_05_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-03] — Phase 5 Milestone 2: Attendance Event Ledger, Idempotency & Punch APIs Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Milestone 2)
- **Summary**:
  - Implemented append-only attendance event ledger, tenant- and employee-scoped idempotency, and punch REST endpoints:
    1. *Attendance Event Ledger (`attendance_events`)*: Append-only relational table capturing `event_type` (`CHECK_IN`, `CHECK_OUT`, `BREAK_START`, `BREAK_END`), `event_category` (`STANDARD`, `CORRECTION_INSERT`, `CORRECTION_SUPERSEDE`, `CORRECTION_VOID`), `source` (`WEB`, `MOBILE`, `BIOMETRIC`, `CCTV`, `ADMIN`, `DEVICE`, `API`), server authoritative receipt timestamp `server_received_at`, device capture timestamp `device_reported_at`, effective timestamp `effective_at`, `clock_drift_seconds`, verification status, review status, hardware/device ID, geofence location ID, GPS coordinates (`latitude`, `longitude`, `accuracy_meters`), actor user ID, idempotency key, metadata JSONB, and self-referencing `supersedes_event_id`.
    2. *Database Immutability Trigger*: Enforced via PostgreSQL trigger `trg_prevent_attendance_events_mutation` calling function `trg_attendance_events_immutability()` which raises `integrity_constraint_violation` on any `UPDATE` or `DELETE`. Normal application roles are strictly granted `SELECT, INSERT` only.
    3. *Idempotency Records (`attendance_idempotency_records`)*: Scoped to `(tenant_id, employee_id, idempotency_key)` with SHA-256 request payload fingerprinting, execution state machine (`IN_PROGRESS`, `COMPLETED`, `FAILED`), cached response code and JSONB payload, linked `event_id`, and 24-hour expiration.
    4. *Deterministic SHA-256 Request Fingerprinting*: Canonical JSON serialization over behavior-altering parameters (`event_type`, `employee_id`, `device_reported_at`, `location_id`, `latitude`, `longitude`, `accuracy_meters`, `device_id`, `metadata`). Replaying with identical key and payload returns cached response (HTTP 200/201 with `idempotent_replay: true`); replaying with modified payload returns HTTP 422 Unprocessable Content.
    5. *Concurrency & Concurrency Locking*: Pessimistic row locking on target employee (`SELECT id FROM employees ... FOR UPDATE`) guarantees sequential, atomic punch execution per employee, eliminating state-machine race conditions. In-progress duplicates return HTTP 409 Conflict.
    6. *Timestamp Semantics & Validation*: Server maintains authoritative time. Device timestamps > 24 hours in the future or > 7 days in the past are rejected with HTTP 422. Clock drift $> 300$s is flagged as `SUSPICIOUS_CLOCK_DRIFT` with review status `PENDING_REVIEW`.
    7. *Atomic Multi-Event Creation*: Checking out while in `ON_BREAK` status automatically creates a `BREAK_END` event followed immediately by `CHECK_OUT` in a single atomic database transaction.
    8. *REST APIs Delivered*:
       - `POST /api/v1/attendance/punch`: Records check-in, check-out, break start, and break end punches.
       - `GET /api/v1/attendance/events`: Cursor-paginated listing with employee, event type, and date range filters.
       - `GET /api/v1/attendance/events/{event_id}`: Retrieves event details with tenant and role isolation.
    9. *RBAC Enforcement*: Employees may punch and view events strictly for themselves (403 on mismatch); Managers can punch for self but cannot punch for other employees (403); Owner, Admin, and HR with `MANAGE_ATTENDANCE` may punch for employees.
    10. *Database Migration*: Created Alembic migration `f1b94c8e7a23_phase_05_attendance_events_and_idempotency.py` (parent: `e9f63b02a145`).
    11. *Idempotency Audit & Safety Enhancement*: Audited 24-hour expiration vs. permanent event permanence. Solved duplicate and replay safety by making `expires_at` nullable on `attendance_idempotency_records` (`expires_at = NULL` on `COMPLETED`), retaining completed punch idempotency records permanently. In-progress locks have a 15-minute lease allowing recovery if a worker terminates midway. Partial index `ix_idempotency_tenant_expires` indexes only rows with `expires_at IS NOT NULL`. Database constraint `uq_attendance_events_tenant_idempotency` physically guarantees 0 duplicate events can ever be inserted into the ledger.
    12. *Live Migration Application & Verification*: Applied migration `f1b94c8e7a23` to live Supabase (PostgreSQL 17.11). Verified RLS enabled and forced, tenant policies active, all 6 composite foreign keys valid, immutability trigger `trg_prevent_attendance_events_mutation` actively blocking `UPDATE` and `DELETE` (raising `integrity_constraint_violation`), unique constraint blocking duplicates, and 0 synthetic records remaining in production via rolled-back transaction testing.
    13. *Testing & Quality*: Added 30 comprehensive unit and API integration tests in `tests/test_phase5_punch_ledger.py`. Entire test suite passing: 223/223 tests (100%), Ruff clean, Mypy clean across 46 source files.
- **Affected Files**:
  - `services/api/attendance/models.py`
  - `services/api/attendance/schemas.py`
  - `services/api/attendance/service.py`
  - `services/api/attendance/routes.py`
  - `services/api/main.py`
  - `database/migrations/versions/f1b94c8e7a23_phase_05_attendance_events_and_idempotency.py`
  - `tests/test_phase5_punch_ledger.py`
  - `docs/ATTENDANCE_ARCHITECTURE.md`
  - `docs/PHASE_05_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-03] — Phase 5 Milestone 3: Attendance Timeline Resolution, Calculation Engine & Live Application Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Milestone 3)
- **Summary**:
  - Implemented derived `attendance_days` projection table, pure timeline resolution engine, pure attendance calculation engine, historical shift version resolver, overnight shift attribution, recalculation service, and read APIs. Conducted exhaustive calculation safety audit and safely applied database migration `a2b3c4d5e6f7` to live Supabase:
    1. *Derived Projection Model (`attendance_days`)*: Implemented in `services/api/attendance/models.py`. Stores tenant-isolated, employee-level daily attendance projections including exact shift template and version references (`shift_template_id`, `shift_template_version_id`), scheduled times (`scheduled_start_time`, `scheduled_end_time`), actual punch times (`first_check_in_at`, `last_check_out_at`), minute metrics (`gross_minutes`, `break_minutes`, `net_work_minutes`, `late_arrival_minutes`, `actual_early_minutes`, `early_exit_minutes`, `overtime_minutes`), boolean flags (`is_late`, `is_early_exit`, `is_half_day`, `is_overtime`, `missing_punch`, `is_incomplete`, `has_anomaly`), anomaly details JSONB, review status (`APPROVED`, `PENDING_REVIEW`, `REJECTED`), and calculation status (`status`: `PRESENT`, `LATE`, `HALF_DAY`, `ABSENT`, `INCOMPLETE`, `WEEK_OFF`, `PENDING_REVIEW`).
    2. *Relational Integrity & RLS*: Enforced composite foreign keys to `employees`, `shift_templates`, and `shift_template_versions`. Multi-tenant isolation enforced via `FORCE ROW LEVEL SECURITY` with `tenant_isolation` policy. Unique constraint `uq_attendance_days_tenant_emp_date` guarantees exactly one projection row per tenant, employee, and attendance date.
    3. *Alembic Migration & Live Application*: Applied chained migration `a2b3c4d5e6f7_phase_05_attendance_days_projection.py` (parent: `f1b94c8e7a23`) to live Supabase (PostgreSQL 17.11). Current live revision is `a2b3c4d5e6f7 (head)`.
    4. *Live Database Verification*: Validated on live Supabase: table `attendance_days` exists; RLS enabled and forced; `tenant_isolation` policy active; all 4 foreign keys active; unique constraints and indexes active; all 10 public tables intact. Conducted live functional RLS test: Tenant A queried inserted record; Tenant B saw 0 rows (RLS enforced); cross-tenant insert strictly rejected by RLS `WITH CHECK`; unique constraint strictly rejected duplicates; all synthetic data safely rolled back leaving 0 rows in production.
    5. *Calculation Engine Safety Audit & Corrections*:
       - *Rejection Filter*: `resolve_active_timeline` strictly filters out events with `review_status == "REJECTED"` so they never count towards active sessions or working minutes.
       - *Weekly Off Daytime Precedence*: In `calculate_attendance_day`, scheduled weekly offs with 0 punches are evaluated before premature absence checking so they evaluate to `WEEK_OFF` throughout the day instead of falsely becoming `INCOMPLETE`.
       - *Atomic Punch Recalculation*: `record_punch` executes daily recalculation inside the same transaction without swallowing real database exceptions. Any database failure rolls back both the punch event and projection atomically.
       - *Pessimistic Concurrency Locking*: `recalculate_attendance_day` acquires a pessimistic row lock on `Employee` (`FOR UPDATE`) to serialize all recalculations per employee, eliminating concurrent insert races on `uq_attendance_days_tenant_emp_date`.
    6. *Pure Timeline Resolution Engine (`resolve_active_timeline`)*: Pure Python function in `services/api/attendance/engine.py` with zero database dependencies. Filters out superseded, voided, and rejected events, pairs `CHECK_IN` and `CHECK_OUT` into work sessions, tracks multi-break sessions (`BREAK_START` / `BREAK_END`), detects unclosed sessions and breaks, handles out-of-order punches gracefully, and records timeline anomalies (unpaired punches, clock drift $>300$s).
    7. *Pure Calculation Engine (`calculate_attendance_day`)*: Pure Python calculator in `services/api/attendance/engine.py`. Computes gross, break, and net working minutes. Strictly enforces enterprise lateness rule: if actual late arrival $\le$ grace period minutes, `late_arrival_minutes = 0`; if grace period is breached, `late_arrival_minutes = actual_late_minutes` measured from scheduled start (no subtraction of grace period). Computes early departure relative to grace periods and overtime past scheduled duration. Accurately determines daily status (`PRESENT`, `LATE`, `HALF_DAY`, `ABSENT`, `INCOMPLETE`, `WEEK_OFF`, `PENDING_REVIEW`). Incomplete sessions are omitted from completed working hours. Shifts in progress are not prematurely marked absent.
    8. *Historical Shift Version Preservation (`resolve_employee_shift_version`)*: Historical dates strictly resolve the exact shift template version where `version_effective_from <= attendance_date`, guaranteeing recalculations never drift when shift templates are updated later.
    9. *Overnight Shift Attribution (`determine_shift_date_for_punch`)*: Overnight shifts crossing midnight are cleanly attributed to the shift start calendar date. Employs configurable early arrival and late departure allowances, state-aware resolution for adjacent shifts, and midpoint boundary partitioning ($T_{\text{sched\_end}}(D) + (T_{\text{sched\_start}}(D+1) - T_{\text{sched\_end}}(D)) / 2$).
    10. *REST APIs Delivered*:
       - `GET /api/v1/attendance/days`: List daily summaries with employee, date range, and status filters.
       - `GET /api/v1/attendance/days/{employee_id}/{attendance_date}`: Get a specific employee's daily calculation.
       - `POST /api/v1/attendance/recalculate`: Explicit recalculation trigger for date ranges.
    11. *RBAC Enforcement*: Employees can only view their own attendance days (403 on other employees); Managers can view their assigned team members; Owner, Admin, and HR can view and trigger recalculations tenant-wide.
    12. *Testing & Quality*: Test suite expanded to 36 tests in `tests/test_phase5_calculation_engine.py` covering safety audit fixes, timeline resolution, unpaired check-ins, multi-break pairing, enterprise lateness formulas, early exit, half-day thresholds, overtime, overnight attribution, boundary partitioning, historical shift version preservation, idempotency, and RBAC scoping. All 259 project tests passing (100%), Ruff clean, Mypy clean.
- **Affected Files**:
  - `services/api/attendance/engine.py`
  - `services/api/attendance/models.py`
  - `services/api/attendance/schemas.py`
  - `services/api/attendance/service.py`
  - `services/api/attendance/routes.py`
  - `database/migrations/versions/a2b3c4d5e6f7_phase_05_attendance_days_projection.py`
  - `tests/test_phase5_calculation_engine.py`
  - `docs/PHASE_05_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-03] — Phase 5 Milestone 4: Attendance Correction Engine, Audit Trail & Reconciliation Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Milestone 4)
- **Summary**:
  - Implemented the full attendance correction lifecycle, audit history trail, and nightly background reconciliation task preserving immutable append-only event ledger invariants:
    1. *Correction Event Operations*:
       - `CORRECTION_INSERT`: Appends an administrative punch to inject a missing punch event without altering past punches.
       - `CORRECTION_SUPERSEDE`: Replaces an erroneous punch by appending a corrected punch linked via `supersedes_event_id`. The original punch remains intact and immutable in the ledger.
       - `CORRECTION_VOID`: Appends a tombstone correction event linked via `supersedes_event_id` to exclude an invalid punch from calculations without deleting the original record.
    2. *Authorization & Reporting Scope*:
       - `CORRECT_ATTENDANCE` permission added to `Permission` enum and mapped to `UserRole.OWNER`, `ADMIN`, `HR`, and `MANAGER`.
       - Owner, Admin, and HR: authorized to correct attendance for any employee within their tenant.
       - Manager: strictly constrained to direct reports within their authorized reporting scope (`Employee.reporting_manager_id == mgr_emp`); cannot self-correct.
       - Employee: forbidden from directly submitting administrative corrections (HTTP 403).
    3. *Business Validation & Invariants*:
       - Mandatory non-empty correction reason ($\ge 5$ characters).
       - Cross-employee correction attempts strictly rejected (HTTP 400).
       - Disallowed superseding an already superseded or voided event (HTTP 400).
       - Disallowed voiding an already voided or superseded event (HTTP 400).
       - Disallowed voiding or superseding a voiding tombstone (HTTP 400).
       - Idempotency with SHA-256 fingerprint divergence conflict check (HTTP 409).
    4. *Atomic Recalculation & Rollback Protection*:
       - Pessimistic row locking on `Employee` (`FOR UPDATE`) serializes correction execution.
       - Discovers affected calendar shift dates for both the correction punch and any target superseded/voided punch, including overnight shift windows crossing calendar dates.
       - Recalculates all affected `attendance_days` projections atomically within the correction transaction. If recalculation fails, the entire transaction rolls back cleanly.
    5. *Audit Trail & Inspection APIs*:
       - `POST /api/v1/attendance/corrections`: Creates administrative correction atomically.
       - `GET /api/v1/attendance/corrections`: Lists non-standard correction events with pagination and role scoping.
       - `GET /api/v1/attendance/records/{record_id}/events` (and alias `.../days/{record_id}/events`): Detailed audit trail of contributing events annotated with active vs superseded vs voided status and correction reasons.
    6. *Nightly Reconciliation Engine & Worker Task*:
       - `run_attendance_reconciliation`: Scans shift assignments, attendance days, and punch events to find unclosed, missing, or stranded attendance dates; executes recalculations in bounded batches with savepoint isolation per employee; logs errors with full PII sanitization (UUIDs and Exception class names only).
       - Celery task `@celery_app.task(name="attendance.nightly_reconciliation", bind=True, max_retries=3)` for asynchronous worker scheduling.
       - `POST /api/v1/attendance/reconcile`: Administrative trigger for manual or scheduled batch reconciliation.
    7. *Testing & Quality*:
       - Created `tests/test_phase5_corrections.py` with 19 comprehensive unit and integration tests.
       - Full backend test suite passing: 280/280 tests (100%).
       - Ruff linting and formatting clean; Mypy clean with zero issues in 10 source files.
- **Affected Files**:
  - `services/api/auth/permissions.py`
  - `services/api/attendance/schemas.py`
  - `services/api/attendance/correction_service.py`
  - `services/api/attendance/reconciliation.py`
  - `services/api/attendance/routes.py`
  - `services/workers/tasks.py`
  - `tests/test_phase5_corrections.py`
  - `docs/PHASE_05_PLAN.md`
  - `docs/ATTENDANCE_ARCHITECTURE.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-03] — Phase 5 Milestone 5: Frontend Integration & Verification Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Milestone 5)
- **Summary**:
  - Integrated the Next.js frontend with the Phase 5 Attendance & Shifts APIs, implementing role-aware dashboards, personal attendance views, and full correction management:
    1. *Attendance Console (`apps/web/src/app/attendance/page.tsx`)*:
       - Single-page responsive console with glassmorphic aesthetic matching platform design system.
       - **Step 2 — KPI Metrics Dashboard**: Present, Absent, Late, Incomplete, Pending Verification, Currently Working, and Unresolved Sessions calculated from live daily attendance projections. Date picker, Department filter, Status filter, search query, and batch reconciliation trigger.
       - **Step 3 — Attendance Records Table**: Employee Name & ID, Date, Shift Name, Actual In/Out, Gross, Break, Net Working Duration, Late Arrival, Early Exit, Overtime, and Status badges. Row actions: Event Timeline drawer, Correction modal, Single employee day recalculation.
       - **Step 4 — Corrections Audit Log**: Dedicated tab for inspecting immutable correction events (`CORRECTION_INSERT`, `CORRECTION_SUPERSEDE`, `CORRECTION_VOID`) with reason justifications, effective timestamps, target event IDs, and actor user IDs.
    2. *Today's Punch Widget (`apps/web/src/components/TodayPunchWidget.tsx`)*:
       - Interactive employee check-in/out and break tracking widget.
       - Live active session timer, dynamic state machine (`NOT_CHECKED_IN`, `WORKING`, `ON_BREAK`, `CHECKED_OUT`), atomic break auto-close, per-punch cryptographic UUID idempotency key, and recent punch timeline stream.
    3. *Personal Attendance Tab (`apps/web/src/components/MyAttendanceTab.tsx`)*:
       - Employee self-service view displaying personal attendance records history with monthly and date-range filters, duration summaries, status breakdown, and audit timeline trigger.
       - Administrative actions strictly concealed for employee role.
    4. *Correction Modal (`apps/web/src/components/AttendanceCorrectionModal.tsx`)*:
       - Administrative dialog supporting `CORRECTION_INSERT`, `CORRECTION_SUPERSEDE`, and `CORRECTION_VOID`.
       - Candidate event picker for supersede/void operations, mandatory reason validation ($\ge 5$ characters), ISO-8601 UTC timestamp conversion, and per-action UUID idempotency key.
    5. *Audit Timeline Drawer (`apps/web/src/components/AttendanceAuditDrawer.tsx`)*:
       - Slide-over drawer presenting the immutable append-only event stream from `/attendance/records/{record_id}/events`.
       - Active, superseded, and voided badges with strike-through styling, server receipt timestamps, drift metrics, source, review status, actor user IDs, and recorded justification reasons.
    6. *Role Scoping & Security Enforcements*:
       - **Employee Role**: Restricts view strictly to personal attendance days via `organizationApi.getMyProfile` and `attendanceApi.getDays({ employee_id: profile.id })`. Administrative correction and recalculation actions are completely hidden.
       - **Manager Role**: Scoped strictly to direct reports where `Employee.reporting_manager_id == manager_id`. Self-correction is blocked on both client and backend service.
       - **Admin/Owner/HR Role**: Tenant-wide visibility and administrative authority.
       - **Client Security**: Access tokens held in React state / memory only. Zero `localStorage` token storage. Refresh tokens transported via HttpOnly cookies with automatic 401 token refresh rotation.
    7. *Testing & Quality Verification*:
       - Added 16 new unit and logic verification tests to `apps/web/src/lib/api.test.ts`. Total frontend test suite: 52/52 passed (100%).
       - Full backend test suite passing: 280/280 tests (100%).
       - TypeScript: 0 errors (`npx tsc --noEmit`).
       - ESLint: 0 warnings/errors (`npm run lint`).
       - Next.js Production Build: Succeeded with `/attendance` static route.
       - Ruff: All checks passed. Mypy: Success (0 issues across 10 source files).
- **Affected Files**:
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/app/attendance/page.tsx`
  - `apps/web/src/components/TodayPunchWidget.tsx`
  - `apps/web/src/components/MyAttendanceTab.tsx`
  - `apps/web/src/components/AttendanceCorrectionModal.tsx`
  - `apps/web/src/components/AttendanceAuditDrawer.tsx`
  - `apps/web/src/app/page.tsx`
  - `apps/web/src/app/organization/page.tsx`
  - `apps/web/src/lib/api.test.ts`
  - `docs/PHASE_05_PLAN.md`
  - `docs/ATTENDANCE_ARCHITECTURE.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-04] — Phase 5 Final Verification & Defect Correction Complete
- **Phase**: Phase 5 (Attendance Engine & Ledger — Final Verification)
- **Status**: Complete & Verified (Ready for Acceptance)
- **Branch**: `phase-05`
- **Actions Taken**:
  - **Check 1 (Git & DB Revision)**: Branch confirmed `phase-05`. Alembic linear history verified (`4f61a7dd311e` -> `e6331816d336` -> `b7d41a89c204` -> `c8e52a91f034` -> `d7a42e88b301` -> `e9f63b02a145` -> `f1b94c8e7a23` -> `a2b3c4d5e6f7 (head)`). Live Supabase DB confirmed at `a2b3c4d5e6f7`. All 6 attendance tables verified with `FORCE ROW LEVEL SECURITY`.
  - **Check 2 (Punch Workflow & Immutability)**: Complete lifecycle tested live against Supabase inside rollback-safe transaction: Check-In, Idempotent duplicate replay, Divergent payload rejection (422), Double check-in rejection (400), Break Start, Break End, Invalid break end rejection (400), Check-Out, Check-out without check-in rejection (400), Clock drift > 300s flagged as `SUSPICIOUS_CLOCK_DRIFT` / `PENDING_REVIEW`, daily attendance projection recomputed. PostgreSQL immutability trigger verified rejecting both `UPDATE` and `DELETE` on `attendance_events` with `IntegrityError`.
  - **Check 3 (Authorization & Tenant Isolation)**: `ROLE_PERMISSIONS` verified. Manager self-correction rejected (HTTP 403), manager correcting unrelated employee rejected (HTTP 403), manager correcting direct report allowed. Cross-tenant isolation verified live on Supabase with `SET LOCAL ROLE authenticated` and `SET LOCAL app.tenant_id`: cross-tenant rows completely masked.
  - **Check 4 (Correction Workflow)**: `CORRECTION_INSERT`, `CORRECTION_SUPERSEDE` (with original event link), duplicate supersede prevention on already superseded events, `CORRECTION_VOID` (tombstone appending), and mandatory correction reason (>= 5 chars) verified live against Supabase.
  - **Check 5 (Shift & Calculation Accuracy)**: Pure calculation engine verified: grace period lateness absorption (10m late <= 15m grace -> 0 late arrival, PRESENT), strict enterprise penalty beyond grace (20m late > 15m grace -> 20m late arrival, LATE), overnight shift date attribution across midnight, weekly off daytime precedence (`WEEK_OFF` with 0 punches), and absence evaluated strictly after configured shift window expires (remains `INCOMPLETE` while window is open).
  - **Check 6 (Frontend Web Integration)**: Next.js frontend verified with 52/52 tests in `apps/web/src/lib/api.test.ts`. `npx tsc --noEmit` passed with 0 errors. `npm run lint` passed with 0 warnings/errors. Next.js production build (`npm run build`) succeeded with optimized static routes including `/attendance` (12.1 kB).
  - **Check 7 (Reconciliation & Celery)**: Direct execution of `run_attendance_reconciliation` verified with employee isolation and sanitized non-PII logging. Celery task `attendance.nightly_reconciliation` verified registered with `max_retries=3`. Redis limitation reported honestly (direct execution and unit verification used).
  - **Check 8 (Full Regression)**: Backend pytest: 281 passed, 41 warnings (deprecation/coroutine test mocks) in 95s. Backend Ruff: All checks passed. Backend Mypy: 0 issues in 10 source files. Frontend tests: 52 passed. Frontend tsc: 0 errors. Frontend lint: clean. Frontend build: clean.
  - **Check 9 (Defect Resolution)**:
    - *Problem*: `apply_attendance_correction` in `services/api/attendance/correction_service.py` failed with `sqlalchemy.exc.InvalidRequestError: Incorrect number of values in identifier to formulate primary key for session.get(); primary key columns are 'attendance_idempotency_records.id'`.
    - *Root Cause*: Step 9 called `session.get(AttendanceIdempotencyRecord, (tenant_id, payload.idempotency_key))`. However, `attendance_idempotency_records` has a single UUID primary key column `id`, whereas `(tenant_id, idempotency_key)` is a composite unique constraint.
    - *Fix*: Directly updated the existing `idem_record` instance attached to the session during Step 3 (`status="COMPLETED"`, `event_id`, `response_payload`, `expires_at=None`) and called `await session.flush()`.
    - *Regression Test*: Added `test_correction_idempotency_record_completion_regression` in `tests/test_phase5_corrections.py`.
  - **Check 10 (Zero Synthetic Residue)**: Baseline row counts in Supabase confirmed 0 across all 6 tables before and after test execution. All mutations rolled back safely.
- **Files Modified / Created**:
  - `services/api/attendance/correction_service.py`
  - `tests/test_phase5_corrections.py`
  - `docs/PHASE_05_PLAN.md`
  - `docs/ATTENDANCE_ARCHITECTURE.md`
  - `PROJECT_CONTEXT.md`

---

## 12. Next Actions

1. **Current State**: Phase 5 (Attendance Engine & Ledger) is fully COMPLETE and VERIFIED across all 5 milestones and final verification checks on branch `phase-05`. Alembic migrations `e9f63b02a145` (Milestone 1), `f1b94c8e7a23` (Milestone 2), and `a2b3c4d5e6f7` (Milestone 3) are safely APPLIED and VERIFIED on live Supabase (`a2b3c4d5e6f7 (head)`). All 281 backend tests and 52 frontend tests pass (100%).
2. **Phase 5 Execution Roadmap**:
   - [x] **Milestone 1 — Shift Templates, Versions & Shift Assignments**: Master shift templates, immutable `shift_template_versions` with effective dates, employee rostering with exclusion constraints, CRUD APIs, RLS, live migration `e9f63b02a145` applied & verified.
   - [x] **Milestone 2 — Event Ledger, Fingerprinting & Idempotent Punch API**: Append-only `attendance_events`, PostgreSQL immutability trigger, permanent `attendance_idempotency_records` with SHA-256 request fingerprinting, `POST /api/v1/attendance/punch`, pessimistic row-locking (`SELECT FOR UPDATE`), atomic break auto-close, live migration `f1b94c8e7a23` applied & verified.
   - [x] **Milestone 3 — Timeline Resolution, Calculation Engine & Live Application**: Derived `attendance_days` projection table, pure timeline resolution and calculation engine, historical shift versioning preservation, overnight shift attribution, recalculation service, read APIs, live migration `a2b3c4d5e6f7` applied & verified.
   - [x] **Milestone 4 — Correction Engine, Audit & Nightly Reconciliation**: Structured corrections (`CORRECTION_INSERT`, `CORRECTION_SUPERSEDE`, `CORRECTION_VOID`) with mandatory reasons and target event references, projection recalculation, Celery nightly reconciliation task, event audit history endpoint.
   - [x] **Milestone 5 — Frontend Integration & Verification**: Next.js Employee Today punch widget with live timer, personal attendance history, HR Daily Attendance Console with KPI cards, records table, manual correction modal (insert/supersede/void), audit trail drawer, manager direct-report scoping, and full test suite verification.
   - [x] **Phase 5 Final Verification & Defect Correction**: Comprehensive 10-check audit, live Supabase testing with zero data residue, PostgreSQL RLS tenant isolation, immutability trigger verification, defect resolution in correction idempotency finalization, regression tests, and full test suite passing.
3. **Strict Boundaries**: Phase 5 is 100% complete. User has formally accepted Phase 5. Proceeding with official closure, release tag `phase-05-complete`, and upstream repository push. Do NOT begin Phase 6 (Flutter mobile app).
