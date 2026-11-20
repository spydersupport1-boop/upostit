# UPOSTIT — Phase 7.2 Implementation Report: GPS Spoofing Defense, Mock Detection & Velocity Analysis

**Project:** UPOSTIT Workforce Attendance SaaS  
**Repository:** `/Users/apple/Upostit`  
**Branch:** `phase-06`  
**Milestone:** 7.2 — GPS Spoofing Defense, Mock Detection & Velocity Analysis  
**Status:** Completed & Validated  
**Date:** November 19, 2026  

---

## 1. Executive Summary

Milestone 7.2 implements backend-authoritative GPS spoofing defense, mock-location telemetry ingestion, device clock drift validation, and impossible-travel velocity analysis within the UPOSTIT Workforce Attendance SaaS platform. 

Building upon the device binding subsystem established in Milestone 7.1, this milestone ensures that incoming attendance punches are rigorously scrutinized for physical plausibility, temporal integrity, and device trustworthiness before attendance events are finalized. When suspicious telemetry is detected (such as simulated GPS, excessive clock skew, or supersonic travel between sequential punches), the backend automatically flags the event for supervisor review (`review_status = "PENDING_REVIEW"`) and persists rich forensic signals directly in the immutable event metadata—all while preserving original attendance records without unhandled crashes.

---

## 2. Extended Attendance Evidence Architecture

### 2.1 Database Schema Migration
A new Alembic database migration was created and verified:
- **Migration Script:** `database/migrations/versions/b4c5d6e7f8a9_phase_07_mock_location_evidence.py`
- **Revision ID:** `b4c5d6e7f8a9`
- **Down Revision:** `a3b4c5d6e7f8` (Phase 7.1 device binding migration)
- **Table Alteration:** Added nullable column `is_mock_location: sa.Boolean()` to table `attendance_events`.
- **Validation:** Both offline SQL upgrade and downgrade scripts were generated and verified.

### 2.2 Domain Models & Schemas
- **SQLAlchemy Model (`services/api/attendance/models.py`):**
  Added `is_mock_location: Mapped[bool | None] = mapped_column(Boolean, nullable=True)` to `AttendanceEvent`.
- **Pydantic Schemas (`services/api/attendance/schemas.py`):**
  - `PunchRequest`: Added optional fields:
    - `is_mock_location: bool | None = Field(default=None, description="Client telemetry indicating simulated location")`
    - `location_captured_at: datetime | None = Field(default=None, description="Hardware GPS fix timestamp")`
  - `AttendanceEventResponse`: Added `is_mock_location: bool | None` to the public serialized response schema.

---

## 3. Fraud Defense Subsystem Architecture

The fraud analysis subsystem was created as an isolated, modular domain service located at `services/api/fraud/`:

```
services/api/fraud/
├── __init__.py
├── schemas.py       # Pydantic schemas, enums for signal types and severities
└── service.py       # Haversine math, velocity analysis, clock drift, and telemetry evaluation
```

### 3.1 Fraud Signal Taxonomy
Defined in `services/api/fraud/schemas.py`:
- **Signal Types (`FraudSignalType`):**
  - `MOCK_LOCATION_DETECTED` (Severity: `HIGH`)
  - `SUSPICIOUS_CLOCK_DRIFT` (Severity: `HIGH`)
  - `IMPOSSIBLE_TRAVEL_VELOCITY` (Severity: `HIGH`)
  - `UNREGISTERED_DEVICE` (Severity: `MEDIUM`)
  - `DEVICE_MISMATCH` (Severity: `HIGH`)
  - `REVOKED_DEVICE` (Severity: `CRITICAL`)
  - `POOR_GPS_ACCURACY` (Severity: `LOW`)
  - `STALE_GPS_LOCATION` (Severity: `LOW`)
- **Signal Severities (`FraudSignalSeverity`):**
  - `LOW`: Informational signal; recorded in metadata without triggering manual review.
  - `MEDIUM`: Elevated anomaly; flagged for logging.
  - `HIGH`: Definite security violation; elevates `review_status` to `PENDING_REVIEW`.
  - `CRITICAL`: Severe security or trust violation; elevates `review_status` to `PENDING_REVIEW`.

### 3.2 Detection Rules & Thresholds

| Rule | Threshold / Condition | Signal Generated | Severity | Review Status |
| :--- | :--- | :--- | :--- | :--- |
| **Mock Location** | `is_mock_location is True` | `MOCK_LOCATION_DETECTED` | `HIGH` | `PENDING_REVIEW` |
| **Poor Accuracy** | `accuracy_meters > 100.0` | `POOR_GPS_ACCURACY` | `LOW` | Unchanged |
| **Stale GPS Fix** | `(device_time - location_captured_at) > 30s` | `STALE_GPS_LOCATION` | `LOW` | Unchanged |
| **Clock Drift** | `\|T_server - T_device\| > 300s` (5 minutes) | `SUSPICIOUS_CLOCK_DRIFT` | `HIGH` | `PENDING_REVIEW` |
| **Impossible Travel** | Velocity $v > 250\text{ m/s}$ (900 km/h) | `IMPOSSIBLE_TRAVEL_VELOCITY` | `HIGH` | `PENDING_REVIEW` |
| **Unregistered Device** | Device ID absent or not registered | `UNREGISTERED_DEVICE` | `MEDIUM` | Unchanged |
| **Revoked Device** | Device marked as `REVOKED` in database | `REVOKED_DEVICE` | `CRITICAL` | `PENDING_REVIEW` |

---

## 4. Sequential Travel Velocity Analysis Algorithm

The impossible-travel detection utilizes a spherical Great-Circle Haversine formula implemented in pure Python with unit tests validating accuracy:

$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1) \cdot \cos(\phi_2) \cdot \sin^2\left(\frac{\Delta \lambda}{2}\right)$$
$$c = 2 \cdot \operatorname{atan2}\left(\sqrt{a}, \sqrt{1 - a}\right)$$
$$d = R \cdot c \quad \text{where } R = 6,371,000 \text{ meters}$$
$$\text{Velocity } v = \frac{\Delta d}{\Delta t}$$

### Safeguards & Edge Cases Handled:
1. **Multi-Tenant & Employee Scoping:** Querying the previous punch is strictly scoped by `tenant_id` and `employee_id`. Punches from other employees or tenants never cross-pollinate.
2. **Missing Coordinates:** If either current or previous punch lacks GPS coordinates, velocity analysis returns `status = "SKIPPED"` without generating false flags.
3. **Zero Elapsed Time ($\Delta t = 0$):**
   - If $\Delta d \le 10\text{m}$: Treated as a duplicate or instantaneous punch at the same place; velocity set to $0.0\text{ m/s}$ (`is_impossible = False`).
   - If $\Delta d > 10\text{m}$: Instantaneous relocation flagged as impossible travel ($v = \infty$).
4. **Out-of-Order Punches ($\Delta t < 0$):** If an offline sync delivers an earlier timestamp than a recorded event, $\Delta t$ is evaluated using absolute time difference $|\Delta t|$ or marked out-of-order.
5. **Exact Boundary Checks:** $v = 250.0\text{ m/s}$ is tolerated; $v > 250.0\text{ m/s}$ triggers `IMPOSSIBLE_TRAVEL_VELOCITY`.

---

## 5. Offline Sync Transport Latency vs. True Clock Drift

To prevent false fraud flags during offline synchronization:
- When a client uploads a batched offline punch (`is_offline_sync = True`), the server reception time $T_{\text{server}}$ naturally lags the punch creation time $T_{\text{device}}$ (i.e., $T_{\text{server}} > T_{\text{device}}$ by minutes or hours).
- Milestone 7.2 evaluates positive drift ($T_{\text{server}} - T_{\text{device}} > 0$) on offline punches as legitimate transport latency, classifying the result as `status = "UNVERIFIED_OFFLINE"` without raising `SUSPICIOUS_CLOCK_DRIFT`.
- Conversely, if an offline punch claims a timestamp in the future ($T_{\text{device}} - T_{\text{server}} > 300\text{s}$), it is flagged as `SUSPICIOUS_CLOCK_DRIFT` regardless of the offline flag.

---

## 6. Attendance Engine Integration

In `services/api/attendance/service.py` (`record_punch`):
1. **Telemetry Evaluation:** Evaluates GPS evidence, clock drift, velocity vs. prior punch, and device binding (`validate_device_for_punch`).
2. **Review Status Elevation:** If any generated signal has severity `HIGH` or `CRITICAL`, the event's `review_status` is automatically set to `"PENDING_REVIEW"`.
3. **Forensic Metadata Persistence:** The resulting `metadata_json` dictionary embeds:
   - `fraud_signals`: List of all detected signals with type, severity, reason, and telemetry snapshots.
   - `velocity_analysis`: Previous event ID, distance, elapsed seconds, calculated velocity, and verdict.
   - `device_validation_status`: Device binding validation verdict and device ID hash.
4. **Model Population:** `is_mock_location` is persisted on the `AttendanceEvent` record and propagated to auto-break completion records when applicable.

---

## 7. Security Caveats & Limitations

> [!WARNING]
> **Client Telemetry Limitations & The Sandbox Asymmetry**
> 1. **Client Telemetry is Inherently Untrusted:** A rooted Android device or jailbroken iOS device with binary hooking (e.g. Frida, Xposed) can tamper with operating system APIs and report `is_mock_location = False` while injecting spoofed coordinates.
> 2. **OS Platform Differences:** Android exposes an explicit mock provider API (`isFromMockProvider()`), whereas iOS does not provide a direct mock location flag for third-party apps outside developer instrumentation modes.
> 3. **Defense-in-Depth:** GPS spoofing cannot be completely prevented via mobile client telemetry alone. True defense-in-depth requires multi-modal evidence correlation: server-side velocity cross-checks, device identifier hashing, office Wi-Fi BSSID validation, and geofencing.

---

## 8. Verification & Test Results

### 8.1 Milestone 7.2 Dedicated Test Suite
Created `tests/test_phase7_gps_spoofing_and_velocity.py` comprising 25 test cases across 5 test classes:
- `TestHaversineAndVelocity` (7 tests): Identical points, known distances, normal commutes, supersonic teleportation, boundary threshold (250 m/s), $\Delta t = 0$ same location, $\Delta t = 0$ different locations.
- `TestClockDriftEvaluation` (6 tests): Missing timestamp, within 300s, boundary at 300s, drift > 300s, offline upload transport delay tolerance, offline future timestamp detection.
- `TestGpsTelemetryAndMockDetection` (5 tests): Missing coordinates, mock location flag, false/none mock location, accuracy > 100m, fix age > 30s.
- `TestPreviousPunchFinder` (2 tests): Most recent coordinate retrieval, multi-tenant database isolation.
- `TestRecordPunchFraudIntegration` & `TestPunchAPIEndpointFraudTelemetry` (5 tests): Mock location review status promotion, clock drift review status promotion, HTTP API endpoint ingestion, velocity-triggered review status, unregistered device signal generation.

**Result:** `25 passed in 1.42s`.

### 8.2 Code Quality & Static Analysis
- **Ruff:** `All checks passed!` across `services/api/fraud/`, `services/api/attendance/`, and `tests/test_phase7_gps_spoofing_and_velocity.py`.
- **Mypy:** `Success: no issues found in 3 source files` (`services/api/fraud/`) and `Success: no issues found in 9 source files` (`services/api/attendance/`).

---

## 9. Next Steps (Milestone 7.3)

Milestone 7.2 provides the telemetry and velocity infrastructure. Future Milestone 7.3 will introduce:
- Comprehensive multi-signal risk-scoring engine (`fraud_rules` and `fraud_flags`).
- Configurable tenant-level risk score thresholds (e.g., Low, Medium, High risk scoring).
- HR manager manual review queue integration.

