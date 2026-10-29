# PHASE 01 — Project Setup & Monorepo Foundation

**Stage**: Stage A — Foundation  
**Branch**: `phase-01`  
**Current Status**: In Progress  

---

## 1. Goal

Establish a robust, standardized monorepo foundation, master project documentation, development toolchain, and containerized local infrastructure that every subsequent phase builds upon.

---

## 2. Scope & Deliverables

1. **Master Project Documentation**:
   - `PROJECT_CONTEXT.md` created at root as the single source of truth.
   - `docs/RULES.md` defining strict architecture, multi-tenancy, and security guidelines.
   - `docs/ARCHITECTURE.md` outlining system design, component boundaries, and data flows.
   - `docs/PHASE_01.md` tracking phase execution and acceptance verification.
2. **Monorepo Directory Layout**:
   - `apps/web`: Next.js 14+ TypeScript dashboard starter.
   - `apps/mobile`: React Native (Expo) employee app starter.
   - `services/api`: FastAPI modular monolith skeleton.
   - `services/workers`: Celery worker task runner skeleton.
   - `services/edge`: Edge gateway skeleton (Phase 16 placeholder).
   - `packages/contracts`: Shared schemas and interfaces.
   - `database/migrations`: Alembic migration configuration.
   - `infra`: Docker Compose setup with PostgreSQL (PostGIS), Redis, and MinIO.
   - `tests`: Test scaffolding for unit, integration, and cross-tenant testing.
3. **Core Services & API**:
   - FastAPI application instance with `GET /health` endpoint verifying database and Redis connectivity.
   - Interactive OpenAPI documentation at `/docs` and `/redoc`.
4. **Developer Tooling & CI/CD**:
   - Standardized `Makefile` supporting `make up`, `make down`, `make test`, and `make lint`.
   - `.env.example` defining all required configuration variables using safe dummy values.
   - GitHub Actions workflow (`.github/workflows/ci.yml`) executing linting, type-checking, and automated tests.

---

## 3. Definition of Done & Acceptance Criteria

- [x] Git repository initialized.
- [x] Root-level `PROJECT_CONTEXT.md` created with all 12 mandatory sections.
- [x] Initial project status accurately reflects the repository state.
- [x] 22-phase progress tracker initialized.
- [x] Supabase connection status recorded as "Not yet verified" (credentials pending from owner).
- [x] Strict exclusion of database credentials, access tokens, and secrets verified.
- [x] `docs/RULES.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_01.md`, and `PROJECT_CONTEXT.md` are in complete agreement.
- [ ] Monorepo directory skeleton populated with standard service starter files.
- [ ] Docker Compose environment boots locally with `make up`.
- [ ] `GET /health` endpoint responds with 200 OK and reports subsystem health.
- [ ] CI pipeline configuration validated on clean clone.

---

## 4. Current Implementation Status

- **Status**: IN PROGRESS (Documentation baseline and master governance established; monorepo scaffolding pending next phase-01 execution step).
- **Supabase PostgreSQL Status**: NOT YET VERIFIED (Awaiting project URL and connection parameters).
- **PostGIS Status**: NOT YET VERIFIED.
