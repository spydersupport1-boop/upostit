# Attendance SaaS — Enterprise Attendance & Workforce Management

A modern, multi-tenant Attendance and Workforce Management platform featuring fraud prevention (selfie liveness, mock-GPS detection, device binding), PostGIS spatial geofencing, and automated attendance-to-payroll workflows.

---

## 1. System Architecture

```text
[ Flutter Mobile App (iOS & Android) ]  ───┐
                                          ├───▶ [ FastAPI Modular Monolith ] ───▶ [ Supabase PostgreSQL 16 + PostGIS ]
[ Next.js 14+ Web Dashboard ]           ───┘            │
                                                        ├───▶ [ Redis 7+ Cache & Rate Limiting ]
                                                        ├───▶ [ Celery Background Workers ]
                                                        └───▶ [ MinIO / S3 Object Storage ]
```

---

## 2. Monorepo Structure

```text
.
├── apps/
│   ├── web/                # Next.js 14+ TypeScript administrative dashboard
│   └── mobile/             # Flutter (Dart) mobile application for Android & iOS
├── services/
│   ├── api/                # FastAPI modular monolith application
│   ├── workers/            # Celery asynchronous background tasks
│   └── edge/               # On-premise CCTV / Biometric hardware edge gateway (Phase 16)
├── packages/
│   └── contracts/          # Shared Pydantic / OpenAPI schema models
├── database/
│   └── migrations/         # Alembic database migration revisions targeting Supabase
├── infra/                  # Docker Compose (Redis & MinIO only), Nginx, PgBouncer
├── tests/                  # Cross-cutting integration, security, and load tests
├── docs/                   # Engineering standards (RULES.md, ARCHITECTURE.md, PHASE_*.md)
├── PROJECT_CONTEXT.md      # Master Project Documentation & 22-Phase Tracker
├── Makefile                # Standardized developer commands
└── .env.example            # Environment variable template with safe placeholders
```

---

## 3. Prerequisites & Toolchain

- **Python**: `>= 3.12` (Host currently running Python 3.13)
- **Node.js**: `>= 20.0.0` (Host currently running Node.js v24.21.0, npm 11.19.0)
- **Flutter SDK**: `>= 3.19.0` (Dart `>= 3.3.0`)
  - Install via Homebrew: `brew install --cask flutter`
  - Or download directly from [Flutter Official Website](https://docs.flutter.dev/get-started/install/macos).
- **Docker & Docker Compose**: Used for local Redis and MinIO services.
- **Supabase Account**: A Supabase PostgreSQL database project with PostGIS extension enabled.

---

## 4. Getting Started

### 4.1 Environment Configuration
Copy the template environment file and provide your project variables:
```bash
cp .env.example .env
```
Edit `.env` to supply your Supabase connection string:
```bash
# In .env (never commit this file)
DATABASE_URL=postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
```

### 4.2 Start Supporting Services (Redis & MinIO)
```bash
make up
```
*Note: Docker Compose only runs Redis and MinIO. It does NOT start a local PostgreSQL container, as Supabase is the primary database.*

### 4.3 Backend API (FastAPI)
Activate the virtual environment and start the development server:
```bash
source .venv/bin/activate
pip install -r services/api/requirements.txt
uvicorn services.api.main:app --reload --port 8000
```
- API Health Check: `http://localhost:8000/health`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

### 4.4 Supabase Connectivity & PostGIS Verification
Run the safe read-only database connectivity test:
```bash
python services/api/verify_db.py
```

### 4.5 Web Dashboard (Next.js)
```bash
cd apps/web
npm install
npm run dev
```
Access the dashboard at `http://localhost:3000`.

### 4.6 Mobile Application (Flutter)
```bash
cd apps/mobile

# Install Dart/Flutter dependencies
flutter pub get

# Run on Web (for rapid UI development)
flutter run -d chrome

# Run on Android Device / Emulator
flutter run -d android --dart-define=API_BASE_URL=http://10.0.2.2:8000

# Run on iOS Simulator
flutter run -d ios --dart-define=API_BASE_URL=http://localhost:8000
```

---

## 5. Testing & Quality Checks

Run all automated checks across the monorepo:
```bash
# Run pytest tests
make test

# Run linting across Python and Web
make lint
```

---

## 6. Engineering Standards & Documentation

Before making any changes, review:
- [`PROJECT_CONTEXT.md`](file:///Users/apple/Upostit/PROJECT_CONTEXT.md): Current phase status, 22-phase tracker, and change log.
- [`docs/RULES.md`](file:///Users/apple/Upostit/docs/RULES.md): Architecture, multi-tenancy, and security guidelines.
- [`docs/ARCHITECTURE.md`](file:///Users/apple/Upostit/docs/ARCHITECTURE.md): Detailed system design and component diagrams.
- [`docs/PHASE_01.md`](file:///Users/apple/Upostit/docs/PHASE_01.md): Phase 1 definition of done and execution tracking.
