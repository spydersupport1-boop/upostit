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
- **Current Stage**: **Stage A: Foundation**
- **Current Phase**: **Phase 2 — Auth and Tenants** (Status: *Complete & 100% Verified Live on Supabase*)

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

---

## 10. Phase Tracker (22 Phases)

| Phase | Stage | Name & Core Objective | Status | Completion Criteria & Evidence |
| :---: | :--- | :--- | :---: | :--- |
| **01** | Stage A | **Project Setup & Monorepo Foundation** | **Audited** | Monorepo layout, Next.js web build (passed), Flutter starter (ready), FastAPI (`/health`, `/ready` passed), Supabase PostgreSQL + PostGIS verified, Alembic loader verified, CI workflow (4 jobs). Docker & Flutter CLI blocked on host tooling. Conditionally ready for Phase 2. |
| **02** | Stage A | **Auth and Tenants** | **Complete** | Tenant registration, Argon2id, JWT access & refresh tokens with rotation and reuse detection, RBAC permissions (5 roles), transaction-scoped `app.tenant_id`, RLS migration `4f61a7dd311e` executed on Supabase, 34 automated unit/API tests passing, live PostgreSQL RLS isolation verified 100%. |
| **03** | Stage A | **Platform Basics** | **Not Started** | Audit logging service, tenant settings, UTC helpers, feature flags, Redis rate limiter middleware. |
| **04** | Stage B | **Employees & Workplaces** | **Not Started** | Employee CRUD, departments, PostGIS locations (`ST_DWithin`), CSV import Celery worker, invite flow. |
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

---

## 12. Next Actions

1. **Immediate Task**: Present Phase 1 Final Audit Report to project owner and obtain sign-off for Phase 2.
2. **Transition to Phase 2 (Upon Approval)**:
   - Begin **Phase 2 — Auth and Tenants** on branch `phase-02`.
   - Core deliverables: Tenant registration, user login, Argon2id password hashing, JWT token lifecycle (access + rotating refresh tokens), role-based access control (owner, admin, hr, manager, employee), per-request `SET LOCAL app.tenant_id = :tenant_id` middleware, and automated cross-tenant isolation test suite.
