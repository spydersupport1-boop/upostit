# UPOSTIT Phase 6 — Milestone 6.5.B Implementation Report
## FIFO Offline Attendance Synchronization Worker & Network Observer

**Date:** 2026-11-18  
**Phase:** 6 — Mobile Attendance Application (Android & iOS)  
**Milestone:** 6.5.B — Strict FIFO Synchronization Worker & Network Observer  
**Branch:** `phase-06`  
**Status:** Implementation & Full Validation Complete (Ready for Review)

---

## 1. Executive Summary

Milestone 6.5.B implements the client-side synchronization engine that automatically and reliably uploads encrypted offline attendance records from the local SQLite/SQLCipher queue to the FastAPI backend when network connectivity is restored.

The synchronization worker enforces:
1. **Strict FIFO sequence order** (`sequence_number ASC, device_reported_at ASC`), guaranteeing earlier punches are acknowledged before dependent punches are dispatched.
2. **Account-level single-worker mutex** (`Set<String> _activeWorkers`), preventing concurrent sync loops, double-tap races, or duplicate submissions.
3. **Multi-tenant and multi-user isolation**, ensuring offline punches belonging to one tenant/user can never be queried, synchronized, or leaked to another.
4. **Exact payload preservation**, reusing the identical original UUID v4 idempotency key, device timestamps, monotonic uptime telemetry, GPS coordinates, and Wi-Fi access point evidence across retries.
5. **Intelligent retry & backoff engine**, applying capped exponential backoff ($2\text{s}, 4\text{s}, 8\text{s}, 16\text{s}, 32\text{s}, 60\text{s}$) or server `Retry-After` headers on transient failures (network errors, DNS timeouts, HTTP 408, HTTP 429, HTTP 5xx).
6. **Session-aware quarantine**, isolating permanently rejected punches (HTTP 400/422) and their dependent session events into an `OfflineSequenceConflictBundle`, while leaving future independent shifts unblocked and eligible for sync.
7. **Crash recovery (zombie reset)**, safely resetting records stuck in `SYNCING` state for $>120\text{s}$ back to `PENDING_SYNC` upon application startup.
8. **Active reachability verification**, debouncing rapid connection fluctuations (1000ms) and verifying socket/DNS reachability to the backend before initiating synchronization.

---

## 2. Architecture & How Synchronization Works

### A. Network Connectivity Observer (`NetworkConnectivityServiceImpl`)
- Uses `connectivity_plus` to monitor network interface transitions (Wi-Fi, cellular, Ethernet).
- Implements a **1000ms debounce** to filter out unstable radio toggles.
- Conducts an active TCP socket/DNS lookup against the backend host (`checkBackendReachability`). If a captive portal or offline router provides a local IP without internet access, `isConnected()` returns `false`, preventing futile sync attempts.
- Exposes `Stream<bool> onConnectivityRestored` that emits `true` only when the device transitions from unreachable to reachable.

### B. Single-Worker Mutex & Tenant Isolation
- Synchronization is keyed by `${tenantId}::${userId}`.
- If a sync run is already active for an account (e.g. background auto-sync triggered while user taps "Sync Now"), subsequent requests immediately return `isCompleted: false` with `"Synchronization is already active for this account."`
- Offline database queries strictly filter by `tenant_id == tenantId AND user_id == userId`.

### C. Strict FIFO Dispatch Pipeline
```
[Network Restored / Manual Sync / App Foreground]
                      │
                      ▼
             Single-Worker Mutex Check
                      │
                      ▼
         Crash Recovery: Reset Zombies (>120s)
                      │
                      ▼
           Fetch Batch (Limit 20 FIFO)
        `sequence_number ASC, device_reported_at ASC`
                      │
                      ▼
            Status -> `SYNCING`
   (Increments retry_count, updates last_attempted_at)
                      │
                      ▼
           Dispatch PunchRequestModel
  (Preserves original UUID v4 idempotency key & telemetry)
                      │
         ┌────────────┴────────────┐
         │                         │
     [Success]                 [Failure]
         │                         │
    Review Status?           Classify Error
    ├─ PENDING_REVIEW ──┐          │
    │  FLAG_DELAYED..   │          ├─ Retryable (Net/408/429/5xx)
    │  -> flaggedReview │          │  -> Keep PENDING_SYNC, break loop,
    └─ Normal -> SYNCED │          │     apply exponential backoff
         │              │          ├─ Permanent (400/422 Domain Error)
         ▼              ▼          │  -> Mark REJECTED_PERMANENT,
    Update Local DB with           │     cascade quarantine for session,
    server_event_id                │     CONTINUE next independent shift!
         │                         ├─ Auth Failure (Refresh Failed)
         ▼                         │  -> Keep PENDING_SYNC, halt sync
    Process Next Item              └─ Account Deactivated
                                      -> Keep PENDING_SYNC, halt sync,
                                         notify UI callback
```

---

## 3. Files Created & Modified

### New Domain & Data Layer Files:
1. `apps/mobile/lib/features/sync/domain/entities/sync_result.dart`: Domain entity reporting synchronization outcomes (`syncedCount`, `permanentlyRejectedCount`, `quarantinedCount`, `retryableFailureCount`, `isCompleted`, `errorMessage`, `retryAfterSeconds`).
2. `apps/mobile/lib/features/sync/domain/repositories/network_connectivity_service.dart`: Abstract contract for network observation and reachability verification.
3. `apps/mobile/lib/features/sync/data/datasources/network_connectivity_service_impl.dart`: Concrete implementation with interface monitoring, debouncing, and socket reachability probes.
4. `apps/mobile/lib/features/sync/domain/repositories/sync_worker.dart`: Abstract contract for FIFO synchronization, auto-sync lifecycle, and foreground triggers.
5. `apps/mobile/lib/features/sync/data/services/sync_worker_impl.dart`: Concrete synchronization worker implementing mutex locking, FIFO batches, error classification, exponential backoff, crash recovery, and session quarantine.

### New Test Suites:
6. `apps/mobile/test/features/sync/data/datasources/network_connectivity_service_test.dart`: 7 unit tests verifying disconnected states, captive portal detection, interface transitions, debouncing, and disposal.
7. `apps/mobile/test/features/sync/data/services/sync_worker_test.dart`: 21 comprehensive unit tests covering all 19 required edge-case scenarios.

### Modified Files:
8. `apps/mobile/pubspec.yaml`: Added `connectivity_plus: ^6.1.0` and `integration_test: sdk: flutter`.
9. `apps/mobile/lib/features/attendance/presentation/bloc/attendance_state.dart`: Added transient `inFlightLocationReading` and `inFlightWifiEvidence` getters for punch retries.
10. `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart`: Corrected `wifiSignalStatus` initialization to `null` for non-Wi-Fi policies.
11. `docs/PHASE_06_PLAN.md`: Updated Milestone 6.5.B roadmap status to Completed.
12. `PROJECT_CONTEXT.md`: Updated master project documentation with Milestone 6.5.B test statistics.

---

## 4. Test Results & Verification

### A. Full Flutter Test Suite (`flutter test`)
```bash
$ cd apps/mobile && flutter test
00:14 +215: All tests passed!
```
* **Passed:** 215 tests
* **Failed:** 0
* **Skipped:** 0
* **Pass Rate:** 100%

### B. Static Code Analysis (`flutter analyze`)
```bash
$ cd apps/mobile && flutter analyze
Analyzing mobile...                                             
No issues found! (ran in 6.0s)
```
* **Errors:** 0
* **Warnings:** 0
* **Lints:** 0

### C. Dart Code Formatting (`dart format`)
```bash
$ cd apps/mobile && dart format --output=none --set-exit-if-changed .
Formatted 119 files (0 changed) in 0.37 seconds.
```
* **Compliance:** 100% clean.

### D. Native Android Debug Build (`flutter build apk --debug`)
```bash
$ cd apps/mobile && flutter build apk --debug
Running Gradle task 'assembleDebug'...                             38.3s
✓ Built build/app/outputs/flutter-apk/app-debug.apk
```
* **Result:** Successful APK build packaging native SQLCipher binaries (`libsqlcipher.so`) and `connectivity_plus`.

### E. Backend Regression Suite (`pytest`)
```bash
$ ./.venv/bin/pytest tests/test_phase6_attendance_policy.py tests/test_phase6_wifi_verification.py -v
======================== 42 passed, 5 warnings in 2.86s ========================
```
* **Passed:** 42 tests
* **Failed:** 0
* **Backend Regressions:** 0

---

## 5. Verification of All 19 Required Scenarios

| # | Scenario | Verification Mechanism & Test Name | Status |
| :-: | :--- | :--- | :-: |
| 1 | **FIFO event processing** | `executes FIFO processing order and crash recovery of zombie records` | Verified |
| 2 | **Prevention of concurrent workers** | `enforces single-worker mutex per account and rejects concurrent sync` | Verified |
| 3 | **Network disconnection & reconnection** | `emits onConnectivityRestored when connectivity returns and reachability is verified` | Verified |
| 4 | **Backend unreachable despite connectivity** | `isConnected returns false when interface is connected but backend is unreachable` | Verified |
| 5 | **Exponential backoff calculation** | `calculates exponential backoff capped at maxBackoff` (2s, 4s, 8s, 16s, 32s, 60s) | Verified |
| 6 | **HTTP 429 Retry-After handling** | `handles HTTP 429 with retry_after header detail` | Verified |
| 7 | **HTTP 5xx retry handling** | `handles HTTP 5xx retryable server error` | Verified |
| 8 | **Permanent HTTP 400/422 failures** | `marks permanent rejection on 422...` and `handles HTTP 400 permanent domain rejection...` | Verified |
| 9 | **Access token expiration & refresh** | `resumes synchronization on subsequent run after token refresh recovery` | Verified |
| 10 | **Failed token refresh** | `pauses sync on AuthException and preserves local records intact` | Verified |
| 11 | **Account switching** | `handles account switching cleanly without cross-account state pollution` | Verified |
| 12 | **Tenant isolation** | `enforces strict tenant and user isolation in queue queries` | Verified |
| 13 | **Deactivated accounts** | `invokes onAccountDeactivated callback when account is deactivated` | Verified |
| 14 | **Lost server response & idempotent replay**| `handles idempotent replay from server without duplicate side effects` | Verified |
| 15 | **Session-aware quarantine** | `marks permanent rejection on 422, cascades session quarantine...` | Verified |
| 16 | **Independent future sessions eligible** | `Shift 2 succeeds despite Shift 1 being quarantined` in same run | Verified |
| 17 | **Preservation of original payload** | `preserves exact original timestamps and metadata in punch request` | Verified |
| 18 | **Preservation of server review status** | `maps server review status PENDING_REVIEW to flaggedPendingReview` | Verified |
| 19 | **Application restart during sync** | `recovers from stranded syncing state via crash recovery zombie reset` (>120s) | Verified |

---

## 6. Security and Data Integrity Findings

1. **Zero Credential Storage in Local Queue Database:** The SQLCipher database stores only attendance punch payloads, UUID v4 idempotency keys, and telemetry. Tokens are managed exclusively in memory and secure keystores.
2. **Zero Plaintext Fallback:** Key acquisition fails closed; if a database exists without valid decryption keys, sync fails closed to prevent data leakage.
3. **Immutability of Local Evidence:** Original `device_reported_at`, timezone offset, monotonic boot uptime, and telemetry are never altered or replaced by the sync worker.
4. **Zero-Deletion on Failure:** Unresolved records are never deleted on authentication failure, token refresh error, or account deactivation.

---

## 7. Known Limitations & Environment Distinctions

1. **Mocked Unit Tests vs. Live Integration:** The 215 mobile tests use mocked HTTP data sources and in-memory SQLite FFI instances on macOS. Live mobile-to-backend network sync will be exercised during Milestone 6.5.D (Chaos & Offline Simulation).
2. **iOS Host Tooling:** CocoaPods is not installed on the macOS host environment; native iOS builds and physical device testing are scheduled for the Milestone 6.7 release gate.
3. **Foreground Lifecycle Trigger:** `onAppForegrounded()` provides the hook; UI binding will be wired in Milestone 6.5.C via `WidgetsBindingObserver`.

---

## 8. Milestone Completion Sign-Off

* **Phase 6.5.B Objectives:** 100% Complete.
* **Phase 6.5.C (UI / Sync Drawer):** NOT started.
* **Phase 8 (Conflict APIs):** NOT started.
* **Git Status:** Uncommitted changes preserved on branch `phase-06`. No commits, tags, or pushes made.

**Ready for Project Owner Review.**

