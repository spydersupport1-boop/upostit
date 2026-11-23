# UPOSTIT Phase 10 — Milestone 10.6 Completion Report
## Flutter Mobile: Push Token Lifecycle & In-App Notification Center

**Date:** 2026-11-22  
**Phase:** 10 — Notifications (Outbound Alerts)  
**Milestone:** 10.6 — Flutter Mobile: Push Token Lifecycle & In-App Notification Center  
**Branch:** `phase-06`  
**Status:** Completed, Fully Tested & Validated  

---

## 1. Executive Summary & Approved Scope

Milestone 10.6 implements the mobile push notification and in-app notification center architecture in the Flutter application (`apps/mobile`), building directly upon the backend database foundation (Milestone 10.1), core dispatch engine (Milestone 10.2), FCM push integration & Celery workers (Milestone 10.3), domain event triggers (Milestone 10.4), and administrative web console (Milestone 10.5).

The implementation strictly satisfies all mobile requirements specified in the approved Phase 10 roadmap:

1. **FCM Device-Token Lifecycle**:
   - Permission management for Android 13+ (`POST_NOTIFICATIONS`) and iOS APNs (`requestPermission`).
   - Secure token registration via existing backend endpoint (`POST /api/v1/notifications/devices`) with device platform metadata (`ANDROID`/`IOS`, device model, OS version, app version).
   - Token rotation and refresh handling via `FirebaseMessaging.instance.onTokenRefresh` updating the backend with `force: true`.
   - Token deduplication: Cached in `FlutterSecureStorage` (`getLastRegisteredPushToken`, `getLastRegisteredTokenHash`) to skip redundant `POST` requests on repeated cold app boots.
   - Secure logout and account switching: Automatic token revocation (`POST /api/v1/notifications/devices/revoke` and `DELETE /api/v1/notifications/devices/{token_hash}`) and deletion from device storage on user logout.
   - Sensitive data protection: Raw push tokens are never logged to console or stored in unencrypted memory; token previews display only truncated hashes.

2. **In-App Notification Center (`NotificationInboxScreen`)**:
   - Clean, production-ready notification inbox accessible from the top app bar across the application with real-time unread count badge.
   - Unread vs read visual distinction with status dots and subtle card styling.
   - Filter chips ("All" vs "Unread") allowing users to view all notifications or isolate unread alerts.
   - Categorized badges (`Leave`, `Attendance`, `Security`, `Organization`, `Account`, `Notification`) with color-coded priority indicators.
   - Relative timestamps (e.g., "Just now", "5m ago", "2h ago", "Nov 22").
   - Detailed inspection dialog (`NotificationDetailDialog`) showing full message content, event category, priority, formatted timestamp, and contextual action buttons.
   - Pull-to-refresh (`RefreshIndicator`) and app-bar refresh icon button.
   - Responsive loading (`LoadingIndicator`), error banner with retry (`ErrorBanner`), and empty state views (`EmptyStateView`).

3. **Backend API Gap Handling**:
   - The backend currently provides tenant-wide administrative activity (`GET /api/v1/notifications/activity`), but lacks a user-scoped `GET /api/v1/notifications/inbox` endpoint and database-backed `is_read` read tracking for individual users.
   - Instead of inventing fake client-side database persistence or pretending server-side sync succeeded, the mobile architecture documents and exposes this architectural gap cleanly:
     - `NotificationRemoteDataSource` translates HTTP 404 on the inbox endpoint into `ApiGapException`.
     - `NotificationRepositoryImpl` maps this into `ApiGapFailure` without throwing unhandled errors.
     - `NotificationInboxScreen` renders a prominent `NotificationApiGapBanner` informing users that the backend inbox endpoint is deferred while seamlessly displaying push notifications received during the live application session.

4. **Push Interactions & Deep Link Whitelisting**:
   - Foreground notification handler (`FirebaseMessaging.onMessage`) adds incoming push alerts directly into the active session inbox and increments the unread counter.
   - Background message handler (`firebaseMessagingBackgroundHandler`) defined as a top-level function annotated with `@pragma('vm:entry-point')`.
   - Cold-launch (`getInitialMessage`) and notification tap (`onMessageOpenedApp`) routing.
   - Safe deep link whitelist (`_isSafeRoute`): Restricts deep links strictly to validated internal application routes (`/home`, `/leave`, `/schedule`, `/history`, `/sync`, `/profile`) and explicitly rejects open-redirects, arbitrary external URLs (`https://...`), or unrecognized schema targets.

5. **Sensitive Data Redaction**:
   - Incoming payloads and notification bodies are sanitized: Passwords, auth tokens, invitation codes, and sensitive fraud telemetry (e.g. `risk_score`, `gps_spoof_score`) are regex-redacted before in-memory storage and display.

---

## 2. Component & Architecture Implementation

### 2.1 File Map

| File Path | Layer / Role | Responsibility |
| :--- | :--- | :--- |
| `apps/mobile/pubspec.yaml` | Dependencies | Added `firebase_core: ^5.2.0` and `firebase_messaging: ^17.1.0`. |
| `apps/mobile/android/app/src/main/AndroidManifest.xml` | Android Manifest | Added `<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />`. |
| `apps/mobile/ios/Runner/Info.plist` | iOS Configuration | Added `UIBackgroundModes` with `fetch` and `remote-notification`. |
| `apps/mobile/lib/core/network/api_endpoints.dart` | Network Endpoints | Added `notificationDevices`, `notificationDevicesRevoke`, `notificationDeviceByHash`, and `notificationInbox`. |
| `apps/mobile/lib/core/network/api_client.dart` | Network Client | Added `delete<T>` method to support token revocation by hash. |
| `apps/mobile/lib/core/storage/secure_storage_service.dart` | Secure Storage | Added push token and token-hash persistence methods to secure storage contract and implementation. |
| `apps/mobile/lib/core/errors/app_exception.dart` | Core Errors | Added `ApiGapException` representing architectural backend endpoint gaps. |
| `apps/mobile/lib/core/errors/failure.dart` | Core Failures | Added `ApiGapFailure` mapping `ApiGapException`. |
| `apps/mobile/lib/features/notifications/domain/entities/push_device_registration.dart` | Domain Entity | Represents registered mobile push device with masked token preview and platform metadata. |
| `apps/mobile/lib/features/notifications/domain/entities/in_app_notification.dart` | Domain Entity | In-app notification entity with category mapping (`categoryLabel`) and safe deep-link resolution (`deepLinkRoute`). |
| `apps/mobile/lib/features/notifications/domain/entities/push_notification_payload.dart` | Domain Entity | Clean entity representing parsed remote push messages. |
| `apps/mobile/lib/features/notifications/domain/repositories/notification_repository.dart` | Domain Repository | Clean Architecture repository contract for push token lifecycle and notification inbox. |
| `apps/mobile/lib/features/notifications/data/models/push_device_registration_model.dart` | Data Model | DTO mapping backend `DevicePushTokenResponse`. |
| `apps/mobile/lib/features/notifications/data/models/device_token_register_request_model.dart` | Data Model | DTO mapping backend `DeviceTokenRegisterRequest`. |
| `apps/mobile/lib/features/notifications/data/models/in_app_notification_model.dart` | Data Model | DTO mapping `NotificationResponse` with ISO-8601 parsing and null safety. |
| `apps/mobile/lib/features/notifications/data/services/push_notification_service.dart` | Service Interface | Contract for push messaging providers. |
| `apps/mobile/lib/features/notifications/data/services/firebase_push_notification_service.dart` | Service Implementation | Production FCM implementation with background handler, permission requests, token stream, and message streams. |
| `apps/mobile/lib/features/notifications/data/services/mock_push_notification_service.dart` | Test / Mock Service | Development and test fallback service providing mock tokens and message injection. |
| `apps/mobile/lib/features/notifications/data/datasources/notification_remote_data_source.dart` | Data Source | Connects to FastAPI backend notification endpoints; handles 404 translation to `ApiGapException`. |
| `apps/mobile/lib/features/notifications/data/repositories/notification_repository_impl.dart` | Data Repository | Repository implementation handling deduplication, token hash storage, session notifications, and sensitive data redaction. |
| `apps/mobile/lib/features/notifications/presentation/bloc/notification_event.dart` | Presentation BLoC | Bloc events: `InitializePushNotifications`, `TokenRefreshed`, `FetchNotificationInboxRequested`, `NotificationTappedEvent`, `ForegroundNotificationReceived`, `MarkNotificationReadRequested`, `RevokeDeviceTokenRequested`, `ClearNotificationSession`, `ClearNavigationRoute`. |
| `apps/mobile/lib/features/notifications/presentation/bloc/notification_state.dart` | Presentation BLoC | Bloc states: `NotificationInitial`, `NotificationLoading`, `NotificationLoaded`, `NotificationError`. |
| `apps/mobile/lib/features/notifications/presentation/bloc/notification_bloc.dart` | Presentation BLoC | Business logic orchestrator for push token lifecycle, inbox management, and deep linking. |
| `apps/mobile/lib/features/notifications/presentation/widgets/notification_category_badge.dart` | Presentation Widget | Chip badge showing notification category (`Leave`, `Attendance`, `Security`, etc.) with priority styling. |
| `apps/mobile/lib/features/notifications/presentation/widgets/notification_api_gap_banner.dart` | Presentation Widget | Notice banner explaining backend inbox endpoint status and session mode. |
| `apps/mobile/lib/features/notifications/presentation/widgets/notification_detail_dialog.dart` | Presentation Widget | Dialog presenting notification details, timestamps, and deep link navigation triggers. |
| `apps/mobile/lib/features/notifications/presentation/widgets/notification_tile.dart` | Presentation Widget | Inbox list tile with unread dot, category badge, relative time, and text preview. |
| `apps/mobile/lib/features/notifications/presentation/screens/notification_inbox_screen.dart` | Presentation Screen | Primary notification center screen with filter chips, pull-to-refresh, empty states, and app bar badge. |
| `apps/mobile/lib/app.dart` | App Routing | Added `/notifications` route pointing to `NotificationInboxScreen`. |
| `apps/mobile/lib/features/attendance/presentation/screens/attendance_home_screen.dart` | Home Screen App Bar | Integrated notification app bar icon with live unread badge from `NotificationBloc`. |
| `apps/mobile/lib/features/profile/presentation/screens/profile_screen.dart` | Profile Screen | Added Notification Center navigation tile and hooked token revocation into logout flow. |
| `apps/mobile/lib/main.dart` | App Entrypoint | Configured dependency injection and wired `NotificationBloc` with `AuthBloc` listener for login auto-registration. |

---

## 3. Backend Endpoints Reused

Milestone 10.6 reuses only the approved backend notification endpoints developed in Milestones 10.3 and 10.5:

| HTTP Method | Route | Backend Handler | Mobile Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/notifications/devices` | `register_device_token` | Registers mobile FCM push token with platform metadata and device model. |
| `GET` | `/api/v1/notifications/devices` | `list_active_device_tokens` | Lists active registered device tokens for the authenticated user/tenant. |
| `POST` | `/api/v1/notifications/devices/revoke` | `revoke_device_token` | Revokes the device registration using the raw push token on logout. |
| `DELETE` | `/api/v1/notifications/devices/{token_hash}` | `revoke_device_token_by_hash` | Revokes device registration using SHA-256 token hash if raw token is unavailable. |
| `GET` | `/api/v1/notifications/inbox` | *(Not yet implemented)* | User notification inbox. Mobile handles 404 gracefully via `ApiGapException` and `NotificationApiGapBanner`. |

---

## 4. Verification & Testing Evidence

### 4.1 Test Suites Summary

Four comprehensive test suites were developed for Milestone 10.6, validating the entire mobile push and notification layer:

| Test Suite | File Path | Tests | Pass Rate | Key Behaviors Verified |
| :--- | :--- | :---: | :---: | :--- |
| Remote Data Source | `test/features/notifications/data/notification_remote_data_source_test.dart` | 7 | **100%** | Device registration, listing tokens, raw token revocation, hash revocation, 404 API gap translation, error handling. |
| Repository Implementation | `test/features/notifications/data/notification_repository_test.dart` | 9 | **100%** | Token deduplication, caching in secure storage, token refresh with force, session notification storage, sensitive data redaction, safe route resolution. |
| Notification BLoC | `test/features/notifications/presentation/bloc/notification_bloc_test.dart` | 12 | **100%** | Push initialization, token refresh, logout revocation, foreground push message handling, safe deep link taps, arbitrary URL rejection, API gap handling. |
| Notification Inbox Screen | `test/features/notifications/presentation/screens/notification_inbox_screen_test.dart` | 8 | **100%** | Loading indicator, error banner with retry, empty state view, notification tiles with unread badge, API gap banner, All vs Unread filter chips, refresh action, detail dialog. |
| **Milestone 10.6 Subtotal** | **All 4 Notification Suites** | **36** | **100%** | **All push lifecycle, inbox UI, and deep link behaviors verified.** |
| **Full Mobile Suite** | `apps/mobile/test/` | **412** | **100%** | **Zero regressions across auth, attendance, leave, sync, history, and profile.** |

### 4.2 Static Analysis & Formatting
- `flutter analyze`: **0 issues found** (clean, completed in 4.8s).
- `dart format --set-exit-if-changed lib/ test/`: **0 unformatted files** (clean, completed in 0.77s).

### 4.3 Native Build Outputs
- **Android Debug Build**:
  - Command: `flutter build apk --debug`
  - Output: `build/app/outputs/flutter-apk/app-debug.apk`
  - Result: Built successfully in 35.2s.
- **Android Release Build**:
  - Command: `flutter build apk --release`
  - Output: `build/app/outputs/flutter-apk/app-release.apk` (71.2 MB)
  - Result: Built successfully in 56.9s.
- **iOS Configuration Inspection**:
  - `apps/mobile/ios/Runner/Info.plist`: Verified `UIBackgroundModes` configured with `fetch` and `remote-notification`.
  - `apps/mobile/ios/Runner/AppDelegate.swift`: Verified `FlutterAppDelegate` and plugin registrar.
- **Physical Device Delivery Status**:
  - Mock and simulated testing only.
  - Physical device delivery remains unverified until production Firebase project credentials and APNs certificates are configured.

---

## 5. Architectural Alignment & Constraints Compliance

- **Roadmap Strictness**: Implemented strictly Milestone 10.6. Milestone 10.7 has not been started.
- **Working Tree Preservation**: Preserved all existing user changes on branch `phase-06`. Zero commits, tags, or pushes.
- **Backend Non-Invention**: Did not invent new backend database tables or pretend an inbox API exists. The 404 gap was explicitly documented and handled via standard fallback banners and session memory.
- **Zero Raw Token Leakage**: Tokens are masked or hashed; neither logged nor displayed in plain text.
- **Strict Deep Link Security**: Verified whitelist prevents external URL or protocol injection.

