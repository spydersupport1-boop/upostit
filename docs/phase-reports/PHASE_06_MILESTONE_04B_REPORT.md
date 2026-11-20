# UPOSTIT — Phase 6, Milestone 6.4.B Report
## Flutter Mobile Wi-Fi Attendance Integration & Policy Fallback Enforcement

**Milestone**: Milestone 6.4.B  
**Date**: November 6, 2026  
**Status**: COMPLETED & VERIFIED  
**Branch**: `phase-06`  
**Flutter SDK**: Flutter 3.47.9 • Dart 3.13.7  
**Platform Targets**: Android (API 26+) & iOS (14.0+)  

---

## 1. Executive Summary

Milestone 6.4.B successfully delivers policy-driven Wi-Fi attendance verification and admin-configurable fallback execution to the UPOSTIT Flutter mobile application (`apps/mobile/`). It integrates directly with the backend Wi-Fi verification engine, access-point models, and authoritative policy engine completed and verified in Milestone 6.4.A.

Key achievements in Milestone 6.4.B:
1. **Connected AP Inspection Only**: Strict adherence to privacy and power requirements via `network_info_plus: ^7.0.0`. The application inspects only the actively connected access point and never performs active background scanning of nearby networks (in compliance with Apple App Store guidelines and Android Wi-Fi scan throttling).
2. **Platform-Specific Access & Permissions**:
   - **Android**: Handled runtime location permissions (`ACCESS_FINE_LOCATION`) and Wi-Fi state (`ACCESS_WIFI_STATE`), detected when system location services are toggled off (preventing dummy MAC `"02:00:00:00:00:00"`), and classified signal status as `PERMISSION_DENIED` or `UNAVAILABLE`.
   - **iOS**: Configured Xcode project entitlements (`com.apple.developer.networking.wifi-info` in `Runner.entitlements`, linked across Debug and Release configurations) and foreground location permission (`NSLocationWhenInUseUsageDescription`). Gracefully handled unprovisioned/simulator builds where BSSID returns `nil`, classifying signal status as `UNSUPPORTED`.
3. **Robust BSSID Normalization & Validation**:
   - Implemented standardized formatting: uppercase, colon-separated two-hex-digit pairs (`XX:XX:XX:XX:XX:XX`).
   - Filtered dummy/placeholder MAC addresses (`02:00:00:00:00:00`, `00:00:00:00:00:00`).
   - Treated SSID strictly as a cosmetic visual label, never as cryptographic proof of presence.
4. **Policy-Driven Verification & Fallback State Machine**:
   - Handled all tenant policy modes: `MANUAL`, `GPS_ONLY`, `WIFI_ONLY`, and `COMBINED` (`AND` vs `OR`).
   - Executed admin-configured fallback actions for `WIFI_ONLY`: `REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, and `MANUAL_FALLBACK`.
   - Enforced strict fail-closed security for dual-factor presence (`COMBINED + AND`): Wi-Fi unavailability immediately blocks the punch and never silently falls back to GPS alone.
5. **Punch Idempotency Safety**:
   - Reused the exact same UUID v4 idempotency key on network or signal retry.
   - Preserved exact Wi-Fi and GPS evidence captured for the in-flight punch.
   - Handled HTTP 422 payload mismatch as a non-retriable idempotency conflict, prompting the employee to initiate a fresh punch.
6. **Zero Backend Regressions & Clean Quality Metrics**:
   - 100% clean static analysis (`flutter analyze` with 0 warnings/errors).
   - 100% formatted codebase (`dart format`).
   - 157 Flutter tests passing (100% of all unit, BLoC, and widget tests across the mobile project).
   - Successful Android debug APK build (`flutter build apk --debug`).
   - 100% backend test pass rate (all 23 Wi-Fi verification tests and 19 policy engine tests pass without error).

---

## 2. Files Created and Modified

### 2.1 Native Platform Declarations & Dependencies
- `apps/mobile/pubspec.yaml`:
  - Added `network_info_plus: ^7.0.0`.
- `apps/mobile/android/app/src/main/AndroidManifest.xml`:
  - Added `<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />`.
- `apps/mobile/ios/Runner/Runner.entitlements`:
  - Created with `<key>com.apple.developer.networking.wifi-info</key><true/>`.
- `apps/mobile/ios/Flutter/Debug.xcconfig` & `Release.xcconfig`:
  - Configured `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements`.

### 2.2 Domain Entities & Value Objects
- `apps/mobile/lib/features/attendance/domain/entities/wifi_evidence.dart`:
  - Created value object `WifiEvidence` with `WifiSignalStatus` enum (`available`, `permissionDenied`, `unavailable`, `unsupported`, `error`).
  - Added canonical MAC normalization (`XX:XX:XX:XX:XX:XX`) and dummy MAC filtering.
  - Added staleness check (`isStale(maxAgeSeconds)`) and masked BSSID helper (`maskedBssid`).
- `apps/mobile/lib/features/attendance/domain/entities/wifi_verification_result.dart`:
  - Created entity representing the server Wi-Fi probe response (`WifiMatchStatus`: `matched`, `mismatched`, `unavailable`, `unsupported`, `stale`).
  - Provided employee-facing display messages and resolution guidance.
- `apps/mobile/lib/features/attendance/domain/entities/attendance_policy.dart`:
  - Extended entity with `maxWifiAgeSeconds`, `wifiFallbackAction`, and `allowedFallbackMethods`.
  - Updated `isSupportedInThisRelease` to mark `wifiOnly` and `combined` as supported.

### 2.3 Network DTOs & Models
- `apps/mobile/lib/core/network/api_endpoints.dart`:
  - Added `verifyWifi = '/api/v1/employees/me/workplaces/verify-wifi'`.
- `apps/mobile/lib/features/attendance/data/models/attendance_policy_model.dart`:
  - Deserialized `max_wifi_age_seconds`, `wifi_fallback_action`, and `allowed_fallback_methods`.
- `apps/mobile/lib/features/attendance/data/models/punch_request_model.dart`:
  - Extended punch payload with `wifi_bssid`, `wifi_ssid`, and `wifi_signal_status`.
- `apps/mobile/lib/features/attendance/data/models/employee_wifi_verify_model.dart`:
  - Created request and response DTOs for `POST /api/v1/employees/me/workplaces/verify-wifi`.

### 2.4 Service Abstraction & Data Layer
- `apps/mobile/lib/features/attendance/data/services/wifi_service.dart`:
  - Created abstract `WifiService` interface enabling complete isolation and deterministic testing.
  - Implemented `NetworkInfoWifiService` leveraging `package:network_info_plus`.
  - Implemented cross-platform detection for Android location-disabled state and iOS entitlement unavailability.
- `apps/mobile/lib/features/attendance/data/datasources/attendance_remote_data_source.dart`:
  - Added `verifyWorkplaceWifi` remote call.
- `apps/mobile/lib/features/attendance/domain/repositories/attendance_repository.dart` & `apps/mobile/lib/features/attendance/data/repositories/attendance_repository_impl.dart`:
  - Implemented `verifyWorkplaceWifi(workplaceId, bssid, ssid, signalStatus)`.
  - Updated `recordPunch(...)` to propagate Wi-Fi parameters to the API client.

### 2.5 BLoC Application State Machine & UI
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_event.dart`:
  - Added `WifiProbeRequested(workplaceId)`.
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_state.dart`:
  - Added `lastWifiEvidence`, `lastWifiVerificationResult`, `wifiStatusMessage`, `isWifiProbing`, `isWifiPermissionDenied`.
- `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart`:
  - Implemented policy-driven punch branching for `WIFI_ONLY` and `COMBINED` modes.
  - Implemented fallback handling (`REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`).
  - Implemented Wi-Fi probe handler updating UI before punch submission.
  - Implemented HTTP 422 payload mismatch handling.
- `apps/mobile/lib/features/attendance/presentation/widgets/wifi_status_card.dart`:
  - Created reusable UI card showing connection state, masked BSSID, network SSID, verification badges, fallback notices, and re-probe / permission resolution actions.
- `apps/mobile/lib/features/attendance/presentation/screens/attendance_home_screen.dart`:
  - Integrated `WifiStatusCard` into the primary attendance view when policy mandates Wi-Fi verification.

---

## 3. Platform Capabilities & Limitations Analysis

### 3.1 Android Nuances (API 26+)
- **Location Services Dependency**: On Android 8.0+ (API 26+), `WifiManager.getConnectionInfo()` returns dummy MAC `"02:00:00:00:00:00"` unless both conditions are met:
  1. `ACCESS_FINE_LOCATION` runtime permission is granted.
  2. System Location Services (GPS) are toggled ON in device settings.
- **Handling in UPOSTIT**: `NetworkInfoWifiService` inspects whether location service is enabled before attempting BSSID lookup. If disabled, it maps the state to `WifiSignalStatus.unavailable` or `permissionDenied` with an explicit prompt guiding the user to turn on Location Services.
- **Dummy MAC Filtering**: Any BSSID matching `"02:00:00:00:00:00"` or all zeros is immediately classified as `UNAVAILABLE` and never submitted as valid evidence.

### 3.2 iOS Nuances (iOS 14+)
- **Access Wi-Fi Information Entitlement**: In iOS 13+, Apple deprecated unrestricted access to Wi-Fi hardware addresses. Third-party applications must have the `com.apple.developer.networking.wifi-info` entitlement and `kCLAuthorizationStatusAuthorizedWhenInUse` location permission.
- **Handling in UPOSTIT**:
  - The entitlement is declared in `ios/Runner/Runner.entitlements`.
  - If running in an unprovisioned environment (e.g. simulator, development team without Network Extensions entitlement), `network_info_plus` returns `null` for BSSID.
  - `NetworkInfoWifiService` detects null BSSID while on iOS and maps it to `WifiSignalStatus.unsupported`.
  - The attendance engine enforces fail-closed behavior: punches are blocked unless company policy explicitly configures a fallback method (`allow_gps_fallback_if_wifi_unsupported` or `wifiFallbackAction`).

### 3.3 Zero Background Scanning
- In strict adherence to security guidelines and battery conservation, UPOSTIT mobile client performs **zero active Wi-Fi scanning**.
- It queries only the currently connected network's parameters synchronously when the employee initiates a probe or punch action.

---

## 4. Policy-Driven Verification & Fallback Decision Matrix

| Policy Mode | Combination Rule | Connected Wi-Fi State | Action Taken by Mobile Client | Punch Payload Fields |
| :--- | :--- | :--- | :--- | :--- |
| **`MANUAL`** | N/A | Ignored | Submits punch immediately; no Wi-Fi checks | `wifi_bssid: null`, `wifi_signal_status: null` |
| **`GPS_ONLY`** | N/A | Ignored | Acquires GPS fix; no Wi-Fi checks | Coordinates included; Wi-Fi null |
| **`WIFI_ONLY`** | N/A | Available & Matched | Submits punch with BSSID and SSID | `wifi_bssid: XX:..`, `wifi_signal_status: "AVAILABLE"` |
| **`WIFI_ONLY`** | N/A | Unavailable (`REJECT`) | Punch strictly blocked; error message displayed | None (no network call dispatched) |
| **`WIFI_ONLY`** | N/A | Unavailable (`GPS_FALLBACK`) | Automatically acquires GPS fix; submits with coordinates | Coordinates included; `wifi_signal_status: "UNAVAILABLE"` |
| **`WIFI_ONLY`** | N/A | Unavailable (`SUPERVISOR_REVIEW`) | Submits punch flagged for manager review | Coordinates null; `wifi_signal_status: "UNAVAILABLE"` |
| **`WIFI_ONLY`** | N/A | Unavailable (`MANUAL_FALLBACK`) | Submits manual punch without evidence | Coordinates null; `wifi_signal_status: "UNAVAILABLE"` |
| **`COMBINED`** | `AND` (Dual-Factor) | Wi-Fi Available + GPS Valid | Submits punch containing both signals | Both GPS coordinates and Wi-Fi BSSID populated |
| **`COMBINED`** | `AND` (Dual-Factor) | Wi-Fi Unavailable | **Strictly Rejected** (fail-closed, no fallback allowed) | None (no network call dispatched) |
| **`COMBINED`** | `OR` | Wi-Fi Available | Submits punch with Wi-Fi evidence immediately | Wi-Fi BSSID populated; GPS skipped |
| **`COMBINED`** | `OR` | Wi-Fi Unavailable | Automatically falls back to GPS acquisition | Coordinates populated; `wifi_signal_status: "UNAVAILABLE"` |

---

## 5. Automated Test Matrix

All automated test suites were executed and verified on the local development environment:

| Test Suite File | Type | Tests | Status | Key Scenarios Covered |
| :--- | :--- | :---: | :---: | :--- |
| `test/features/attendance/data/services/wifi_service_test.dart` | Unit | 14 | **PASS** | BSSID normalization, dummy MAC filtering, iOS null BSSID (`UNSUPPORTED`), Android location disabled (`UNAVAILABLE`), PlatformException handling |
| `test/features/attendance/presentation/bloc/attendance_wifi_bloc_test.dart` | BLoC Unit | 12 | **PASS** | `WIFI_ONLY` matched, `REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`, `PERMISSION_DENIED`, `COMBINED` AND/OR, HTTP 422 idempotency handling, Wi-Fi probe |
| `test/features/attendance/presentation/widgets/wifi_status_card_test.dart` | Widget | 5 | **PASS** | Probing spinner, matched state, mismatched warning, permission prompt, probe button tap dispatch |
| `test/features/attendance/data/models/punch_request_model_test.dart` | Unit | 13 | **PASS** | Payload serialization with Wi-Fi fields, policy deserialization with fallback settings |
| `test/features/attendance/data/repositories/attendance_repository_test.dart` | Unit | 12 | **PASS** | Remote punch with Wi-Fi arguments, workplace Wi-Fi verification remote call |
| `test/features/attendance/presentation/bloc/attendance_gps_bloc_test.dart` | BLoC Unit | 17 | **PASS** | Regression verification of Milestone 6.3.B GPS flows and idempotency key safety |
| `test/features/attendance/presentation/bloc/attendance_bloc_test.dart` | BLoC Unit | 11 | **PASS** | Regression verification of Milestone 6.2 manual punch flows and break transitions |
| `test/features/attendance/presentation/screens/attendance_home_screen_test.dart` | Widget | 5 | **PASS** | Screen layout, status banner, retry tap, pending review notice |
| **Total Flutter Test Suite** | **Full** | **157** | **PASS** | **157 / 157 passing (0 failures, 0 regressions)** |
| `tests/test_phase6_wifi_verification.py` | Pytest | 23 | **PASS** | Backend Wi-Fi verification, AP management, RLS, audit trail |
| `tests/test_phase6_attendance_policy.py` | Pytest | 19 | **PASS** | Backend policy versioning, immutability, GPS geofence checks |

---

## 6. Physical Device Testing Disclosure

In strict accordance with project directives regarding honest verification reporting:

- **What was tested**:
  - The implementation was tested via comprehensive automated unit, BLoC, and widget tests using mocked device abstractions (`Mocktail`) simulating all hardware and platform permutations (authorized Wi-Fi, mismatched BSSID, disabled location services, iOS entitlement missing, network timeouts).
  - The full Flutter project was compiled into an Android debug APK (`build/app/outputs/flutter-apk/app-debug.apk`) via Gradle 9.3.1 and Android SDK 36.0.0 without errors.
  - Static code analysis (`flutter analyze`) passed with 0 warnings and 0 errors.
  - Code formatting (`dart format`) was validated across 101 files.
- **What was not tested on physical hardware**:
  - Physical iPhone Wi-Fi inspection with an Apple-provisioned profile (the `com.apple.developer.networking.wifi-info` entitlement requires an Apple Developer Program paid team account and cannot be tested on an Xcode simulator).
  - Physical Android device over-the-air BSSID reading across multiple hardware manufacturers.
- **Scheduled Phase**: Comprehensive physical multi-device testing and Apple Developer provisioning are explicitly scheduled for **Milestone 6.7 (Security Hardening, Real-Device iOS Testing & Release Readiness)**.

---

## 7. Acceptance Criteria Verification Checklist

- [x] Connected Wi-Fi BSSID and SSID inspected via `network_info_plus` without background network scanning.
- [x] Canonical BSSID normalization implemented (`XX:XX:XX:XX:XX:XX`).
- [x] Dummy MAC address filtering implemented (`02:00:00:00:00:00`).
- [x] Platform abstraction layer (`WifiService`) decouples UI from hardware SDKs.
- [x] Android location services toggle check implemented to prevent dummy MAC false positives.
- [x] iOS `com.apple.developer.networking.wifi-info` entitlement added to Xcode configuration.
- [x] `WIFI_ONLY` policy enforced client-side with all 4 fallback actions (`REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`).
- [x] `COMBINED` policy enforced client-side (`AND` dual-factor fail-closed vs `OR` flexible fallback).
- [x] `WifiStatusCard` UI widget displays connection state, probe trigger, and permission resolution prompts.
- [x] Punch idempotency key strictly preserved on retry with exact original evidence.
- [x] HTTP 422 payload mismatch handled cleanly without infinite retries.
- [x] 157 / 157 Flutter tests passing cleanly.
- [x] Android debug APK compiled successfully.
- [x] Zero backend source code or migration modifications.

