# UPOSTIT — Phase 7.3 Implementation Report: Fraud Rule Engine & Deterministic Risk Scoring

**Project:** UPOSTIT Workforce Attendance SaaS  
**Repository:** `/Users/apple/Upostit`  
**Branch:** `phase-06`  
**Milestone:** 7.3 — Fraud Rule Engine & Deterministic Risk Scoring  
**Status:** Completed & Validated  
**Date:** November 19, 2026  

---

## 1. Executive Summary

Milestone 7.3 establishes a centralized, backend-authoritative, tenant-configurable fraud rule engine and deterministic attendance risk-scoring subsystem within the UPOSTIT Workforce Attendance SaaS platform. 

Building upon the device binding subsystem (Milestone 7.1) and GPS mock/velocity telemetry (Milestone 7.2), this milestone introduces formal data modeling for configurable tenant fraud rules (`fraud_rules`) and immutable forensic evidence flags (`fraud_flags`). The risk engine deterministically evaluates incoming telemetry signals against tenant-configured weights and severities, computes a bounded risk score ($0 \dots 100$), assigns a risk category (`NORMAL`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `REQUIRES_REVIEW`), and triggers supervisor adjudication (`review_status = "PENDING_REVIEW"`) when thresholds are breached.

Additionally, device security has been strictly enforced: punches attempted from a revoked mobile device are actively rejected with `HTTP 403 Forbidden`, while historical records created prior to revocation remain permanently preserved in the immutable ledger.

---

## 2. Database Schema & Migration Architecture

### 2.1 Database Migration
- **Migration Script:** `database/migrations/versions/c5d6e7f8a9b0_phase_07_fraud_rules_and_flags.py`
- **Revision ID:** `c5d6e7f8a9b0`
- **Down Revision:** `b4c5d6e7f8a9` (Phase 7.2 mock location evidence)
- **Validation:** Both offline SQL upgrade and downgrade scripts were generated and verified.

### 2.2 Table: `fraud_rules`
Stores tenant-configurable detection rules, severity ratings, risk weights, and review requirements:

| Column | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, `gen_random_uuid()` | Unique rule identifier |
| `tenant_id` | `UUID` | FK `tenants.id` ON DELETE RESTRICT | Multi-tenant organization reference |
| `rule_code` | `VARCHAR(64)` | NOT NULL | Canonical code (e.g., `MOCK_LOCATION_DETECTED`) |
| `rule_name` | `VARCHAR(128)` | NOT NULL | Human-readable name |
| `description` | `TEXT` | Nullable | Explanatory description |
| `enabled` | `BOOLEAN` | DEFAULT `true`, NOT NULL | Active status toggle |
| `severity` | `VARCHAR(20)` | DEFAULT `'HIGH'`, NOT NULL | Enum: `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `risk_weight` | `INTEGER` | DEFAULT `25`, CHECK $0 \le w \le 100$ | Point contribution to risk score |
| `threshold_config` | `JSONB` | DEFAULT `'{}'`, NOT NULL | Threshold parameters (e.g. max meters) |
| `review_required` | `BOOLEAN` | DEFAULT `false`, NOT NULL | Forces `PENDING_REVIEW` when triggered |
| `created_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Audit creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Audit update timestamp |
| `created_by` | `UUID` | Composite FK `(tenant_id, users.id)` | Administrative creator user |
| `updated_by` | `UUID` | Composite FK `(tenant_id, users.id)` | Administrative last updater user |

- **Table Constraints:**
  - `uq_fraud_rules_tenant_rule_code`: `UNIQUE (tenant_id, rule_code)`
  - `uq_fraud_rules_tenant_id`: `UNIQUE (tenant_id, id)`
  - `chk_fraud_rules_severity`: `severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')`
  - `chk_fraud_rules_risk_weight`: `risk_weight >= 0 AND risk_weight <= 100`
- **Row-Level Security:** Enforced with `FORCE ROW LEVEL SECURITY` and policy `tenant_isolation` using `app.tenant_id`.

### 2.3 Table: `fraud_flags`
Maintains an immutable forensic audit trail of every suspicious signal triggered by an attendance punch:

| Column | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, `gen_random_uuid()` | Unique flag identifier |
| `tenant_id` | `UUID` | FK `tenants.id` ON DELETE RESTRICT | Organization scope |
| `attendance_event_id`| `UUID` | Composite FK `attendance_events(tenant_id, id)` | Target attendance event |
| `employee_id` | `UUID` | Composite FK `employees(tenant_id, id)` | Employee involved |
| `device_id` | `UUID` | Composite FK `devices(tenant_id, id)` | Device hardware record (nullable) |
| `rule_id` | `UUID` | Composite FK `fraud_rules(tenant_id, id)` | Configured rule matched (nullable) |
| `signal_code` | `VARCHAR(64)` | NOT NULL | Signal identifier |
| `severity` | `VARCHAR(20)` | NOT NULL | Effective severity rating |
| `risk_weight` | `INTEGER` | NOT NULL, CHECK $0 \le w \le 100$ | Risk points assigned |
| `description` | `TEXT` | NOT NULL | Human-readable forensic summary |
| `evidence_json` | `JSONB` | DEFAULT `'{}'`, NOT NULL | Telemetry snapshot and metrics |
| `detected_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Event detection timestamp |
| `created_at` | `TIMESTAMPTZ` | DEFAULT `now()`, NOT NULL | Persistence timestamp |

- **Table Constraints:**
  - `uq_fraud_flags_tenant_id`: `UNIQUE (tenant_id, id)`
  - `uq_fraud_flags_tenant_event_signal`: `UNIQUE (tenant_id, attendance_event_id, signal_code)` (prevents duplicate flags on idempotent replay)
  - `chk_fraud_flags_severity`: `severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')`
  - `chk_fraud_flags_risk_weight`: `risk_weight >= 0 AND risk_weight <= 100`
- **Indexes:**
  - `ix_fraud_flags_tenant_emp`: `(tenant_id, employee_id)`
  - `ix_fraud_flags_tenant_event`: `(tenant_id, attendance_event_id)`
  - `ix_fraud_flags_tenant_severity`: `(tenant_id, severity)`
  - `ix_fraud_flags_tenant_detected`: `(tenant_id, detected_at)`
  - `ix_fraud_flags_tenant_signal`: `(tenant_id, signal_code)`
- **Row-Level Security:** Enforced with `FORCE ROW LEVEL SECURITY` and policy `tenant_isolation` using `app.tenant_id`.

---

## 3. Initial Default Fraud Rules

Each organization is provisioned with 8 initial rules covering all Phase 7.2 signals:

| Rule Code | Rule Name | Default Severity | Default Weight | Review Required | Default Threshold Configuration |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `MOCK_LOCATION_DETECTED` | Mock Location Detection | `HIGH` | `40` | `True` | `{"allow_mock": false}` |
| `SUSPICIOUS_CLOCK_DRIFT` | Device Clock Skew | `HIGH` | `35` | `True` | `{"max_drift_seconds": 300.0}` |
| `IMPOSSIBLE_TRAVEL_VELOCITY`| Impossible Travel Velocity | `HIGH` | `50` | `True` | `{"max_velocity_mps": 250.0}` |
| `UNREGISTERED_DEVICE` | Unregistered Device | `MEDIUM` | `30` | `False` | `{}` |
| `DEVICE_MISMATCH` | Device Mismatch | `HIGH` | `40` | `True` | `{}` |
| `REVOKED_DEVICE` | Revoked Device Access | `CRITICAL` | `60` | `True` | `{}` |
| `POOR_GPS_ACCURACY` | Poor GPS Accuracy | `LOW` | `10` | `False` | `{"max_accuracy_meters": 100.0}` |
| `STALE_GPS_LOCATION` | Stale GPS Fix | `LOW` | `10` | `False` | `{"max_age_seconds": 30.0}` |

---

## 4. Deterministic Risk Scoring Algorithm

The risk assessment engine executes pure, repeatable arithmetic without heuristics or opaque ML scoring:

### 4.1 Deduplication & Matching
1. **Signal Normalization:** Alias signal codes (such as `REVOKED_DEVICE_ATTEMPT`) are normalized to their canonical rule codes (`REVOKED_DEVICE`).
2. **Event Deduplication:** Signals are deduplicated by normalized signal code. The same signal code is never counted twice for the same event.
3. **Rule Matching & Disabled Rules:** Each unique signal is matched against the tenant's configured `fraud_rules`.
   - If a matching rule is **disabled** (`enabled = false`), it contributes `0` points and generates no fraud flag.
   - If enabled, the rule's configured `severity`, `risk_weight`, and `review_required` are applied.
   - If no tenant override exists, standard default weights are used.

### 4.2 Score Calculation & Bounding
The total risk score $S$ is the bounded sum of all active flag weights:
$$S = \min\left(100, \max\left(0, \sum_{i \in \text{Flags}} w_i\right)\right)$$

### 4.3 Review Requirement Derivation
Review is explicitly required (`is_review_required = True`) if any of the following conditions hold:
- Any triggered rule has `review_required = True`.
- Any triggered flag has severity `CRITICAL`.
- Any triggered flag has severity `HIGH` and review is configured.
- Total risk score $S \ge 80$.

### 4.4 Risk Category Classification

$$\text{Category} = \begin{cases} 
\text{REQUIRES\_REVIEW} & \text{if } \text{is\_review\_required is True} \\
\text{NORMAL} & \text{if } S = 0 \\
\text{LOW\_RISK} & \text{if } 1 \le S \le 30 \\
\text{MEDIUM\_RISK} & \text{if } 31 \le S \le 60 \\
\text{HIGH\_RISK} & \text{if } 61 \le S \le 79 
\end{cases}$$

---

## 5. Attendance Engine Integration & Device Authorization

In `services/api/attendance/service.py` (`record_punch`):
1. **Strict Revoked Device Rejection:** Before recording any attendance punch, the supplied device ID is validated against `devices`. If `status == "REVOKED"`, the punch is immediately aborted with `HTTP 403 Forbidden` (`"Device registration has been revoked. Attendance punches are not authorized from this device."`).
2. **Unregistered Device Handling:** Attendance punches from unregistered devices are permitted to record (ensuring field workers are not silently stranded without presence records), but generate an `UNREGISTERED_DEVICE` flag ($+30$ risk points).
3. **Immutable Ledger Preservation:** The core `attendance_events` record is inserted with authoritative timestamps. Detailed risk telemetry is appended to `metadata_json`:
   - `risk_score`: Integer ($0 \dots 100$)
   - `risk_category`: String enum value
   - `fraud_flags`: List of signal codes applied
4. **Review Status Promotion:** If `risk_result.is_review_required` is True or `review_status` was already `"PENDING_REVIEW"` (due to policy violation or clock drift), `main_event.review_status` is guaranteed to be `"PENDING_REVIEW"`.
5. **Idempotent Replay Protection:** If an attendance punch with an existing idempotency key is replayed, the cached response is returned without generating duplicate `fraud_flags`.

---

## 6. Tenant Rule Management & Flag Retrieval APIs

All endpoints are registered under `/api/v1/fraud`:

| Method | Path | Required Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/fraud/rules` | `VIEW_FRAUD_RULES` | List tenant rules with optional `?enabled=` filter |
| `GET` | `/api/v1/fraud/rules/{id}` | `VIEW_FRAUD_RULES` | Get rule details by UUID |
| `POST` | `/api/v1/fraud/rules` | `MANAGE_FRAUD_RULES` | Create custom or override fraud rule (201) |
| `PATCH` | `/api/v1/fraud/rules/{id}` | `MANAGE_FRAUD_RULES` | Update rule weights, severity, and review toggle |
| `POST` | `/api/v1/fraud/rules/{id}/enable` | `MANAGE_FRAUD_RULES` | Enable a disabled fraud rule |
| `POST` | `/api/v1/fraud/rules/{id}/disable` | `MANAGE_FRAUD_RULES` | Disable a fraud rule |
| `GET` | `/api/v1/fraud/flags` | `VIEW_FRAUD_FLAGS` | Paginated forensic flags with employee, event, severity, and date filters |

### Granular RBAC Mapping
- `Owner`, `Admin`, and `HR` roles possess `MANAGE_FRAUD_RULES`, `VIEW_FRAUD_RULES`, and `VIEW_FRAUD_FLAGS`.
- `Manager` role possesses `VIEW_FRAUD_FLAGS` (read-only flag visibility for supervised staff).
- `Employee` role is denied (`HTTP 403 Forbidden`) across all rule and flag endpoints.

---

## 7. Verification & Automated Test Results

### 7.1 Dedicated Milestone 7.3 Test Suite
Authored [tests/test_phase7_fraud_rules_and_risk_scoring.py](file:///Users/apple/Upostit/tests/test_phase7_fraud_rules_and_risk_scoring.py) comprising 25 test cases across 4 test classes:
- `TestFraudRuleConfiguration` (6 tests): Default rule seeding (8 rules), custom rule creation, duplicate rule_code 409 conflict, rule updates with audit fields, enable/disable toggling, multi-tenant isolation.
- `TestDeterministicRiskEngine` (10 tests): Zero-signal baseline (score=0, NORMAL), single low-risk signal (score=10, LOW_RISK), multi-signal additive scoring (score=50, MEDIUM_RISK), high-risk signal review promotion (score=40, REQUIRES_REVIEW), critical signal review promotion, disabled rule score exclusion, duplicate signal deduplication, score bounding at 100, score $\ge 80$ mandatory review, repeated calculation determinism.
- `TestAttendancePunchFraudIntegration` (3 tests): Revoked device rejection (HTTP 403 Forbidden), unregistered device punch allowed with fraud flag, idempotent punch replay avoiding duplicate flags.
- `TestFraudAPIEndpoints` (6 tests): Admin list rules (200), admin create rule (201), admin update & toggle rule (200), employee denied rule management (403), manager list flags with severity filter (200), employee denied flag retrieval (403).

**Result:** `25 passed in 1.54s`.

### 7.2 Combined Phase 7 Regression Pass
Ran all Phase 7 test suites:
- `tests/test_phase7_devices.py`: 32 passed
- `tests/test_phase7_gps_spoofing_and_velocity.py`: 25 passed
- `tests/test_phase7_fraud_rules_and_risk_scoring.py`: 25 passed
**Combined Phase 7 Total:** **82 / 82 Passed (100%) in 1.75s**.

### 7.3 Code Quality & Static Analysis
- **Ruff:** `All checks passed!` across `services/api/fraud/`, `services/api/attendance/`, and `tests/test_phase7_fraud_rules_and_risk_scoring.py`.
- **Mypy:** `Success: no issues found in 7 source files` (`services/api/fraud/`) and `Success: no issues found in 9 source files` (`services/api/attendance/`).

---

## 8. Known Limitations & Strict Boundaries

1. **Client Telemetry Untrusted:** As documented in Phase 7.2, client mock flags and timestamps are advisory evidence. The deterministic risk engine evaluates client evidence server-side, but physical correlation (Wi-Fi access points, geofencing, hardware device hashes) remains essential.
2. **Human HR Adjudication Mandatory:** Risk scores and fraud flags are strictly advisory to assist HR supervisors. The system **never** automatically fires, fines, or deactivates an employee based on a risk score.
3. **No Machine Learning:** In accordance with roadmap specifications, Phase 7 uses deterministic rule-based scoring. Probabilistic ML anomaly detection is strictly deferred to Phase 19.
4. **Deferred to Milestone 7.4:** The full HR administrative review queue and decision resolution workflows (`APPROVED` / `REJECTED` with audit reasons) belong to Milestone 7.4.

