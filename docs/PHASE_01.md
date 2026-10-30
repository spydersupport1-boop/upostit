# PHASE 01 — Project Setup & Monorepo Foundation

**Stage**: Stage A — Foundation  
**Branch**: `phase-01`  
**Current Status**: In Progress  

---

## 1. Goal

Establish a robust, standardized monorepo foundation, master project documentation, development toolchain, containerized local services (Redis & MinIO), Supabase PostgreSQL database integration, Next.js web shell, and Flutter mobile starter that every subsequent phase builds upon.

---

## 2. Scope & Deliverables

1. **Master Project Documentation**:
   - `PROJECT_CONTEXT.md` maintained at root as the single source of truth.
   - `docs/RULES.md` defining strict architecture, Flutter mobile standards, and Supabase RLS policies.
   - `docs/ARCHITECTURE.md` detailing system design: Flutter → FastAPI → Supabase PostgreSQL.
   - `docs/PHASE_01.md` tracking phase execution and acceptance verification.
   - `README.md` providing onboarding instructions, setup guides, and Flutter requirements.
2. **Monorepo Directory Layout**:
   - `apps/web`: Next.js 14+ TypeScript dashboard starter.
   - `apps/mobile`: **Flutter (Dart)** cross-platform mobile application starter.
   - `services/api`: FastAPI modular monolith application skeleton with `/health` and `/ready` probes.
   - `services/workers`: Celery worker task runner skeleton with smoke test.
   - `services/edge`: Edge gateway skeleton (Phase 16 placeholder).
   - `packages/contracts`: Shared schemas and interfaces.
   - `database/migrations`: Alembic migration configuration targeting Supabase PostgreSQL.
   - `infra`: Docker Compose setup strictly for Redis and MinIO (no duplicate PostgreSQL container).
   - `tests`: Test scaffolding for backend API, Celery smoke test, and cross-cutting checks.
3. **Supabase Database Integration**:
   - Asynchronous connection via SQLAlchemy 2 + `asyncpg`.
   - Safe connectivity verification script (`SELECT 1`).
   - PostGIS capability probe (`SELECT postgis_full_version();`).
   - Zero modifications, drops, or speculative tables in Phase 1.
4. **Developer Tooling & CI/CD**:
   - Standardized `Makefile` supporting `make up`, `make down`, `make test`, and `make lint`.
   - `.env.example` defining all required configuration variables using safe dummy values.
   - `.gitignore` preventing secrets, virtual environments, and build artifacts from entering Git.
   - GitHub Actions workflow (`.github/workflows/ci.yml`) executing linting, type-checking, dependency scans, secret scans, and automated tests.

---

## 3. Definition of Done & Acceptance Criteria

- [x] Git repository initialized.
- [x] Root-level `PROJECT_CONTEXT.md` created and updated with all 12 mandatory sections.
- [x] Architectural decisions updated: Flutter selected as mobile framework; Supabase PostgreSQL as sole database.
- [x] 22-phase progress tracker preserved and initialized.
- [x] Strict exclusion of database credentials, access tokens, and secrets verified.
- [x] `.gitignore` established to prevent `.env`, `.venv`, and build files from being tracked.
- [x] `docs/RULES.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_01.md`, and `PROJECT_CONTEXT.md` are in complete agreement.
- [x] Monorepo directory skeleton created.
- [x] FastAPI application implemented with `/health` and `/ready` endpoints.
- [x] Safe Supabase database connectivity test script implemented.
- [x] Next.js responsive web shell created under `apps/web/`.
- [x] Flutter mobile starter created under `apps/mobile/` with responsive welcome screen and configurable API URL.
- [x] Docker Compose configured for Redis and MinIO only (no local PostgreSQL).
- [x] Celery worker skeleton and smoke test implemented.
- [x] Alembic migration configuration initialized.
- [x] `.env.example` and `Makefile` created.
- [x] GitHub Actions workflow created for lint, type checks, tests, and security scans.

---

## 4. Current Implementation Status

- **Status**: AUDITED & CONDITIONALLY READY FOR PHASE 2 (Core Phase 1 criteria passed; Docker and Flutter container/binary execution blocked on host environment tooling).
- **Mobile Framework**: Flutter (Dart) selected; feature-based starter shell initialized under `apps/mobile/` with welcome screen, accessible controls, and configurable API URL.
- **Supabase PostgreSQL Status**: TESTED & VERIFIED (Direct asyncpg connection passed with safe `SELECT 1`).
- **PostGIS Status**: TESTED & VERIFIED (PostGIS extension enabled and operational for spatial geofencing).
- **Web Dashboard**: TESTED & VERIFIED (Next.js 14 production build and ESLint passed cleanly with static prerendering).

---

## 5. Phase 1 Verification & Audit Results

| Verification Area | Command Executed | Result | Exact Evidence / Log |
| :--- | :--- | :--- | :--- |
| **Git Repository** | `git status --short`, `git log -5` | **PASS** | Clean working tree, untracked `.env` strictly ignored (`.gitignore:2:.env`). |
| **Secret Protection** | `git ls-files --error-unmatch .env` | **PASS** | Exit code 1; `.env` is not tracked by Git. No secrets leaked. |
| **Supabase REST API** | `make verify-db` (Step 1) | **PASS** | Endpoint reachable, HTTP 200 OK for project `qnkgndfzuhrjuopzlcxy`. |
| **Direct PostgreSQL** | `make verify-db` (Step 2) | **PASS** | Safe `SELECT 1` query succeeded via SQLAlchemy 2 asyncpg. |
| **PostGIS Extension** | `make verify-db` (Step 3) | **PASS** | `SELECT postgis_full_version();` succeeded. PostGIS operational. |
| **Backend Unit Tests**| `make test` (`pytest tests/ -v`) | **PASS** | 4 passed in 5.70s (0 failed, 0 skipped). |
| **Code Linting** | `make lint` (`ruff check`) | **PASS** | `All checks passed!` across services, packages, tests. |
| **Type Checking** | `make lint` (`mypy services/api/`) | **PASS** | `Success: no issues found in 5 source files`. |
| **FastAPI Probes** | Live ASGI probe `/health` & `/ready` | **PASS** | `/health` returned 200 OK; `/ready` returned 200 OK with `database: connected`, `postgis: PostGIS available`. |
| **Celery Smoke Test** | `make celery-smoke` | **PASS** | App initialized, `attendance.ping` registered, direct execution returned `'pong'`. |
| **Celery Broker/Worker**| Live connection to `REDIS_URL` | **BLOCKED** | Docker is not installed on host machine; local Redis broker container not running. |
| **Web Compilation** | `npm run build` in `apps/web/` | **PASS** | Next.js 14.2.5 compiled successfully; static pages generated (4/4). |
| **Web Linting** | `npm run lint` in `apps/web/` | **PASS** | `✔ No ESLint warnings or errors`. |
| **Web Type-Check** | `npx tsc --noEmit` in `apps/web/` | **PASS** | Exited code 0; zero type errors. |
| **Flutter Binary Check**| `which flutter`, `which dart` | **BLOCKED** | `flutter` and `dart` not installed on host macOS (`brew install --cask flutter` needed). |
| **Flutter Mobile Code**| Code inspection `apps/mobile/` | **PASS** | Valid entry point, welcome screen, compile-time `--dart-define=API_BASE_URL`, real widget test. |
| **Docker Infrastructure**| `which docker`, `which docker-compose` | **BLOCKED** | `docker` not installed on host macOS; running Redis/MinIO containers blocked locally. |
| **Alembic Migrations**| `alembic current` & `heads` | **PASS** | Loaded root configuration and PostgreSQL migration environment cleanly (`PostgresqlImpl`). |
| **CI Workflow** | Python YAML syntax check | **PASS** | Valid YAML; 4 jobs configured: `backend-checks`, `web-checks`, `mobile-checks`, `security-scans`. |
