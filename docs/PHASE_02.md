# PHASE 02 — Authentication & Multi-Tenant Foundation

**Stage**: Stage A — Foundation  
**Branch**: `phase-02`  
**Current Status**: Complete & 100% Verified Live on Supabase (Migration executed, tables created, RLS enabled & verified, bootstrap function verified, 34 automated tests passing).

---

## 1. Goal & Architectural Overview

Phase 2 establishes the multi-tenant SaaS foundation for the Attendance SaaS platform. It provides secure company registration, user authentication, role-based access control, session lifecycle management with refresh token rotation and reuse detection, and transaction-scoped PostgreSQL Row-Level Security (RLS).

Conceptually:

```text
Platform
  │
  ├── Company A (Tenant A)
  │     ├── Owner
  │     ├── Admin
  │     ├── HR
  │     ├── Manager
  │     └── Employees
  │
  └── Company B (Tenant B)
        ├── Owner
        ├── Admin
        ├── HR
        ├── Manager
        └── Employees
```

All companies share the same application and Supabase PostgreSQL database infrastructure, but tenant records are strictly isolated at both the application API layer and the PostgreSQL engine layer.

---

## 2. Multi-Tenant Architecture & Isolation Boundaries

1. **Shared Database, Shared Schema**: Multi-tenancy is enforced within a single PostgreSQL database. Every tenant-scoped table includes a foreign key `tenant_id UUID NOT NULL REFERENCES tenants(id)`.
2. **Token-Derived Tenant Identity**: Tenant context is extracted strictly from the cryptographically verified JWT access token claims (`tenant_id`, `sub`, `role`). Clients can never impersonate another tenant by providing a tenant ID in the request body, path, or headers.
3. **Database-Level Row-Level Security (RLS)**:
   - Every tenant transaction sets `SELECT set_config('app.tenant_id', :tenant_id, true)`.
   - The application runtime session sets `SET LOCAL ROLE authenticated`, ensuring the executing role lacks `rolbypassrls` privileges.
   - RLS policies filter and enforce `tenant_id = current_setting('app.tenant_id', true)::uuid` on every `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
4. **Registration Bootstrap**: New company registrations are handled atomically via a `SECURITY DEFINER` function `register_tenant_bootstrap` with fixed `search_path = public, pg_temp`, creating the tenant, initial owner, and initial session token without weakening table policies.

---

## 3. Database Schema

### A. `tenants` Table
Represents a registered company customer:
- `id`: UUID (Primary Key, default `gen_random_uuid()`)
- `name`: VARCHAR(255) NOT NULL
- `slug`: VARCHAR(100) NOT NULL UNIQUE (URL-friendly normalized identifier)
- `legal_name`: VARCHAR(255) NULL
- `industry`: VARCHAR(100) NULL
- `company_email`: VARCHAR(255) NOT NULL
- `company_phone`: VARCHAR(50) NULL
- `country_code`: VARCHAR(2) NOT NULL (ISO 2-letter uppercase)
- `timezone`: VARCHAR(50) NOT NULL (IANA timezone string, e.g. "UTC", "America/New_York")
- `status`: VARCHAR(20) NOT NULL DEFAULT 'active' (`active`, `suspended`, `pending`)
- `created_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
- `updated_at`: TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())

### B. `users` Table
Stores users belonging to a company:
- `id`: UUID (Primary Key)
- `tenant_id`: UUID NOT NULL REFERENCES `tenants(id)` ON DELETE RESTRICT
- `full_name`: VARCHAR(255) NOT NULL
- `email`: VARCHAR(255) NOT NULL (Normalized lowercase)
- `password_hash`: VARCHAR(255) NOT NULL (Argon2id)
- `role`: VARCHAR(20) NOT NULL DEFAULT 'employee' (`owner`, `admin`, `hr`, `manager`, `employee`)
- `status`: VARCHAR(20) NOT NULL DEFAULT 'active' (`active`, `inactive`, `suspended`)
- `email_verified_at`: TIMESTAMPTZ NULL
- `last_login_at`: TIMESTAMPTZ NULL
- `created_at`: TIMESTAMPTZ NOT NULL
- `updated_at`: TIMESTAMPTZ NOT NULL
- **Constraints**: `UNIQUE (tenant_id, email)` — User emails are unique per tenant.

### C. `refresh_tokens` Table
Tracks long-lived refresh token sessions with rotation and compromise detection:
- `id`: UUID (Primary Key)
- `tenant_id`: UUID NOT NULL REFERENCES `tenants(id)` ON DELETE CASCADE
- `user_id`: UUID NOT NULL REFERENCES `users(id)` ON DELETE CASCADE
- `token_hash`: VARCHAR(64) NOT NULL UNIQUE (SHA-256 hex digest of raw token)
- `family_id`: UUID NOT NULL (Identifies the token rotation lineage)
- `expires_at`: TIMESTAMPTZ NOT NULL (Default 7 days)
- `revoked_at`: TIMESTAMPTZ NULL
- `replaced_by_token_id`: UUID NULL REFERENCES `refresh_tokens(id)` ON DELETE SET NULL
- `created_at`: TIMESTAMPTZ NOT NULL
- `last_used_at`: TIMESTAMPTZ NULL

---

## 4. Cryptographic Security & Authentication System

### 4.1 Password Hashing (Argon2id)
- Algorithm: Argon2id (RFC 9106 recommended enterprise configuration).
- Parameters: `time_cost=2`, `memory_cost=19456` (19 MiB), `parallelism=1`, `hash_len=32`.
- Complexity Enforcement: Minimum 8 characters, maximum 128 characters, requires at least one uppercase letter, one lowercase letter, one digit, and one special symbol.

### 4.2 Short-Lived Access Tokens (JWT)
- Lifetime: 15 minutes.
- Algorithm: HMAC-SHA256 (`HS256`).
- Required Claims:
  - `sub`: User UUID string
  - `tenant_id`: Company tenant UUID string
  - `role`: User role (`owner`, `admin`, `hr`, `manager`, `employee`)
  - `jti`: Unique token UUID
  - `iss`: Issuer (`attendance-saas`)
  - `aud`: Audience (`attendance-app`)
  - `iat`: Issued at timestamp (UTC)
  - `exp`: Expiration timestamp (UTC)

### 4.3 Refresh Token Rotation & Reuse Detection
- Lifetime: 7 days.
- Format: Cryptographically secure random tokens (`secrets.token_urlsafe(32)`).
- Storage: SHA-256 hash stored in DB; raw token never persisted.
- **Rotation**: On every `/api/v1/auth/refresh` invocation, the old refresh token is marked `revoked_at = now()`, and a new refresh token is issued within the same `family_id`.
- **Reuse Detection**: If a revoked refresh token is presented, the system immediately revokes all tokens sharing that `family_id` to mitigate replay attacks.

---

## 5. Role-Based Access Control (RBAC)

Deny-by-default permission model with centralized definitions in `services/api/auth/permissions.py`:

| Permission | Owner | Admin | HR | Manager | Employee |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `VIEW_COMPANY_PROFILE` | **Yes** | **Yes** | **Yes** | **Yes** | No |
| `MANAGE_COMPANY_SETTINGS` | **Yes** | **Yes** | No | No | No |
| `MANAGE_USERS` | **Yes** | **Yes** | **Yes** | No | No |
| `ASSIGN_ROLES` | **Yes** | **Yes** | No | No | No |
| `VIEW_OWN_PROFILE` | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## 6. API Endpoints

All endpoints are versioned under `/api/v1`:

### Public Endpoints
- `POST /api/v1/auth/register-tenant`: Atomic registration of company and initial owner. Issues access & refresh tokens.
- `POST /api/v1/auth/login`: Authenticates user within tenant slug. Returns tokens.
- `POST /api/v1/auth/refresh`: Rotates refresh token (from JSON body or secure HTTP-only cookie). Returns new token pair.
- `POST /api/v1/auth/logout`: Revokes active refresh token and clears cookie.

### Protected Endpoints
- `GET /api/v1/auth/me`: Returns authenticated user and company profile.
- `POST /api/v1/auth/logout-all`: Revokes all active refresh sessions across all devices for current user.
- `GET /api/v1/tenants/current`: Returns authenticated tenant company metadata.

---

## 7. Migration & Database Roles

- **Migration Revision**: `4f61a7dd311e_phase_02_auth_and_multitenancy.py`
- **Tables Created**: `tenants`, `users`, `refresh_tokens`.
- **RLS Enabled**: Forced RLS on `tenants`, `users`, and `refresh_tokens`.
- **Roles Strategy**:
  - Migration role: `postgres` (or `MIGRATION_DATABASE_URL`) with DDL privileges.
  - Runtime application role: `authenticated` (or `RUNTIME_DATABASE_ROLE`) without `BYPASSRLS`.

---

## 8. Verification Results

| Suite | Description | Result | Details |
| :--- | :--- | :---: | :--- |
| `tests/test_auth_security.py` | Argon2id, JWT, expired token, signature tampering, token hashing | **PASS** | 7 passed |
| `tests/test_auth_schemas.py` | Registration validation, timezone, country codes, email normalization | **PASS** | 6 passed |
| `tests/test_rbac.py` | Role matrix, permissions registry, deny-by-default, privilege escalation | **PASS** | 7 passed |
| `tests/test_cross_tenant_isolation.py` | Tenant identity derivation, token tampering, parameter spoofing | **PASS** | 4 passed |
| `tests/test_auth_api.py` | API auth headers, missing token, expired token, validation failures | **PASS** | 6 passed |
| `tests/test_health.py` | Phase 1 health and readiness probes regression checks | **PASS** | 4 passed |
| `alembic upgrade head` | Live Supabase migration DDL & RLS policy application | **PASS** | Applied revision `4f61a7dd311e` |
| Live RLS Isolation Probe | Real cross-tenant query and cross-tenant insert isolation on Supabase | **PASS** | Blocked cross-tenant insert with RLS policy violation |
| Live Bootstrap Probe | Atomic `register_tenant_bootstrap` execution on Supabase | **PASS** | Successfully created tenant, owner, tokens |
| `make lint` | Ruff linter & Mypy static type checker | **PASS** | Clean across all 17 source files |
| **Total Test Suite** | Automated pytest execution | **PASS** | **34 passed in 7.08s** |

---

## 9. Final End-to-End API Journey Verification

Conducted focused HTTP API testing against the live Supabase database via the FastAPI application:

| Check | HTTP Request | Expected Status | Actual Status | Result | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Test A: Registration** | `POST /api/v1/auth/register-tenant` | 201 | 201 | **PASS** | Created company, owner, tokens; set HTTP-only cookie; zero secrets exposed. |
| **Test B: Login** | `POST /api/v1/auth/login` | 200 / 401 | 200 / 401 | **PASS** | Valid credentials issued token pair; bad passwords rejected with generic 401. |
| **Test C: User Profile** | `GET /api/v1/auth/me` | 200 | 200 | **PASS** | Returns authenticated owner matching tenant; no password/token hashes exposed. |
| **Test D: Current Tenant** | `GET /api/v1/tenants/current` | 200 | 200 | **PASS** | Verified company details; spoofed `X-Tenant-ID` header safely ignored. |
| **Test E: Token Rotation** | `POST /api/v1/auth/refresh` | 200 / 401 | 200 / 401 | **PASS** | Rotates token; old token reuse rejected with 401; entire family revoked upon reuse. |
| **Test F: Logout** | `POST /api/v1/auth/logout` | 200 / 401 | 200 / 401 | **PASS** | Active refresh session revoked; revoked token cannot refresh. |
| **Test G: Logout All** | `POST /api/v1/auth/logout-all` | 200 / 401 | 200 / 401 | **PASS** | Revoked all concurrent device sessions for user; subsequent refresh rejected with 401. |
| **Test H: Cross-Tenant** | Cross-tenant API requests | 200 / 401 | 200 / 401 | **PASS** | Tenant A only accesses Tenant A; Tenant B only accesses Tenant B. |
| **Cleanup Verification** | SQL deletion of test records | 0 remaining | 0 remaining | **PASS** | All synthetic tenants, users, and tokens cleaned up from Supabase. |

