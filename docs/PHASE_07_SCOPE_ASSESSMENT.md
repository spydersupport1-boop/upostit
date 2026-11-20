# UPOSTIT — Phase 7 Scope Assessment & Architectural Specification
## Mobile Attendance Fraud Shield v1

**Date:** 2026-11-19  
**Branch:** `phase-06`  
**Status:** Scope Assessment & Milestone Roadmap (Approved for Review)

---

## 1. Roadmap & Cross-Document Inspection

To establish the exact, authoritative boundaries of **Phase 7: Mobile Attendance Fraud Shield v1**, a comprehensive audit was conducted across all existing design documents, the original 22-phase roadmap, and completed phase implementation reports:

| Source Document | Phase 7 Reference & Canonical Scope Definition |
| :--- | :--- |
| `PROJECT_CONTEXT.md` (22-Phase Roadmap, §10) | **Phase 7: Fraud Shield v1 (Stage B)**: *"Device binding, check-in selfie capture, mock GPS detection, clock drift check, risk score calculation."* |
| `docs/ARCHITECTURE.md` (§4 & §6) | Database tables: `devices`, `fraud_rules`, `fraud_flags`, `selfies`. Layered anti-fraud framework: Device hardware binding (1 device per employee), geofence & mock GPS detection (Android mock provider flags, iOS jailbreaks), impossible travel & velocity analysis, server clock authority ($>120\text{s}$ drift flag), review queue. |
| `docs/ATTENDANCE_ARCHITECTURE.md` (§2 & §9) | Strict boundary isolation: Hardware device binding, check-in selfies, mock-GPS detection, velocity checks, risk scoring. Schema readiness: `device_id`, `clock_drift_seconds`, `timestamp_verification_status`, `review_status = 'PENDING_REVIEW'`. |
| `docs/MOBILE_ATTENDANCE_ARCHITECTURE.md` (§3.2) | Anti-spoofing and biometric liveness are assigned to Phase 7. Server-authoritative PostGIS validation is retained; mobile app serves purely as evidence sensor. |
| `docs/RULES.md` (§2 & §4) | Server clock authority (client device timestamp is for drift/fraud analysis only). Append-only attendance ledger (never mutate/delete events). Client-generated idempotency keys (replay protection). Biometric/selfie privacy rules (verifiable consent, retention policies). |
| `docs/PHASE_04_PLAN.md` & `PHASE_06_PLAN.md` | Anti-spoofing controls (Android `isFromMockProvider`, iOS `isSimulatedBySoftware`, velocity analysis) are strictly allocated to Phase 7. |

---

## 2. Approved Phase 7 Scope vs. Deferred Concepts

### 2.1 In-Scope Features (Authorized for Phase 7)

1. **Hardware Device Binding (`devices` subsystem)**:
   - Registration of employee mobile device upon first authenticated login or manual registration.
   - Enforce single-device binding policy (maximum 1 active device per employee by default).
   - Cryptographically secure hardware/install identifier storage in hardware-backed keystore/keychain.
   - Storage of device metadata: model, OS type, OS version, app version, registration timestamp, status (`PENDING_APPROVAL`, `ACTIVE`, `REVOKED`, `REPLACED`).
   - Admin/HR device replacement workflow: employee can request device replacement; replacement invalidates old device upon approval.
   - Device verification during check-in: attendance punches from unregistered or revoked devices trigger risk flags (`UNREGISTERED_DEVICE`, `REVOKED_DEVICE_ATTEMPT`) and are held for manager review.
   - Strict multi-tenant data isolation and RLS enforcement.

2. **GPS Spoofing Defense & Spatial Evidence Hardening**:
   - Capture of client-side location evidence: `is_mock_location` (Android `isFromMockProvider` / iOS simulated location), horizontal accuracy, location fix age.
   - Authoritative backend validation: PostGIS `ST_DWithin` geofencing, horizontal accuracy thresholding ($>100\text{m}$ rejected or flagged), location age filtering ($>30\text{s}$ flagged as stale).
   - Telemetry Clock Drift: Comparison between authoritative UTC server time and device reported timestamp ($|T_{\text{server}} - T_{\text{device}}| > 300\text{s}$) triggering `SUSPICIOUS_CLOCK_DRIFT`.
   - Impossible Travel & Velocity Analysis: Sequential punch velocity analysis ($v = \Delta d / \Delta t$) across consecutive punches for the same employee. Exceeding supersonic or transit thresholds ($>250\text{m/s}$ / 900 km/h) generates an `IMPOSSIBLE_TRAVEL_VELOCITY` signal.

3. **Fraud Rule Engine & Deterministic Risk Scoring (`fraud_rules`, `fraud_flags`)**:
   - Extensible, tenant-configurable fraud rule definitions (`fraud_rules`).
   - Generation and persistence of audit-grade fraud signal records (`fraud_flags`) associated with `(tenant_id, event_id, employee_id, device_id)`.
   - Evaluation of composite risk levels:
     - `NORMAL`: Zero risk indicators present.
     - `LOW_RISK`: Minor single indicator (e.g., slight location inaccuracy or borderline stale fix).
     - `MEDIUM_RISK`: Multiple low-risk indicators or moderate clock drift ($>120\text{s}$).
     - `HIGH_RISK`: Mock location detected, unregistered device attempt, or impossible travel velocity.
     - `REQUIRES_REVIEW`: Event flagged for supervisor/HR adjudication (`attendance_days.status = 'PENDING_REVIEW'`).
   - Zero event mutation: The immutable event ledger (`attendance_events`) is never deleted or rewritten; risk records are maintained in parallel audit tables.

4. **HR / Admin Fraud Review Queue & Audit Ledger**:
   - Administrative review queue endpoints (`GET /api/v1/fraud/flags`, `GET /api/v1/fraud/events/{id}/review`).
   - Review decision workflow (`POST /api/v1/fraud/events/{id}/decision`): `APPROVED` or `REJECTED` with mandatory reviewer reason.
   - Full audit trail capturing reviewer `user_id`, timestamp, previous status, and updated status.

5. **Mobile Client Integration (Flutter)**:
   - Device ID Provider using `FlutterSecureStorage` (persisting unique UUID in Keychain/Keystore).
   - Location sensor enhancement: capturing `isMocked` from `geolocator` and passing it securely in `PunchRequestModel`.
   - Device binding status indicator in mobile profile/settings.
   - Clear employee feedback for pending device approval or registration errors.

6. **Offline Queue & FIFO Synchronization Compatibility**:
   - Local offline queue stores original device ID and monotonic boot counter.
   - FIFO sync worker submits stored evidence without client-side risk filtering.
   - Backend evaluates velocity and device binding at synchronization time.
   - Legitimate delayed synchronization due to network coverage outage is **never** flagged as fraud.

---

### 2.2 Explicitly Deferred / Out-of-Scope Concepts

The following concepts were identified in earlier discussions or future roadmap phases and are **strictly excluded** from Phase 7:

| Feature / Concept | Roadmap Phase | Architectural Reason for Exclusion |
| :--- | :---: | :--- |
| **On-Premise Biometric Hardware Clocks** | **Phase 15** | Requires hardware vendor SDKs, local network discovery, and edge terminal HMAC protocols. |
| **Facial Recognition / Template Matching** | **Phase 15** | Enterprise face template storage, 1:N matching engines, and biometric consent laws belong to Phase 15. Phase 7 focuses on device, spatial, and telemetry fraud shields. |
| **CCTV Edge Video Streams & RTSP** | **Phase 16** | Dedicated to standalone edge gateway service (`services/edge`) and on-premise camera pipelines. |
| **Random Mid-Shift In-App Presence Challenges** | **Phase 17** | Push notification presence challenges ("phone left at desk" prevention) are scheduled for Phase 17. |
| **BLE Beacons & NFC Physical Touchpoints** | **Phase 18** | Physical hardware beacons and NFC tags belong to Phase 18. |
| **Machine Learning / AI Anomaly Detection** | **Phase 19** | Phase 7 uses deterministic rule-based scoring. Unsupervised ML, clustering, and behavioral models are Phase 19. |
| **Automated Disciplinary Actions / Deactivation** | **Prohibited** | Project rules strictly forbid automatic employee deactivation based solely on risk scores. Human HR review is required. |

---

## 3. Implementation Milestone Breakdown

Phase 7 is organized into 7 sequential milestones:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 7: MOBILE ATTENDANCE FRAUD SHIELD v1                        │
└───────────────────────────────────┬────────────────────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
[ Milestone 7.1 ]           [ Milestone 7.2 ]               [ Milestone 7.3 ]
Device Binding              GPS Spoofing &                  Fraud Rules &
Subsystem & DB              Velocity Analysis               Risk Scoring Engine
    │                               │                               │
    └───────────────────────────────┼───────────────────────────────┘
                                    │
    ┌───────────────────────────────┴───────────────────────────────┐
    ▼                               ▼                               ▼
[ Milestone 7.4 ]           [ Milestone 7.5 ]               [ Milestone 7.6 ]
Review Queue &              Flutter Mobile Device           Offline Sync &
HR Audit Console            & Mock Telemetry                End-to-End Simulation
                                    │
                                    ▼
                            [ Milestone 7.7 ]
                            Security Audit & Release
                            Final Phase 7 Report
```

### Milestone Details:
- **Milestone 7.1: Device Binding Subsystem & Database Migration**
  - Migration: Create `devices` table with composite foreign keys, unique constraint on active employee device, and PostgreSQL RLS.
  - Backend models, schemas, and services for device registration, listing, revocation, and replacement requests.
  - RBAC permissions: `MANAGE_DEVICES`, `VIEW_DEVICES`.
  - Automated tests for multi-tenant device isolation, single-device limit, and replacement approvals.

- **Milestone 7.2: GPS Spoofing Defense, Mock Detection & Velocity Analysis**
  - Ingestion of mock location telemetry (`is_mock_location`, accuracy, timestamp).
  - Spatial velocity calculation ($v = \Delta d / \Delta t$) comparing current punch with employee's previous sequential punch.
  - Clock drift validation ($|T_{\text{server}} - T_{\text{device}}| > 300\text{s}$).
  - Backend unit and API tests asserting detection of mock GPS, impossible travel, and clock drift.

- **Milestone 7.3: Fraud Rule Engine & Risk Scoring Subsystem**
  - Migration: Create `fraud_rules` and `fraud_flags` tables with composite foreign keys and RLS.
  - Deterministic risk assessment engine deriving composite risk level (`NORMAL`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `REQUIRES_REVIEW`).
  - Integration with `record_punch` in `services/api/attendance/service.py`: persists flags and sets `review_status = 'PENDING_REVIEW'` when risk thresholds are breached.
  - Tests verifying immutable event ledger preservation and flag generation.

- **Milestone 7.4: Review Queue, HR Decision Workflows & Audit Ledger**
  - Endpoints: `GET /api/v1/fraud/flags`, `GET /api/v1/fraud/events/{id}/review`, `POST /api/v1/fraud/events/{id}/decision`.
  - Reviewer audit logging (captures reviewer ID, timestamp, approval/rejection decision, reason).
  - Automatic recalculation trigger when an event is approved or rejected by HR.
  - RBAC enforcement (`REVIEW_FRAUD_ALERTS`).

- **Milestone 7.5: Flutter Mobile Device Binding & Fraud Telemetry**
  - Secure hardware/install ID generation and persistent storage via `FlutterSecureStorage`.
  - Integration of `isMocked` property from `geolocator` into `PunchRequestModel`.
  - Device status and binding screen/card in Mobile UI.
  - Error and guidance messaging when an unregistered or revoked device attempts a punch.

- **Milestone 7.6: Offline Sync Compatibility & End-to-End Simulation**
  - Validate that queued offline punches carry persistent hardware device ID.
  - Ensure delayed synchronization does not trigger false-positive velocity or clock drift flags.
  - Comprehensive end-to-end simulation test suite: device mismatch, mock GPS, velocity jumps, offline sync.

- **Milestone 7.7: Security Audit, Documentation & Release Readiness**
  - Full automated validation: `flutter test`, `flutter analyze`, `pytest` regression suites.
  - Creation of `docs/phase-reports/PHASE_07_COMPLETION_REPORT.md`.
  - Updating `PROJECT_CONTEXT.md` and roadmap tracking.

