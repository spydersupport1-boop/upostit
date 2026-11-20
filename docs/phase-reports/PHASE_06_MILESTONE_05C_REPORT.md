# UPOSTIT Phase 6 — Milestone 6.5.C Implementation Report
## Offline UI Integration, Sync Status & Logout Safety

**Date:** 2026-11-18  
**Phase:** 6 — Mobile Attendance Application (Android & iOS)  
**Milestone:** 6.5.C — Offline UI Integration, Sync Status & Logout Safety  
**Branch:** `phase-06`  
**Status:** Implementation & Full Validation Complete (Ready for Review)

---

## 1. Executive Summary

Milestone 6.5.C completes the end-user integration of the offline attendance queue and synchronization engine into the employee-facing Flutter application. It delivers a transparent, reassuring experience where employees always understand device connectivity state, know that their punches are safely and immutably persisted when offline, can inspect queued records and synchronization metrics on demand, and are protected against accidental session abandonment that would strand unsynced punches.

Key capabilities delivered:
1. **Dynamic Offline Status Banner (`OfflineStatusBanner`)**:
   - Reusable banner displayed on the attendance home screen that automatically shows when internet connectivity is unavailable or when queued records are pending/syncing.
   - Discretely assures the employee that punches will be saved securely on device.
   - Provides live visual feedback with a progress indicator while actively synchronizing.
   - Tapping the banner immediately navigates to the dedicated Sync Status screen (`/sync`).
   - Cleanly hides (`SizedBox.shrink()`) when online with zero unresolved items.
2. **Dedicated Sync Status & History Screen (`SyncStatusScreen` at `/sync`)**:
   - Accessible from the Attendance Home AppBar (`cloud_sync_outlined`) and the Profile screen.
   - Real-time aggregated metric breakdown across 6 distinct categories: Pending Sync, Syncing, Synced, Flagged Review, Quarantined, and Rejected.
   - Displays formatted last synchronized timestamp.
   - Mutual exclusion manual "Sync Now" button that triggers `SyncWorkerImpl` with debounce and mutex protection, disabled when offline or while sync is in progress.
   - Chronological timeline of local queue records (`SyncEventTile`) showing punch event types, localized timestamps, sync status badges, server event IDs, and sanitized error explanations.
   - Strictly conforms to Phase 6.5 specification: quarantined records explain sequence dependency without falsely claiming submission to a supervisor (Phase 8 API).
3. **Pre-Logout Safety Guard (`LogoutWarningDialog`)**:
   - Before signing out from `ProfileScreen`, queries `LocalQueueDao.getUnresolvedCount(tenantId, userId)`.
   - If unresolved count $> 0$, intercepts the logout action with a high-visibility modal warning dialog detailing the consequences: records remain encrypted on device, will not be lost, but will not sync until logging back in with the same account; other users logging in will not see or sync them.
   - Provides "Cancel & Stay Signed In" (aborting logout, leaving auth session and stored tokens completely intact) and "Sign Out Anyway".
   - If unresolved count is 0, presents the standard workspace sign-out confirmation dialog.
   - Strictly never purges, deletes, or modifies local queue records on logout.
4. **Seamless Offline Punch Capture (`AttendanceBloc`)**:
   - When device is offline or when `repository.recordPunch` returns `NetworkFailure`, punches are captured locally via `LocalQueueDao.insertPendingEvent`.
   - Emits an informative floating `offlineNotice` SnackBar only after durable persistence succeeds.
   - Preserves original UUID v4 idempotency key, device timestamps, monotonic uptime telemetry, GPS coordinates, and Wi-Fi evidence without modification.
5. **Architectural Wiring & Dependency Injection (`main.dart` & `app.dart`)**:
   - Wired `FlutterSecureStorageDatabaseKeyProvider`, `LocalQueueDatabase`, `SqfliteLocalQueueDao`, `NetworkConnectivityServiceImpl`, and `SyncWorkerImpl` into `MultiRepositoryProvider`.
   - Provided `SyncBloc` alongside `AuthBloc`, `ProfileBloc`, and `AttendanceBloc` in root `MultiBlocProvider`.
   - Registered `/sync` declarative route in GoRouter.

---

## 2. Component Architecture & Implementation Details

### A. Aggregated Queue Metrics (`SyncQueueSummary`)
- **Domain Entity:** `apps/mobile/lib/features/sync/domain/entities/sync_queue_summary.dart`
  - Encapsulates counts for `pendingCount`, `syncingCount`, `syncedCount`, `permanentlyRejectedCount`, `quarantinedCount`, `flaggedCount`, and `lastSyncedAt`.
  - Computes `unresolvedCount` strictly as `pendingCount + syncingCount + quarantinedCount` (the set consuming the 500-record local storage quota).
  - Computes `totalCount` across all statuses.
- **DAO Implementation:** `apps/mobile/lib/features/sync/data/datasources/sqflite_local_queue_dao.dart`
  - Implements `getQueueSummary(tenantId, userId)` using a single optimized SQL query with `GROUP BY sync_status`.
  - Queries latest synced timestamp with `MAX(device_reported_at) WHERE sync_status = 'SYNCED'`.

### B. Offline Status Banner (`OfflineStatusBanner`)
- **File:** `apps/mobile/lib/features/sync/presentation/widgets/offline_status_banner.dart`
- **Behavior:**
  - Evaluates `SyncState`: if `isConnected && unresolvedCount == 0 && !isSyncing`, returns `const SizedBox.shrink()`.
  - Offline Mode: Sky blue / info-toned container with `Icons.cloud_off_rounded`, copy: *"Offline Mode — Punches are saved locally and will sync when connected"*, and pending badge count.
  - Syncing Mode: Primary brand light container with active `CircularProgressIndicator(strokeWidth: 2)` and copy: *"Synchronizing offline attendance records..."*.
  - Tapping navigates to `/sync` via `context.push('/sync')` or custom callback.
  - Defensive context check: returns `SizedBox.shrink()` if `SyncBloc` is absent in legacy test fixtures.

### C. Sync Status Screen (`SyncStatusScreen`)
- **File:** `apps/mobile/lib/features/sync/presentation/screens/sync_status_screen.dart`
- **Route:** `/sync` registered in `apps/mobile/lib/app.dart`.
- **UI Sections:**
  1. **Connectivity Header Banner:** Shows whether live synchronization is active or phone is offline.
  2. **Error Banner:** Displays sanitized worker error messages if synchronization encountered issues.
  3. **Metrics Grid:** Responsive 6-card grid (Pending, Syncing, Synced, Flagged, Quarantined, Rejected) with status-specific colors and count typography.
  4. **Manual Sync Action Card:** Displays formatted last synced timestamp and the "Sync Now" action button. Button is disabled when syncing or when offline with an explanatory caption.
  5. **Stored Records Timeline:** Renders `SyncEventTile` for each record, or `EmptyStateView` when queue is empty.

### D. Queue Event Tile (`SyncEventTile`)
- **File:** `apps/mobile/lib/features/sync/presentation/widgets/sync_event_tile.dart`
- **Visual Presentation:**
  - Leading rounded container with icon colored by attendance action (Green Check-In, Red Check-Out, Amber Break Start, Blue Break End).
  - Action title and localized device timestamp (`MMM d, yyyy • h:mm a`).
  - Status badge chip (`Pending`, `Syncing`, `Synced`, `Flagged`, `Quarantined`, `Rejected`).
  - Monospace server confirmation badge showing `Server ID: <server_event_id>` when synced.
  - Flagged notice informing employee that punch was ingested but flagged for supervisor review.
  - Quarantined card explaining dependency on an earlier rejected punch without claiming Phase 8 supervisor submission.
  - Rejection explanation card displaying sanitized server rejection message.

### E. Logout Safety Flow (`ProfileScreen` & `LogoutWarningDialog`)
- **Files:**
  - `apps/mobile/lib/features/profile/presentation/screens/profile_screen.dart`
  - `apps/mobile/lib/features/sync/presentation/widgets/logout_warning_dialog.dart`
- **Flow:**
  1. Employee taps "Sign Out of Account" on profile screen.
  2. `_onLogoutPressed` invokes `dao.getUnresolvedCount(tenantId: authState.tenant.id, userId: authState.user.id)`.
  3. If `unresolvedCount == 0`: shows standard confirmation alert dialog (`"Are you sure you want to sign out...?"`).
  4. If `unresolvedCount > 0`: displays `LogoutWarningDialog` with warning icon, exact punch count, bulleted consequences, and two explicit actions:
     - **"Cancel & Stay Signed In"**: pops dialog; leaves authentication state and tokens completely untouched.
     - **"Sign Out Anyway"**: pops dialog and dispatches `LogoutRequested()` to `AuthBloc`.
  5. Local database records are never modified or purged on logout.

### F. Offline Punch Capture (`AttendanceBloc`)
- **File:** `apps/mobile/lib/features/attendance/presentation/bloc/attendance_bloc.dart`
- **Behavior:**
  - Checks reachability before network dispatch: if `connectivityService.isConnected() == false` and `localQueueDao != null`, immediately persists to local queue without network failure latency.
  - If network dispatch is attempted and returns `Left(NetworkFailure)` and `localQueueDao != null`, immediately falls back to local queue persistence.
  - Generates immutable `LocalQueueItem` with original UUID v4 idempotency key, device timestamp, monotonic telemetry, GPS coordinates, Wi-Fi evidence, and metadata.
  - After persistence succeeds, emits `offlineNotice: 'Punch saved locally. It will automatically synchronize when connection is restored.'`
  - If persistence fails (e.g. queue capacity exceeded), emits sanitized `errorMessage`.

---

## 3. Verification & Test Results

### A. Full Flutter Test Suite
```bash
cd apps/mobile && flutter test
```
- **Result:** **240 / 240 tests passed** (0 failed, 0 skipped).
- **Execution Time:** ~16 seconds.
- **Coverage Areas:**
  - `sync_bloc_test.dart` (6 tests): summary loading, manual sync now, mutex concurrency, connectivity changes, offline rejection.
  - `offline_status_banner_test.dart` (4 tests): hidden when clean, offline active banner, syncing spinner, tap navigation.
  - `sync_event_tile_test.dart` (5 tests): pending badge, synced confirmation, rejected explanation, quarantined dependency notice, flagged review note.
  - `sync_status_screen_test.dart` (4 tests): metric breakdown grid, empty state view, populated event timeline, sync button offline disablement.
  - `profile_screen_logout_safety_test.dart` (4 tests): offline queue tile, warning dialog on unresolved punches, cancel preserving session, sign-out anyway, standard dialog when 0 unresolved.
  - `attendance_offline_punch_test.dart` (2 tests): offline punch capture on device disconnect, offline punch capture on `NetworkFailure`.
  - All 215 baseline unit/widget/integration tests passed without regression.

### B. Static Analysis & Code Formatting
```bash
cd apps/mobile && flutter analyze
cd apps/mobile && dart format --output=none --set-exit-if-changed .
```
- **Static Analysis:** `No issues found!` (0 errors, 0 warnings, 0 infos).
- **Formatting:** 133 files verified with zero diffs.

### C. Native Android Compilation
```bash
cd apps/mobile && flutter build apk --debug
```
- **Result:** `✓ Built build/app/outputs/flutter-apk/app-debug.apk (30.8s)`
- **Artifact:** Compiled clean debug APK with SQLCipher, Flutter Secure Storage, and Connectivity native dependencies linked.

### D. Backend Regression Test Suite
```bash
./.venv/bin/pytest tests/test_phase6_attendance_policy.py tests/test_phase6_wifi_verification.py -v
```
- **Result:** **42 / 42 passed in 2.35s** (0 failed). Zero backend changes made.

---

## 4. Phase 6.5.C Requirements Traceability Matrix

| Requirement | Description | Implementation | Verification |
|---|---|---|---|
| **REQ-C.1** | Offline Status Banner on Attendance Home | `OfflineStatusBanner` placed prominently above punch card | `offline_status_banner_test.dart` |
| **REQ-C.2** | Debounced network transitions | `NetworkConnectivityServiceImpl` 1000ms debounce | Verified in Milestone 6.5.B test suite |
| **REQ-C.3** | Inform employee punches are saved locally | Banner copy: *"Offline Mode — Punches are saved locally and will sync when connected."* | `offline_status_banner_test.dart` |
| **REQ-C.4** | Live sync feedback spinner | `CircularProgressIndicator` on banner and sync screen while `isSyncing` | `offline_status_banner_test.dart` |
| **REQ-C.5** | Tap banner navigates to `/sync` | `InkWell` triggers `context.push('/sync')` | `offline_status_banner_test.dart` |
| **REQ-C.6** | Banner hidden when clean | Returns `SizedBox.shrink()` when online with 0 unresolved | `offline_status_banner_test.dart` |
| **REQ-C.7** | Sync Status Screen route | `/sync` route mapped to `SyncStatusScreen` in `appRouter` | App build & widget tests |
| **REQ-C.8** | Aggregated summary metrics | 6 cards: Pending, Syncing, Synced, Flagged, Quarantined, Rejected | `sync_status_screen_test.dart` |
| **REQ-C.9** | Last synced timestamp | Formatted timestamp from `summary.lastSyncedAt` | `sync_status_screen_test.dart` |
| **REQ-C.10** | Manual "Sync Now" button | Mutex-guarded button dispatching `SyncNowRequested` | `sync_status_screen_test.dart`, `sync_bloc_test.dart` |
| **REQ-C.11** | Disabled while offline / syncing | Button disabled with caption when disconnected or in progress | `sync_status_screen_test.dart` |
| **REQ-C.12** | Immutable timeline of queued records | `SyncEventTile` displaying device time, event type, status, and server ID | `sync_event_tile_test.dart` |
| **REQ-C.13** | Sanitized error explanations | Sanitized rejection messages displayed without technical stack traces | `sync_event_tile_test.dart` |
| **REQ-C.14** | No false supervisor claim | Quarantined items explain dependency without claiming supervisor endpoint | `sync_event_tile_test.dart` |
| **REQ-C.15** | Logout safety check | `ProfileScreen` checks `dao.getUnresolvedCount(tenantId, userId)` | `profile_screen_logout_safety_test.dart` |
| **REQ-C.16** | Logout warning dialog | `LogoutWarningDialog` details consequences of logging out with pending items | `profile_screen_logout_safety_test.dart` |
| **REQ-C.17** | Cancel preserves session | "Cancel & Stay Signed In" dismisses dialog and leaves auth intact | `profile_screen_logout_safety_test.dart` |
| **REQ-C.18** | Offline punch capture | `AttendanceBloc` persists to `LocalQueueDao` and emits `offlineNotice` | `attendance_offline_punch_test.dart` |

---

## 5. Scope Boundary Compliance

- **No Phase 6.5.D Implementation:** Chaos simulation framework, battery drain testing, and high-latency simulation remain untouched.
- **No Phase 8 Implementation:** No supervisor conflict submission endpoints or mock APIs were introduced.
- **Git State:** No commits, tags, or pushes executed. Working directory contains all Phase 6.5 changes intact for owner review.

