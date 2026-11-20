# UPOSTIT — Phase 7.5 Implementation Report: Flutter Mobile Device Binding & Fraud Telemetry

**Project:** UPOSTIT Workforce Attendance SaaS  
**Repository:** `/Users/apple/Upostit`  
**Branch:** `phase-06`  
**Milestone:** 7.5 — Flutter Mobile Device Binding & Fraud Telemetry  
**Status:** Completed & Validated  
**Date:** November 19, 2026  

---

## 1. Executive Summary

Milestone 7.5 delivers the native Flutter mobile client integration for the Phase 7 Mobile Attendance Fraud Shield within the UPOSTIT platform.

The mobile application now securely identifies its installation, registers the mobile device with the UPOSTIT backend, displays and tracks its binding authorization lifecycle state, and attaches fraud telemetry signals (including hardware platform, OS/app versioning, mock-location flags, and GPS capture timestamps) to all attendance presence requests and offline persistence queues.

Following strict architectural boundaries, the mobile client **never** performs fraud risk scoring or decides attendance validity on its own; all fraud scoring and decision rules remain exclusively backend-authoritative.

---

## 2. Architecture & Design Principles

### 2.1 Secure Installation Identifier Lifecycle
- **Cryptographic Generation**: A unique UUID v4 is generated upon first installation and persisted in platform hardware-backed secure storage via `FlutterSecureStorage`.
- **Platform Keystore Integration**:
  - Android: `AndroidOptions(encryptedSharedPreferences: true)` using Android Keystore.
  - iOS: `IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device)` using iOS Keychain.
- **Persistence & Isolation**:
  - Reused across app restarts, lifecycle pauses, and app version upgrades.
  - Distinct from the backend HMAC hash (`hash_device_identifier`). The Flutter application transmits the installation identifier as `device_id`; the backend hashes it for database storage and index matching.
  - Never logged, printed, or exposed in plaintext in the UI or client logs.
  - Not cleared on user logout. The installation identifier represents physical device presence, independent of session credentials.
  - Resilient recovery: if corrupted or invalid in length, `FlutterDeviceIdentityService` regenerates and re-persists a valid UUID v4 without crashing.
  - No invasive hardware IDs: strictly avoids deprecated or restricted hardware serials (IMEI, MAC address, ANDROID_ID, or baseband serials).

### 2.2 Device Binding Lifecycle & Domain Modeling
The mobile client models all 5 backend device lifecycle states via `DeviceBindingStatus`:
1. `ACTIVE`: Device is authorized; employee can record attendance punches.
2. `PENDING_APPROVAL`: Device registration is awaiting HR administrator approval.
3. `REVOKED`: Device binding has been revoked by an administrator; punches are blocked.
4. `REPLACED`: Device has been superseded by another registered device.
5. `UNREGISTERED`: App has not yet registered with the organization backend.

---

## 3. Implementation Details

### 3.1 Network Endpoints
Extended `ApiEndpoints` (`apps/mobile/lib/core/network/api_endpoints.dart`):
```dart
static const String devicesRegister = '/api/v1/devices/register';
static const String devicesMe = '/api/v1/devices/me';
```

### 3.2 Secure Device Identity Service
Created `apps/mobile/lib/features/devices/data/services/device_identity_service.dart`:
- `DevicePlatformInfo`: Structured container for platform (`ANDROID`, `IOS`, `WEB`, `OTHER`), `deviceModel`, `osName`, `osVersion`, `appVersion`, and metadata.
- `DeviceIdentityService`: Abstract interface for `getOrCreateInstallationId()`, `getInstallationId()`, and `getPlatformMetadata()`.
- `FlutterDeviceIdentityService`: Concrete implementation backed by `FlutterSecureStorage`, `DeviceInfoPlugin`, and `PackageInfo`.

### 3.3 Device Feature Clean Architecture
- **Domain Entities & Contract**:
  - `DeviceBindingStatus`: Enum representing lifecycle states with display formatting and `canPunch` evaluation (`apps/mobile/lib/features/devices/domain/entities/device_binding_status.dart`).
  - `DeviceInfo`: Entity mapping registered device details (`apps/mobile/lib/features/devices/domain/entities/device_info.dart`).
  - `DeviceStatusResult`: Entity modeling status response (`apps/mobile/lib/features/devices/domain/entities/device_status_result.dart`).
  - `DeviceRepository`: Interface defining `getDeviceStatus()` and `registerCurrentDevice()` (`apps/mobile/lib/features/devices/domain/repositories/device_repository.dart`).
- **Data Layer Models & Datasource**:
  - `DeviceModel`: DTO for `DeviceResponse` JSON parsing (`apps/mobile/lib/features/devices/data/models/device_model.dart`).
  - `DeviceRegisterRequestModel`: DTO for registration payload (`apps/mobile/lib/features/devices/data/models/device_register_request_model.dart`).
  - `DeviceRegisterResponseModel`: DTO for registration response (`apps/mobile/lib/features/devices/data/models/device_register_response_model.dart`).
  - `DeviceStatusResponseModel`: DTO for `GET /api/v1/devices/me` response (`apps/mobile/lib/features/devices/data/models/device_status_response_model.dart`).
  - `DeviceRemoteDataSourceImpl`: Communicates with backend endpoints using typed `ApiClient` (`apps/mobile/lib/features/devices/data/datasources/device_remote_data_source.dart`).
  - `DeviceRepositoryImpl`: Coordinates identity collection, platform metadata, remote API calls, and Dio error mapping (`apps/mobile/lib/features/devices/data/repositories/device_repository_impl.dart`).
- **Presentation Layer (BLoC & UI)**:
  - `DeviceEvent`: `CheckDeviceStatusRequested`, `RegisterCurrentDeviceRequested` (`apps/mobile/lib/features/devices/presentation/bloc/device_event.dart`).
  - `DeviceState`: `DeviceInitial`, `DeviceLoading`, `DeviceLoaded`, `DeviceFailure` (`apps/mobile/lib/features/devices/presentation/bloc/device_state.dart`).
  - `DeviceBloc`: State machine handling device registration and queries (`apps/mobile/lib/features/devices/presentation/bloc/device_bloc.dart`).
  - `DeviceStatusCard`: Card component displaying status badge, device model, OS/app version, registered date, status explanation, and registration/refresh buttons (`apps/mobile/lib/features/devices/presentation/widgets/device_status_card.dart`).
  - `ProfileScreen`: Integrated `DeviceStatusCard` into the employee profile view (`apps/mobile/lib/features/profile/presentation/screens/profile_screen.dart`).

### 3.4 Fraud Telemetry Integration in Attendance & Offline Sync
- **Punch Request DTO**:
  - Updated `PunchRequestModel` (`apps/mobile/lib/features/attendance/data/models/punch_request_model.dart`) to serialize `is_mock_location` (bool) and `location_captured_at` (ISO 8601 UTC string).
- **Attendance Repository**:
  - Extended `AttendanceRepository.recordPunch` and `AttendanceRepositoryImpl` to forward `deviceId`, `isMockLocation`, and `locationCapturedAt`.
- **Attendance BLoC (`AttendanceBloc`)**:
  - Injected `DeviceIdentityService`.
  - When recording a punch, acquires the persistent installation identifier and extracts `isMocked` and GPS `timestamp` from `LocationReading`.
  - Transmits telemetry to online punch and passes it to offline queue persister.
  - Graceful revocation handling: when backend returns `403 Forbidden` with a revoked device notice, displays an informative non-retriable message: `"Device access revoked. Please contact HR to authorize this device."`
- **Offline Queue & FIFO Sync Worker**:
  - `AttendanceBloc._persistOfflinePunch`: Populates `LocalQueueItem.deviceId` and embeds `is_mock_location` and `location_captured_at` in `metadataJson`.
  - `SyncWorkerImpl._buildPunchRequest`: Extracts `is_mock_location` and `location_captured_at` from `metadata` and constructs a complete `PunchRequestModel` during FIFO sync replay.

---

## 4. Verification & Testing

### 4.1 Automated Flutter Test Suite
Authoring and executing 32 new unit, BLoC, and widget tests across 5 test files:

1. **`test/features/devices/data/services/device_identity_service_test.dart` (7 tests)**:
   - First-run UUID v4 generation and secure persistence.
   - Subsequent run reuse of stored installation identifier.
   - Automatic regeneration on corrupted/truncated stored keys.
   - Graceful recovery when secure storage read throws.
   - Read-only lookup without generation.
   - Platform and app version metadata resolution.

2. **`test/features/devices/data/repositories/device_repository_test.dart` (6 tests)**:
   - `getDeviceStatus()` returns `DeviceStatusResult` when bound (`ACTIVE`).
   - `getDeviceStatus()` returns `DeviceStatusResult` when unregistered.
   - Maps connection timeout to `NetworkFailure`.
   - Maps HTTP 401 to `ServerFailure(statusCode: 401)`.
   - `registerCurrentDevice()` collects metadata and registers successfully.
   - Handles HTTP 400 "device already registered" error cleanly.

3. **`test/features/devices/presentation/bloc/device_bloc_test.dart` (8 tests)**:
   - Initial state is `DeviceInitial`.
   - Transitions `[DeviceLoading, DeviceLoaded]` for `ACTIVE`, `UNREGISTERED`, `PENDING_APPROVAL`, and `REVOKED` states.
   - Emits `[DeviceLoading, DeviceFailure]` on network connectivity error.
   - `RegisterCurrentDeviceRequested` transitions `isRegistering: true` to updated `DeviceLoaded`.
   - Emits `DeviceFailure` on HTTP 403 registration rejection.

4. **`test/features/devices/presentation/widgets/device_status_card_test.dart` (6 tests)**:
   - Renders `CircularProgressIndicator` on `DeviceLoading`.
   - Renders error banner and Retry button on `DeviceFailure`.
   - Renders `ACTIVE` badge, model details, app version, and "Refresh Status" button.
   - Renders `PENDING APPROVAL` badge and administrator approval notice.
   - Renders `REVOKED` badge, revocation explanation, and warning reason.
   - Renders `UNREGISTERED` badge and "Register This Device" button, verifying event dispatch on tap.

5. **`test/features/attendance/attendance_bloc_fraud_telemetry_test.dart` (5 tests)**:
   - Forwards `deviceId`, `is_mock_location: false`, and `location_captured_at` on authentic GPS punch.
   - Forwards `is_mock_location: true` when simulated mock GPS fix is detected.
   - Handles HTTP 403 device revoked response with non-retriable friendly error.
   - Preserves `deviceId`, `is_mock_location`, and `location_captured_at` in offline `LocalQueueItem`.
   - Verifies `PunchRequestModel.toJson()` serialization format with fraud telemetry.

### 4.2 Test Suite Execution Results
```text
00:21 +316: All tests passed!
```
- **Total Flutter Tests:** 316 passed (284 existing + 32 new).
- **Pass Rate:** 100% (0 failures, 0 regressions).

### 4.3 Static Analysis & Formatting
- **Static Analysis:** `flutter analyze` — **No issues found!** (ran in 6.9s).
- **Code Formatting:** `dart format --output=none --set-exit-if-changed .` — Clean, zero formatting diffs across 185 files.
- **Android Compilation:** `flutter build apk --debug` succeeded (`build/app/outputs/flutter-apk/app-debug.apk`).

---

## 5. Artifact Checklist

| Component | Path | Status |
| :--- | :--- | :--- |
| API Endpoints | `apps/mobile/lib/core/network/api_endpoints.dart` | Updated |
| Identity Service | `apps/mobile/lib/features/devices/data/services/device_identity_service.dart` | Created |
| Device Status Enum | `apps/mobile/lib/features/devices/domain/entities/device_binding_status.dart` | Created |
| Device Info Entity | `apps/mobile/lib/features/devices/domain/entities/device_info.dart` | Created |
| Status Result Entity | `apps/mobile/lib/features/devices/domain/entities/device_status_result.dart` | Created |
| Repository Interface | `apps/mobile/lib/features/devices/domain/repositories/device_repository.dart` | Created |
| Device Model | `apps/mobile/lib/features/devices/data/models/device_model.dart` | Created |
| Request Model | `apps/mobile/lib/features/devices/data/models/device_register_request_model.dart` | Created |
| Response Model | `apps/mobile/lib/features/devices/data/models/device_register_response_model.dart` | Created |
| Status Model | `apps/mobile/lib/features/devices/data/models/device_status_response_model.dart` | Created |
| Remote Data Source | `apps/mobile/lib/features/devices/data/datasources/device_remote_data_source.dart` | Created |
| Repository Impl | `apps/mobile/lib/features/devices/data/repositories/device_repository_impl.dart` | Created |
| Device BLoC | `apps/mobile/lib/features/devices/presentation/bloc/device_bloc.dart` | Created |
| Device Events/States| `apps/mobile/lib/features/devices/presentation/bloc/device_event.dart`, `device_state.dart` | Created |
| Device Status Card | `apps/mobile/lib/features/devices/presentation/widgets/device_status_card.dart` | Created |
| Profile Screen | `apps/mobile/lib/features/profile/presentation/screens/profile_screen.dart` | Updated |
| App Wiring | `apps/mobile/lib/main.dart` | Updated |
| Punch Request DTO | `apps/mobile/lib/features/attendance/data/models/punch_request_model.dart` | Updated |
| Attendance Repo | `apps/mobile/lib/features/attendance/domain/repositories/attendance_repository.dart` | Updated |
| Attendance Repo Impl| `apps/mobile/lib/features/attendance/data/repositories/attendance_repository_impl.dart` | Updated |
| Attendance BLoC | `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart` | Updated |
| Sync Worker | `apps/mobile/lib/features/sync/data/services/sync_worker_impl.dart` | Updated |
| Unit Tests | `apps/mobile/test/features/devices/data/services/device_identity_service_test.dart` | Created |
| Repo Tests | `apps/mobile/test/features/devices/data/repositories/device_repository_test.dart` | Created |
| BLoC Tests | `apps/mobile/test/features/devices/presentation/bloc/device_bloc_test.dart` | Created |
| Widget Tests | `apps/mobile/test/features/devices/presentation/widgets/device_status_card_test.dart` | Created |
| Telemetry Tests | `apps/mobile/test/features/attendance/attendance_bloc_fraud_telemetry_test.dart` | Created |
| Master Documentation | `PROJECT_CONTEXT.md` | Updated |

