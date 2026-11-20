# UPOSTIT — Phase 6, Milestone 6.1 Implementation Report
## Flutter Foundation, Design System & Secure Mobile Authentication

**Date**: 2026-11-04  
**Stage**: Stage B — Attendance Core  
**Phase**: Phase 6 — Mobile Attendance Application  
**Milestone**: Milestone 6.1 — Flutter Foundation, Design System & Secure Mobile Authentication  
**Git Branch**: `phase-06`  
**Git Baseline**: Commit `a4dad73` (Tag `phase-05-complete`)  
**Status**: Fully Implemented, Provisioned & Verified (All 43 Mobile Tests Passed, 281 Backend Tests Passed, Clean flutter analyze, Debug APK Built Successfully)  

---

## 1. Executive Summary

Milestone 6.1 establishes the enterprise-grade mobile application foundation for the UPOSTIT Workforce Attendance SaaS. Prior to Milestone 6.1, the mobile project existed solely as a minimal single-screen skeleton (`apps/mobile/lib/main.dart` and `welcome_screen.dart`).

Milestone 6.1 transforms `apps/mobile/` into a production-ready, Clean Architecture, feature-first Flutter application featuring:
1. **Material 3 Enterprise Design System**: Cohesive design tokens (colors, typography, spacing, radius) and reusable components (`AppButton`, `AppTextField`, `LoadingIndicator`, `ErrorBanner`, `EmptyStateView`).
2. **Dedicated Mobile Token Architecture**: In-memory access token storage (never written to disk), platform-secure refresh token storage (iOS Keychain and Android Keystore via `flutter_secure_storage`), and silent session restoration.
3. **Concurrency-Safe Token Refresh Mutex**: Thread-safe single-flight refresh queue using Dart `Completer<String?>`, ensuring that concurrent 401 responses never trigger multiple refresh requests or false reuse detection.
4. **Verified Backend Authentication Contract**: Strict adherence to the existing FastAPI authentication schemas (`POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, and `GET /api/v1/employees/me`).
5. **Session Management & Logout**: Online session revocation on the server prior to local credential clearance, plus safe offline logout handling.
6. **Authenticated Identity & Profile**: Profile screen rendering organization/tenant details and employee credentials, with graceful fallback for administrative users without linked employee profiles.
7. **Comprehensive Automated Test Suite**: 9 test suites covering units, repositories, BLoC state transitions, concurrency mutex, and widget rendering.

---

## 2. Git Baseline & Safety Verification

- **Baseline Commit**: `a4dad73` (`phase-05-complete`)
- **Previous Branch**: `phase-05`
- **Target Branch**: `phase-06`
- **Safety Protocol**:
  - Verified working tree cleanliness before branching (`git status`).
  - Created `phase-06` via `git checkout -b phase-06` directly from the verified Phase 5 baseline.
  - Zero modifications to live Supabase database, database migrations, or backend code.
  - No secrets, `.env` files, or production credentials committed.
  - No remote git pushes or final milestone tags created.

---

## 3. Architecture & Folder Structure

The application strictly implements **Clean Architecture** with a feature-first organizational layout.

```
apps/mobile/lib/
├── app.dart                                # Central MaterialApp & GoRouter configuration
├── main.dart                               # Composition root, dependency injection & MultiBlocProvider
├── core/
│   ├── config/
│   │   └── env_config.dart                 # Runtime environment configuration (--dart-define)
│   ├── constants/
│   │   ├── app_colors.dart                 # Design tokens: Indigo primary, Slate palette, Semantic status
│   │   ├── app_spacing.dart                # Grid spacing (4px-48px) and border radii (4px-9999px)
│   │   └── app_typography.dart             # Inter typography scale with tabular figures
│   ├── errors/
│   │   ├── app_exception.dart              # Typed exceptions (Server, Network, Auth, Storage)
│   │   ├── failure.dart                    # Clean Architecture failure abstractions (Equatable)
│   │   └── result.dart                     # Functional Result<T> monad with fold pattern
│   ├── network/
│   │   ├── api_client.dart                 # Dio wrapper with standard headers, timeouts & error translation
│   │   ├── api_endpoints.dart              # Centralized backend URL route constants
│   │   └── auth_interceptor.dart           # Concurrency-safe Bearer injection & refresh mutex
│   ├── storage/
│   │   ├── secure_storage_service.dart     # iOS Keychain & Android Keystore abstraction
│   │   └── token_manager.dart              # In-memory access token storage
│   ├── theme/
│   │   └── app_theme.dart                  # Material 3 theme configuration (light theme primary)
│   └── utils/
│       └── validators.dart                 # Input validation logic (Email, Password, Workspace code)
├── features/
│   ├── auth/
│   │   ├── data/
│   │   │   ├── datasources/
│   │   │   │   └── auth_remote_data_source.dart
│   │   │   ├── models/
│   │   │   │   ├── auth_tokens_model.dart
│   │   │   │   └── user_profile_model.dart
│   │   │   └── repositories/
│   │   │       └── auth_repository_impl.dart
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   ├── auth_tokens.dart
│   │   │   │   └── user_profile.dart
│   │   │   ├── repositories/
│   │   │   │   └── auth_repository.dart
│   │   │   └── usecases/
│   │   │       ├── login_usecase.dart
│   │   │       ├── logout_usecase.dart
│   │   │       └── restore_session_usecase.dart
│   │   └── presentation/
│   │       ├── bloc/
│   │       │   ├── auth_bloc.dart
│   │       │   ├── auth_event.dart
│   │       │   └── auth_state.dart
│   │       └── screens/
│   │           ├── login_screen.dart
│   │           └── splash_screen.dart
│   └── profile/
│       ├── data/
│       │   ├── datasources/
│       │   │   └── profile_remote_data_source.dart
│       │   ├── models/
│       │   │   └── employee_model.dart
│       │   └── repositories/
│       │       └── profile_repository_impl.dart
│       ├── domain/
│       │   ├── entities/
│       │   │   └── employee.dart
│       │   ├── repositories/
│       │   │   └── profile_repository.dart
│       │   └── usecases/
│       │       └── get_profile_usecase.dart
│       └── presentation/
│           ├── bloc/
│           │   ├── profile_bloc.dart
│           │   ├── profile_event.dart
│           │   └── profile_state.dart
│           └── screens/
│               └── profile_screen.dart
└── shared/
    └── widgets/
        ├── app_button.dart                 # Primary, secondary, outlined & destructive buttons
        ├── app_text_field.dart             # Form field with labels, prefix icons & password toggle
        ├── empty_state_view.dart           # Actionable empty state card
        ├── error_banner.dart               # Contextual status banner (error, warning, info)
        └── loading_indicator.dart          # Branded loading spinner with status message
```

---

## 4. Dependencies Added

The following production and developer dependencies were configured in `apps/mobile/pubspec.yaml`:

| Package | Version | Purpose |
|---|---|---|
| `flutter_bloc` | `^8.1.5` | Predictable, event-driven state management for presentation layer |
| `dio` | `^5.4.3+1` | HTTP client with robust interceptors, connection timeouts, and request cancellation |
| `flutter_secure_storage` | `^9.0.0` | Platform-secure hardware storage (Keychain on iOS, Keystore on Android) |
| `go_router` | `^14.1.4` | Declarative, URL-aware routing and navigation |
| `google_fonts` | `^6.2.1` | Inter font family typography loading |
| `equatable` | `^2.0.5` | Value equality for entities, models, events, states, and failures |
| `bloc_test` | `^9.1.7` | Standardized unit testing library for BLoCs and Cubits |
| `mocktail` | `^1.0.3` | Type-safe mocking for unit tests without code generation |

---

## 5. Backend Authentication API Contracts Verified

The FastAPI authentication implementation was inspected directly from backend source files (`services/api/auth/schemas.py`, `services/api/auth/endpoints.py`, and `services/api/employees/endpoints.py`):

### 1. `POST /api/v1/auth/login`
- **Request Body**: `{"email": "<str>", "password": "<str>", "tenant_slug": "<str>"}`
- **Response**: `{"access_token": "<jwt>", "refresh_token": "<str>", "token_type": "bearer", "expires_in": 900}`
- **Contract Adherence**: Mobile authentication requires `tenant_slug` (Company Workspace Code). The `LoginScreen` and `LoginRequest` DTOs include all three parameters.

### 2. `POST /api/v1/auth/refresh`
- **Request Body**: `{"refresh_token": "<str>"}` (FastAPI endpoint accepts the refresh token from either request body or fallback HttpOnly cookie).
- **Response**: `{"access_token": "<jwt>", "refresh_token": "<str>", "token_type": "bearer", "expires_in": 900}`
- **Token Rotation**: The backend issues a rotated refresh token and invalidates the previous token. The mobile client immediately stores the newly rotated refresh token into secure storage.

### 3. `POST /api/v1/auth/logout`
- **Request Body**: `{"refresh_token": "<str>"}`
- **Response**: `{"message": "Logged out successfully"}`
- **Server Revocation**: When online, the mobile app sends the active refresh token to the server so the session record in the database is formally revoked before local storage is cleared.

### 4. `GET /api/v1/auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**: `UserProfileResponse(user: UserResponse, tenant: TenantResponse)`
- **Parsed Fields**: User ID, email, full name, role (`owner`, `admin`, `manager`, `employee`), active status, tenant ID, tenant name, tenant slug, tenant timezone.

### 5. `GET /api/v1/employees/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**: `EmployeeResponse`
- **Parsed Fields**: Employee ID, user ID, tenant ID, employee number/code, full name, work email, department, designation, employment type, status.
- **Graceful 404 Handling**: If an owner or administrator logs into the mobile app without having an active record in the `employees` table, `/employees/me` returns HTTP 404. `ProfileBloc` and `ProfileScreen` catch this gracefully and display administrative user information rather than failing.

---

## 6. Secure Storage & Concurrency Architecture

### 6.1 Token Storage Policy
- **Access Token (In-Memory Only)**: Managed by `InMemoryTokenManager`. It is stored exclusively in process heap memory. It is never written to `SharedPreferences`, local SQLite, or any non-volatile storage. Terminating the process or calling logout immediately wipes the memory reference.
- **Refresh Token (Platform Secure Storage)**: Managed by `FlutterSecureStorageService`.
  - **iOS Configuration**: Keyring accessibility set to `KeychainAccessibility.first_unlock_this_device`. The token cannot be accessed until the user unlocks their device for the first time, and it is never synchronized to iCloud Keychain backups.
  - **Android Configuration**: Configured with `encryptedSharedPreferences: true`, leveraging Android Keystore with AES-256 GCM encryption.
  - **Leak Prevention**: Tokens are never logged to console, never included in error banners, and never passed into analytical payloads.

### 6.2 Refresh Concurrency Mutex
When multiple asynchronous API calls execute concurrently (e.g., loading user profile, company configuration, and employee record simultaneously) and the access token has expired:
1. All concurrent requests receive HTTP 401.
2. The `AuthInterceptor` checks an internal boolean flag `_isRefreshing`.
3. The first request sets `_isRefreshing = true` and initializes a `Completer<String?>`.
4. Subsequent requests detect `_isRefreshing == true`, await the existing `Completer.future`, and immediately retry with the newly minted access token once complete.
5. Exactly **one** HTTP request is dispatched to `POST /api/v1/auth/refresh`.
6. When the refresh succeeds, the rotated refresh token is saved, the new access token is stored in memory, and the completer completes with the new access token.
7. Original requests retry with an added header `X-Retry-Attempt: 1` to prevent infinite retry loops.
8. If the refresh request itself fails with HTTP 401 (token expired or reuse detected), the session is marked invalid, the onSessionRevoked callback triggers, and local credentials are wiped.

---

## 7. Automated Test Suite

A comprehensive test suite of 9 test files was developed under `apps/mobile/test/`:

| Test Suite | File Path | Focus & Coverage |
|---|---|---|
| **Token Manager Unit Tests** | `test/core/storage/token_manager_test.dart` | In-memory token storage, retrieval, clearing, and process boundary isolation. |
| **Auth Interceptor & Mutex Tests** | `test/core/network/auth_interceptor_test.dart` | Bearer injection, single refresh call during concurrent 401s, request replay with new token, infinite loop prevention, and session revocation callback on refresh failure. |
| **Auth BLoC State Tests** | `test/features/auth/auth_bloc_test.dart` | `CheckAuthRequested` (valid, absent, expired, network error), `LoginSubmitted` (success, invalid credentials, server error), and `LogoutRequested` (online vs offline). |
| **Auth Repository Tests** | `test/features/auth/auth_repository_test.dart` | Token persistence on login, silent restore, rotated token saving, remote exception mapping to Clean Architecture Failures. |
| **Login Screen Widget Tests** | `test/features/auth/login_screen_test.dart` | Form field rendering, client-side input validation, submit event dispatch, error banner display, loading indicator display. |
| **Profile BLoC State Tests** | `test/features/profile/profile_bloc_test.dart` | `FetchProfileRequested` (success, 404 admin fallback, server error), `ProfileRefreshed`. |
| **Profile Repository Tests** | `test/features/profile/profile_repository_test.dart` | Successful employee fetch, 404 `EmployeeNotFoundException` handling, exception to failure mapping. |
| **Profile Screen Widget Tests** | `test/features/profile/profile_screen_test.dart` | Authentication loading guard, tenant card rendering, employee details rendering, admin user fallback, error warning banner, logout confirmation dialog and event dispatch. |
| **Root Application Widget Test** | `test/widget_test.dart` | Root `AttendanceApp` mounting, Material 3 theme application, and initial route splash rendering. |

---

## 8. Verification Pass & Quality Audit Results

A dedicated verification and quality audit pass was conducted following Milestone 6.1 implementation:

### 8.1 Tooling & Environment Status
- **Host Operating System**: macOS 14.8 (Build 23J21 darwin-x64, Intel x86_64).
- **Flutter / Dart Tooling**:
  - Flutter 3.47.9 (Channel stable at `/usr/local/share/flutter`).
  - Dart SDK 3.13.7.
  - Analytics explicitly disabled (`flutter --disable-analytics`).
- **Java Runtime**:
  - Eclipse Temurin OpenJDK 17.0.21+9 installed at `~/Library/Java/JavaVirtualMachines/jdk-17.0.21+9/Contents/Home`.
  - Configured as active `JAVA_HOME`.
- **Android Toolchain & SDK**:
  - Android Studio 2026.2.2.8 installed at `/Applications/Android Studio.app`.
  - Android SDK configured at `~/Library/Android/sdk` (`ANDROID_HOME`).
  - Platform installed: `platforms;android-36` and `platforms;android-34`.
  - Build-Tools installed: `build-tools;36.0.0` and `build-tools;34.0.0`.
  - Platform-Tools: `adb` 37.0.1.
  - Command-line Tools: `cmdline-tools;latest` (sdkmanager 22.0).
  - All Android SDK package licenses accepted.
  - `flutter doctor -v` reported Android toolchain completely operational: `[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)`.
- **Native Platform Scaffolding**:
  - Executed `flutter create --platforms=android,ios --org=com.upostit .` in `apps/mobile/`.
  - Cleanly generated `android/` and `ios/` platform harnesses while preserving all existing `lib/`, `test/`, and `pubspec.yaml` files.
- **Static Analysis**:
  - Executed `flutter analyze` in `apps/mobile/`.
  - **Result**: `Analyzing mobile... No issues found! (ran in 8.2s)` (0 errors, 0 warnings, 0 hints).
- **Automated Mobile Tests**:
  - Executed `flutter test` across all 9 test suites in `apps/mobile/`.
  - **Result**: **43 passed, 0 failed, 0 skipped** (ran in 5s).
- **Android Debug Build**:
  - Executed `flutter build apk --debug`.
  - Gradle 9.3.1 configured and cached via local wrapper.
  - **Result**: `✓ Built build/app/outputs/flutter-apk/app-debug.apk` (154 MB verified on disk).
- **Backend Test Suite (Pytest)**:
  - Executed via `.venv/bin/pytest tests/ -v`.
  - **Result**: **281 passed, 0 failed, 41 warnings** in 85.44s.
- **Database & Supabase Connectivity**:
  - Executed `services/api/verify_db.py`.
  - **Result**: Supabase Project URL (`https://qnkgndfzuhrjuopzlcxy.supabase.co`) HTTP 200 OK; PostgreSQL direct connection (`db.qnkgndfzuhrjuopzlcxy.supabase.co:5432/postgres`) safe `SELECT 1` succeeded; PostGIS extension available.

### 8.2 Test Execution Breakdown & Demarcation

| Category | Count | Status | Notes |
|---|---|---|---|
| **Backend Pytest Tests** | 281 | ✅ PASSED | All existing backend auth, RBAC, shifts, and punch ledger tests |
| **Flutter Test Suites** | 9 suites / 43 tests | ✅ PASSED | In-memory token manager, AuthInterceptor mutex, BLoCs, Repositories, Login & Profile screens |
| **Flutter Static Analysis** | 0 issues | ✅ CLEAN | `flutter analyze` reported "No issues found!" |
| **Android APK Build** | 1 | ✅ VERIFIED | `build/app/outputs/flutter-apk/app-debug.apk` (154 MB) |
| **Database Verification** | 3 probes | ✅ PASSED | Supabase API (200), PostgreSQL (SELECT 1), PostGIS extension check |
| **Physical Device Wi-Fi / Biometrics** | 0 | Deferred | Scheduled for Milestone 6.7 physical release hardening |

### 8.3 Implementation Defects Identified & Resolved During Audit
During the verification pass, three specific code-level discrepancies were identified and resolved:
1. **Defect 1 — `ProfileLoaded` Constructor Parameter Mismatch**:
   - *Issue*: `profile_state.dart` defined `ProfileLoaded({this.employee, this.hasLinkedEmployee = true})` with named arguments, but initial test helpers in `profile_screen_test.dart` invoked it with positional arguments (`ProfileLoaded(testEmployee)` and `ProfileLoaded(null)`).
   - *Fix*: Refactored `profile_screen_test.dart` to strictly use named parameters (`ProfileLoaded(employee: testEmployee)` and `ProfileLoaded(employee: null, hasLinkedEmployee: false)`).
2. **Defect 2 — Entity Constructor Field Mapping in Widget Test**:
   - *Issue*: `profile_screen_test.dart` instantiated `UserEntity` with `isActive: true` instead of `status: 'active'`, and omitted required fields `companyEmail` and `countryCode` on `TenantEntity`, plus passed `fullName` to `Employee` instead of `firstName` / `lastName`.
   - *Fix*: Aligned all entity fixture definitions in `profile_screen_test.dart` with domain entities.
3. **Defect 3 — Subtitle Text String Mismatch in Root Widget Test**:
   - *Issue*: `widget_test.dart` looked for `'Workforce Attendance & Verification'`, whereas `splash_screen.dart` renders `'Workforce Attendance Platform'`.
   - *Fix*: Corrected text expectation in `widget_test.dart` to match `splash_screen.dart`.

### 8.4 Security & Session Lifecycle Audit
- **Access Tokens**: Re-verified that `InMemoryTokenManager` keeps access tokens strictly in process heap memory. No tokens are written to disk, files, or `SharedPreferences`.
- **Refresh Tokens**: Re-verified that `FlutterSecureStorageService` targets iOS Keychain (`first_unlock_this_device`) and Android Keystore (`encryptedSharedPreferences: true`).
- **Token Logging**: Grep scan confirms no tokens, secrets, or passwords are logged to `debugPrint`, `print`, error banners, or analytics.
- **Concurrency Mutex**: Verified that `AuthInterceptor` uses a shared `Completer<String?>` to serialize parallel 401s into a single `POST /api/v1/auth/refresh` request, with `isRetry: true` flag preventing retry loops.
- **Online Logout**: Dispatches `POST /api/v1/auth/logout` with `{ "refresh_token": "..." }` to revoke database session before clearing local secure storage.
- **Offline Logout**: When network is unreachable, `LogoutUseCase` clears in-memory and secure storage credentials immediately while returning an explicit warning message stating that server-side revocation could not be confirmed.

---

## 9. Explicit Out-of-Scope Confirmations

In strict accordance with the Section 2 Phase Boundary, grep audits confirm that the following features were **NOT** implemented in Milestone 6.1:
- ❌ No attendance punch APIs (`/attendance/punch`).
- ❌ No check-in, check-out, break-start, or break-end buttons.
- ❌ No punch timers or live elapsed session counters.
- ❌ No GPS location permissions, geolocator APIs, or geofence calculations.
- ❌ No Wi-Fi network detection, BSSID inspection, or Wi-Fi policy checks.
- ❌ No workplace assignment verification.
- ❌ No offline SQLite database or durable synchronization queue.
- ❌ No SQLCipher encrypted local attendance storage.
- ❌ No background synchronization or workmanager tasks.
- ❌ No shift dashboard, monthly roster, or attendance history timeline.
- ❌ No biometric authentication (Face ID / Fingerprint).
- ❌ No camera capture, face recognition, selfies, or CCTV.
- ❌ No Phase 7 fraud detection or Phase 8 correction workflows.

---

## 10. Milestone 6.2 Readiness

Milestone 6.1 is complete. The application is now fully prepared for **Milestone 6.2: Online Attendance & Punch Interface**, which will introduce:
1. `AttendanceBloc` for state management of active punch shifts.
2. Online punch repository calling `POST /api/v1/attendance/punch`.
3. Hero punch card UI with `CHECK_IN`, `CHECK_OUT`, `BREAK_START`, and `BREAK_END` actions.
4. Elapsed session timer calculation.
5. Today's punch history feed displaying server-verified events.
