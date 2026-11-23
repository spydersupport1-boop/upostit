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
- **Current Phase**: **Phase 10 — Notifications (Outbound Alerts)** (Status: *Milestones 10.1 through 10.8 Completed, Formally Closed under Outcome B [Conditionally Closed] on branch phase-06: 4 database models, Alembic migration `b5c6d7e8f9a0`, Row-Level Security policies, safe template renderer, preference resolver, quiet hours evaluator [all categories strictly respect quiet hours without bypass], mock providers, repository & dispatcher; Firebase Cloud Messaging [FCM] adapter, Fernet token authenticated encryption, mobile device token registration APIs, Celery dispatch workers; 13 business domain events, 23 canonical default templates, transactional outbox pattern, secret protection; Next.js 14 Web Console for notification administration [overview metrics, template overrides with safe variable guidance, PUT endpoint for editing tenant overrides, strict system template immutability, channel readiness indicators with CONFIGURED_UNVERIFIED taxonomy, tenant preferences with quiet hours & RBAC, filterable paginated activity log with inspection drawer]; Flutter Mobile Push Token Lifecycle & In-App Notification Center [Android 13+ & iOS permissions, secure device token registration, token deduplication caching, automatic rotation on refresh, logout revocation, top-level background handler, in-app notification center screen with unread badge, All/Unread filter chips, detail dialog, documented backend inbox 404 API gap handling, safe deep link whitelist, sensitive data redaction]; End-to-End Simulation, Chaos Testing & Multi-Tenant Validation [Leave, Conflicts, Fraud Shield, Invitations, and Password Reset lifecycle simulations; Transaction rollback atomicity, Celery/Redis failure non-blocking fallback, stuck worker recovery, provider timeouts and exponential backoff, worker concurrency atomic lock, cross-tenant data/template/token/preference isolation, RBAC and PostgreSQL RLS verification, cross-platform web/mobile simulation]; Security Audit & Penetration Testing [RBAC hardening on admin endpoints, template SSTI pre-validation against dunder expressions, device token length boundary enforcement, client-side web privilege guards, secret credential masking]; 178 Phase 10 backend tests passing [100%], 833 total backend tests passing [100%], 412 Flutter tests passing [100%], 132 web tests passing [100%], grand total 1,377 automated tests across monorepo; Outcome B due to host lacking live PostgreSQL/Redis daemons and physical mobile hardware; awaiting authorization for Phase 11*)
- **Current Phase**: **Phase 11 — Offline-First Sync Engine & Advanced Conflict Resolution** (Status: *Milestones 11.1, 11.2, 11.3, and 11.4 Completed, Audited & Verified: Architecture assessment & blueprint [11.1]; Batch sync protocol `POST /attendance/sync/batch`, savepoint transaction isolation, dual-tier idempotency, timestamp semantic hardening, zero synthetic break-end events, manager direct-report scoping [11.2]; Downward delta sync protocol `GET /sync/delta` and alias `GET /attendance/sync/delta`, composite keyset pagination v2, frozen session snapshot isolation (`session_ts`), HMAC-SHA256 tamper-resistant cursors, key rotation with fallback keys, TTL expiration, tenant and user context verification, deactivation and soft-deletion semantics, workplace tombstones across page boundaries, mobile SQLite schema upgrade to version 2 with 10 versioned cache tables, queue preservation invariant, atomic transactional delta application, mobile sync coordinator with concurrency mutex, pagination loop, self-healing cursor reset [11.3]; Flutter Mobile Enhanced Offline Queue & Resilient Sync Engine [11.4]: Unified bidirectional synchronization coordinator (`UnifiedSyncCoordinator`), upward batch upload integration with partial receipt reconciliation (ACCEPTED, DUPLICATE, REQUIRES_REVIEW, RETRYABLE, REJECTED), session quarantine cascades, monotonic stale-response protection in downward sync (version-based policy protection and timestamp-based entity updates), background synchronization scheduler with synchronous entry mutex, resilient BLoC operational phase tracking, offline status banners and UX components, strict non-destructive queue preservation; 879 backend tests passing [100%], 438 Flutter tests passing [100%], 132 web tests passing [100%], grand total 1,449 automated tests passing 100% across monorepo; 0 Ruff issues, 0 Flutter analyzer issues, 0 Mypy issues; awaiting authorization for Milestone 11.5*)

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
| **05** | Stage B | **Shifts and Punch Engine** | **Complete** | Immutable punch event ledger, shift versioning, grace periods, daily presence projections, PostGIS ST_DWithin geofence verification, Celery nightly reconciliation, Next.js /attendance dashboard. Live migration a2b3c4d5e6f7 applied. 281 backend & 52 frontend tests passing. Git tag phase-05-complete (commit a4dad73). |
| **06** | Stage B | **Mobile Check-in (Flutter)** | **Complete (Milestones 6.1–6.7 Verified)** | Milestones 6.1 through 6.7 complete on branch `phase-06`. 284 Flutter tests passing (100%), Android debug APK and release APK (69.0MB with ProGuard/R8 rules and SQLCipher) built cleanly, network security config enforced, 101 backend regression tests passing (385 combined). Awaiting review before Phase 7. |
| **07** | Stage B | **Fraud Shield v1** | **In Progress (Milestones 7.1–7.5 Complete)** | Milestones 7.1 (device binding & `devices` table), 7.2 (GPS mock detection, clock drift, velocity), 7.3 (fraud rules & deterministic risk scoring engine), 7.4 (review queue, decision workflows & audit ledger), and 7.5 (Flutter mobile device binding, status card & fraud telemetry) complete and verified. 425 backend tests and 316 Flutter tests passing (100%). Ready for Milestone 7.6. |
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

### [2026-11-04] — Phase 6 Mobile Attendance Architecture & Implementation Plan Complete
- **Phase**: Phase 6 (Mobile Attendance Application — Architecture & Planning)
- **Status**: Planning Complete (Awaiting User Review & Approval to Begin Milestone 6.1)
- **Branch**: `phase-05` (Planning documentation only; no new branch created)
- **Actions Taken**:
  - **Comprehensive Architecture Document**: Authored [`docs/MOBILE_ATTENDANCE_ARCHITECTURE.md`](file:///Users/apple/Upostit/docs/MOBILE_ATTENDANCE_ARCHITECTURE.md) defining the Clean Architecture / BLoC pattern, company-configurable verification modes (A: GPS, B: Wi-Fi, C: Combined), cross-platform capabilities matrix, encrypted local SQLite queue, stable UUID idempotency protocol, and mobile JWT session lifecycle.
  - **Actionable Milestone Plan**: Authored [`docs/PHASE_06_PLAN.md`](file:///Users/apple/Upostit/docs/PHASE_06_PLAN.md) detailing Milestones 6.1 through 6.7 with full 15-point specifications per milestone (objectives, scopes, files, reused APIs, permissions, error cases, automated/manual tests, acceptance criteria, and risks).
  - **Backend Reuse Identified**: Reused `POST /auth/login`, `POST /auth/refresh` (body transport), `POST /attendance/punch` (with Phase 5 idempotency and drift detection), `GET /employees/me/workplaces`, `GET /attendance/shifts/assignments`, and `GET /attendance/days/me`.
  - **Strict Boundaries Enforced**: Zero application code, zero Flutter modifications, zero database migrations, zero dependency installations, and zero Git commits made.
- **Files Modified / Created**:
  - `docs/MOBILE_ATTENDANCE_ARCHITECTURE.md` (Created)
  - `docs/PHASE_06_PLAN.md` (Created)
  - `PROJECT_CONTEXT.md` (Updated)

### [2026-11-04] — Phase 6 Architecture Refinement (Planning Only)
- **Phase**: Phase 6 (Mobile Attendance Application — Architecture Refinement)
- **Status**: Refined Architecture Complete (Awaiting Approval to Begin Implementation)
- **Branch**: `phase-05` (Planning documentation only; no new branch created)
- **Actions Taken**:
  - **1. iOS Wi-Fi Compatibility Policy**:
    - Documented hard dependency on Apple's `com.apple.developer.networking.wifi-info` entitlement and `NSLocationWhenInUseUsageDescription` with Precise Location enabled.
    - Identified real-world BSSID unavailability triggers (simulators, missing entitlement, approximate location toggle, private MAC randomization, enterprise MDM restrictions).
    - Specified dynamic capability probe `isWifiVerificationAvailable()`.
    - Enforced **fail-closed policy**: Wi-Fi-only attendance (Mode B) must NEVER silently succeed when verification is unavailable.
    - Defined administrator-configured fallback: GPS fallback in Mode B or Mode C is allowed **only when explicitly configured by company administrator** (`allow_gps_fallback_if_wifi_unsupported: true`).
    - Standardized actionable user-facing error messages across all Wi-Fi failure states.
    - Mandated **physical real-device iOS testing** with active provisioning profile as a release requirement.
  - **2. Offline Attendance Trust & Zero-Trust Policy**:
    - Specified RFC4122 UUID v4 idempotency key generated once at punch tap and replayed across all retries.
    - Mandated immutable preservation of original `device_reported_at` (ISO 8601 UTC) and `timezone_offset_minutes`.
    - Selected SQLCipher (AES-256) for local SQLite encryption at rest with keys in platform Keychain/Keystore.
    - Enforced UI labeling as **Pending Synchronization** (`PENDING_SYNC`) with distinct sky-blue badge (never "Verified Attendance").
    - Reaffirmed core invariant: **The client never decides its own final attendance verification status.** Server-side calculation engine holds sole authority over presence, lateness, and verification.
    - Detailed server handling for suspicious timestamps (clock drift > 300s flagged with `FLAG_SUSPICIOUS_CLOCK_DRIFT` and `PENDING_REVIEW`, future timestamps, stale offline punches).
  - **3. Dedicated Mobile Authentication Strategy**:
    - Clearly contrasted mobile Bearer auth with web HttpOnly cookies (eliminates mobile cookie jar vulnerabilities and native bridge friction).
    - Access tokens kept in volatile memory; refresh tokens stored in platform-secure storage (iOS Keychain with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, Android Keystore with `EncryptedSharedPreferences`).
    - Implemented concurrency-safe **Refresh Mutex** in Dio `AuthInterceptor` on HTTP 401 to prevent parallel refresh races and false backend reuse revocation.
    - Online logout dispatches `POST /api/v1/auth/logout` to revoke refresh token in database before clearing local vault.
  - **4. Pending Offline Punches During Logout**:
    - High-visibility modal warning dialog detailing pending offline punch count before logout confirmation.
    - **Zero silent deletion**: Pending punches are strictly preserved in local encrypted SQLite.
    - Enforced row binding to `(tenant_id, employee_id, user_id)` in `local_attendance_queue`, guaranteeing complete isolation on shared multi-user devices.
    - Defined automatic sync resumption upon original user re-login.
    - Defined recovery workflows for deactivated accounts (HTTP 403 handling + encrypted diagnostic receipt) and lost/changed devices (missed punch correction via web console).
  - **5. Reviewed & Updated Milestones 6.1–6.7**:
    - Updated acceptance criteria, security checks, test requirements, and platform limitation warnings across all 7 milestones.
- **Files Modified**:
  - `docs/MOBILE_ATTENDANCE_ARCHITECTURE.md` (Updated to Revision 2.0)
  - `docs/PHASE_06_PLAN.md` (Updated to Revision 2.0)
  - `PROJECT_CONTEXT.md` (Updated)

### [2026-11-04] — Phase 6 Milestone 6.1 Implementation Complete (Flutter Foundation, Design System & Secure Mobile Authentication)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.1)
- **Status**: Milestone 6.1 Implementation Complete (Awaiting User Review Before Milestone 6.2)
- **Branch**: `phase-06` (Branched from `a4dad73` / `phase-05-complete`)
- **Actions Taken**:
  - **1. Flutter Clean Architecture Foundation**:
    - Created feature-first directory layout under `apps/mobile/lib/` (`core/`, `features/auth/`, `features/profile/`, `shared/widgets/`).
    - Configured Material 3 enterprise design system with tokens (`AppColors`, `AppSpacing`, `AppRadius`, `AppTypography`) and reusable widgets (`AppButton`, `AppTextField`, `LoadingIndicator`, `ErrorBanner`, `EmptyStateView`).
    - Added core dependencies in `pubspec.yaml` (`flutter_bloc: ^8.1.5`, `dio: ^5.4.3+1`, `flutter_secure_storage: ^9.0.0`, `go_router: ^14.1.4`, `google_fonts: ^6.2.1`, `equatable: ^2.0.5`, `bloc_test: ^9.1.7`, `mocktail: ^1.0.3`).
  - **2. Dedicated Mobile Token Architecture & Concurrency Mutex**:
    - Implemented in-memory access token storage via `InMemoryTokenManager` (volatile heap only, never written to disk).
    - Implemented platform-secure storage via `FlutterSecureStorageService` with iOS Keychain (`first_unlock_this_device`) and Android Keystore (`encryptedSharedPreferences: true`, AES-256 GCM).
    - Implemented thread-safe token refresh mutex in `AuthInterceptor` using Dart `Completer<String?>` to serialize concurrent HTTP 401s into exactly one refresh call to `POST /api/v1/auth/refresh`, with request replay and infinite loop prevention.
  - **3. Authentication & Profile Endpoints**:
    - Verified and implemented contracts for `POST /api/v1/auth/login` (email, password, tenant_slug), `POST /api/v1/auth/refresh` (rotated refresh token), `POST /api/v1/auth/logout` (server session revocation), `GET /api/v1/auth/me` (user & tenant identity), and `GET /api/v1/employees/me` (employee details with graceful 404 fallback for administrative accounts).
    - Created `SplashScreen` (silent session restore), `LoginScreen` (validation, error banners), and `ProfileScreen` (organization, identity, employee badge, sign out confirmation modal).
  - **4. Automated Testing Suite & Backend Verification**:
    - Created 9 comprehensive test suites under `apps/mobile/test/` covering units, repositories, BLoCs, concurrency mutex, and widget rendering.
    - Verified all 281 existing backend pytest tests pass without regression.
  - **5. Milestone Documentation**:
    - Created `docs/phase-reports/PHASE_06_MILESTONE_01_REPORT.md`.
    - Updated `docs/PHASE_06_PLAN.md` to Revision 2.1 (Milestone 6.1 complete).
  - **6. Environment Provisioning & Verification Pass**:
    - Installed Flutter 3.47.9 / Dart 3.13.7 via Homebrew cask.
    - Installed Eclipse Temurin OpenJDK 17.0.21+9 and configured `JAVA_HOME`.
    - Installed Android Studio 2026.2.2.8, Android SDK Platform 36 & 34, Build-Tools 36.0.0 & 34.0.0, Platform-Tools 37.0.1, and Command-line Tools (`cmdline-tools;latest`).
    - Configured Android SDK directory at `~/Library/Android/sdk` (`ANDROID_HOME`); accepted all SDK package licenses; confirmed `[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)` in `flutter doctor -v`.
    - Generated native Android and iOS scaffolding: `flutter create --platforms=android,ios --org=com.upostit .` without overwriting existing code.
    - Resolved all 101 dependencies with `flutter pub get`.
    - Resolved 22 static analysis issues; ran `flutter analyze` -> `Analyzing mobile... No issues found! (ran in 8.2s)`.
    - Executed all 9 mobile test suites: `flutter test` -> **43 passed, 0 failed, 0 skipped**.
    - Executed Android debug build: `flutter build apk --debug` -> `✓ Built build/app/outputs/flutter-apk/app-debug.apk` (154 MB verified on disk).
    - Executed backend pytest suite: `.venv/bin/pytest tests/ -v` -> **281 passed, 0 failed, 41 warnings** in 85.44s.
    - Verified database connectivity with `services/api/verify_db.py`: Supabase Project (HTTP 200 OK), PostgreSQL direct connection (safe `SELECT 1` succeeded), PostGIS extension active.
- **Files Created**:
  - `apps/mobile/lib/app.dart`
  - `apps/mobile/lib/core/config/env_config.dart`
  - `apps/mobile/lib/core/constants/app_colors.dart`
  - `apps/mobile/lib/core/constants/app_spacing.dart`
  - `apps/mobile/lib/core/constants/app_typography.dart`
  - `apps/mobile/lib/core/errors/app_exception.dart`, `failure.dart`, `result.dart`
  - `apps/mobile/lib/core/network/api_client.dart`, `api_endpoints.dart`, `auth_interceptor.dart`
  - `apps/mobile/lib/core/storage/secure_storage_service.dart`, `token_manager.dart`
  - `apps/mobile/lib/core/theme/app_theme.dart`
  - `apps/mobile/lib/core/utils/validators.dart`
  - `apps/mobile/lib/features/auth/` (data, domain, presentation)
  - `apps/mobile/lib/features/profile/` (data, domain, presentation)
  - `apps/mobile/lib/shared/widgets/` (`app_button.dart`, `app_text_field.dart`, `empty_state_view.dart`, `error_banner.dart`, `loading_indicator.dart`)
  - `apps/mobile/test/` (9 test files)
  - `docs/phase-reports/PHASE_06_MILESTONE_01_REPORT.md`
- **Files Modified**:
  - `apps/mobile/pubspec.yaml`
  - `apps/mobile/lib/main.dart`
  - `docs/PHASE_06_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-05] — Phase 6 Milestone 6.2 Implementation Complete (Online Attendance & Punch UI Implementation)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.2)
- **Status**: Milestone 6.2 Implementation Complete (Awaiting User Review Before Milestone 6.3)
- **Branch**: `phase-06` (Baseline: `a4dad73` / `phase-05-complete`)
- **Actions Taken**:
  - **1. Clean Architecture Attendance Feature Layout**:
    - Created domain layer under `apps/mobile/lib/features/attendance/domain/`: entities (`attendance_status.dart`, `attendance_event.dart`, `attendance_day.dart`, `punch_result.dart`, `today_shift.dart`, `assigned_workplace.dart`, `attendance_dashboard.dart`) and abstract repository contract (`attendance_repository.dart`).
    - Created data layer under `apps/mobile/lib/features/attendance/data/`: DTO models (`punch_request_model.dart`, `attendance_event_model.dart`, `punch_response_model.dart`, `attendance_day_model.dart`, `shift_assignment_model.dart`, `employee_workplace_model.dart`), remote data source (`attendance_remote_data_source.dart`), and repository implementation (`attendance_repository_impl.dart`).
    - Created presentation layer under `apps/mobile/lib/features/attendance/presentation/`: BLoC (`attendance_bloc.dart`, `attendance_event.dart`, `attendance_state.dart`), attendance widgets (`hero_punch_card.dart`, `working_timer_card.dart`, `attendance_status_badge.dart`, `last_punch_badge.dart`, `shift_workplace_card.dart`, `today_punches_list.dart`), and complete employee attendance screen (`attendance_home_screen.dart`).
  - **2. Interactive Hero Punch Interface & Real-Time Timers**:
    - Implemented state-aware hero button dynamically adapting across `CHECK IN`, `CHECK OUT`, `START BREAK`, and `RESUME WORK` with in-flight disablement and animated loading spinner to block double-taps.
    - Integrated live digital elapsed session timer ticker (`HH:MM:SS`) using Monospace tabular typography, anchored to server-confirmed punch times (`effective_at`) to eliminate client clock drift skew.
    - Added haptic feedback (`HapticFeedback.mediumImpact()`) on button trigger.
  - **3. Server-Authoritative State Machine & Idempotency Protocol**:
    - The client derives state exclusively from the server's ledger events and daily projection (`AttendanceStatus.notCheckedIn`, `working`, `onBreak`, `completed`).
    - Client generates RFC4122 UUID v4 `idempotency_key` per punch attempt and strictly reuses the same key on retry, enabling backend `attendance_idempotency_records` table to return idempotent HTTP 200 without duplicate ledger insertion.
    - Preserved client device UTC timestamp (`device_reported_at`) and timezone offset (`timezone_offset_minutes`).
  - **4. Backend Endpoint Integration**:
    - Integrated Phase 5 endpoints: `POST /api/v1/attendance/punch`, `GET /api/v1/attendance/days`, `GET /api/v1/attendance/events`, `GET /api/v1/shifts/assignments`, and `GET /api/v1/employees/me/workplaces` without backend modifications.
  - **5. Testing & Verification Suite**:
    - Created 5 new test suites in `apps/mobile/test/features/attendance/` covering DTO serialization, repository logic, BLoC state transitions & retry idempotency, hero button interactions, and attendance home screen rendering.
    - Ran `flutter analyze`: **0 issues found** (Clean).
    - Ran `flutter test`: **81 passed, 0 failed, 0 skipped** across all 14 mobile test suites.
    - Built Android debug APK: `flutter build apk --debug` -> `✓ Built build/app/outputs/flutter-apk/app-debug.apk` (**177 MB** verified on disk).
    - Ran backend attendance regression: `.venv/bin/pytest tests/test_phase5_punch_ledger.py tests/test_phase5_shifts.py tests/test_phase5_calculation_engine.py -v` -> **89 passed, 0 failed, 26 warnings** in 2.88s.
  - **6. Milestone Documentation**:
    - Created `docs/phase-reports/PHASE_06_MILESTONE_02_REPORT.md`.
    - Updated `docs/PHASE_06_PLAN.md` to Revision 2.2.
- **Files Created**:
  - `apps/mobile/lib/features/attendance/` (14 source files)
  - `apps/mobile/test/features/attendance/` (5 test suites)
  - `docs/phase-reports/PHASE_06_MILESTONE_02_REPORT.md`
- **Files Modified**:
  - `apps/mobile/lib/app.dart`
  - `apps/mobile/lib/main.dart`
  - `apps/mobile/lib/core/network/api_endpoints.dart`
  - `apps/mobile/lib/features/auth/presentation/screens/splash_screen.dart`
  - `apps/mobile/lib/features/auth/presentation/screens/login_screen.dart`
  - `apps/mobile/lib/features/profile/presentation/screens/profile_screen.dart`
  - `apps/mobile/test/widget_test.dart`
  - `docs/PHASE_06_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-05] — Architecture Refinement: Company Attendance Policy Engine & GPS Remediation Planning
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.3 Architecture Planning)
- **Status**: Planning Refinement Complete (Awaiting User Review & Approval Before Code Changes)
- **Branch**: `phase-06` (Baseline: `a4dad73` / `phase-05-complete`)
- **Key Architectural Decisions Formulated**:
  - **1. Central Company Attendance Policy Engine**:
    - Designed tenant-configurable presence rules: `MANUAL` (default for web/remote; zero location requirements), `GPS_ONLY` (Mode A), `WIFI_ONLY` (Mode B), `BIOMETRIC` (Phase 15), `FACE_RECOGNITION` (Phase 7), and `COMBINED` (Mode C: AND / OR with fallbacks).
    - Preserves common append-only event ledger (`attendance_events`) and calculation engine (`calculate_attendance_day`) across all methods.
    - Server-authoritative enforcement: The backend, not the mobile app, determines whether location or Wi-Fi evidence is required and valid.
  - **2. Three Backend GPS Remediations**:
    - **Remediation A (Workplace Coordinates)**: Extend `EmployeeWorkplaceResponse` (`GET /api/v1/employees/me/workplaces`) to include `latitude`, `longitude`, and `radius_meters` for assigned active workplaces only, maintaining privacy boundaries without exposing tenant-wide location directories.
    - **Remediation B (Employee Geofence Probe)**: Introduce dedicated `POST /api/v1/employees/me/workplaces/verify-coordinates` guarded by `Permission.RECORD_PUNCH`, validating employee assignment and date effectiveness before running PostGIS `ST_DWithin`.
    - **Remediation C (Server Punch Enforcement)**: Enforce PostGIS `ST_DWithin` spatial verification in `record_punch` when mandated by active policy, rejecting (HTTP 400) or reviewing out-of-geofence punches while maintaining idempotency and append-only ledger integrity.
  - **3. Planning Documentation Updated**:
    - `docs/MOBILE_ATTENDANCE_ARCHITECTURE.md`: Updated to Revision 2.1 with Company Attendance Policy Engine & verification modes.
    - `docs/PHASE_06_PLAN.md`: Updated to Revision 2.3 with Milestone 6.3 remediated scope.
    - `PROJECT_CONTEXT.md`: Updated with architecture refinement record.

---

### [2026-11-05] — Phase 6 Milestone 6.3.A Implementation Complete (Backend Attendance Policy Engine & GPS Geofence Enforcement)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.3.A)
- **Status**: Backend Implementation & Live Verification Complete
- **Branch**: `phase-06` (Baseline: `a4dad73` / `phase-05-complete`)
- **Live Supabase Head**: `b3c4d5e6f7a8 (head)` (Down: `a2b3c4d5e6f7`)
- **Key Deliverables Delivered**:
  - **1. Central Tenant Attendance Policy Model**:
    - Created `tenant_attendance_policies` table with RLS, immutable versioning, composite foreign keys, and seeded initial Version 1 `MANUAL` policy for all existing tenants.
    - Guaranteed strictly one active policy per tenant via partial unique index `uq_tenant_attendance_policy_one_active`.
    - Added `applied_policy_version INTEGER` to `attendance_events` for immutable historical traceability.
  - **2. Dedicated Policy Engine Service**:
    - Built `services/api/attendance/policy_engine.py` supporting `MANUAL`, `GPS_ONLY`, `COMBINED`, and `PRIMARY_WITH_FALLBACK`.
    - Enforced fail-safe handling (`HTTP 422`) for future methods (`WIFI`, `BIOMETRIC`, `FACE_RECOGNITION`), preventing silent downgrade to manual punching.
  - **3. Employee-Safe Policy Endpoint**:
    - Implemented `GET /api/v1/attendance/policy/me` guarded by `Permission.VIEW_ATTENDANCE_POLICY` or `RECORD_PUNCH`.
    - Returns sanitized policy fields without leaking administrative audit timestamps or creator IDs.
  - **4. Workplace Coordinates & Geofence Verification Probe**:
    - Extended `GET /api/v1/employees/me/workplaces` with `latitude`, `longitude`, and `radius_meters` for assigned active workplaces.
    - Implemented `POST /api/v1/employees/me/workplaces/verify-coordinates` probe guarded by `Permission.RECORD_PUNCH`, authoritatively checking distance and geofence containment via PostGIS `ST_Distance` and `ST_DWithin`.
  - **5. Server-Authoritative Punch Ingestion**:
    - Integrated policy evaluation into `POST /api/v1/attendance/punch`.
    - Under `MANUAL`: Coordinates are optional telemetry and never gate punches.
    - Under `GPS_ONLY`: Enforces workplace assignment, accuracy ($\le 100\text{m}$), freshness ($\le 30\text{s}$), and PostGIS `ST_DWithin` spatial perimeter (rejects or flags for review per tenant policy).
    - Preserved 100% idempotency replay behavior and backward compatibility.
  - **6. Verification & Test Suite**:
    - 19 new tests in `tests/test_phase6_attendance_policy.py` passing (100%).
    - Complete regression suite: **300 passed, 0 failures** across all backend tests.
    - Zero lint issues (`ruff check`) and zero type errors (`mypy 50 source files`).
  - **7. Artifacts Updated**:
    - `database/migrations/versions/b3c4d5e6f7a8_phase_06_tenant_attendance_policies.py`
    - `services/api/attendance/policy_engine.py`
    - `services/api/attendance/models.py`
    - `services/api/attendance/schemas.py`
    - `services/api/attendance/routes.py`
    - `services/api/attendance/service.py`
    - `services/api/employees/routes.py`
    - `services/api/locations/assignment_service.py`
    - `services/api/locations/schemas.py`
    - `services/api/auth/permissions.py`
    - `tests/test_phase6_attendance_policy.py`
    - `docs/phase-reports/PHASE_06_MILESTONE_03A_REPORT.md`
    - `PROJECT_CONTEXT.md`

### [2026-11-05] — Phase 6 Milestone 6.3.B Implementation Complete (Flutter Mobile GPS Attendance Integration & Policy Enforcement)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.3.B)
- **Status**: Milestone 6.3.B Implementation Complete (Awaiting User Review Before Milestone 6.4)
- **Changes Completed**:
  - Integrated `GET /api/v1/attendance/policy/me` in Flutter mobile client (`apps/mobile/`).
  - Implemented `MANUAL` attendance mode: zero GPS permissions requested, zero location hardware calls, clean dashboard without location warnings.
  - Implemented `GPS_ONLY` mode (Mode A): checks/requests foreground location permission, enforces accuracy filtering ($\le 100\text{m}$) and freshness ($\le 30\text{s}$), binds assigned workplace identifier, and submits coordinates to server-authoritative PostGIS `ST_DWithin` geofence validation. Client-side Haversine is strictly advisory.
  - Implemented explicit blocking for unsupported attendance modes (`WIFI_ONLY`, `BIOMETRIC_ONLY`, `FACE_RECOGNITION`, `COMBINED`) with informative employee guidance.
  - Handled location exceptions gracefully: `LocationPermissionDeniedException`, `LocationPermissionPermanentlyDeniedException`, `LocationServiceDisabledException`, `LocationTimeoutException`, `LocationAccuracyException`, `LocationStaleException`, and `MockLocationDetectedException`.
  - Added Android mock-location indicator inspection (`isMocked == true`) as a risk signal with documented iOS sandbox limitations.
  - Created `GeofenceStatusCard` widget (rendered only when GPS is mandated) showing workplace name, perimeter distance, and permission resolution prompts.
  - Maintained single RFC 4122 UUID v4 idempotency key across network/GPS retries and enforced double-tap protection.
  - Implemented `WidgetsBindingObserver` in `AttendanceHomeScreen` for auto-recovery when returning from system settings.
  - Added 43 new unit/BLoC/widget tests (124 total mobile tests, 100% pass).
  - Built Android debug APK cleanly (`flutter build apk --debug`, 38.3s).
  - Executed full backend regression suite (300/300 tests passing, `ruff` and `mypy` 100% clean).
- **Files Modified / Created**:
  - `apps/mobile/pubspec.yaml`
  - `apps/mobile/android/app/src/main/AndroidManifest.xml`
  - `apps/mobile/ios/Runner/Info.plist`
  - `apps/mobile/lib/core/network/api_endpoints.dart`
  - `apps/mobile/lib/features/attendance/data/models/punch_request_model.dart`
  - `apps/mobile/lib/features/attendance/data/models/employee_workplace_model.dart`
  - `apps/mobile/lib/features/attendance/data/models/attendance_policy_model.dart`
  - `apps/mobile/lib/features/attendance/data/datasources/attendance_remote_data_source.dart`
  - `apps/mobile/lib/features/attendance/domain/entities/attendance_policy.dart`
  - `apps/mobile/lib/features/attendance/domain/entities/assigned_workplace.dart`
  - `apps/mobile/lib/features/attendance/domain/entities/attendance_dashboard.dart`
  - `apps/mobile/lib/features/attendance/domain/repositories/attendance_repository.dart`
  - `apps/mobile/lib/features/attendance/data/repositories/attendance_repository_impl.dart`
  - `apps/mobile/lib/features/attendance/data/services/location_service.dart`
  - `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart`
  - `apps/mobile/lib/features/attendance/presentation/bloc/attendance_event.dart`
  - `apps/mobile/lib/features/attendance/presentation/bloc/attendance_state.dart`
  - `apps/mobile/lib/features/attendance/presentation/widgets/geofence_status_card.dart`
  - `apps/mobile/lib/features/attendance/presentation/widgets/hero_punch_card.dart`
  - `apps/mobile/lib/features/attendance/presentation/screens/attendance_home_screen.dart`
  - `apps/mobile/test/features/attendance/data/models/punch_request_model_test.dart`
  - `apps/mobile/test/features/attendance/data/services/location_service_test.dart`
  - `apps/mobile/test/features/attendance/presentation/bloc/attendance_gps_bloc_test.dart`
  - `apps/mobile/test/features/attendance/presentation/widgets/geofence_status_card_test.dart`
  - `docs/phase-reports/PHASE_06_MILESTONE_03B_REPORT.md`
  - `docs/MOBILE_ATTENDANCE_ARCHITECTURE.md`
  - `docs/PHASE_06_PLAN.md`
  - `PROJECT_CONTEXT.md`

### [2026-11-05] — Phase 6 Milestone 6.4.A Implementation Complete (Backend Wi-Fi Attendance Verification & Admin-Configurable Fallback)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.4.A)
- **Status**: Milestone 6.4.A Complete & Verified (Awaiting User Review Before Milestone 6.4.B)
- **Deliverables Completed**:
  - Live Supabase Alembic migration `c4d5e6f7a8b9` created and executed: `workplace_wifi_access_points` table with RLS, foreign keys, indexes; `locations.wifi_config_override`; `attendance_events.wifi_bssid` & `wifi_ssid`.
  - SQLAlchemy models and Pydantic schemas for access point management (`WorkplaceWifiAccessPoint`) and Wi-Fi probe/punch DTOs.
  - Admin access point management APIs (`GET`, `POST`, `PATCH`, `DELETE /api/v1/locations/{id}/wifi-access-points`) with RBAC and soft deactivation.
  - Employee Wi-Fi probe endpoint (`POST /api/v1/employees/me/workplaces/verify-wifi`) returning signal states (`MATCHED`, `MISMATCHED`, `UNAVAILABLE`, `UNSUPPORTED`, `STALE`).
  - Authoritative Policy Engine Wi-Fi verification (`evaluate_punch_policy`) supporting all four fallback actions (`REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`).
  - Combination rule enforcement (`AND`, `OR`, `PRIMARY_WITH_FALLBACK`), strictly preventing fallbacks from weakening multi-factor `AND` rules.
  - Workplace-level policy overrides with fail-closed conflict resolution.
  - Comprehensive automated test suite (`tests/test_phase6_wifi_verification.py` — 15 tests) passing 100%.
  - Full backend regression suite (315 tests passing, Ruff clean, Mypy clean).
  - Live Supabase synthetic end-to-end verification and 100% cleanup confirmed.
  - Milestone report published: `docs/phase-reports/PHASE_06_MILESTONE_04A_REPORT.md`.

### [2026-11-06] — Phase 6 Milestone 6.4.B Implementation Complete (Flutter Mobile Wi-Fi Attendance Integration & Policy Fallback Enforcement)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.4.B)
- **Status**: Milestone 6.4.B Complete & Verified (Awaiting User Review Before Milestone 6.5)
- **Deliverables Completed**:
  - Integrated `network_info_plus: ^7.0.0` for connected workplace AP inspection with zero background scanning.
  - Native platform declarations: Android `ACCESS_WIFI_STATE` & `ACCESS_FINE_LOCATION`; iOS `Runner.entitlements` with `com.apple.developer.networking.wifi-info` linked in Debug and Release xcconfig.
  - BSSID canonical normalization (`XX:XX:XX:XX:XX:XX`) and dummy/placeholder MAC address filtering (`02:00:00:00:00:00`).
  - Implemented `WifiService` and `NetworkInfoWifiService` cross-platform device abstraction layer with Android location-toggle detection and iOS entitlement fallback mapping.
  - Extended domain entities (`WifiEvidence`, `WifiVerificationResult`, `AttendancePolicy`) and network models (`PunchRequestModel`, `EmployeeWifiVerifyModel`).
  - Added remote Wi-Fi verification probe API (`POST /api/v1/employees/me/workplaces/verify-wifi`) to repository and data sources.
  - Implemented policy-driven punch flows in `AttendanceBloc` for `MANUAL`, `GPS_ONLY`, `WIFI_ONLY` (with `REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`), and `COMBINED` (with `AND` fail-closed dual-factor vs `OR`).
  - Added `WifiStatusCard` UI component to `AttendanceHomeScreen` with probe action and permission resolution.
  - Ensured punch idempotency safety: single UUID v4 preserved across retries, exact Wi-Fi/GPS evidence retained, HTTP 422 payload mismatch handled cleanly.
  - 100% clean static analysis (`flutter analyze` with 0 issues), 100% code formatted (`dart format`).
  - 158 / 158 Flutter tests passing (100% test pass rate across unit, BLoC, and widget suites).
  - Android debug APK successfully compiled (`flutter build apk --debug`).
  - 100% backend test pass rate (23 Wi-Fi tests, 19 policy engine tests passing).
  - Milestone report published: `docs/phase-reports/PHASE_06_MILESTONE_04B_REPORT.md`.

### [2026-11-06] — Phase 6 Milestone 6.5 Architecture Planning Complete (Encrypted Offline Attendance Queue & Synchronization Engine)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.5 Architecture)
- **Status**: Planning Complete & Approved (Awaiting User Review & Approval to Begin Milestone 6.5.A)
- **Deliverables Completed**:
  - Published comprehensive technical design specification: [`docs/PHASE_06_MILESTONE_05_DESIGN.md`](file:///Users/apple/Upostit/docs/PHASE_06_MILESTONE_05_DESIGN.md) (v2.1).
  - Resolved core design decisions and formalized trust boundaries:
    1. **Offline Timestamps & Drift (DDR-6.5-01)**: Immutable `device_reported_at` vs independent `server_received_at`; standard automated ingest up to 24 hours (`FLAG_DELAYED_OFFLINE_SYNC`), supervisor review for 24–72 hours (`FLAG_OFFLINE_WINDOW_EXCEEDED`), hard rejection beyond 72 hours; future timestamps $> 300\text{s}$ rejected.
    2. **Trust Boundary & Monotonic Clock Risk Telemetry (DDR-6.5-02)**: Explicit boundary: all client telemetry (wall clock, monotonic uptime, boot ID, GPS, Wi-Fi) is untrusted risk telemetry, not cryptographic proof. Rooted/jailbroken platforms can spoof values; client claims can never override server rules. Native channel captures `boot_session_id` and monotonic uptime; intra-boot drift $> 60\text{s}$ flagged as suspected clock tampering.
    3. **Offline Sequence Conflict Resolution Workflow (DDR-6.5-03)**: Verified that existing `POST /api/v1/attendance/corrections` is admin-only (employees get HTTP 403) and operates on single ledger events. Defined conflict bundle workflow (`QUARANTINED_DEPENDENT_FAILURE`) grouping failed and dependent session punches for supervisor resolution in Phase 8, unblocking future sessions and preventing duplicate submissions via unique bundle ID and row-level locking.
    4. **SQLCipher Primary with Approved Envelope Alternative (DDR-6.5-04)**: SQLCipher full-page encryption preferred; envelope encryption on standard `sqflite` approved as production alternative if native C/CocoaPods linking encounters host blockers. Fail-closed: zero plaintext database fallback on encryption initialization error.
  - Relational queue schema defined (`local_attendance_queue`) with `(tenant_id, employee_id, user_id)` isolation, UUID v4 idempotency keys generated once at punch time, monotonic sequence, and audit timestamps.
  - Decomposed Phase 6.5 into 4 discrete sub-milestones (6.5.A, 6.5.B, 6.5.C, 6.5.D).
  - Synchronized documentation: updated [`docs/MOBILE_ATTENDANCE_ARCHITECTURE.md`](file:///Users/apple/Upostit/docs/MOBILE_ATTENDANCE_ARCHITECTURE.md) (v2.5) and [`docs/PHASE_06_PLAN.md`](file:///Users/apple/Upostit/docs/PHASE_06_PLAN.md) (v2.7).

### [2026-11-16] — Phase 6 Milestone 6.5.A Implementation & Security Audit Hardening
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.5.A Implementation & Correction)
- **Status**: Audit Hardening Complete & Fully Verified (Awaiting Review Before Milestone 6.5.B)
- **Implemented Security & Data Integrity Corrections**:
  - **Session-Aware Quarantine**: Introduced `sessionId` in `LocalQueueItem`, `LocalQueueItemModel`, and `local_attendance_queue.session_id`. `quarantineDependentEvents()` isolates failures strictly to the rejected punch's session (`session_id`), ensuring subsequent shifts/sessions remain eligible for synchronization.
  - **Fail-Closed Keystore Key Management**: Updated `DatabaseKeyProvider.getEncryptionKey({required bool databaseExists})` to generate keys ONLY when creating a genuinely new database (`databaseExists == false`). If a database file already exists but the key is missing or malformed, it throws `DatabaseEncryptionException` without overwriting keys or creating an unencrypted file over existing data.
  - **Comprehensive Queue Capacity Enforcement**: Updated `insertPendingEvent` to count all unresolved records (`PENDING_SYNC`, `SYNCING`, `QUARANTINED_DEPENDENT_FAILURE`). When $\ge 500$, throws `QueueCapacityExceededException` while preserving 100% of existing punches without silent deletions.
  - **SQLCipher Runtime Integration Test**: Authored `apps/mobile/integration_test/sqlcipher_runtime_encryption_test.dart` to verify AES-256 page encryption, correct-key reopen, wrong-key failure, and plaintext rejection. Disclosed test environment distinction: unit tests on macOS host use system SQLite via FFI (`sqflite_common_ffi`), while native Android build packages native `libsqlcipher.so` (verified in `app-debug.apk`).
- **Verification & Test Results**:
  - `cd apps/mobile && flutter test test/features/sync/`: 29 / 29 unit tests passed (100%).
  - `cd apps/mobile && flutter test`: 187 / 187 tests passed (100% pass rate, 0 regressions).
  - `cd apps/mobile && flutter analyze`: 0 issues found (clean).
  - `cd apps/mobile && dart format .`: 100% compliant.
  - `cd apps/mobile && flutter build apk --debug`: native Android build succeeded (`build/app/outputs/flutter-apk/app-debug.apk`, 78.5s).
  - Host environment limitations: CocoaPods not installed on macOS host; no Android emulator/device connected for running on-device integration tests (marked as physical device release-readiness verification gate for Milestone 6.7).

### [2026-11-16] — Phase 6 Milestone 6.5.B Implementation Complete (Strict FIFO Sync Worker & Network Observer)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.5.B)
- **Status**: Implementation & Validation Complete (Awaiting Review Before Milestone 6.5.C)
- **Implemented Components**:
  - **Network Observer (`NetworkConnectivityServiceImpl`)**: Listens to connectivity changes (`connectivity_plus`), applies 1000ms debounce, and validates real backend reachability via DNS/socket probe (`checkBackendReachability`).
  - **Account-Level Mutex**: Single-worker mutex lock per account (`Set<String> _activeWorkers`) preventing race conditions or duplicate concurrent syncs.
  - **Crash Recovery**: Automatically resets zombie items stranded in `SYNCING` state for >120s back to `PENDING_SYNC` via `resetZombieSyncingItems`.
  - **Strict FIFO Queue Processing**: Sequential in-order processing (`sequence_number ASC, device_reported_at ASC`) with exact original idempotency key, device timestamps, and telemetry preservation.
  - **Error Classification & Retry Engine**:
    - Retryable failures (network dropped, socket timeout, HTTP 408, HTTP 429 with `Retry-After`, HTTP 5xx) apply exponential backoff (2s, 4s, 8s... up to 60s max) and halt the batch safely.
    - Permanent failures (HTTP 400, 422) mark records `REJECTED_PERMANENT` and trigger session-aware quarantine (`quarantineDependentEvents`), while allowing subsequent independent shifts to continue syncing.
    - Authentication failures (refresh failed) pause sync gracefully without deleting or rejecting local punches.
    - Account deactivation triggers callback and halts sync.
    - Server review statuses (`PENDING_REVIEW`, `FLAG_DELAYED_OFFLINE_SYNC`) map to `SyncStatus.flaggedPendingReview`.
- **Verification & Test Results**:
  - `cd apps/mobile && flutter test`: 208 / 208 tests passed (100% pass rate, 0 failed, 0 skipped).
    - Added `network_connectivity_service_test.dart` (7 tests).
    - Added `sync_worker_test.dart` (14 comprehensive tests).
  - `cd apps/mobile && flutter analyze`: 0 issues found (clean).
  - `cd apps/mobile && dart format --output=none --set-exit-if-changed .`: 100% clean.
  - `cd apps/mobile && flutter build apk --debug`: native Android build succeeded (`build/app/outputs/flutter-apk/app-debug.apk`, 93.8s).
  - Backend regression: `./.venv/bin/pytest tests/test_phase6_attendance_policy.py tests/test_phase6_wifi_verification.py -v`: 42 / 42 passed (100% pass rate, 0 backend regressions).
  - Strict scope boundary: Milestone 6.5.C (UI / sync drawer / offline banner) has NOT been started.

---

### [2026-11-19] — Phase 6 Milestone 6.5.D Implementation & Comprehensive Security Audit Complete
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.5.D Offline Simulation & Security Audit)
- **Status**: Complete & Verified (Milestone 6.5 Complete, Awaiting Review Before Milestone 6.6)
- **Key Deliverables Completed**:
  1. **End-to-End Shift Journey Simulation**: 4-punch offline employee shift (CHECK_IN, BREAK_START, BREAK_END, CHECK_OUT) with sequential sequence numbers, persistent local storage, cold restart recovery, and FIFO backend ingestion.
  2. **Network Flap & Idempotent Replay**: Verified connection drop mid-batch, idempotent replay with `is_idempotent_replay: true` on lost responses, and HTTP 429 `Retry-After` backoff handling.
  3. **Crash Recovery & Zombie Mitigation**: Automatic recovery of stranded `SYNCING` records (>120s) back to `PENDING_SYNC` and device reboot handling with monotonic reset and new `boot_session_id`.
  4. **Session-Aware Cascading Quarantine**: Verified that permanent domain rejections in Shift 1 quarantine dependent punches within that session while leaving independent future shifts (Shift 2) intact and eligible to sync.
  5. **Shared Device & Multi-Tenant Isolation**: Verified that logging out User A (Tenant Alpha) and logging in User B (Tenant Beta) exhibits 0 cross-account leakage; User B cannot see or sync User A's records; User A logs back in to find all punches intact and syncs exclusively to Tenant Alpha.
  6. **Security & Database Hygiene Audit**: Fail-closed `DatabaseKeyProvider` on missing/corrupt keys; zero tokens, credentials, or biometric PII stored in offline queue; atomic schema versioning; non-destructive error preservation; and `android:allowBackup="false"` in `AndroidManifest.xml`.
  7. **Native APK Verification**: Confirmed `libsqlcipher.so` bundled across `arm64-v8a`, `armeabi-v7a`, and `x86_64` in `app-debug.apk`. 254 Flutter tests passing, 42 backend tests passing (296 combined).
- **Report**: `docs/phase-reports/PHASE_06_MILESTONE_05D_REPORT.md`

### [2026-11-19] — Phase 6 Milestone 6.6 Implementation Complete (Employee Mobile Dashboard, Shifts & Attendance History)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.6)
- **Status**: Complete & Verified (Awaiting User Review Before Milestone 6.7)
- **What Was Done**:
  1. **Employee Home Dashboard Polish**: Integrated authenticated employee profile, active shift card with real scheduled hours, gross & break duration, remaining shift time countdown, and quick navigation shortcuts.
  2. **Shift Schedule Feature (`ScheduleScreen` at `/schedule`)**: Integrated shift assignments with operational parameters (`start_time`, `end_time`, `grace_period_minutes`, `break_duration_minutes`, `is_overnight`, `is_flexible`, `weekly_off_days`), active shift card, upcoming assigned shifts roster, and empty state for unassigned employees.
  3. **Attendance History & Interactive Calendar (`HistoryScreen` at `/history`)**: Custom 7-column monthly calendar grid with presence status indicators (`PRESENT`, `LATE`, `HALF_DAY`, `ABSENT`, `INCOMPLETE`, `PENDING_REVIEW`, `PENDING_SYNC`), previous/next month navigation, 4-card aggregated monthly summary metrics (Present, Late, Absent, Worked Hours), and chronological monthly daily records.
  4. **Daily Attendance Detail Screen (`DailyAttendanceDetailScreen` at `/history/day`)**: Day-level detail view with date, status badge, assigned shift details, working time metrics (net work, break, late arrival, early departure), local pending sync notice, and chronological event ledger audit stream (`AuditTimelineTile`).
  5. **Backend Data Scoping**: Safely enhanced `ShiftAssignmentResponse` schema and `list_shift_assignments` endpoint to resolve effective shift version parameters and enforce strict employee-level isolation.
  6. **Automated Verification**: 277 Flutter unit and widget tests passing (100%), `flutter analyze` passing with 0 warnings/errors, Dart formatting 100% compliant, Android debug APK built cleanly in 13.9s, and 101 backend regression tests passing (378 tests combined).
- **Report**: `docs/phase-reports/PHASE_06_MILESTONE_06_REPORT.md`

### [2026-11-19] — Phase 6 Milestone 6.7 Implementation Complete (Security Hardening, Real-Device Testing & Release Readiness)
- **Phase**: Phase 6 (Mobile Attendance Application — Milestone 6.7)
- **Status**: Complete & Fully Verified (Phase 6 Complete; Awaiting Review Before Phase 7)
- **What Was Done**:
  1. **Comprehensive Security Audit**: Verified in-memory volatile JWT access-token lifecycle, hardware Keystore/Keychain refresh token storage with `encryptedSharedPreferences: true` and `first_unlock_this_device`, fail-closed SQLCipher key handling, 0 hardcoded credentials/secrets, and 0 log leaks.
  2. **Network Security Configuration**: Created `apps/mobile/android/app/src/main/res/xml/network_security_config.xml` with `cleartextTrafficPermitted="false"`, enforcing HTTPS and strict TLS across Android builds.
  3. **Release Build & ProGuard/R8 Optimization**: Created `apps/mobile/android/app/proguard-rules.pro` protecting SQLCipher native libraries, Flutter secure storage, and serialization models. Assembled production `app-release.apk` (69.0MB) in 153.0s and `app-debug.apk` in 24.7s.
  4. **Native Package Verification**: Verified binary inclusion of `libsqlcipher.so` across `arm64-v8a`, `armeabi-v7a`, and `x86_64` in the production release APK; verified `android:allowBackup="false"` and `android:networkSecurityConfig` via aapt2.
  5. **iOS Project Configuration**: Created `ios/Podfile` targeting iOS 15.0 matching `Runner.xcodeproj` with `SQLITE_HAS_CODEC=1`; verified `Runner.entitlements` includes `com.apple.developer.networking.wifi-info`; documented host environment constraints (Xcode & CocoaPods absent on host).
  6. **Automated Verification**: 284 Flutter unit, widget, and security tests passing (100%), `flutter analyze` passing with 0 warnings/errors, Dart formatting 100% compliant, and 101 backend regression tests passing (385 tests combined).
- **Report**: `docs/phase-reports/PHASE_06_MILESTONE_07_REPORT.md`

### [2026-11-19] — Phase 7 Milestone 7.1 Implementation Complete (Device Binding Subsystem & Database Migration)
- **Phase**: Phase 7 (Mobile Attendance Fraud Shield v1 — Milestone 7.1)
- **Status**: Complete & Fully Verified (Alembic Head `a3b4c5d6e7f8`; 355 backend tests passing 100%; Ready for Milestone 7.2)
- **What Was Done**:
  1. **Database Schema & Migration**: Created migration `a3b4c5d6e7f8_phase_07_devices.py` introducing the `devices` table with composite tenant foreign keys, platform and status check constraints, PostgreSQL RLS enabled and forced, and a database-level partial unique index `ix_devices_tenant_emp_active` on `(tenant_id, employee_id) WHERE status = 'ACTIVE'` enforcing the single active device policy.
  2. **Cryptographic Identity Salting**: Built `hash_device_id` using HMAC-SHA256 keyed with server `SECRET_KEY` and salted with tenant UUID, guaranteeing raw client hardware identifiers are never stored and preventing cross-tenant correlation.
  3. **Domain Models & Pydantic Schemas**: Implemented `Device` SQLAlchemy model and safe Pydantic schemas (`DeviceRegisterRequest`, `DeviceResponse`, `DeviceRegistrationResponse`, `DeviceListResponse`, `DeviceRevokeRequest`, `DeviceReplacementApprovalRequest`, `DeviceStatusResponse`).
  4. **Device Registration API (`POST /api/v1/devices/register`)**: Authenticated employee device registration. Idempotent for matching active device; automatically initiates an audit-logged `PENDING_APPROVAL` replacement request when a different device is registered for an employee with an existing active device.
  5. **Device Management APIs**: Implemented `GET /api/v1/devices` (paginated list with filters), `GET /api/v1/devices/me` (employee self-service status), `POST /api/v1/devices/{id}/revoke` (mandatory reason), and `POST /api/v1/devices/{id}/approve-replacement` (atomic replacement rotation in a single transaction).
  6. **Granular RBAC**: Added `Permission.MANAGE_DEVICES` and `Permission.VIEW_DEVICES` under Owner, Admin, and HR roles; denied to Manager and Employee.
  7. **Attendance Integration Preparation**: Built `validate_device_for_punch()` helper distinguishing `ACTIVE`, `UNREGISTERED`, `REVOKED`, `REPLACED`, `PENDING_APPROVAL`, and `NO_DEVICE_SUPPLIED`.
  8. **Automated Verification**: Authored 32 unit and API tests in `tests/test_phase7_devices.py`. Ran full regression suite with 355 backend tests passing (100%), verified Ruff clean (0 errors), and Mypy clean.
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_01_REPORT.md`

### 2026-11-19: Phase 7 — Milestone 7.2 Complete & Verified (GPS Spoofing Defense, Mock Detection & Velocity Analysis)
- **Status**: Completed & Verified.
- **Git Branch**: `phase-06` (preserving uncommitted working-tree changes; no git commit or tag created).
- **Alembic Revision**: `b4c5d6e7f8a9` (`database/migrations/versions/b4c5d6e7f8a9_phase_07_mock_location_evidence.py`).
- **Core Changes Implemented**:
  1. **Database Migration (`b4c5d6e7f8a9`)**: Added `is_mock_location: sa.Boolean()` column to `attendance_events`. Offline SQL upgrade and downgrade validated.
  2. **Model & Schema Extensions**: Added `is_mock_location` to `AttendanceEvent` and `AttendanceEventResponse`. Added `is_mock_location` and `location_captured_at` to `PunchRequest`.
  3. **Fraud Domain Package (`services/api/fraud/`)**:
     - `services/api/fraud/schemas.py`: Pydantic models and enums for signals (`FraudSignalType`, `FraudSignalSeverity`, `FraudEvidenceAssessment`, `VelocityResult`, `ClockDriftResult`, `GpsEvidenceResult`).
     - `services/api/fraud/service.py`: Haversine great-circle distance algorithm, sequential velocity analysis ($v = \Delta d / \Delta t$), device clock drift check with offline transport latency tolerance, GPS accuracy (>100m) and freshness (>30s) checks, and previous punch lookup strictly scoped by `tenant_id` and `employee_id`.
  4. **Attendance Engine Integration**: Extended `record_punch` in `services/api/attendance/service.py` to evaluate all fraud signals, automatically set `review_status = "PENDING_REVIEW"` on HIGH/CRITICAL signals, and store rich forensic telemetry (`fraud_signals`, `velocity_analysis`, `device_validation_status`) in `metadata_json`.
  5. **Automated Verification**: Authored 25 unit and API integration tests in `tests/test_phase7_gps_spoofing_and_velocity.py`. Ran full backend regression suite (380 tests passing, 100%), verified Ruff clean (0 errors), and Mypy clean (0 errors across fraud and attendance packages).
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_02_REPORT.md`

### 2026-11-19: Phase 7 — Milestone 7.3 Complete & Verified (Fraud Rule Engine & Deterministic Risk Scoring)
- **Status**: Completed & Verified.
- **Git Branch**: `phase-06` (preserving uncommitted working-tree changes; no git commit or tag created).
- **Alembic Revision**: `c5d6e7f8a9b0` (`database/migrations/versions/c5d6e7f8a9b0_phase_07_fraud_rules_and_flags.py`).
- **Core Changes Implemented**:
  1. **Database Migration (`c5d6e7f8a9b0`)**:
     - Created `fraud_rules` table with composite unique constraints `(tenant_id, rule_code)` and `(tenant_id, id)`, audit tracking, and enforced RLS.
     - Created `fraud_flags` table with composite unique constraint `(tenant_id, attendance_event_id, signal_code)` for idempotent replay safety, composite foreign keys, and enforced RLS.
     - Offline SQL upgrade and downgrade validated.
  2. **SQLAlchemy & Pydantic Models**:
     - `services/api/fraud/models.py`: `FraudRule` and `FraudFlag`.
     - `services/api/fraud/schemas.py`: `RiskCategory` (`NORMAL`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `REQUIRES_REVIEW`), `FraudRuleCreateRequest`, `FraudRuleUpdateRequest`, `FraudRuleResponse`, `FraudFlagResponse`, `RiskScoreResult`.
  3. **Deterministic Fraud Rule Engine (`services/api/fraud/engine.py`)**:
     - Provisioned 8 default rules with standard weights and severities.
     - Implemented deterministic signal deduplication, rule matching, disabled rule exclusion, bounded scoring ($0 \dots 100$), and review requirement derivation.
  4. **Strict Device Security & Attendance Integration**:
     - Punches attempted from a `REVOKED` device are aborted with `HTTP 403 Forbidden`, while historical records remain intact.
     - Punches from unregistered devices are recorded and flagged (`UNREGISTERED_DEVICE`, $+30$ risk score).
     - Integrated risk scoring and idempotent flag persistence into `record_punch`.
  5. **Tenant Rule Management & Flag APIs (`services/api/fraud/routes.py`)**:
     - CRUD endpoints for rules under `/api/v1/fraud/rules` (`GET`, `POST`, `PATCH`, `/enable`, `/disable`) protected by `MANAGE_FRAUD_RULES` and `VIEW_FRAUD_RULES`.
     - Flag retrieval under `/api/v1/fraud/flags` with filtering by employee, event, severity, and date range protected by `VIEW_FRAUD_FLAGS`.
  6. **Automated Verification**: Authored 25 unit and API integration tests in `tests/test_phase7_fraud_rules_and_risk_scoring.py` (82 total Phase 7 tests). Full backend test suite passing 100% (405 tests passing, 0 failed), verified Ruff clean (0 errors), and Mypy clean.
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_03_REPORT.md`

### 2026-11-19: Phase 7 — Milestone 7.4 Complete & Verified (HR Fraud Review Queue, Decision Workflows & Audit Ledger)
- **Status**: Completed & Verified.
- **Git Branch**: `phase-06` (preserving uncommitted working-tree changes; no git commit or tag created).
- **Alembic Revision**: `d6e7f8a9b0c1` (`database/migrations/versions/d6e7f8a9b0c1_phase_07_fraud_reviews.py`).
- **Core Changes Implemented**:
  1. **Database Migration (`d6e7f8a9b0c1`)**:
     - Created `fraud_reviews` table with composite foreign keys to `tenants`, `attendance_events`, and `users`, check constraints for decision (`APPROVED`, `REJECTED`) and mandatory reason ($>=3$ characters), and enforced Row-Level Security (`tenant_isolation`).
     - Validated via offline SQL upgrade and downgrade tests.
  2. **RBAC & Organizational Hierarchy Permissions**:
     - Added `REVIEW_FRAUD_EVENTS` and `VIEW_FRAUD_REVIEWS` permissions in `services/api/auth/permissions.py`.
     - Owner, Admin, and HR granted organization-wide review and adjudication access.
     - Manager granted `VIEW_FRAUD_REVIEWS` restricted to direct reports and same-department employees.
     - Strict self-review prohibition: users cannot adjudicate their own attendance fraud reviews (`HTTP 403 Forbidden`).
  3. **Review Detail API (`GET /api/v1/fraud/events/{id}/review`)**:
     - Assembles forensic dossier: employee profile, event timestamps, shift assignment, location coordinates and geofence status, device binding telemetry, mock indicators, clock drift, rule signals, and decision audit history.
     - Enforces manager reporting-line visibility checks.
  4. **Atomic Adjudication & Recalculation (`POST /api/v1/fraud/events/{id}/decision`)**:
     - Row-locks target `AttendanceEvent` with `with_for_update()`.
     - Records immutable `FraudReview` audit entry and updates `AttendanceEvent.review_status`.
     - Deterministically triggers `recalculate_attendance_day`: `APPROVED` reconciles the punch into normal shift calculation; `REJECTED` excludes the punch from timeline intervals.
  5. **Review Queue Filtering (`GET /api/v1/fraud/flags`)**:
     - Added filters for `review_status`, `risk_category`, `min_risk_score`, `max_risk_score`, and `department_id`.
  6. **Automated Verification**: Authored 20 unit and API tests in `tests/test_phase7_fraud_review_workflow.py` (102 total Phase 7 tests). Full backend regression passing 100% (425 tests passing, 0 failed), Ruff clean (0 errors), and Mypy clean.
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_04_REPORT.md`

### 2026-11-19: Phase 7 — Milestone 7.5 Complete & Verified (Flutter Mobile Device Binding & Fraud Telemetry)
- **Status**: Completed & Verified.
- **Git Branch**: `phase-06` (preserving uncommitted working-tree changes; no git commit or tag created).
- **Mobile Stack**: Flutter 3.47.9 / Dart 3.13.7.
- **Core Changes Implemented**:
  1. **Secure Installation Identifier (`FlutterDeviceIdentityService`)**:
     - Cryptographically random UUID v4 generated on first install and persisted in hardware-backed `FlutterSecureStorage` (`encryptedSharedPreferences: true` on Android, `KeychainAccessibility.first_unlock_this_device` on iOS).
     - Distinct from backend HMAC hash; never logged or exposed; survives app updates and logout; regenerates if corrupted.
     - Safe platform metadata resolution using `device_info_plus` and `package_info_plus` with graceful fallbacks.
  2. **Device Feature Architecture (`apps/mobile/lib/features/devices/`)**:
     - Domain entities (`DeviceInfo`, `DeviceBindingStatus`, `DeviceStatusResult`), repository contract (`DeviceRepository`), data models (`DeviceModel`, `DeviceRegisterRequestModel`, `DeviceRegisterResponseModel`, `DeviceStatusResponseModel`), and remote data source (`DeviceRemoteDataSourceImpl` integrating `GET /api/v1/devices/me` and `POST /api/v1/devices/register`).
     - BLoC state management (`DeviceBloc`) handling all 5 lifecycle states (`ACTIVE`, `PENDING_APPROVAL`, `REVOKED`, `REPLACED`, `UNREGISTERED`).
  3. **Fraud Telemetry Integration in Attendance & Offline Queue**:
     - Extended `PunchRequestModel` with `deviceId`, `isMockLocation`, and `locationCapturedAt`.
     - `AttendanceBloc` acquires installation ID from `DeviceIdentityService`, reads mock location state and GPS timestamp from `LocationReading`, and forwards telemetry to `recordPunch` and `_persistOfflinePunch`.
     - Offline `LocalQueueItem` persists `deviceId` and embeds `is_mock_location` and `location_captured_at` into `metadataJson`.
     - `SyncWorkerImpl._buildPunchRequest` extracts and forwards fraud telemetry from queued items during FIFO background sync.
     - Rejection handling: backend HTTP 403 device revoked responses display a friendly, actionable notice ("Device access revoked. Please contact HR to authorize this device.") and flag state as non-retriable.
  4. **Device Status Card in Employee Profile**:
     - Created `DeviceStatusCard` displaying device status badge, hardware model, OS version, app version, binding date, status explanation, and registration/refresh actions.
     - Integrated into `ProfileScreen` with fail-safe bloc resolution preserving all existing profile widget tests.
  5. **Automated Verification**:
     - 32 new unit, BLoC, and widget tests across services, repository, BLoC, widgets, and attendance telemetry.
     - All 316 Flutter tests passing (100% pass rate).
     - Clean `flutter analyze` (0 issues), clean `dart format`.
     - Verified Android debug build: `flutter build apk --debug` succeeded (`build/app/outputs/flutter-apk/app-debug.apk`).
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_05_REPORT.md`

### 11.6 Phase 7.6 Summary: Offline Sync Compatibility & End-to-End Simulation
- **Delivered**:
  1. **Comprehensive Mobile Simulation Suite (`apps/mobile/test/features/sync/simulation/phase7_fraud_telemetry_and_device_sync_simulation_test.dart`)**:
     - *Scenario A*: Normal offline shift journey (CHECK_IN, BREAK_START, BREAK_END, CHECK_OUT) maintaining strict FIFO, verifying device ID, mock GPS flag, GPS capture timestamp, and successful local sync transitions.
     - *Scenario B*: App process termination and cold reboot; queue persistence verification across crashes without token leaks.
     - *Scenario C*: Response drop at network boundary; idempotency replay handling without duplicate records.
     - *Scenario D*: Device revocation while offline events pending; backend HTTP 403 classification, permanent rejection marking, and cascade quarantine to dependent session events.
     - *Scenario E*: Fraud telemetry mock GPS propagation (`is_mock_location: true`) and server `PENDING_REVIEW` mapping to `flaggedPendingReview`.
     - *Scenario F & H*: Server HTTP status code handling and exponential backoff progression (2s, 4s, 8s, 16s, 32s, 60s cap; 429 Retry-After header adherence; 422 permanent failure).
     - *Scenario G*: Session dependency quarantine vs independent session continuation.
  2. **Authoritative Backend Simulation Suite (`tests/test_phase7_offline_sync_simulation.py`)**:
     - *Scenario A*: Normal offline attendance processing with `device_id` recording, `AttendanceEvent` commit, and day projection calculation.
     - *Scenarios B & C*: Network loss and idempotency replay (identical fingerprint returns cached response with `idempotent_replay: True`, no duplicate event or fraud flag records; payload tampering rejected with HTTP 422).
     - *Scenario D*: Device revocation check (`device_validation_status == 'REVOKED'` immediately raises HTTP 403 Forbidden).
     - *Scenario E*: Mock location flag and clock drift trigger deterministic risk scoring, fraud flag persistence, and `PENDING_REVIEW` review status.
     - *Scenario F*: Multi-tier timestamp validation limits.
     - *Scenario G*: Dependent session events and auto-break closure on checkout.
     - *Unregistered Device*: Punch recorded into immutable ledger with `UNREGISTERED_DEVICE` flag and `PENDING_REVIEW`.
     - *API Integration*: Tested `POST /api/v1/attendance/punch` ASGI route for offline telemetry and revoked device 403 behavior.
  3. **Corrective Validation — Timestamp Policy & Offline Fraud Evaluation**:
     - Enforced approved timestamp policy replacing 7-day stale and 24-hour future absolute rules:
       - Future skew > 300s: HTTP 422 rejection.
       - Future skew 61–300s: Supervisor review (`PENDING_REVIEW`, `FLAG_FUTURE_TIMESTAMP_DETECTED`).
       - Past drift > configured maximum (8–72h, default 72h): HTTP 422 rejection (`"Device reported timestamp is older than allowable limit"`).
       - Past drift 24h to maximum: Supervisor review (`PENDING_REVIEW`, `FLAG_OFFLINE_WINDOW_EXCEEDED`).
       - Standard offline past $\le 24$h: Accepted without review (`UNVERIFIED_OFFLINE`, `NOT_REQUIRED`, `FLAG_DELAYED_OFFLINE_SYNC`).
       - Unqueued online drift > 300s: Supervisor review (`PENDING_REVIEW`, `FLAG_CLOCK_MANIPULATION_SUSPECTED`).
     - Added 15-test granular boundary regression suite (`TestTimestampPolicyAndOfflineFraudCorrectiveSuite` in `tests/test_phase7_offline_sync_simulation.py`).
     - Hardened policy engine against async mock dispatchers (`and not callable(side_effect)`).
     - Ensured mock location indicators are evaluated and flagged even without GPS coordinates.
  4. **Automated Verification**:
     - 9 new Flutter simulation tests (325 total Flutter tests passing 100%).
     - 24 Backend simulation & corrective tests (449 total Backend tests passing 100%, 126 Phase 7 specific).
     - Total automated tests: 774 tests passing (100% pass rate).
     - `flutter analyze` 100% clean (0 issues).
     - `dart format` 100% clean across all 186 mobile files.
     - Verified Android debug build: `flutter build apk --debug` succeeded (`build/app/outputs/flutter-apk/app-debug.apk`).
- **Report**: `docs/phase-reports/PHASE_07_MILESTONE_06_REPORT.md`

### 11.7 Phase 7.7 Summary: Security Audit, Penetration Testing & Phase 7 Completion
- **Delivered**:
  1. **Comprehensive Security Audit & Threat Modeling**:
     - Audited all components built across Milestones 7.1–7.6: device binding, GPS spoofing, velocity analysis, fraud rule engine, HR review workflows, Flutter telemetry, and offline sync.
     - Modeled mobile sensor/client, transport, and backend/RLS attack surfaces.
  2. **Vulnerability Remediation & Defensive Hardening**:
     - *FINDING-7.7-01 (HIGH)*: Fixed device replacement workflow in `services/api/devices/service.py` to evaluate revocation and cross-employee active conflicts prior to creating `PENDING_APPROVAL` records, blocking unauthorized replacement attempts.
     - *FINDING-7.7-02 (MEDIUM)*: Hardened `revoke_device` in `services/api/devices/service.py` against whitespace-only justification bypass (`if len(reason.strip()) < 3: raise 422`).
     - *FINDING-7.7-03 (LOW / HARDENING)*: Hardened `approve_device_replacement` against activating hardware identifiers revoked subsequent to submission.
  3. **Penetration & Security Regression Suite (`tests/test_phase7_security_audit.py`)**:
     - 19 new security audit tests covering device binding attacks, boundary score capping at 100, disabled rule exclusion, manager reporting-line visibility scoping, self-review prohibition, cross-tenant isolation, mock GPS detection, and impossible-travel velocity analysis.
  4. **Automated Verification & Packaging**:
     - Full backend regression: **468 tests passed in 115.78s (100% pass rate, 0 failed, 145 Phase 7 specific)**.
     - Static analysis (Ruff): Clean (`All checks passed!`).
     - Full Flutter test suite: **325 tests passed in 20s (100% pass rate, 0 failed)**.
     - Flutter static analysis: Clean (`No issues found!`).
     - Code formatting: Clean (`186 files formatted, 0 changed`).
     - Android builds: Both debug (`build/app/outputs/flutter-apk/app-debug.apk`) and release (`build/app/outputs/flutter-apk/app-release.apk`) verified.
     - Total automated coverage: **793 tests passing (100% pass rate)**.
  5. **Formal Phase 7 Completion Documentation**:
     - Detailed security audit report: `docs/phase-reports/PHASE_07_MILESTONE_07_SECURITY_AUDIT.md`.
     - Master Phase 7 completion report: `docs/phase-reports/PHASE_07_FINAL_COMPLETION_REPORT.md`.

### 11.8 Phase 8 Summary: Offline Attendance Conflict Resolution & Supervisor Approvals
- **Delivered**:
  1. **Milestone 8.1 — Database Architecture, Data Models & Alembic Migration**:
     - Created `attendance_conflict_incidents` table with composite foreign keys, RLS policies, unique constraints (`tenant_id`, `bundle_id`), and check constraints.
     - Alembic revision `e7f8a9b0c1d2_phase_08_attendance_conflicts.py` verified.
  2. **Milestone 8.2 — Backend Conflict Submission Engine & Employee APIs**:
     - Implemented `POST /api/v1/attendance/offline-conflicts/submit` and `GET /api/v1/attendance/offline-conflicts/my`.
     - Deterministic canonical SHA-256 bundle fingerprinting, chronological validation, and idempotent replay handling.
  3. **Milestone 8.3 — Supervisor Adjudication Workflow & Atomic Correction Integration**:
     - Implemented `GET /api/v1/attendance/offline-conflicts`, `GET /api/v1/attendance/offline-conflicts/{id}`, and `POST /api/v1/attendance/offline-conflicts/{id}/decision`.
     - Row-level locking (`SELECT ... FOR UPDATE`), atomic reuse of Phase 5 `apply_attendance_correction(CORRECTION_INSERT)` for all bundle events, session projection recalculation, manager direct-report hierarchy scoping, and anti-self-approval rule.
  4. **Milestone 8.4 — Flutter Mobile Conflict Bundling & Submission**:
     - Built `OfflineSequenceConflictBundle` extraction from `LocalQueueDao`.
     - Encrypted SQLCipher metadata tracking (`conflict_bundle_id`, `conflict_status`, `supervisor_decision`).
     - Created `ConflictSubmissionRequested` and `ConflictRefreshRequested` in `SyncBloc`.
     - Integrated `ConflictSessionCard` in `SyncStatusScreen`.
  5. **Milestone 8.5 — Next.js Web Supervisor Console & Adjudication Views**:
     - Created supervisor route `/attendance/corrections/conflicts` and `ConflictIncidentDetailModal`.
     - Filter tabs, KPI summary cards, forensic evidence telemetry inspection, mandatory reason validation ($\ge 3$ characters), and location override dropdown.
  6. **Milestone 8.6 — End-to-End Integration, Chaos & Synchronization Simulation**:
     - Full lifecycle success scenario: Mobile offline punches $\to$ 422 geofence rejection $\to$ cascading quarantine $\to$ bundle extraction $\to$ submission $\to$ supervisor review in web console $\to$ approval with location override $\to$ atomic ledger insertion $\to$ projections recalculation $\to$ mobile status update to `synced`.
     - Rejection scenario: Supervisor rejects incident $\to$ status `REJECTED` $\to$ zero ledger rows added $\to$ projections unchanged $\to$ forensic evidence preserved.
     - Chaos and edge cases: Network loss after commit (idempotent replay), payload tampering on reused bundle ID (409 Conflict), concurrent supervisor adjudication collision (409 Conflict with row locking), atomic transaction rollback on partial failure, overnight shifts spanning calendar dates, cross-tenant isolation (404 Not Found), manager direct-report scoping (403 Forbidden), and anti-self-approval rule (403 Forbidden).
     - Automated verification: 10 backend chaos tests, 4 mobile simulation tests, 7 web simulation tests; 952 total monorepo automated tests passing (100% pass rate).
  7. **Milestone 8.7 — Security Audit, Penetration Testing & Phase 8 Completion**:
     - Audited cross-tenant IDOR, employee self-ownership, manager direct-report scoping, anti-self-approval enforcement, canonical SHA-256 bundle fingerprinting, and atomic transaction rollback boundaries.
     - Reconciled original 22-phase roadmap ("Corrections and Reports") with completed offline conflict resolution and daily projection recalculation engines; documented deferred async export jobs (`export_jobs`) to Phase 12.
     - Verified Flutter local encryption configuration (`sqflite_sqlcipher`), offline queue capacity limits (500 events), and successful Android debug APK assembly (`assembleDebug`).
     - Verified Next.js supervisor console role-based access, client-side reason validation, and workplace location override contract compatibility with backend API.
     - Fresh automated regression verification: **952 tests passing (100% pass rate: 534 Backend, 348 Flutter, 70 Web)**; Ruff clean; Mypy clean; `flutter analyze` 100% clean; `dart format` 100% clean across 195 files; Next.js 14 production build compiled cleanly.
- **Reports**:
  - `docs/phase-reports/PHASE_08_MILESTONE_06_REPORT.md`
  - `docs/phase-reports/PHASE_08_MILESTONE_07_REPORT.md`

### 11.9 Phase 9 Scope Assessment: Leave, Holidays and Overtime Multipliers
- **Assessment Document**: [`docs/PHASE_09_SCOPE_ASSESSMENT.md`](file:///Users/apple/Upostit/docs/PHASE_09_SCOPE_ASSESSMENT.md)
- **Authoritative Scope Established**:
  - Entities: `leave_types`, `leave_balances`, `leave_requests`, `holiday_calendars`, `holidays`, `overtime_rules`, `overtime_records`.
  - Core Workflow: Leave type configuration, employee balance hold/deduction, manager direct-report approval hierarchy with anti-self-approval, hierarchical holiday calendar resolution (Location $\to$ Tenant Default), overtime multipliers (1.5x workday, 2.0x weekend/holiday), and attendance projection engine integration (`ON_LEAVE`, `HOLIDAY`, `WEEK_OFF`, `PRESENT`).
  - Strict Boundaries: Immutable ledger preserved (no fake punch events). Outbound notifications deferred to Phase 10; payroll financial disbursements deferred to Phase 14.
- **Status**: Assessment completed.

### 11.10 Phase 9 Milestone 9.1 Summary: Database Architecture, Models & Alembic Migration
- **Delivered**:
  1. **SQLAlchemy 2.0 Models (`services/api/leave/models.py`)**:
     - All 7 Phase 9 entities created: `LeaveType`, `LeaveBalance`, `LeaveRequest`, `HolidayCalendar`, `Holiday`, `OvertimeRule`, `OvertimeRecord`.
     - Strict composite foreign keys referencing `(tenant_id, id)` across parent-child relationships.
     - Database check constraints, unique constraints, and zero-warning SQLAlchemy relationship overlaps annotations.
  2. **Alembic Migration (`f2a3b4c5d6e7_phase_09_leave_holidays_overtime.py`)**:
     - Chained cleanly from Phase 8 head `e7f8a9b0c1d2`.
     - Full DDL for all 7 tables with composite foreign keys, unique indexes, and check constraints.
     - PostgreSQL Row-Level Security (RLS) enabled and forced on all tables with tenant isolation policies.
     - Clean, reverse-order downgrade DDL.
  3. **Metadata & Migration Registration (`database/migrations/env.py`)**:
     - Registered all 7 models in `Base.metadata`. Verified single Alembic head `f2a3b4c5d6e7`.
  4. **Contract & Regression Testing**:
     - 24 unit and contract tests in `tests/test_phase9_database_models_and_migration.py` passed 100%.
     - Full monorepo regression suite: **976 tests passing (100% pass rate: 558 Backend, 348 Flutter, 70 Web)**.
     - Ruff clean, Mypy clean, Dart format clean, Flutter analyze clean.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_01_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_01_REPORT.md)

### 11.11 Phase 9 Milestone 9.2 Summary: Holiday Calendars & Leave Type Configuration
- **Delivered**:
  1. **Leave Type Management (`services/api/leave/leave_type_service.py`)**:
     - Tenant-scoped CRUD for leave categories (`CL`, `SL`, `AL`, `LOP`).
     - Case-insensitive unique code enforcement (`(tenant_id, UPPER(code))`).
     - Reference integrity guard: blocks deletion (`409 Conflict`) if leave type is referenced by employee balances or requests.
  2. **Holiday Calendars & Entries (`services/api/leave/holiday_service.py`)**:
     - Annual schedules with location and department override scoping.
     - Annual default calendar uniqueness enforcement with automatic demotion of prior defaults.
     - Holiday entries CRUD with duplicate-date prevention per calendar (`409 Conflict`) and date-range querying.
  3. **Dedicated Hierarchical Calendar Resolution Engine**:
     - Strict 3-tier precedence: **Workplace Location** (Tier 1) $\to$ **Department** (Tier 2) $\to$ **Tenant Default** (Tier 3).
     - Inactive location bypass and fallback handling.
  4. **Employee Upcoming Holiday Inquiry (`GET /api/v1/holidays/upcoming`)**:
     - Authenticated employee self-scoping derived from server-side JWT context.
     - Anti-peer sniffing protection (`403 Forbidden` if an employee queries another employee's schedule).
     - Manager/HR multi-employee inquiry support.
  5. **RBAC & Permissions Registry Update (`services/api/auth/permissions.py`)**:
     - Added `MANAGE_POLICIES`, `VIEW_POLICIES`, `MANAGE_LEAVE_TYPES`, `VIEW_LEAVE_TYPES`, `MANAGE_HOLIDAYS`, `VIEW_HOLIDAYS`.
  6. **Comprehensive Automated Verification**:
     - 26 tests in `tests/test_phase9_milestone2_leave_and_holidays.py` passed 100%.
     - Full monorepo regression suite: **1,002 tests passing (100% pass rate: 584 Backend, 348 Flutter, 70 Web)**.
     - Ruff clean, Mypy clean across all services and tests.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_02_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_02_REPORT.md)

### 11.12 Phase 9 Milestone 9.3 Summary: Leave Application, Balance Tracking & Supervisor Adjudication
- **Delivered**:
  1. **Employee Leave APIs (`services/api/leave/routes.py`, `services/api/leave/leave_request_service.py`)**:
     - Authenticated employee balance inquiry (`GET /api/v1/leave/balances/my`) with dynamic `available_balance` calculation.
     - Leave submission (`POST /api/v1/leave/requests`) supporting full-day, multi-day, and half-day (`FIRST_HALF`, `SECOND_HALF`) requests.
     - Personal request history (`GET /api/v1/leave/requests/my`) and request detail (`GET /api/v1/leave/requests/{id}`).
     - Leave cancellation (`POST /api/v1/leave/requests/{id}/cancel`): releases pending hold or safely reverses future approved leave (`start_date > today`).
  2. **Balance Reservation & Available Balance Invariant Engine**:
     - Row-level locking (`SELECT ... FOR UPDATE`) on `LeaveBalance` during application, adjudication, and cancellation.
     - Enforces invariant: $\text{Available Balance} = \text{allocation} + \text{carried\_forward} + \text{accrued} - \text{used} - \text{pending\_approval} \ge \text{requested\_days}$.
     - Atomic increment of `pending_approval += requested_days` on application.
  3. **Working Days & Calendar Exclusions Calculation**:
     - Integrates with Milestone 9.2 hierarchical calendar resolver to exclude non-working public holidays.
     - Integrates with employee shift version resolver to exclude weekly-off days.
     - Validates half-day constraints (single working day, 0.50 deductible days).
  4. **Supervisor Review Queue & Adjudication (`services/api/leave/routes.py`)**:
     - Supervisor review queue (`GET /api/v1/leave/requests`): scoped to direct reports for managers (`reporting_manager_id == reviewer.id`); tenant-wide for HR/Admin; blocked for employees (`403 Forbidden`).
     - Adjudication endpoint (`POST /api/v1/leave/requests/{id}/decision`): atomic transition to `APPROVED` or `REJECTED`.
     - Strict anti-self-approval enforcement (`403 Forbidden` if reviewer attempts to adjudicate their own request).
     - Mandatory rejection reason enforcement ($\ge 3$ non-whitespace chars, `422 Unprocessable Content`).
  5. **Atomic Balance Transitions & Attendance Recalculation Integration**:
     - Approval commits balance (`pending_approval -= days`, `used += days`) and invokes `recalculate_attendance_day()` for each affected date in the leave window.
     - Rejection releases hold (`pending_approval -= days`).
     - Cancellation of future approved leave reverses used balance (`used -= days`) and recalculates daily attendance.
     - Transactional rollback: any failure during attendance recalculation rolls back all balance and status changes.
     - Immutable ledger guarantee: zero synthetic punches inserted or mutated in `attendance_events`.
  6. **RBAC & Permissions Registry Update (`services/api/auth/permissions.py`)**:
     - Added `APPLY_LEAVE`, `VIEW_LEAVE_REQUESTS`, and `APPROVE_LEAVE`.
  7. **Comprehensive Automated Verification**:
     - 20 tests in `tests/test_phase9_milestone3_leave_workflow.py` passed 100%.
     - Full monorepo regression suite: **1,022 tests passing (100% pass rate: 604 Backend, 348 Flutter, 70 Web)**.
     - Ruff clean, Mypy clean on all leave services and test suites.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_03_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_03_REPORT.md)

### 11.13 Phase 9 Milestone 9.4 Summary: Overtime Rules Engine & Attendance Calculation Integration
- **Delivered**:
  1. **Alembic Migration (`database/migrations/versions/a4b5c6d7e8f9_phase_09_overtime_enhancements.py`)**:
     - Single clean head upgrade from `f2a3b4c5d6e7`.
     - Added `is_default` and `requires_pre_approval` columns with composite index `ix_overtime_rules_tenant_default` to `overtime_rules`.
     - Added `overtime_rule_id` foreign key column, composite foreign key to `overtime_rules`, and index `ix_overtime_records_rule` to `overtime_records`.
     - Reversible upgrade and downgrade paths tested.
  2. **Pure Functional Attendance Engine Updates (`services/api/attendance/engine.py`)**:
     - Extended `calculate_attendance_day()` without DB dependencies.
     - Implemented `OvertimeCalculationDetails` dataclass returning raw overtime, eligible overtime, capped overtime, multiplier, payable overtime minutes, category (`WORKDAY`, `WEEK_OFF`, `HOLIDAY`), status (`AUTO_APPROVED`, `PENDING_APPROVAL`), and rule ID.
     - Deterministic category precedence: Statutory Holiday takes absolute precedence over Weekly Off (no double counting).
     - Enforces `daily_overtime_threshold_minutes` eligibility gate and `max_daily_overtime_minutes` daily ceiling.
     - Separates raw vs approved vs payable overtime minutes without premature currency conversion.
     - Absence safety: Incomplete attendance sessions and full-day approved leaves yield zero overtime.
  3. **Overtime Rule Management Services & APIs (`services/api/leave/overtime_service.py`, `services/api/leave/routes.py`)**:
     - Tenant-scoped rule CRUD: `POST /api/v1/overtime/rules`, `GET /api/v1/overtime/rules`, `GET /api/v1/overtime/rules/{id}`, `PUT /api/v1/overtime/rules/{id}`, `DELETE /api/v1/overtime/rules/{id}`.
     - Enforces single default rule per tenant with automatic demotion of existing default rule.
     - Multiplier range constraints ($1.00 \le \text{multiplier} \le 5.00$) and daily cap constraints ($0 \le \text{threshold} \le \text{cap} \le 1440$).
     - Referential integrity: deletion blocked with `409 Conflict` if rule is referenced by existing `OvertimeRecord` rows.
  4. **Supervisor Overtime Review Queue & Adjudication (`services/api/leave/routes.py`)**:
     - Supervisor review queue (`GET /api/v1/overtime/records`): direct-report filtering for managers; tenant-wide for HR/Admin; blocked for employees (`403 Forbidden`).
     - Employee self-service view (`GET /api/v1/overtime/records/my`).
     - Adjudication endpoint (`POST /api/v1/overtime/records/{id}/decision`) with row-level locking (`with_for_update()`).
     - Anti-self-approval enforcement (`403 Forbidden` if reviewer attempts to adjudicate own overtime).
     - Mandatory rejection reason enforcement ($\ge 3$ non-whitespace characters, `422 Unprocessable Content`).
     - Ledger updates: Approval updates `approved_overtime_minutes` and `AttendanceDay.overtime_minutes`; rejection sets `approved_overtime_minutes = 0` and `AttendanceDay.overtime_minutes = 0`.
  5. **Attendance Recalculation Integration (`services/api/attendance/service.py`)**:
     - Queries applicable holiday calendar, leave requests, and overtime rules during `recalculate_attendance_day()`.
     - Idempotent upsert of `OvertimeRecord` linked to `AttendanceDay`.
     - Decision preservation: Existing `APPROVED` supervisor decisions survive attendance recalculation (capped to raw overtime if raw was reduced); existing `REJECTED` decisions remain rejected.
     - Immutable event ledger guarantee: zero synthetic punches inserted or mutated in `attendance_events`.
  6. **RBAC & Permissions Registry Update (`services/api/auth/permissions.py`)**:
     - Added `MANAGE_OVERTIME_RULES`, `VIEW_OVERTIME_RULES`, `APPROVE_OVERTIME`, and `VIEW_OVERTIME_RECORDS`.
  7. **Comprehensive Automated Verification**:
     - 25 tests in `tests/test_phase9_milestone4_overtime_engine.py` passed 100%.
     - Full monorepo regression suite: **1,047 tests passing (100% pass rate: 629 Backend, 348 Flutter, 70 Web)**.
     - Ruff clean, Mypy clean on all leave services, attendance engine, and test suites.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_04_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_04_REPORT.md)

### 11.14 Phase 9 Milestone 9.5 Summary: Next.js Web Console — Leave & Overtime Administration
- **Delivered**:
  1. **Next.js Web Routes & Interfaces**:
     - `/leave`: Employee leave dashboard with real-time balance cards, holiday clashing awareness, application modal (full/half-day), request history, and cancellation.
     - `/leave/approvals`: Manager/HR review queue with anti-self-approval protection, mandatory rejection reason ($\ge 3$ non-whitespace chars), and balance context.
     - `/organization/leave-types`: HR leave policy configuration (quota, paid/unpaid, carry forward, approval requirements, active toggle, 409 conflict safety).
     - `/organization/holidays`: Annual holiday calendar administration with Location, Department, or Tenant Default scoping and inline holiday entries.
     - `/attendance/overtime`: Overtime records dashboard, supervisor adjudication dialog (approve with adjusted minutes / reject), and overtime rules configuration tab.
  2. **API Client & TypeScript DTOs (`apps/web/src/lib/api.ts`)**:
     - Added comprehensive typed DTOs and API clients (`leaveApi`, `holidayApi`, `overtimeApi`).
  3. **Role-Based Cross-Navigation Updates**:
     - Updated header navigation bars across `apps/web/src/app/page.tsx`, `/attendance`, and `/organization`.
  4. **Comprehensive Automated Verification**:
     - 26 tests in `apps/web/src/lib/leave-and-overtime-api.test.ts` passed 100%.
     - Full Next.js web test suite: **96 tests passing (100%)** across 29 test suites.
     - Next.js production build: **14/14 static pages generated successfully**.
     - Next.js linting: **0 warnings, 0 errors**.
     - Full monorepo regression suite: **1,073 tests passing (629 Backend, 348 Flutter, 96 Web)**.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_05_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_05_REPORT.md)

### 11.15 Phase 9 Milestone 9.6 Summary: Flutter Mobile — Leave Application, Balances & Holiday Hub
- **Delivered**:
  1. **Core Network & Domain Architecture (`apps/mobile/lib/features/leave/`)**:
     - Endpoints defined in `ApiEndpoints`: balances, types, personal requests, application, cancellation, supervisor queue, decision adjudication, and upcoming holidays.
     - Domain entities: `LeaveType`, `LeaveBalance`, `LeaveRequest` (with `canCancel(today)` business invariants), and `UpcomingHoliday`.
     - Data models: `LeaveTypeModel`, `LeaveBalanceModel`, `LeaveRequestModel`, and `UpcomingHolidayModel` with resilient JSON deserialization and list mapping.
     - Remote data source & repository: `LeaveRemoteDataSourceImpl` and `LeaveRepositoryImpl` returning functional `Result<T>` with `ServerFailure` and `NetworkFailure` mapping.
  2. **BLoC State Management (`apps/mobile/lib/features/leave/presentation/bloc/`)**:
     - `LeaveBloc`, `LeaveEvent`, and `LeaveState`:
     - Handlers for dashboard loading, leave application submission, cancellation, history queries, upcoming holidays, and supervisor decision adjudication.
     - Double-submission protection: `isSubmitting: true` disables buttons and guards against duplicate requests.
     - Transient notice management: `successNotice` and `errorMessage` with explicit `LeaveNoticesCleared`.
  3. **Presentation Widgets (`apps/mobile/lib/features/leave/presentation/widgets/`)**:
     - `BalanceCard`: Clean horizontal card displaying available days hero font, visual linear progress bar, and used/pending days breakdown.
     - `LeaveStatusBadge`: Semantic status pills for `Approved` (emerald), `Pending` (amber), `Rejected` (rose), and `Cancelled` (slate).
     - `HolidayTile`: Formatted calendar date block, holiday name, weekday, holiday type badge, and resolution source badge (`Location`, `Department`, `Tenant default`).
     - `LeaveRequestCard`: Request details, date range, half-day sessions (`First Half` / `Second Half`), supervisor feedback, and action-gated cancellation button.
  4. **Presentation Screens (`apps/mobile/lib/features/leave/presentation/screens/`)**:
     - `/leave`: Employee leave dashboard with balances carousel, recent requests feed, upcoming holidays card, pull-to-refresh, and quick action bar.
     - `/leave/apply`: Leave application form with type dropdown, conditional half-day toggle (`allowHalfDay == true`), morning/afternoon session chip selector, material date picker, mandatory reason input, live duration calculation, and submit loading state.
     - `/leave/history`: Status filter chips (`All`, `Pending`, `Approved`, `Rejected`, `Cancelled`), request cards, and cancellation confirmation dialog.
     - `/leave/holidays`: Three-tier resolved holiday calendar list with location/department contextual info banner.
     - `/leave/approvals`: Supervisor review queue for managers/HR with anti-self-approval protection (disables actions if `employeeId == currentUserId`), approval dialog with notes, and rejection dialog requiring mandatory reason ($\ge 3$ characters).
  5. **Routing & DI Integration**:
     - Registered 5 declarative routes in `appRouter` (`apps/mobile/lib/app.dart`).
     - Injected `LeaveRepository` and `LeaveBloc` at root level in `main.dart`.
     - Added "Leave" quick action card to `AttendanceHomeScreen`.
  6. **Comprehensive Automated Verification**:
     - 28 new tests authored in `apps/mobile/test/features/leave/`:
       - `leave_models_and_repository_test.dart`: 13 tests passed (JSON parsing, `canCancel` invariants, repository calls, error mapping).
       - `leave_bloc_test.dart`: 6 tests passed (dashboard, apply, cancel, double-submission guard, supervisor approval).
       - `leave_screens_and_widgets_test.dart`: 9 tests passed (widgets and screens, form validations, anti-self-approval).
     - Full mobile test suite: **376 tests passing (100% pass rate)**.
     - Static analysis: `flutter analyze` reports **0 errors, 0 warnings, 0 infos**.
     - Full monorepo regression suite: **1,101 tests passing (629 Backend, 376 Flutter, 96 Web)** with 0 failures across the codebase.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_06_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_06_REPORT.md)

### 11.16 Phase 9 Milestone 9.7 Summary: End-to-End Cross-Platform Simulation, Concurrency & Chaos Testing
- **Delivered**:
  1. **Backend Automated E2E & Chaos Suite (`tests/test_phase9_e2e_and_chaos_simulation.py`)**:
     - 12 automated simulation tests validating complete leave lifecycle, balance holds, attendance recalculation without event ledger modification, weekend/holiday exclusion from deductible days, insufficient balance 400 rejection, max consecutive days enforcement, commenced/past leave cancellation rejection 400, statutory overtime multipliers (1.5x workday, 2.0x weekend, 2.0x holiday) with daily caps, supervisor adjusted minutes approval, anti-self-approval 403 enforcement, competing balance race conditions with row locking, duplicate supervisor decision 409 conflict, attendance recalculation failure atomic transaction rollback, and cross-tenant 404 isolation.
  2. **Web Console Cross-Platform Simulation (`apps/web/src/lib/leave-and-overtime-simulation.test.ts`)**:
     - 8 automated tests simulating full leave lifecycle, anti-self-approval rejection for leave and overtime, duplicate approval 409 conflict, competing request balance rejection, network timeout retry idempotency, overtime multiplier verification, and supervisor adjusted minutes adjudication.
  3. **Anti-Self-Approval Identity Mapping Defect Resolution**:
     - Resolved UUID mismatch across Flutter mobile and Next.js web where `Employee.id` was compared directly to `User.id`, causing false negatives in client-side anti-self-approval guards. Updated mobile `leave_approvals_screen.dart` and web `apps/web/src/app/leave/approvals/page.tsx` and `apps/web/src/app/attendance/overtime/page.tsx` to match against both employee ID and user ID.
  4. **PostgreSQL Environment Documentation**:
     - Explicitly documented that live PostgreSQL RLS policy execution was not available on this host environment (`pg_isready`/`docker` unavailable), without substituting or falsely claiming RLS checks passed.
  5. **Comprehensive Monorepo Verification**:
     - Full monorepo regression suite: **1,121 tests passing (641 Backend, 376 Flutter, 104 Web)** with 0 failures across the entire codebase.
     - Next.js build: 14/14 static pages compiled successfully with 0 linting warnings or errors.
     - Flutter static analysis: `flutter analyze` reports 0 issues.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_07_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_07_REPORT.md)

### 11.17 Phase 9 Milestone 9.8 Summary: Security Audit, Vulnerability Assessment & Phase 9 Closure
- **Delivered**:
  1. **Comprehensive Security Audit & Penetration Suite (`tests/test_phase9_security_audit.py`)**:
     - 14 automated security regression tests validating multi-tenant boundary enforcement, cross-tenant injection prevention, employee self-only scoping, manager direct-report scoping, anti-self-approval identity mapping, balance invariant formula consistency, inactive policy application blocks, overtime multiplier deflation prevention (Pydantic & service level), pre-approval non-auto-approval invariant, and append-only event ledger protection (0 synthetic punches inserted).
  2. **Vulnerability Remediation**:
     - SEC-09-01: Corrected client-side anti-self-approval checks in Flutter mobile and Next.js web to evaluate both `Employee.id` and `User.id` entities, eliminating false-negative approval buttons.
     - SEC-09-02: Guaranteed transaction rollback on attendance projection recalculation failures in leave approval.
     - SEC-09-03: Reinforced multiplier $\ge 1.00$ and cap bounds at both Pydantic schema ingress and service layer.
  3. **Static & Dependency Security Analysis**:
     - Python: `pip check` clean, `ruff` 0 errors.
     - Web: `npm audit` documented, Next.js build 14/14 static pages generated with 0 errors, ESLint 0 warnings/errors.
     - Flutter: `flutter analyze` 0 issues.
     - Secrets: 0 hardcoded keys or leaked credentials found across Phase 9 code.
  4. **Formal Phase 9 Closure Decision**:
     - Designated **Outcome B: Implementation complete, infrastructure validation outstanding** due to absence of local PostgreSQL/Docker runtime on the test execution host. Direct PostgreSQL RLS policy execution deferred to deployment staging on a live PostgreSQL 16/Supabase instance.
  5. **Monorepo Test Totals**:
     - **1,135 total automated tests passing (100% pass rate)**: 655 backend pytest tests (121 Phase 9), 104 Next.js web tests, and 376 Flutter mobile tests.
- **Report**: [`docs/phase-reports/PHASE_09_MILESTONE_08_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_09_MILESTONE_08_REPORT.md)

### 11.11 Phase 10 Scope Verification & Authorization
- **Scope Verification Report**: [`docs/phase-reports/PHASE_10_SCOPE_VERIFICATION_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_SCOPE_VERIFICATION_REPORT.md)
- **Authoritative Scope Reconciled**: Reconciled the scope discrepancy between earlier documentation ("Outbound Alerts") and the Phase 9.8 report ("Payroll Integration"). Confirmed Phase 10 is **Notifications (Outbound Alerts)** per the original 22-phase roadmap, Section 5.4, and `ARCHITECTURE.md` Section 4. Payroll is assigned to Phase 14.
- **Approved Roadmap Breakdown**:
  - Milestone 10.1: Notification Database Architecture, Models & Alembic Migration (COMPLETED)
  - Milestone 10.2: Core Dispatch Engine & Notification Repository
  - Milestone 10.3: Push Notification Provider (FCM Adapter & Token Registration)
  - Milestone 10.4: Email & SMS Notification Providers (SMTP / Gateway Adapters)
  - Milestone 10.5: Domain Event Triggers & Integration Hooks
  - Milestone 10.6: Web Console Management UI (Templates, Preferences, Delivery Logs)
  - Milestone 10.7: Flutter Mobile Push & In-App Notification Center
  - Milestone 10.8: End-to-End Simulation, Security Audit & Phase 10 Verification

### 11.12 Phase 10 Milestone 10.1 Summary: Notification Database Foundation
- **Delivered**:
  1. **SQLAlchemy 2.0 Models (`services/api/notifications/models.py`)**:
     - `NotificationTemplate` (`notification_templates`): System-defined default templates (`tenant_id IS NULL`) and tenant overrides; partial unique indexes.
     - `NotificationPreference` (`notification_preferences`): Tenant fallback defaults (`user_id IS NULL`) and user-level overrides (`user_id=<uuid>`); quiet-hours format `HH:MM` and timezone support.
     - `Notification` (`notifications`): Outbound dispatch requests and persistent audit ledger; lifecycle status checks (`PENDING`, `PROCESSING`, `RETRY_SCHEDULED`, `SENT`, `DELIVERED`, `FAILED`, `CANCELLED`); priority levels; worker queue index; tenant idempotency partial index; audit preservation via `ondelete="SET NULL"` on recipient foreign keys.
     - `DevicePushToken` (`device_push_tokens`): FCM device registration tokens with SHA-256 `token_hash`, active status partial unique index, rotation and revocation support.
  2. **Alembic Migration (`database/migrations/versions/b5c6d7e8f9a0_phase_10_notifications.py`)**:
     - Revision ID `b5c6d7e8f9a0` chained linearly to head `a4b5c6d7e8f9`.
     - Enables and forces Row Level Security (RLS) on all 4 tables.
     - Multi-tenant read and write policies distinguishing system templates from tenant modifications.
     - Fully reversible downgrade script.
  3. **Alembic Configuration (`database/migrations/env.py`)**:
     - Registered all 4 models on `Base.metadata`.
     - Single head confirmed: `b5c6d7e8f9a0 (head)`.
  4. **Automated Test Suite (`tests/test_phase10_database_models_and_migration.py`)**:
     - 20 unit and contract tests verifying migration chain, model constraints, partial unique indexes, RLS script DDL, and audit preservation.
     - **20 passed in 0.94s (100% pass rate)**.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_01_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_01_REPORT.md)

### 11.13 Phase 10 Milestone 10.2 Summary: Core Notification Dispatch Engine & Repository
- **Delivered**:
  1. **Notification Backend Package (`services/api/notifications/`)**:
     - `exceptions.py`: Typed domain exceptions (`TemplateNotFoundError`, `TemplateRenderError`, `RecipientNotFoundError`, `ChannelDisabledError`, `QuietHoursDeferredError`, `DuplicateNotificationError`, `InvalidStateTransitionError`, `ProviderError`, `ProviderTimeoutError`).
     - `schemas.py`: Pydantic V2 schemas and string enums (`NotificationChannel`, `NotificationStatus`, `NotificationPriority`, `DevicePlatform`, `DeviceTokenStatus`, `ProviderStatus`, `NotificationCreateRequest`, `NotificationResponse`, `ProviderResult`, `DispatchResult`).
     - `template_renderer.py` (`SafeTemplateRenderer`): Safe restricted parameter substitution; strict prohibition of Python `eval`/`exec`/dunders; context-aware HTML entity escaping and subject CRLF injection stripping.
     - `preference_resolver.py` (`PreferenceResolver`): Hierarchical resolution (User override -> Tenant default -> System fallback); audit logging of channel skip reasons.
     - `quiet_hours.py` (`QuietHoursEvaluator`): Timezone-aware quiet-hours evaluator supporting daytime and overnight intervals, exact boundaries, DST handling, and urgent priority bypass.
     - `provider.py` (`BaseNotificationProvider`): Channel provider abstraction; `MockPushProvider`, `MockEmailProvider`, and `MockSmsProvider` simulating acceptance, transient retryable failures, unretryable rejections, invalid tokens, and timeouts; token hashing (`hash_push_token`) and encryption at rest (`encrypt_token_at_rest`).
     - `repository.py` (`NotificationRepository`): Async repository supporting tenant-isolated queries, idempotency checks, atomic status transition (`claim_for_processing`), retry scheduling, permanent failure recording, recipient pagination, template fallback, preference upsert, and device token rotation/revocation.
     - `service.py` (`NotificationService`): Creation service resolving recipient destinations (user email, employee phone, active FCM token), evaluating preferences, rendering templates, and scheduling initial quiet-hours deferrals.
     - `dispatcher.py` (`NotificationDispatcher`): Core dispatch orchestrator handling atomic claims, quiet hours re-evaluation, provider invocation, exponential backoff calculation (60s, 120s, 240s... capped at 1h), and delivery lifecycle tracking (SENT vs DELIVERED).
  2. **Automated Test Suite (`tests/test_phase10_milestone2_dispatch_engine.py`)**:
     - 37 dedicated unit and contract tests verifying template safety, preference hierarchy, quiet-hours boundaries, mock provider behaviors, repository idempotency, and dispatch lifecycles.
     - **37 passed in 2.62s (100% pass rate)**.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_02_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_02_REPORT.md)

### 11.14 Phase 10 Milestone 10.3 Summary: FCM Push Integration, Device Token Registration APIs & Celery Dispatch Workers
- **Delivered**:
  1. **Firebase Cloud Messaging Adapter (`services/api/notifications/fcm_provider.py`)**:
     - Official Google Firebase Admin SDK (`firebase-admin`) adapter implementing `BaseNotificationProvider`.
     - Android configuration: high priority, `upostit_alerts` notification channel, sound, `FLUTTER_NOTIFICATION_CLICK`.
     - iOS APNs configuration: priority 10, APS alert payload, sound, badge 1.
     - Normalized `ProviderResult`: status `ACCEPTED`, `provider_message_id`, raw provider payload (`SENT != DELIVERED`).
     - Error classification: `UnregisteredError`/`SenderIdMismatchError`/`NotFoundError` -> unretryable; `QuotaExceededError`/`UnavailableError`/`DeadlineExceededError` -> retryable; `TimeoutError` -> `ProviderTimeoutError`.
     - Safe fallback: falls back to `MockPushProvider` when `FCM_ENABLED=False`.
  2. **Authenticated Token Encryption at Rest (`services/api/notifications/crypto.py`)**:
     - Vetted `cryptography.fernet.Fernet` implementing AES-128-CBC + HMAC-SHA256 authenticated encryption.
     - Key derivation via `PBKDF2HMAC` (SHA-256, 100,000 iterations) from secret key.
     - Strict `fernet:` prefix enforcement and zero plaintext fallback; tampered payloads fail MAC verification.
     - Safe display masking (`mask_token_for_display`) ensuring raw push tokens never appear in logs or API responses.
  3. **Device Push Token Registration & Management APIs (`services/api/notifications/routes.py`)**:
     - `POST /api/v1/notifications/devices`: Register or rotate device push token for authenticated user and tenant context; encrypts token, stores SHA-256 hash, invalidates superseded tokens for the same physical device ID.
     - `GET /api/v1/notifications/devices`: List active device tokens with masked preview for current authenticated user.
     - `DELETE /api/v1/notifications/devices/{token_hash}`: Revoke device push token by hash.
     - `POST /api/v1/notifications/devices/revoke`: Revoke device push token by raw token value or hash.
     - Strict tenant and user isolation: derived strictly from `AuthenticatedContext`.
  4. **Celery Asynchronous Notification Workers (`services/workers/notification_tasks.py`)**:
     - `notifications.dispatch_single`: Atomically claims and dispatches a single notification.
     - `notifications.dispatch_batch`: Bounded batch dispatch querying pending notifications.
     - `notifications.process_retries`: Enqueues notifications in `RETRY` where `next_retry_at <= now()`.
     - `notifications.reconcile_stuck_processing`: Recovers crashed notifications stuck in `PROCESSING` (> 15m).
     - `notifications.cleanup_revoked_tokens`: Purges inactive/revoked device tokens older than 90 days.
     - Exponential backoff with jitter and dead-letter preservation upon reaching `max_attempts=3`.
  5. **Quiet-Hours Compliance**:
     - Removed unconditional URGENT bypass; quiet hours strictly respected per roadmap instructions.
  6. **Automated Test Suite (`tests/test_phase10_milestone3_fcm_and_celery.py`)**:
     - 19 comprehensive unit and contract tests verifying FCM adapter error classification, Android/iOS configurations, token registration APIs, Celery workers, and Fernet authenticated encryption.
     - **19 passed in 6.36s (100% pass rate)**.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_03_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_03_REPORT.md)

### 11.15 Phase 10 Milestone 10.4 Summary: Domain Event Triggers & Notification Integration
- **Delivered**:
  1. **Typed Domain Event Schemas (`services/api/notifications/events.py`)**:
     - 13 strongly-typed Pydantic V2 domain events (`DomainEvent`, `LeaveRequestSubmittedEvent`, `LeaveRequestApprovedEvent`, `LeaveRequestRejectedEvent`, `LeaveRequestCancelledEvent`, `OfflineConflictSubmittedEvent`, `AttendanceConflictApprovedEvent`, `AttendanceConflictRejectedEvent`, `HighRiskFraudAlertEvent`, `ImpossibleTravelSignalEvent`, `MockGpsDetectedEvent`, `EmployeeInvitationCreatedEvent`, `EmployeeInvitationSentEvent`, `PasswordResetRequestedEvent`).
     - Standardized event metadata: `tenant_id`, `event_id`, `correlation_id`, `occurred_at`, `actor_user_id`.
  2. **Canonical System Default Templates (`services/api/notifications/default_templates.py`)**:
     - 23 canonical system default templates for all 13 domain events (10 events with both EMAIL and PUSH = 20 templates; 3 events with EMAIL only = 3 templates; SMS is intentionally not configured in this phase).
     - Fallback mechanism in `NotificationRepository.get_template` guarantees zero template miss errors if tenant customization does not exist.
  3. **Domain Notification Handler (`services/api/notifications/event_handler.py`)**:
     - `DomainNotificationHandler`: Orchestrates recipient resolution, preference filtering, and notification creation.
     - Recipient resolution: hierarchy resolution for reporting managers (`Employee.reporting_manager_id`) with fallback to tenant owners/admins (`User.role IN ('owner', 'admin')`).
     - Preference filtering: user override and tenant default channel opt-out enforcement.
     - Quiet-hours scheduling: all notification categories (including fraud alerts and password resets) strictly respect recipient quiet hours without bypass. Non-urgent and urgent events during quiet hours are scheduled for the next eligible dispatch time (morning 07:00).
     - Deterministic idempotency keys: `{event_type}:{entity_id}:{recipient}:{channel}` format preventing duplicate notifications.
  4. **Transactional Outbox Architecture**:
     - Atomic staging: `dispatch_domain_event` stages notifications directly into the database within the calling transaction.
     - Rollback resilience: if the business transaction fails, the staged notification rolls back atomically (zero orphan notifications).
     - Asynchronous dispatch: post-transaction helper `enqueue_celery_dispatch` enqueues background delivery with zero-loss fallback.
     - At-least-once delivery guarantee: provider failure transitions notification to `RETRY_SCHEDULED`, never affecting the already-committed business record.
  5. **Strict Secret Protection**:
     - Zero raw tokens or credential hashes in `payload_json`, subjects, or body text.
     - Action tokens strictly delivered in single-use HTTPS URLs (`activation_url`, `reset_url`).
  6. **Business Domain Integration Hooks**:
     - Phase 9 Leave: `leave_request_service.py` (submitted, approved, rejected, cancelled).
     - Phase 8 Attendance Conflicts: `conflict_service.py` (submitted, approved, rejected).
     - Phase 7 Fraud Shield: `attendance/service.py` (high risk score, impossible travel velocity, mock GPS).
     - Phase 4 Invitations: `invitation_service.py` (invitation created, resend).
     - Phase 2 Auth: `auth/service.py` (`request_password_reset` service helper; full user-facing password reset route and token model documented as pending).
  7. **Automated Test Suite (`tests/test_phase10_milestone4_domain_events.py`)**:
     - 23 comprehensive unit and integration tests verifying all 13 events, outbox rollback, idempotency replay, secret hygiene, quiet hours deferral (including fraud and password reset), user preference opt-outs, provider failure isolation, and cross-tenant isolation.
     - **23 passed in 4.80s (100% pass rate)**.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_04_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_04_REPORT.md)

### 11.5 Milestone 10.5 — Next.js Web Console: Notification Administration (Completed & Fully Verified 2026-11-22)
- **Key Deliverables**:
  1. **Next.js App Router Page (`apps/web/src/app/notifications/page.tsx`)**:
     - Dedicated Notification Administration Console with 5 operational views: Overview, Templates, Channels, Preferences, and Activity Log.
     - Overview: metrics cards (Total, Sent, Delivered, In-Flight, Failed), visual SENT vs DELIVERED milestone distinction banner, lifecycle status breakdown, and channel traffic distribution.
     - Templates: catalog table distinguishing `🌐 System Default` from `🏢 Tenant Override`; template inspection and customization modal with safe variable documentation based on domain event schemas; system default immutability protection with tenant-level overrides via `PUT /templates/{id}`; zero credential leakage.
     - Channels: real-time readiness dashboard reflecting runtime FCM, SMTP, and deferred SMS capabilities with `CONFIGURED_UNVERIFIED` / `MOCK` / `UNCONFIGURED` status taxonomy (never displaying "Active (Production)" for unverified gateways).
     - Preferences: tenant-wide default communication rules (channel enable toggles, quiet-hours windows in 24h `HH:MM` format, timezone selector); strict RBAC enforcement (read-only for non-admins).
     - Activity Log: filterable (status, channel, event type), paginated activity table with detail inspection modal displaying full delivery timeline, masked destination, provider acknowledgment, and sanitized bodies.
  2. **Frontend API Client (`apps/web/src/lib/api.ts`)**:
     - Added typed DTOs and `notificationApi` methods (`getOverview`, `getTemplates`, `createOrUpdateTemplate`, `updateTemplate`, `getPreferences`, `updatePreferences`, `getChannels`, `getActivity`).
  3. **Backend Administrative Endpoints (`services/api/notifications/routes.py`, `schemas.py`, `repository.py`, `main.py`)**:
     - Router registered in FastAPI `main.py` under `api_v1_router` (`/api/v1/notifications`).
     - Added REST endpoints: `GET /overview`, `GET /templates`, `POST /templates`, `PUT /templates/{template_id}`, `GET /preferences`, `PUT /preferences`, `GET /channels`, `GET /activity`.
     - System template immutability enforced (403 Forbidden when attempting to update system templates in-place).
     - Cross-tenant isolation enforced (404 Not Found on cross-tenant template updates).
     - Enforced `require_roles(UserRole.OWNER, UserRole.ADMIN)` on preference updates and `require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR)` on template overrides.
  4. **Automated Test Suites & Static Verification**:
     - Frontend: `apps/web/src/lib/notification-console.test.ts` (15 dedicated tests, 100% pass; 119 total web unit tests passing).
     - Backend: `tests/test_phase10_milestone5_web_routes.py` (21 dedicated integration & security tests, 100% pass; 120 total Phase 10 backend tests passing).
     - Static checks: Next.js build passed with 15/15 static pages prerendered; ESLint 0 errors / 0 warnings; Ruff 0 errors.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_05_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_05_REPORT.md)

### 11.17 Phase 10 Milestone 10.6 Summary: Flutter Mobile: Push Token Lifecycle & In-App Notification Center
- **Objective**: Implement the complete mobile push notification token lifecycle, foreground/background message handling, and in-app notification center in the Flutter mobile application (`apps/mobile`).
- **Key Deliverables**:
  1. **FCM Device-Token Lifecycle**:
     - Configured Android (`POST_NOTIFICATIONS` permission in `AndroidManifest.xml`) and iOS (`UIBackgroundModes` `fetch` and `remote-notification` in `Info.plist`).
     - Implemented `FirebasePushNotificationService` with top-level `@pragma('vm:entry-point') firebaseMessagingBackgroundHandler`, runtime permission request, and `onTokenRefresh` stream listener.
     - Implemented `MockPushNotificationService` for deterministic unit testing and unconfigured environment fallback.
     - Secure token registration via `POST /api/v1/notifications/devices` with device platform metadata (`ANDROID`/`IOS`, device model, OS version, app version).
     - Token deduplication caching in `FlutterSecureStorage` (`getLastRegisteredPushToken`, `getLastRegisteredTokenHash`) avoiding redundant POST requests on cold app boots.
     - Automatic token rotation re-registration with `force: true` on provider token refresh.
     - Secure logout revocation: Dispatches `POST /api/v1/notifications/devices/revoke` (raw token) or `DELETE /api/v1/notifications/devices/{token_hash}` and deletes local cached tokens on session termination.
  2. **In-App Notification Center (`NotificationInboxScreen`)**:
     - Screen accessible via top app bar with real-time unread count badge.
     - Unread vs read visual distinction with status dots and card styles.
     - Filter chips ("All" vs "Unread") allowing quick filtering.
     - Categorized badges (`Leave`, `Attendance`, `Security`, `Organization`, `Account`, `Notification`) with priority styling.
     - Relative timestamps ("Just now", "5m ago", "2h ago", "Nov 22").
     - Notification detail inspection modal (`NotificationDetailDialog`) showing full message content, event category, priority, formatted timestamp, and contextual action buttons.
     - Pull-to-refresh (`RefreshIndicator`) and app-bar refresh icon button.
     - Responsive loading (`LoadingIndicator`), error banner with retry (`ErrorBanner`), and empty state views (`EmptyStateView`).
  3. **Documented Backend API Gap Handling**:
     - Documented architectural gap: The backend currently lacks a user-scoped `GET /api/v1/notifications/inbox` endpoint and database-backed `is_read` read tracking for individual users.
     - Preserved backend schema integrity without inventing fake database tables or pretend server synchronization:
       - `NotificationRemoteDataSource` translates HTTP 404 into `ApiGapException`.
       - `NotificationRepositoryImpl` maps this into `ApiGapFailure` without throwing unhandled exceptions.
       - `NotificationInboxScreen` renders `NotificationApiGapBanner` while presenting in-memory push notifications received during the live session.
  4. **Push Interactions & Safe Deep Link Whitelist**:
     - Foreground push alerts (`onMessage`) are sanitized and added directly to the active session inbox.
     - Safe deep link whitelist (`_isSafeRoute`): Restricts deep links strictly to validated internal application routes (`/home`, `/leave`, `/schedule`, `/history`, `/sync`, `/profile`) and explicitly rejects open-redirects or arbitrary external URLs (`https://...`).
     - Sensitive data redaction: Passwords, auth tokens, invitation codes, and sensitive fraud telemetry (`risk_score`, `gps_spoof_score`) are regex-redacted before in-memory storage.
  5. **Verification & Test Results**:
     - 4 dedicated notification test suites in `apps/mobile/test/features/notifications/` (36 tests, 100% pass):
       - `notification_remote_data_source_test.dart` (7 tests, 100% pass)
       - `notification_repository_test.dart` (9 tests, 100% pass)
       - `notification_bloc_test.dart` (12 tests, 100% pass)
       - `notification_inbox_screen_test.dart` (8 tests, 100% pass)
     - Full mobile test suite: **412 tests passing 100%** with zero regressions across attendance, auth, profile, leave, sync, devices, and history.
     - Static checks: `flutter analyze` (0 issues found, clean); `dart format --set-exit-if-changed` (clean).
     - Native builds: Android debug APK (`build/app/outputs/flutter-apk/app-debug.apk`) built successfully in 35.2s; Android release APK (`build/app/outputs/flutter-apk/app-release.apk`) built successfully in 56.9s.
     - iOS APNs config verified; physical device delivery status: mock/simulated only (pending production FCM credentials and APNs certificates).
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_06_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_06_REPORT.md)

### 11.18 Phase 10 Milestone 10.7 Summary: End-to-End Simulation, Chaos Testing & Multi-Tenant Validation
- **Objective**: Execute an exhaustive automated validation, failure-mode/chaos testing, and multi-tenant security verification across the Phase 10 notification subsystem and its cross-platform clients (FastAPI, Celery, Next.js web console, Flutter mobile app).
- **Key Deliverables**:
  1. **End-to-End Business Workflows**:
     - Automated lifecycle simulations for Leave (`leave_request_submitted`, `approved`, `rejected`, `cancelled`), Attendance Conflicts (`submitted`, `approved`, `rejected`), Fraud Shield (`fraud_incident_high_risk`, `fraud_alert_digest`), Employee Invitations (`created`, `resent`), and Password Reset (`auth_password_reset_requested`).
     - Accurate recipient resolution via tenant reporting hierarchy; strict enforcement of user quiet hours and channel preferences.
     - Verification of secret protection: Passwords, auth tokens, invitation tokens, and sensitive fraud telemetry (`risk_score`, `gps_spoof_score`) are never logged or leaked into external payloads.
  2. **Transaction and Outbox Chaos Engineering**:
     - *Rollback Atomicity*: Business transaction rollbacks leave zero orphan notification records in outbox.
     - *Broker Decoupling*: Celery enqueue failure / Redis unavailability preserves notifications in `PENDING` outbox status without crashing caller threads; outbox polling/sweeping recovers dispatch.
     - *Worker Failure Recovery*: `reconcile_stuck_processing_task` reconciles stuck `PROCESSING` tasks past lock timeout (300s) to `RETRY_SCHEDULED` or `FAILED`.
     - *Backoff & Exhaustion*: Transient provider failures trigger exponential backoff (60s -> 120s -> 240s) up to `max_attempts=3`, then transition to `FAILED`.
     - *Concurrency Race Protection*: Atomic SQL claiming (`UPDATE ... WHERE status IN ('PENDING', 'RETRY_SCHEDULED') RETURNING ...`) guarantees single-worker execution.
     - *Delivery Semantics*: External delivery is formally characterized as **at-least-once**, not exactly-once.
  3. **Multi-Tenant Security & Isolation**:
     - Verified Tenant A cannot inspect, modify, or receive Tenant B notifications, templates, device tokens, quiet hours, or preferences.
     - Cross-tenant template isolation with global system template fallback (`is_system=True`, `tenant_id IS NULL`).
     - RBAC enforcement: 401 Unauthorized for unauthenticated requests, 403 Forbidden for unauthorized roles.
     - PostgreSQL Row-Level Security: Verified Alembic migration DDL enforces `FORCE ROW LEVEL SECURITY` and `tenant_isolation` policies with `current_setting('app.tenant_id', true)::uuid`.
  4. **Cross-Platform Integration Simulation**:
     - Simulated complete lifecycle: Backend Outbox -> Web Admin Console -> Mobile Token Registration -> Mock FCM Dispatch -> Foreground In-App Alert -> Deep Link Whitelisting -> Logout Token Revocation.
     - Documented mobile inbox API gap: Confirmed that mobile app maps HTTP 404 to `ApiGapException` / `NotificationApiGapBanner` gracefully without inventing mock persistence.
  5. **Provider Readiness & Delivery Taxonomy**:
     - Verified taxonomy: Mock PUSH/EMAIL (`READY_FOR_USE`), SMS (`UNCONFIGURED_DEFERRED`), FCM/SMTP (`CONFIGURED_UNVERIFIED`).
     - Verified delivery progression: `CREATED` -> `WORKER_ACCEPTED` -> `PROVIDER_ACCEPTED` (`SENT`) -> `DEVICE_DELIVERED` -> `USER_OPENED`.
  6. **Automated Test Results & Performance Metrics**:
     - Backend: `tests/test_phase10_milestone7_e2e_and_chaos.py` (24 tests, 100% pass in 2.54s).
     - Full Phase 10 backend suite: **144 tests passing 100%** (20 DB, 37 engine, 19 FCM/Celery, 23 events, 21 web routes, 24 chaos/E2E).
     - Full backend suite: **799 tests passing 100%** across 37 test files (in 107.46s).
     - Web frontend: `apps/web/src/lib/notification-e2e-simulation.test.ts` (6 tests, 100% pass); total 125 web unit tests passing (100%).
     - Mobile: 412 Flutter tests passing (100%); `flutter analyze` 0 issues; `dart format` clean.
     - Monorepo grand total: **1,336 automated tests passing 100%**.
     - Performance: 50 concurrent outbox writes in 12ms (>4,000/s); 50 dispatches in 5ms (>10,000/s); 10 worker recoveries in 2ms.
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_07_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_07_REPORT.md)

### 11.19 Phase 10 Milestone 10.8 Summary: Security Audit, Penetration Testing & Formal Phase 10 Closure
- **Objective**: Execute a rigorous security audit, controlled automated penetration testing, remediation of discovered vulnerabilities, monorepo regression testing, and formal Phase 10 closure under Outcome B (Conditionally closed due to host environment boundaries).
- **Key Deliverables & Security Remediations**:
  1. **Finding 1 (High Severity) — RBAC Hardening on Administration Endpoints**:
     - Secured `GET /notifications/overview`, `GET /notifications/templates`, `GET /notifications/preferences`, `GET /notifications/channels`, and `GET /notifications/activity` in `services/api/notifications/routes.py` with `dependencies=[Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.HR))]`. Previously, authenticated employees could view company-wide delivery statistics and activity logs containing sensitive leave details and fraud alerts.
     - Added client-side role privilege guard in Next.js web console (`apps/web/src/app/notifications/page.tsx`), displaying an `Access Denied` card for non-admin/HR users.
  2. **Finding 2 (Medium Severity) — Template SSTI Pre-Validation Gap**:
     - Added `@field_validator("body_template", "subject_template")` in `TemplateCreateRequest` and `TemplateUpdateRequest` (`services/api/notifications/schemas.py`) utilizing `_SUSPICIOUS_EXPRESSION_REGEX`. Prohibited Jinja2/Python dunder expressions (`__class__`, `__mro__`, `__import__`, `eval(`, `exec(`, `os.`) are rejected with HTTP 422 Unprocessable Entity at API request parsing time before persisting to database.
     - Enforced max length (50 characters) on `timezone` in `PreferenceUpdateRequest`.
  3. **Finding 3 (Low Severity) — Device Token Boundary & Hash Length Enforcement**:
     - Enforced maximum string length (`len(clean_hash) <= 128`) on `DELETE /notifications/devices/{token_hash}` and `len(raw_token) <= 4096` on `POST /notifications/devices/revoke` (`services/api/notifications/routes.py`), returning HTTP 400 Bad Request on oversized inputs.
  4. **Finding 4 (Informational) — Upstream Next.js 14.2.5 Security Advisories**:
     - `npm audit` flagged known upstream Next.js 14.2.5 image optimization / server actions advisories. Packages remain safely pinned per policy to prevent breaking monorepo stability; framework upgrade scheduled for deployment hardening.
  5. **PostgreSQL RLS & Celery Background Execution**:
     - Verified that Celery background workers in `services/workers/notification_tasks.py` explicitly invoke `await set_tenant_context(session, str(tenant_id))` before querying notifications or invoking dispatchers, ensuring fail-closed PostgreSQL Row-Level Security outside HTTP request threads.
  6. **Automated Penetration Test Suites**:
     - Backend: `tests/test_phase10_milestone8_security_audit.py` (34 test cases across Authentication, Cross-Tenant Isolation, RBAC Hardening, API/Input Attacks, and Notification Data Protection — 100% pass in 2.14s).
     - Web: `apps/web/src/lib/notification-security-audit.test.ts` (7 penetration test cases covering RBAC 403, SSTI 422, token length 400, and credential masking — 100% pass).
  7. **Monorepo Regression Matrix & Test Counts**:
     - Backend: **833 tests passing 100%** (178 Phase 10 tests).
     - Web Console: **132 tests passing 100%**; `npm run lint` clean (0 warnings/errors); `npm run build` clean (15/15 static pages prerendered).
     - Mobile: **412 tests passing 100%**; `flutter analyze` clean (0 issues).
     - Grand Total: **1,377 automated tests passing 100%** across the monorepo.
  8. **Formal Closure Verdict**:
     - **Outcome B — Conditionally Closed**: All automated suites and security tests pass with 100% success. Conditionally closed due to development workstation boundary (no live host PostgreSQL/Redis daemons and no physical Android/iOS hardware).
- **Report**: [`docs/phase-reports/PHASE_10_MILESTONE_08_SECURITY_AUDIT_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_10_MILESTONE_08_SECURITY_AUDIT_REPORT.md)

### 11.20 Phase 11 Milestone 11.1 Summary: Offline-First Sync Engine Architecture Assessment & Blueprint
- **Objective**: Conduct a complete architecture assessment of the existing offline-first synchronization subsystem and produce a technically rigorous implementation blueprint for Phase 11.
- **Key Deliverables**:
  1. **Comprehensive Scope Assessment (`docs/PHASE_11_SCOPE_ASSESSMENT.md`)**:
     - Audited all 19 technical dimensions across Flutter local queues, SQLite schemas, backend punch ledger, idempotency records, conflict submission APIs, and PostgreSQL Row-Level Security.
     - Documented gaps: Lack of batch sync API (`POST /attendance/sync/batch`), single-item network chatriness, timestamp assignment placing offline punches at sync time rather than punch time, missing downward sync, and missing supervisor conflict adjudication on mobile.
  2. **8-Milestone Implementation Plan (`docs/PHASE_11_PLAN.md`)**:
     - Formulated 8 detailed milestones: 11.1 (Blueprint), 11.2 (Batch Ingestion & Timestamp Hardening), 11.3 (Downward Sync Protocol), 11.4 (Mobile SQLite Queue & Sync BLoC), 11.5 (Supervisor Mobile Conflict Resolution UI), 11.6 (Web Admin Sync Monitoring Console), 11.7 (End-to-End Simulation & Chaos), 11.8 (Security Audit & Closure).
     - Reconciled roadmap sequence: Confirmed Phase 11 is specialized as **Offline-First Sync Engine & Advanced Conflict Resolution** while Plans & Billing is re-sequenced.
- **Report**: [`docs/PHASE_11_SCOPE_ASSESSMENT.md`](file:///Users/apple/Upostit/docs/PHASE_11_SCOPE_ASSESSMENT.md) & [`docs/PHASE_11_PLAN.md`](file:///Users/apple/Upostit/docs/PHASE_11_PLAN.md)

### 11.21 Phase 11 Milestone 11.2 Summary: Backend Batch Sync Protocol & Timestamp Semantic Hardening
- **Objective**: Implement the backend batch synchronization protocol for queued offline attendance events with atomic savepoint isolation, dual-tier idempotency, and timestamp semantic hardening.
- **Key Deliverables**:
  1. **Batch Sync Endpoint (`POST /api/v1/attendance/sync/batch`)**:
     - Accepts up to 50 items per batch (`AttendanceBatchSyncRequest`), returning aggregate counts and item receipts (`ACCEPTED`, `DUPLICATE`, `REQUIRES_REVIEW`, `REJECTED`, `CONFLICT`, `RETRYABLE`).
     - Derives employee and tenant identity strictly from authenticated JWT (`AuthenticatedContext`). Cross-tenant requests rejected with HTTP 400.
     - Role scoping strictly enforced: `OWNER`, `ADMIN`, `HR` tenant-wide; `MANAGER` scoped to self and verified direct reports (`Employee.reporting_manager_id == mgr_emp.id`, 403 Forbidden on non-direct reports); `EMPLOYEE` scoped to own attendance only (403 Forbidden on peers).
     - Enforces row-level lock (`with_for_update()`) on Employee to serialize concurrent syncs.
  2. **Partial Batch Success via Savepoint Isolation**:
     - Executes each item inside nested transaction savepoints (`session.begin_nested()`). Policy violations or state conflicts roll back only that specific event while preceding and subsequent items proceed cleanly.
  3. **Dual-Tier Idempotency**:
     - Intra-batch deduplication: First occurrence processed; duplicate keys within same batch receive `DUPLICATE` receipt replaying original `server_event_id` and `effective_at`.
     - Database-level deduplication: Checks `attendance_idempotency_records`. Completed punches replayed without inserting duplicate ledger rows into `attendance_events`.
  4. **Timestamp Semantic Hardening & Warning Window Invariant**:
     - Legitimate offline punches (`is_offline_sync=True`) within allowable windows assign `effective_at = device_reported_at`, anchoring to the historical shift date and calculating correct work duration.
     - Preserves `server_received_at` in dedicated audit column for forensic analysis.
     - Future timestamps within warning window (60s–300s) preserve original `device_reported_at` intact for auditability and supervisor adjudication, while assigning `effective_at = server_received_at` to prevent premature future working duration or shift distortion until reviewed, attaching `review_status = "PENDING_REVIEW"` (`FLAG_FUTURE_TIMESTAMP_DETECTED`) and `timestamp_verification_status = "SUSPICIOUS_CLOCK_DRIFT"`.
     - Extended offline events (24h–72h) retain original event time with `PENDING_REVIEW` (`FLAG_OFFLINE_WINDOW_EXCEEDED`).
     - Hard rejections with HTTP 422 for future > 300s (`FUTURE_TIMESTAMP`) and past > 72h (`OFFLINE_WINDOW_EXCEEDED`).
     - Applied matching hardened timestamp semantics to `POST /attendance/punch` for backwards compatibility.
  5. **State Machine & Invariant on Unclosed Breaks**:
     - In-memory state tracking (`CHECKED_OUT`, `WORKING`, `ON_BREAK`) initialized from DB.
     - Detects out-of-order punches and missing prerequisites (`SEQUENCE_CONFLICT`).
     - **Strict Break-End Invariant**: Never fabricates a `BREAK_END` event or invents break-end timestamps. When checking out while on break, preserves original open break, marks check-out with `PENDING_REVIEW` (`UNCLOSED_BREAK_ON_CHECKOUT`), and returns `REQUIRES_REVIEW` receipt.
  6. **Automated Verification Matrix**:
     - Implemented all 20 required scenarios plus manager direct-report checks and warning window integration test in `tests/test_phase11_sync_batch_api.py` (25/25 passed 100%).
     - Monorepo regression suites: Backend (858/858 passed), Web (132/132 passed), Mobile (412/412 passed). **1,402 total automated tests passing 100%**.
  7. **Roadmap Discrepancy Note**:
     - Preserves the historical roadmap discrepancy: Phase 11 was originally designated as Plans and Billing in initial plans, re-sequenced to prioritize the Offline-First Sync Engine & Advanced Conflict Resolution.
- **Report**: [`docs/phase-reports/PHASE_11_MILESTONE_02_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_11_MILESTONE_02_REPORT.md)

### 11.22 Phase 11 Milestone 11.3 Summary: Downward Delta Sync Protocol: Reference Data & Shift Rosters
- **Objective**: Implement reliable server-to-mobile synchronization of reference data and shift rosters so the mobile client reflects updates made by HR/Admins without requiring logout or app reinstall.
- **Key Deliverables Completed & Acceptance Hardened**:
  1. **Pydantic v2 Delta Schemas (`services/api/attendance/downward_sync_schemas.py`)**:
     - `SyncDeltaResponse`, `SyncEmployeePayload`, `SyncShiftPayload`, `SyncWorkplacePayload`, `SyncHolidayPayload`, `SyncLeaveTypePayload`, `SyncLeaveBalancePayload`, `SyncLeaveRequestPayload`, `SyncAttendancePolicyPayload`, `SyncDirectReportPayload`, `SyncReportingHierarchyPayload`, `SyncTombstonePayload`.
  2. **Downward Delta Sync Engine & Acceptance Hardening (`services/api/attendance/downward_sync_service.py`)**:
     - Composite keyset cursor pagination v2 (`v=2`, `tid`, `uid`, `eid`, `bts`, `sts`, `ent`, `lid`, `exp`, `sig`) progressing through `COLLECTION_ORDER`.
     - Frozen session snapshot isolation (`session_ts`) preventing concurrent database inserts/updates from skewing multi-page sync sessions.
     - Identical timestamp preservation without skips or duplicates across page boundaries.
     - HMAC-SHA256 tamper-resistant signatures, cursor TTL expiration enforcement, tenant/user/employee context binding, and zero-downtime key rotation via `fallback_keys`.
     - Full sync fallback when `cursor=None`.
     - Deactivation semantics (inactive employee returns empty reference collections).
     - Workplace unassignment tombstones (`entity_type="workplace"`) delivered across page boundaries.
  3. **Backend API Endpoints (`services/api/attendance/sync_routes.py` & `routes.py`)**:
     - Registered `GET /api/v1/sync/delta` and compatibility alias `GET /api/v1/attendance/sync/delta` under `Permission.VIEW_OWN_PROFILE`.
  4. **Mobile SQLite Schema Upgrade to v2 (`local_queue_database.dart`)**:
     - Bumped `databaseVersion` to 2; created 10 versioned cache tables in `_onUpgrade` (`sync_state`, `cached_employee`, `cached_shifts`, `cached_workplaces`, `cached_holidays`, `cached_leave_types`, `cached_leave_balances`, `cached_leave_requests`, `cached_attendance_policy`, `cached_direct_reports`).
     - **Queue Preservation Invariant**: Pending punches in `local_attendance_queue` are never dropped, modified, or cleared across migrations or cache purges.
  5. **Mobile Downward Sync DAO (`downward_sync_dao.dart`)**:
     - Atomic transactional delta application (`applyDeltaTransactionally`). Rollback on failure prevents cursor skew or partial cache corruption.
     - Duplicate response idempotency via `ConflictAlgorithm.replace`.
     - Tombstone deletions and dedicated offline reading queries.
  6. **Mobile Sync Coordinator (`downward_sync_coordinator.dart`)**:
     - Concurrency mutex deduplicating overlapping calls via `Completer`.
     - Multi-page pagination loop; self-healing cursor reset on HTTP 400 rejection (purging reference cache while strictly preserving `local_attendance_queue`); offline detection.
  7. **Automated Verification Matrix**:
     - 21 Pytest backend integration and acceptance audit tests in `tests/test_phase11_downward_sync_api.py` (21/21 passed 100%).
     - 15 Flutter unit and acceptance audit tests in `apps/mobile/test/features/sync/` (15/15 passed 100%).
     - Monorepo regression suites: Backend (879/879 passed), Web (132/132 passed), Mobile (427/427 passed). **1,438 total automated tests passing 100%**. 0 Ruff issues, 0 Flutter analyzer issues.
- **Report**: [`docs/phase-reports/PHASE_11_MILESTONE_03_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_11_MILESTONE_03_REPORT.md)

### 11.23 Phase 11 Milestone 11.4 Summary: Flutter Mobile: Enhanced Offline Queue & Resilient Sync Engine
- **Objective**: Implement a cohesive, unified client-side synchronization engine in Flutter mobile orchestrating upward attendance batch submissions and downward delta sync, with monotonic stale-response protection, background scheduler mutex, and non-destructive queue preservation.
- **Key Deliverables Completed & Verified**:
  1. **Unified Synchronization Orchestrator (`unified_sync_coordinator.dart`)**:
     - Centralized bidirectional synchronization (`UnifiedSyncCoordinator`) orchestrating upward attendance batch upload followed by downward reference data delta synchronization.
     - 11 distinct operational phases (`idle`, `checkingConnectivity`, `uploadingAttendance`, `downloadingReferenceData`, `applyingLocalUpdates`, `waitingForRetry`, `partiallySynchronized`, `fullySynchronized`, `authenticationRequired`, `conflictRequiresReview`, `fatalLocalStorageError`).
     - Concurrency mutex deduplication via active future cache and completers.
     - Cross-state resilience: upward punch submissions and downward delta updates do not corrupt or invalidate each other's state.
  2. **Batch Upload Protocol Integration & Enhanced Queue (`batch_sync_models.dart` & `sync_worker_impl.dart`)**:
     - Strongly typed batch request/response and receipt models.
     - Integration with `POST /api/v1/attendance/sync/batch` via `AttendanceRemoteDataSource.syncBatch`.
     - Partial batch receipt reconciliation: `ACCEPTED`, `DUPLICATE`, `REQUIRES_REVIEW` (mapped to `flaggedPendingReview`), `RETRYABLE` (pending with backoff), and `REJECTED` (permanent failure with cascading session quarantine).
     - Non-destructive queue preservation invariant: never deletes un-synced, pending, or permanently rejected punches.
  3. **Downward Sync Stale-Response Protection (`downward_sync_dao.dart`)**:
     - `SqfliteDownwardSyncDao.isIncomingStale` and `isTombstoneStale`.
     - Monotonic version comparison: policy version 5 cannot overwrite version 6.
     - Monotonic timestamp comparison: older entity timestamps cannot overwrite fresh local state.
     - Monotonic tombstone check: older deletions cannot delete newer modified entities.
  4. **Background Synchronization Scheduler (`background_sync_scheduler.dart`)**:
     - `BackgroundSyncScheduler` interface and `DefaultBackgroundSyncScheduler`.
     - Native Android WorkManager periodic task registration with `NetworkType.connected`, `ExistingPeriodicWorkPolicy.keep`, and exponential backoff.
     - Native iOS BGTaskScheduler configuration with permitted task identifiers in `Info.plist` and `processing` background mode.
     - Synchronous entry mutex lock preventing overlapping concurrent runs.
     - Network reachability checks deferring execution when offline.
  5. **Resilient BLoC Architecture & Offline UX (`sync_bloc.dart`, `sync_state.dart`, `offline_status_banner.dart`, `sync_status_screen.dart`)**:
     - Extended `SyncState` with operational phase, current operation message, retry status, and last sync timestamps without leaking PII.
     - Dynamic offline and authentication-required banner displays with manual sync trigger actions.
  6. **Automated Verification Matrix**:
     - 17 dedicated Phase 11.4 tests in `apps/mobile/test/features/sync/phase11_4_enhanced_offline_sync_test.dart` (17/17 passed 100%).
     - 154 feature sync tests in `apps/mobile/test/features/sync/` (154/154 passed 100%).
     - 444 total Flutter tests in `apps/mobile/test/` (444/444 passed 100%).
     - Flutter static analysis: 0 issues found (`flutter analyze`).
     - Monorepo regression suites: Backend (879/879 passed), Web (132/132 passed), Mobile (444/444 passed). **1,455 total automated tests passing 100%**. 0 Ruff issues, 0 Mypy issues, 0 Flutter analyzer issues.
- **Report**: [`docs/phase-reports/PHASE_11_MILESTONE_04_REPORT.md`](file:///Users/apple/Upostit/docs/phase-reports/PHASE_11_MILESTONE_04_REPORT.md)

## 12. Next Actions

1. **Current State**: Phase 11 Milestone 11.4 (Flutter Mobile: Enhanced Offline Queue & Resilient Sync Engine) is **ACCEPTED, REMEDIATED & FULLY VERIFIED** across the monorepo (879 backend tests, 444 Flutter tests, and 132 web tests passing, **1,455 total automated tests passing 100%** across the monorepo; 0 Ruff issues, 0 Mypy issues, 0 Flutter analyzer issues).
2. **Current Alembic Head**: `b5c6d7e8f9a0` (no backend database schema changes required for Phase 11.4; existing schema and mobile SQLite database v2 reused).
3. **Phase 11 Milestone Implementation Status (Approved 8-Milestone Sequence)**:
   - [x] **Milestone 11.1 — Offline-First Architecture Assessment, Gap Analysis & Implementation Blueprint**: Comprehensive scope audit, 19 technical dimensions analyzed, 8-milestone plan authored. (COMPLETED)
   - [x] **Milestone 11.2 — Backend Batch Sync Protocol & Timestamp Semantic Hardening**: `POST /attendance/sync/batch`, savepoint isolation, dual-tier idempotency, timestamp semantic hardening, zero synthetic break-end events, manager direct-report scoping, all 20 required scenarios verified, 25 tests. (COMPLETED & VERIFIED)
   - [x] **Milestone 11.3 — Downward Delta Sync Protocol (Reference Data & Shift Rosters)**: Server change tracking, composite keyset pagination v2, frozen session snapshot isolation, HMAC-SHA256 cursor security with fallback keys, 7 domain entities, mobile SQLite v2 schema upgrade with queue preservation invariant, atomic transactional application, coordinator mutex and self-healing. (COMPLETED & AUDITED)
   - [x] **Milestone 11.4 — Flutter Mobile: Enhanced SQLite Offline Queue & Resilient Sync Engine**: Unified synchronization coordinator, batch punch submission, partial-receipt reconciliation, monotonic stale-response protection, native Android WorkManager & iOS BGTaskScheduler background scheduling, resilient BLoC architecture, offline UX components. (COMPLETED, REMEDIATED & VERIFIED)
   - [ ] **Milestone 11.5 — Advanced Multi-Device Conflict Arbitration & Session Reconciliation**: Chronological session arbitration across concurrent devices, multi-device indicator metadata. (AWAITING AUTHORIZATION)
   - [ ] **Milestone 11.6 — Key Recovery, Tamper-Resistance & Eviction**: Keystore invalidation recovery, 30-day queue eviction maintenance. (PLANNED)
   - [ ] **Milestone 11.7 — End-to-End Simulation, Multi-Device Chaos Testing & Offline Ledger Integrity**: Chaos testing, battery dropouts, concurrent sync races, ledger integrity audits. (PLANNED)
   - [ ] **Milestone 11.8 — Security Audit, Penetration Testing & Formal Phase 11 Closure**: Security hardening, tamper resistance, replay attack testing, formal closure. (PLANNED)
4. **Execution Rules**:
   - Do NOT begin Milestone 11.5 without explicit user authorization.
   - Do NOT commit, tag, or push to git.
   - Preserve all existing user changes.



