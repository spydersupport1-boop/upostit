# UPOSTIT — Phase 6, Milestone 6.3.B Report
## Flutter Mobile GPS Attendance Integration & Policy Enforcement

**Milestone**: Milestone 6.3.B  
**Date**: November 5, 2026  
**Status**: COMPLETED & VERIFIED  
**Branch**: `phase-06`  
**Flutter SDK**: Flutter 3.47.9 • Dart 3.13.7  
**Platform Targets**: Android (API 26+) & iOS (14.0+)  

---

## 1. Executive Summary

Milestone 6.3.B successfully delivers native, policy-driven GPS attendance verification to the UPOSTIT Flutter mobile client (`apps/mobile/`), seamlessly integrating with the backend company policy engine and PostGIS geofencing infrastructure delivered in Milestone 6.3.A.

The mobile client dynamically queries `GET /api/v1/attendance/policy/me`, enforcing appropriate device behavior:
- **`MANUAL` Attendance**: Zero GPS permissions requested, zero location hardware calls, clean employee-friendly dashboard without location warnings or UI clutter.
- **`GPS_ONLY` Attendance**: Enforces foreground location permission checks, acquires fresh high-accuracy location fixes ($\le 100\text{m}$ accuracy, $\le 30\text{s}$ age), binds assigned workplace identifier, and submits coordinates to server PostGIS `ST_DWithin` geofence validation. Client-side Haversine distance is strictly advisory.
- **Unsupported Policy Modes** (`WIFI_ONLY`, `BIOMETRIC_ONLY`, `FACE_RECOGNITION`, `COMBINED`): Explicitly blocked with actionable employee messaging rather than silently defaulting to manual punches.

---

## 2. Files Created and Modified

### 2.1 Configuration & Platform Declarations
- `apps/mobile/pubspec.yaml`: Added `geolocator: ^14.0.2` dependency for foreground location capabilities.
- `apps/mobile/android/app/src/main/AndroidManifest.xml`: Added `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `INTERNET`, `ACCESS_NETWORK_STATE` (no background location permissions requested).
- `apps/mobile/ios/Runner/Info.plist`: Added `NSLocationWhenInUseUsageDescription` explaining attendance verification rationale.

### 2.2 Network & DTO Layer
- `apps/mobile/lib/core/network/api_endpoints.dart`: Added `attendancePolicyMe` (`/api/v1/attendance/policy/me`) and `verifyCoordinates` (`/api/v1/employees/me/workplaces/verify-coordinates`).
- `apps/mobile/lib/features/attendance/data/models/punch_request_model.dart`: Extended with `locationId`, `latitude`, `longitude`, `accuracyMeters`.
- `apps/mobile/lib/features/attendance/data/models/employee_workplace_model.dart`: Extended with `latitude`, `longitude`, `radius_meters`.
- `apps/mobile/lib/features/attendance/data/models/attendance_policy_model.dart`: Created DTO parsing `EmployeeAttendancePolicyResponse`.
- `apps/mobile/lib/features/attendance/data/datasources/attendance_remote_data_source.dart`: Implemented `getMyAttendancePolicy()`.

### 2.3 Domain Entities & Repositories
- `apps/mobile/lib/features/attendance/domain/entities/attendance_policy.dart`: Created domain entity with `PolicyVerificationMode`, `isSupportedInThisRelease`, `unsupportedMessage`, and `AttendancePolicy.defaultManual()`.
- `apps/mobile/lib/features/attendance/domain/entities/assigned_workplace.dart`: Extended with nullable `latitude`, `longitude`, `radiusMeters`.
- `apps/mobile/lib/features/attendance/domain/entities/attendance_dashboard.dart`: Integrated `AttendancePolicy? policy` into dashboard state.
- `apps/mobile/lib/features/attendance/domain/repositories/attendance_repository.dart`: Updated `recordPunch` signature with GPS parameters; added `getActivePolicy()`.
- `apps/mobile/lib/features/attendance/data/repositories/attendance_repository_impl.dart`: Implemented `getActivePolicy()`, passed GPS fields, safely loaded policy on dashboard fetch.

### 2.4 Location Service & Device Abstraction
- `apps/mobile/lib/features/attendance/data/services/location_service.dart`:
  - Abstract interface `LocationService` enabling 100% test mocking without hardware dependencies.
  - Value object `LocationReading` with `.isStale()` and `.isAccurate()` evaluation methods.
  - Concrete `GeolocatorLocationService` backed by `package:geolocator`.
  - Advisory Haversine great-circle distance calculator.
  - Domain exception hierarchy: `LocationServiceDisabledException`, `LocationPermissionDeniedException`, `LocationPermissionPermanentlyDeniedException`, `LocationTimeoutException`, `LocationAccuracyException`, `LocationStaleException`, `MockLocationDetectedException`.

### 2.5 BLoC Application State Machine
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_event.dart`: Added `LocationPermissionResolutionRequested` and `LocationProbeRequested`.
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_state.dart`: Added location status attributes (`locationStatusMessage`, `lastLocationReading`, `advisoryDistanceMeters`, `isInsideGeofence`, `isLocationPermissionDenied`, `isLocationServiceDisabled`, and `clearInFlight`).
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart`:
  - Wired `LocationService` with policy-driven branching.
  - Generated single UUID v4 idempotency key per logical punch, strictly preserved across network and GPS retries.
  - Protected against double-tap submissions with in-flight locking.
  - Handled all location exception paths gracefully with clear employee recovery prompts.

### 2.6 User Interface
- `apps/mobile/lib/features/attendance/presentation/widgets/geofence_status_card.dart`: Clean, employee-centric card displaying workplace name, perimeter distance, accuracy, and permission/service resolution buttons (rendered strictly when GPS is mandated).
- `apps/mobile/lib/features/attendance/presentation/widgets/hero_punch_card.dart`: Added `isUnsupported` property to cleanly disable punch buttons when policy mode is unsupported.
- `apps/mobile/lib/features/attendance/presentation/screens/attendance_home_screen.dart`:
  - Integrated `WidgetsBindingObserver` for app-resume settings recovery (`didChangeAppLifecycleState`).
  - Added unsupported policy banner alerting employees to contact their administrator.
  - Integrated `GeofenceStatusCard`.

### 2.7 Automated Tests
- `apps/mobile/test/features/attendance/data/models/punch_request_model_test.dart`: Added serialization tests for GPS fields and `AttendancePolicyModel` deserialization.
- `apps/mobile/test/features/attendance/data/services/location_service_test.dart`: Unit tests for staleness, accuracy, mock flag, Haversine distance, and exceptions.
- `apps/mobile/test/features/attendance/presentation/bloc/attendance_gps_bloc_test.dart`: 17 comprehensive BLoC unit tests covering all policy modes, hardware errors, mock locations, geofence rejection, and idempotency key preservation.
- `apps/mobile/test/features/attendance/presentation/widgets/geofence_status_card_test.dart`: 8 widget tests verifying clean MANUAL hiding, GPS status rendering, permission alerts, and button callbacks.

---

## 3. Policy-Driven Location Behavior

| Policy Mode | Location Permissions | GPS Hardware Access | Punch Request Payload | UI Presentation |
| :--- | :--- | :--- | :--- | :--- |
| **`MANUAL`** | Not requested | Never accessed | `latitude: null`, `longitude: null`, `location_id: null` | Clean dashboard; zero GPS cards, zero permission prompts |
| **`GPS_ONLY`** | Foreground (`WhenInUse`) | High accuracy fix with timeout | Includes coordinates, accuracy, `location_id`, UTC timestamp | Shows `GeofenceStatusCard` with assigned workplace & proximity |
| **`WIFI_ONLY`** | Not requested | Never accessed | Punch blocked client-side | Shows unsupported mode warning banner; punch button disabled |
| **`BIOMETRIC_ONLY`** | Not requested | Never accessed | Punch blocked client-side | Shows dedicated terminal warning banner; punch button disabled |
| **`FACE_RECOGNITION`** | Not requested | Never accessed | Punch blocked client-side | Shows unsupported facial recognition banner; punch button disabled |

---

## 4. Mock-Location Inspection & Security Analysis

### 4.1 Android Implementation
- `geolocator` inspects Android's native `Location.isFromMockProvider()` (represented via `Position.isMocked`).
- When `isMocked == true`, `LocationReading.isMocked` is set to `true`, and `GeolocatorLocationService` raises `MockLocationDetectedException`.
- The punch attempt is blocked immediately with a clear security notice: *"Simulated or mock location detected. Please disable mock location apps to record attendance."*

### 4.2 Platform Limitations (Especially iOS)
- **iOS Sandbox**: Apple's CoreLocation framework does not expose a public mock-location flag or API to third-party applications.
- **Security Posture**: Client-side mock detection is strictly an advisory defense-in-depth signal and is **never treated as authoritative**.
- **Backend Authority**: The FastAPI backend and PostgreSQL PostGIS spatial engine serve as the final authority. Phase 5 & Phase 6 velocity checks, IP/ASN corroboration, and PostGIS geofence evaluation guard against location spoofing regardless of client OS indicators.

---

## 5. Verification Results

### 5.1 Flutter Static Analysis & Formatting
```bash
cd apps/mobile && dart format --output=none --set-exit-if-changed .
# Result: Formatted 93 files (0 changed) in 0.26 seconds. Exit Code: 0

cd apps/mobile && flutter analyze
# Result: Analyzing mobile... No issues found! (ran in 3.9s). Exit Code: 0
```

### 5.2 Mobile Automated Test Suite
```bash
cd apps/mobile && flutter test
# Result: 00:06 +124: All tests passed! Exit Code: 0
```
- Total mobile tests: **124 tests** (100% passing).
- Breakdown:
  - 17 GPS BLoC unit tests (`attendance_gps_bloc_test.dart`)
  - 11 Core BLoC unit tests (`attendance_bloc_test.dart`)
  - 13 Location service unit tests (`location_service_test.dart`)
  - 13 Punch request & policy DTO tests (`punch_request_model_test.dart`)
  - 8 Geofence widget tests (`geofence_status_card_test.dart`)
  - Remaining: Repository, Auth, Profile, Interceptor, and Screen tests.

### 5.3 Android Debug APK Build
```bash
cd apps/mobile && flutter build apk --debug
# Result: ✓ Built build/app/outputs/flutter-apk/app-debug.apk (38.3s). Exit Code: 0
```

### 5.4 Backend Regression Suite
```bash
./.venv/bin/pytest tests/
# Result: 300 passed, 43 warnings in 89.07s (0:01:29). Exit Code: 0
```
- Total backend tests: **300 tests** (100% passing across all Phase 3, 4, 5, and 6 test suites).

### 5.5 Backend Linting & Type Checking
```bash
./.venv/bin/ruff check services/ tests/
# Result: All checks passed! Exit Code: 0

./.venv/bin/mypy services/ tests/
# Result: Success: no issues found in 77 source files. Exit Code: 0
```

### 5.6 Physical Device Testing Status
- Connected devices detected: macOS (desktop) and Chrome (web). No physical Android or iOS device was connected to the development host.
- Physical device GPS tests (satellite lock in various physical locations, hardware GPS toggle switch) could not be physically executed and were simulated via mocked location providers in automated tests.

---

## 6. Git Status & Scope Control

- **Branch**: `phase-06`
- **Working Tree**: All changes uncommitted in working directory (no commits, tags, or pushes made).
- **Milestone 6.4 Status**: Not started. Awaiting user review and approval.

