# UPOSTIT — Phase 8 Milestone 8.4 Implementation Report
## Flutter Mobile Conflict Bundling & Submission

**Repository:** `/Users/apple/Upostit`  
**Branch:** `phase-06`  
**Phase:** 8 — Offline Attendance Conflict Resolution & Supervisor Approvals  
**Milestone:** 8.4 — Flutter Mobile Conflict Bundling & Submission  
**Date:** 2026-11-20  

---

### 1. Executive Summary

Milestone 8.4 connects the Flutter mobile application's encrypted offline attendance queue to the backend conflict submission APIs delivered in Milestone 8.2 and the supervisor adjudication engine delivered in Milestone 8.3.

When an offline punch is permanently rejected by backend policies (e.g., beyond maximum drift window, impossible travel, or rule failure), downstream punches recorded within the same session are automatically quarantined. Milestone 8.4 enables the mobile client to bundle the primary rejected punch with all dependent quarantined punches, attach original GPS and device telemetry evidence, assign a stable UUID v4 `bundle_id`, and submit the package to `POST /api/v1/attendance/offline-conflicts/submit` for supervisor review.

Upon submission, the submission state, incident ID, and review status are durably persisted in local SQLCipher storage (`local_storage_metadata`). When the supervisor reviews and approves the incident (or when refreshed via `GET /api/v1/attendance/offline-conflicts/my`), local records are updated to `SYNCED` and the offline capacity threshold is released without data loss or tampering.

---

### 2. Architecture & Components Implemented

#### 2.1 Entity & DTO Models
- **`OfflineSequenceConflictBundle`** (`lib/features/sync/domain/entities/offline_sequence_conflict_bundle.dart`):
  - Captures the primary rejected event, dependent quarantined events, session ID, tenant ID, user ID, optional employee explanation note, submission status enum (`notSubmitted`, `pendingReview`, `approved`, `rejected`), supervisor decision, and review timestamps.
- **`ConflictSubmissionStatus` Enum**:
  - Encapsulates lifecycle states matching backend status values (`PENDING_REVIEW`, `APPROVED`, `REJECTED`).
- **`OfflineConflictBundleSubmitRequestModel`** (`lib/features/sync/data/models/offline_conflict_bundle_submit_request_model.dart`):
  - Serializes the conflict bundle and dependent events matching backend `ConflictBundleSubmitRequest` schema:
    - Primary rejected event with `local_id`, `idempotency_key`, `event_type`, `device_reported_at`, GPS coordinates, accuracy, device metadata, and rejection reason.
    - Chronologically ordered dependent quarantined punches.
- **`OfflineConflictIncidentModel` & `EmployeeConflictIncidentListModel`** (`lib/features/sync/data/models/`):
  - Deserializes backend incident responses from submission and personal incident listing endpoints.

#### 2.2 Remote Data Source Integration
- **`AttendanceRemoteDataSource` & `AttendanceRemoteDataSourceImpl`** (`lib/features/attendance/data/datasources/attendance_remote_data_source.dart`):
  - `submitConflictBundle(OfflineConflictBundleSubmitRequestModel request)`:
    - Calls `POST /api/v1/attendance/offline-conflicts/submit`.
    - Handles HTTP 201 (Created), HTTP 200 (Idempotent replay), and maps HTTP 409 (Conflict) to `ServerException`.
  - `getMyConflictIncidents({int limit = 50, String? cursor})`:
    - Calls `GET /api/v1/attendance/offline-conflicts/my` to retrieve the employee's submitted incidents and supervisor decisions.
- **`ApiEndpoints`** (`lib/core/network/api_endpoints.dart`):
  - Registered `/api/v1/attendance/offline-conflicts/submit` and `/api/v1/attendance/offline-conflicts/my`.

#### 2.3 SQLCipher Encrypted Persistence & Local Queue DAO
- **`LocalQueueDao`** (`lib/features/sync/domain/repositories/local_queue_dao.dart`):
  - Added `getConflictBundles`, `saveConflictBundleSubmission`, `getConflictBundleSubmission`, and `markConflictBundleResolved`.
- **`SqfliteLocalQueueDao`** (`lib/features/sync/data/datasources/sqflite_local_queue_dao.dart`):
  - **Deterministic Bundle Extraction (`getConflictBundles`)**:
    - Queries all `REJECTED_PERMANENT` events for the active user.
    - Checks for an existing `conflict_bundle_id`; if unset, generates a cryptographically secure UUID v4 and atomically updates local rows.
    - Queries all downstream `QUARANTINED_DEPENDENT_FAILURE` events belonging to the same attendance session.
    - Reconstructs bundle state with cached submission metadata from SQLCipher `metadataTable`.
  - **Encrypted Metadata Tracking (`saveConflictBundleSubmission`)**:
    - Persists JSON metadata under key `conflict_submission_$bundleId` in SQLCipher `local_storage_metadata` table.
    - Survives app restarts and offline periods.
    - If status is `APPROVED`, automatically invokes `markConflictBundleResolved` to set local items to `SYNCED`.
  - **Resolution (`markConflictBundleResolved`)**:
    - Updates all items matching `conflict_bundle_id` to `SYNCED`, releasing local queue storage.

#### 2.4 State Management (`SyncBloc`)
- **Events Added** (`lib/features/sync/presentation/bloc/sync_event.dart`):
  - `SyncConflictBundlesRequested`: Requests extraction of local conflict bundles.
  - `SyncSubmitConflictBundleRequested`: Dispatches bundle submission with optional employee notes.
  - `SyncRefreshConflictStatusRequested`: Polls `/my` endpoint for supervisor decisions and synchronizes local storage.
- **State Updated** (`lib/features/sync/presentation/bloc/sync_state.dart`):
  - `conflictBundles`: List of extracted conflict bundles.
  - `isSubmittingConflict`: Loading state for submission operations.
  - `submittingBundleId`: Bundle ID actively being submitted.
  - `conflictActionError` & `conflictActionSuccess`: Action notifications.
- **Bloc Logic** (`lib/features/sync/presentation/bloc/sync_bloc.dart`):
  - Integrated `AttendanceRemoteDataSource`.
  - In `_onSummaryRequested`: Automatically loads conflict bundles alongside queue metrics.
  - In `_onSubmitConflictBundleRequested`: Submits bundle, saves metadata, marks resolved if approved, emits snackbar message.
  - In `_onRefreshConflictStatusRequested`: Updates local metadata for all incidents and reconciles local statuses.

#### 2.5 User Interface
- **`ConflictSessionCard`** (`lib/features/sync/presentation/widgets/conflict_session_card.dart`):
  - Dedicated interactive card with session title and event count.
  - Status badges: `Needs Review` (Amber), `Pending Review` (Indigo), `Approved` (Emerald), `Rejected` (Rose).
  - Primary rejected punch callout with event type, timestamp, and server rejection reason.
  - Chronological timeline of dependent quarantined session punches.
  - Supervisor decision and reasoning display when adjudicated.
  - Employee notes `TextField` for optional contextual explanation.
  - "Submit for Supervisor Review" CTA button with loading and connectivity states.
  - "Check Status" button for pending incidents.
- **`SyncStatusScreen`** (`lib/features/sync/presentation/screens/sync_status_screen.dart`):
  - Embedded "Quarantined Conflicts" section right above stored records.
  - Real-time SnackBar notifications for submission success and server errors.

---

### 3. Verification & Test Coverage

All automated test suites pass 100% with zero regressions across mobile and backend:

| Test Suite | Scope | Status | Count |
|---|---|---|---|
| `offline_sequence_conflict_bundle_test.dart` | Entity state, DTO mapping, and JSON schemas | PASSED | 5 tests |
| `sync_conflict_bloc_test.dart` | BLoC events, API submissions, idempotent replays, 409 conflict, status refresh | PASSED | 6 tests |
| `conflict_session_card_test.dart` | Widget rendering, badge states, notes input, submit & refresh buttons | PASSED | 5 tests |
| `sync_status_screen_test.dart` | Dashboard rendering with Quarantined Conflicts section | PASSED | 5 tests |
| `sqflite_local_queue_dao_test.dart` | SQLCipher bundle extraction, stable UUID v4, metadata persistence, approval resolution | PASSED | 13 tests |
| **All Mobile Tests (`apps/mobile`)** | Clean architecture, BLoCs, SQLite, UI, E2E sync simulation | **PASSED** | **344 tests** |
| **All Backend Tests (`pytest`)** | Conflict submission, supervisor adjudication, RLS, DB models, migrations | **PASSED** | **524 tests** |
| **Total Automated Tests** | Full stack integration verification | **PASSED** | **868 tests** |

Static analysis verification:
- `flutter analyze` in `apps/mobile`: **No issues found!**
- PostgreSQL Alembic migration head: `e7f8a9b0c1d2_phase_08_attendance_conflicts.py` intact.

---

### 4. Git State & Working Tree

- Working branch: `phase-06`
- Working tree clean of accidental modifications.
- No git commits, tags, or pushes made, adhering to system instructions.
- Ready for user review and transition to Milestone 8.5 (Web Next.js Supervisor Console & Audit Views).

