# RULES.md — Engineering Rules and Standards

This document defines the strict engineering, architectural, multi-tenancy, and security rules for the Attendance SaaS project. Every developer and AI coding agent must adhere to these rules without exception.

---

## 1. Technology Stack

| Layer | Technology | Purpose & Architectural Notes |
| :--- | :--- | :--- |
| **Web Dashboard** | Next.js 14+ (App Router) + TypeScript | Admin, HR, Manager, and Billing portals. |
| **Mobile App** | **Flutter (Android & iOS) + Dart** | Employee check-in, GPS geofencing, selfie liveness, offline queue. Maintainable feature-based architecture. |
| **Backend API** | Python 3.12 + FastAPI | Modular monolith with Pydantic v2, SQLAlchemy 2 (async with asyncpg), and Alembic. |
| **Database** | PostgreSQL 16 + PostGIS (via Supabase) | Primary source of truth, Row-Level Security (RLS), spatial calculations. Single database instance; no second local PostgreSQL container. |
| **Cache & Queues** | Redis 7+ & Celery | Per-tenant rate limiting, short-lived entitlement caches, async worker tasks. |
| **File Storage** | S3-Compatible / MinIO / Supabase Storage | Check-in selfies, exported reports, payslips; path prefixed with `tenant_id`. |
| **Delivery & CI/CD**| Docker Compose (Redis + MinIO), GitHub Actions | Automated linting, type-checking, pytest, and Vitest runs. |
| **Monitoring** | Sentry + OpenTelemetry | Distributed tracing, error tracking, and performance monitoring (Phase 13). |

---

## 2. Core Architecture Rules

1. **Modular Monolith**: One unified FastAPI application structured into domain modules (`auth`, `tenants`, `employees`, `attendance`, `fraud`, `leave`, `billing`, `payroll`). No premature microservices.
2. **Mobile Architecture (Flutter)**:
   - Built with Flutter for Android and iOS using Dart.
   - Clean, feature-based project structure under `apps/mobile/` (`features/`, `core/`, `shared/`).
   - Environment-based API configuration pointing to FastAPI base URL.
   - Offline queue using local encrypted storage (e.g. Hive/sqflite/flutter_secure_storage) with idempotency keys.
   - No React Native, Expo, or WebView.
3. **Edge Gateway Isolation**: The edge gateway (`services/edge`, Phase 16) is the only separate standalone service, interfacing on-premise CCTV cameras and biometric terminals.
4. **UTC Everywhere**: All timestamps are stored strictly in UTC (`TIMESTAMPTZ`). Conversion to the tenant's local time zone occurs solely at the presentation and shift-rule evaluation layers.
5. **Append-Only Attendance Events**: `attendance_events` is an immutable, append-only ledger (`IN`, `OUT`, `BREAK_START`, `BREAK_END`). Attendance corrections never mutate or delete historical event rows; they append compensating events.
6. **Server Time Authority**: The authoritative punch timestamp is determined by the server upon receipt. The client device timestamp is stored purely for drift and fraud analysis.
7. **Client-Generated Idempotency Keys**: Every punch payload must include a client-generated UUID (`client_event_id`). Repeated transmissions with identical keys return identical results without duplicating events.
8. **Cache is Never the Source of Truth**: Redis is strictly a performance acceleration and rate-limiting tier. All persistent state resides in Supabase PostgreSQL.
9. **Cursor Pagination Mandatory**: Every list endpoint must implement cursor-based pagination. Unbounded queries (`SELECT *` without limits) are strictly forbidden.

---

## 3. Multi-Tenancy & Data Isolation Rules

1. **Shared Database Architecture**: Multi-tenancy is enforced within a single shared Supabase PostgreSQL database. Every tenant-scoped table must include `tenant_id UUID NOT NULL`.
2. **Token-Derived Tenant Identity**: The active `tenant_id` must be extracted exclusively from the cryptographically verified JWT access token. It must never be accepted from request parameters, path variables, or body payloads.
3. **Non-Superuser Application Role**: The API database user operates under a dedicated non-superuser role without `BYPASSRLS` privileges.
4. **Per-Request Transaction Context**: Every database transaction executes `SET LOCAL app.tenant_id = :tenant_id` before running queries, ensuring safe connection pooling across requests.
5. **Mandatory Row-Level Security (RLS)**:
   ```sql
   ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
   ALTER TABLE employees FORCE ROW LEVEL SECURITY;

   CREATE POLICY tenant_isolation ON employees
     USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
     WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
   ```
6. **Tenant-Prefixed External Keys**: Redis cache keys, object storage paths, and rate-limiting counters must always be prefixed with the `tenant_id` (e.g., `tenant:{tenant_id}:rate:...`, `/{tenant_id}/selfies/...`).
7. **Automated Cross-Tenant Leak Tests**: The test suite must assert that Tenant A cannot access, modify, or infer data belonging to Tenant B under any circumstance. CI fails if any table containing `tenant_id` lacks active RLS.

---

## 4. Security & Compliance Rules

1. **Password Hashing**: Passwords must be hashed using Argon2id.
2. **Token Lifecycle**: Short-lived JWT access tokens (15 minutes) paired with cryptographically secure, rotating refresh tokens stored in the database.
3. **Server-Side Authorization**: Role-based access control (RBAC) and plan feature entitlements must be verified server-side on every request. Client-side UI gating is cosmetic only.
4. **Standard Error Schema**: All API errors adhere to a uniform JSON structure with a unique `request_id`, error code, and sanitized error message.
5. **Rate Limiting**: Enforced at the gateway/middleware level per IP and per tenant using Redis token buckets.
6. **Biometric & Selfie Privacy**: Storage of check-in selfies and biometric templates requires verifiable employee consent, tenant-configurable retention policies, and hard deletion workflows.
7. **Zero Secrets in Repository**: Secrets must never be committed. All configuration must be injected via environment variables following the 12-factor application methodology.
