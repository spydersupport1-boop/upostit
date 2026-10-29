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

- **Status**: IMPLEMENTED (All Phase 1 acceptance criteria met; awaiting owner approval for Phase 2).
- **Mobile Framework**: Flutter (Dart) selected and starter shell initialized under `apps/mobile/`.
- **Supabase PostgreSQL Status**: TESTED & VERIFIED (Direct asyncpg connection passed with safe `SELECT 1`).
- **PostGIS Status**: TESTED & VERIFIED (PostGIS extension enabled and operational for spatial geofencing).
