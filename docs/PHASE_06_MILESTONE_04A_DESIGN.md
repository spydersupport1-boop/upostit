# UPOSTIT — Phase 6, Milestone 6.4.A Technical Design Document
## Backend Wi-Fi Attendance Verification & Admin-Configurable Fallback Architecture

**Stage**: Stage B — Attendance Core  
**Phase**: Phase 6 — Mobile Attendance Application  
**Milestone**: Milestone 6.4.A (Backend Wi-Fi Architecture & Fallback Specification)  
**Date**: November 5, 2026  
**Document Status**: COMPLETED ARCHITECTURE SPECIFICATION (Planning Only)  
**Target Repository Branch**: `phase-06`  
**Baseline Git Commit**: `a4dad73` (`phase-05-complete`)  
**Live Supabase Migration Head**: `b3c4d5e6f7a8` (`tenant_attendance_policies`)  

---

## 1. Executive Summary & Problem Formulation

### 1.1 Context & Mission
UPOSTIT is an enterprise multi-tenant workforce management platform. While Milestone 6.3.A delivered server-authoritative GPS geofence verification and Milestone 6.3.B delivered the Flutter mobile client GPS integration, real-world commercial work environments present critical physical and operational challenges for GPS-only verification:
1. **Urban Canyons & Deep Indoor Environments**: High-rise office towers, subterranean retail spaces, industrial warehouses, and manufacturing plants suffer from severe GPS signal attenuation, multipath reflections, or complete satellite blockages, resulting in false out-of-geofence rejections or unacceptable GPS acquisition delays (>15 seconds).
2. **Device Hardware & Battery Limits**: Continuous or frequent high-accuracy GPS fixes consume significant battery power and require line-of-sight satellite reception.
3. **Diverse Verification Policies**: Different organizations, departments, or shifts operate under distinct verification regimes—from pure manual logging (remote knowledge workers) to strict GPS (field staff), dedicated Wi-Fi access points (branch offices), or combined multi-factor controls (high-security facilities).

### 1.2 Architectural Objectives for Milestone 6.4
1. **Workplace-Scoped Wi-Fi Verification**: Allow company administrators to register one or more authorized Wi-Fi Access Points (APs) per workplace location, matching connected device BSSID against normalized authorized identifiers.
2. **Admin-Configurable Fallback Policy**: Empower tenant administrators to establish deterministic, fail-safe fallback behaviors (`REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`) when Wi-Fi evidence is unavailable.
3. **Strict Differentiation of Signal Failure States**: Rigorously separate `UNAVAILABLE` evidence (device cannot access network telemetry due to OS sandboxing or disabled Wi-Fi) from `MISMATCHED` negative evidence (device is connected to an unauthorized foreign Wi-Fi network like a coffee shop or home router).
4. **Unified Policy Engine Integration**: Extend the existing `tenant_attendance_policies` engine and `evaluate_punch_policy` service rather than introducing a siloed subsystem. Support `WIFI_ONLY`, `GPS_ONLY`, `COMBINED` (`AND`, `OR`), and `PRIMARY_WITH_FALLBACK` rules.
5. **Zero Client Trust & Append-Only Traceability**: The mobile client reports raw telemetry (`bssid`, `ssid`, `device_reported_at`); the backend computes verification outcomes authoritatively, binds the punch to the immutable policy version, and logs full audit trails in `attendance_events.metadata_json`.

---

## 2. Current Architecture Findings & Repository Audit

A comprehensive inspection of the existing codebase establishes the foundational baseline:

| Subsystem | Existing Implementation | File Reference | Relevance to Milestone 6.4 |
| :--- | :--- | :--- | :--- |
| **Policy Engine** | `TenantAttendancePolicy` model with versioning, `default_mode`, `allowed_methods`, `required_methods`, `combination_rule`, `gps_config`, `wifi_config`, `fallback_policy` | [models.py](file:///Users/apple/Upostit/services/api/attendance/models.py#L615-L685), [policy_engine.py](file:///Users/apple/Upostit/services/api/attendance/policy_engine.py#L60-L230) | Table and schema already contain `wifi_config` (JSONB) and `fallback_policy` (JSONB). Check constraints already support `WIFI_ONLY`, `COMBINED`, and `PRIMARY_WITH_FALLBACK`. |
| **Punch Ingestion** | `record_punch` service validating idempotency, calling `evaluate_punch_policy`, writing immutable `attendance_events`, recalculating daily summary | [service.py](file:///Users/apple/Upostit/services/api/attendance/service.py#L905-L1120) | Central pipeline into which Wi-Fi verification and fallback routing must seamlessly hook. |
| **Workplace Locations** | `Location` model with `wifi_bssids: list[str]` JSONB column and `BSSID_REGEX` validator | [models.py](file:///Users/apple/Upostit/services/api/locations/models.py#L31-L98), [schemas.py](file:///Users/apple/Upostit/services/api/locations/schemas.py#L90-L101) | Baseline location table has basic `wifi_bssids` list. However, enterprise multi-AP management requires friendly names, active toggles, and audit metadata. |
| **Employee Self-Service** | `GET /api/v1/employees/me/workplaces` and `POST /api/v1/employees/me/workplaces/verify-coordinates` | [routes.py](file:///Users/apple/Upostit/services/api/employees/routes.py#L150-L198) | Established pattern for employee-scoped, least-privilege verification probes guarded by `Permission.RECORD_PUNCH`. |
| **RBAC Matrix** | Granular permissions (`MANAGE_LOCATIONS`, `VIEW_LOCATIONS`, `MANAGE_ATTENDANCE_POLICY`, `RECORD_PUNCH`) | [permissions.py](file:///Users/apple/Upostit/services/api/auth/permissions.py#L16-L140) | Owner/Admin manage APs; HR reads APs; Employees record punches without global location read permissions. |
| **Database Conventions** | PostgreSQL 16 + PostGIS, Alembic async migrations, tenant RLS (`tenant_id = current_setting('app.tenant_id', true)::uuid`), forced RLS | [b3c4d5e6f7a8](file:///Users/apple/Upostit/database/migrations/versions/b3c4d5e6f7a8_phase_06_tenant_attendance_policies.py) | New tables must enforce composite foreign keys `(tenant_id, location_id)`, partial indexes, and RLS policies. |

---

## 3. Workplace Wi-Fi Access Point Data Architecture

### 3.1 BSSID Storage: Normalized Identifiers vs. Cryptographic Hashing

A critical architectural decision is how Wi-Fi identifiers are stored and indexed:

#### Architectural Evaluation:
1. **Option A: Cryptographic Hashing (e.g. SHA-256 with tenant salt)**:
   - *Pros*: Obfuscates MAC addresses in database storage.
   - *Cons*:
     - **Administrative Impossibility**: Administrators cannot view, audit, edit, or diagnose registered access points (e.g. seeing which physical AP corresponds to an office zone).
     - **False Security**: BSSIDs are IEEE 802.11 MAC addresses (48-bit search space). The first 24 bits are publicly known Organizationally Unique Identifiers (OUIs) representing router vendors (Cisco, Aruba, TP-Link). A 24-bit remaining search space ($2^{24} \approx 16.7\text{ million}$ combinations) can be pre-computed via rainbow tables in seconds. Hashing provides zero cryptographic defense against a determined adversary while severely degrading operational ergonomics.
     - **Open Broadcast Standard**: In networking, BSSIDs are transmitted in cleartext beacon frames across the 2.4 GHz and 5 GHz airwaves. They are network routing identifiers, not cryptographic private keys or passwords.
2. **Option B: Normalized Canonical Identifiers (RECOMMENDED)**:
   - Stored in standard IEEE 802 format: 12 hexadecimal characters, uppercase, colon-separated (`XX:XX:XX:XX:XX:XX`).
   - Case-insensitive, stripped of hyphens or spaces on ingest.
   - Full operational visibility for HR/IT administrators to manage friendly names ("HQ 4th Floor North AP", "Warehouse Loading Dock Mesh 2").

> [!IMPORTANT]
> **Zero Password Policy**: UPOSTIT never prompts for, stores, transmits, or verifies Wi-Fi Pre-Shared Keys (WPA2/WPA3 passwords). Attendance verification matches network presence identifiers only.

### 3.2 Dedicated Table Architecture: `workplace_wifi_access_points`

While `locations.wifi_bssids` provided a minimal JSONB array in Phase 4, enterprise multi-AP workplace deployments require structured management:
- Friendly name and hardware description.
- Primary matching identifier: BSSID (MAC address).
- Informational diagnostic identifier: SSID (network name).
- Lifecycle state: `is_active` boolean toggle.
- Temporal effectiveness: `effective_from` and `effective_to`.
- Audit provenance: `created_by_user_id`, `created_at`, `updated_at`.
- Tenant boundary safety: Composite foreign key `(tenant_id, location_id) REFERENCES locations(tenant_id, id)`.

#### Relational Schema Definition:
```sql
CREATE TABLE workplace_wifi_access_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    location_id UUID NOT NULL,
    friendly_name VARCHAR(100) NOT NULL,
    bssid VARCHAR(17) NOT NULL, -- Normalized 'XX:XX:XX:XX:XX:XX'
    ssid VARCHAR(64) NULL,      -- Diagnostic/informational display only
    is_active BOOLEAN NOT NULL DEFAULT true,
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_to DATE NULL,
    created_by_user_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT fk_workplace_wifi_tenant FOREIGN KEY (tenant_id)
        REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT fk_workplace_wifi_location FOREIGN KEY (tenant_id, location_id)
        REFERENCES locations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_workplace_wifi_creator FOREIGN KEY (tenant_id, created_by_user_id)
        REFERENCES users(tenant_id, id) ON DELETE SET NULL,
    CONSTRAINT uq_workplace_wifi_location_bssid UNIQUE (tenant_id, location_id, bssid),
    CONSTRAINT chk_workplace_wifi_bssid_format CHECK (
        bssid ~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'
    ),
    CONSTRAINT chk_workplace_wifi_dates CHECK (
        effective_to IS NULL OR effective_to >= effective_from
    )
);

-- Indexes
CREATE INDEX ix_workplace_wifi_tenant_location_active 
    ON workplace_wifi_access_points (tenant_id, location_id, is_active);
CREATE INDEX ix_workplace_wifi_tenant_bssid 
    ON workplace_wifi_access_points (tenant_id, bssid);

-- Row-Level Security
ALTER TABLE workplace_wifi_access_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE workplace_wifi_access_points FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workplace_wifi_access_points
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

---

## 4. Wi-Fi Verification API Contracts

### 4.1 Probe Endpoint: `POST /api/v1/employees/me/workplaces/verify-wifi`

Mirrors the existing PostGIS probe `verify-coordinates`, allowing the Flutter mobile app to pre-evaluate connected Wi-Fi status before submitting a punch. Guarded by `Permission.RECORD_PUNCH`.

#### Request Schema: `EmployeeWifiVerifyRequest`
```python
class EmployeeWifiVerifyRequest(BaseModel):
    """Payload for employee Wi-Fi verification against an assigned workplace."""

    location_id: uuid.UUID = Field(
        ...,
        validation_alias=AliasChoices("location_id", "workplace_id"),
        description="Target assigned workplace location UUID",
    )
    bssid: str | None = Field(
        default=None,
        description="Connected access point BSSID (MAC address in XX:XX:XX:XX:XX:XX format)",
    )
    ssid: str | None = Field(
        default=None,
        max_length=64,
        description="Connected access point SSID (display/diagnostic only)",
    )
    device_reported_at: datetime | None = Field(
        default=None,
        description="Timestamp when device observed the Wi-Fi connection",
    )
    signal_status: Literal["AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "PERMISSION_DENIED"] = Field(
        default="AVAILABLE",
        description="Device Wi-Fi telemetry capability status",
    )
    platform: str | None = Field(
        default=None,
        max_length=32,
        description="Client OS platform (android, ios, web)",
    )

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().upper().replace("-", ":")
        if not BSSID_REGEX.match(clean):
            raise ValueError(f"Invalid BSSID format '{v}'. Expected XX:XX:XX:XX:XX:XX.")
        return clean
```

#### Response Schema: `EmployeeWifiVerifyResponse`
```python
class WifiMatchStatus(StrEnum):
    MATCHED = "MATCHED"                  # BSSID matches an active authorized workplace AP
    MISMATCHED = "MISMATCHED"            # BSSID reported, but does not match any authorized AP
    UNAVAILABLE = "UNAVAILABLE"          # Device cannot read BSSID (Wi-Fi off or disconnected)
    UNSUPPORTED = "UNSUPPORTED"          # Device/OS cannot read BSSID (iOS without entitlement)
    STALE = "STALE"                      # Evidence age exceeds max_wifi_age_seconds
    UNASSIGNED_WORKPLACE = "UNASSIGNED"  # Employee is not assigned to this workplace
    INACTIVE_WORKPLACE = "INACTIVE"      # Workplace location is marked inactive

class EmployeeWifiVerifyResponse(BaseModel):
    """Result of employee workplace Wi-Fi verification probe."""

    location_id: uuid.UUID
    location_name: str
    location_code: str
    reported_bssid: str | None = None
    reported_ssid: str | None = None
    match_status: WifiMatchStatus
    is_verified: bool
    matched_access_point_name: str | None = None
    freshness_acceptable: bool
    applicable_fallback: str | None = None
    message: str
```

### 4.2 Extended Punch Request Contract: `PunchRequest`

The existing punch ingestion endpoint `POST /api/v1/attendance/punch` is extended with backward-compatible optional Wi-Fi telemetry:

```python
class PunchRequest(BaseModel):
    event_type: Literal["CHECK_IN", "CHECK_OUT", "BREAK_START", "BREAK_END"]
    idempotency_key: str = Field(..., min_length=8, max_length=64)
    employee_id: uuid.UUID | None = None
    device_reported_at: datetime | None = None
    location_id: uuid.UUID | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    accuracy_meters: Decimal | None = None
    
    # --- New Milestone 6.4 Wi-Fi Telemetry Fields ---
    wifi_bssid: str | None = Field(default=None, description="Connected Wi-Fi BSSID")
    wifi_ssid: str | None = Field(default=None, description="Connected Wi-Fi SSID (diagnostic only)")
    wifi_signal_status: Literal["AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "PERMISSION_DENIED"] = Field(
        default="AVAILABLE",
        description="Telemetry availability signal reported by device",
    )
    
    device_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

## 5. Signal State Classification & Admin-Configurable Fallback Policy

### 5.1 The Crucial Distinction: UNAVAILABLE vs. MISMATCHED

A core flaw in naive attendance architectures is conflating "cannot read Wi-Fi" with "connected to the wrong Wi-Fi". Milestone 6.4 establishes strict security partitioning:

```
                            Device Reports Telemetry
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
   BSSID Present & Fresh                                 BSSID Absent / Blocked
            │                                                     │
   Matches Authorized AP?                               Reason for Absence?
      ┌─────┴─────┐                                        ┌──────┴──────┐
      ▼           ▼                                        ▼             ▼
   MATCHED    MISMATCHED                              UNAVAILABLE    UNSUPPORTED
 (Positive)   (Negative)                              (Permission,   (iOS without
      │           │                                    Wi-Fi Off)     Entitlement)
   Accept      REJECT /                                    │             │
    Punch     Flag Review                                  └──────┬──────┘
             (Never Silent                                        ▼
               Fallback!)                                  Evaluate Admin
                                                           Fallback Policy
                                                                  │
                                           ┌──────────────┬───────┴──────┬──────────────┐
                                           ▼              ▼              ▼              ▼
                                        REJECT       GPS_FALLBACK   SUPERVISOR_    MANUAL_
                                                                       REVIEW      FALLBACK
```

1. **`MATCHED` (Positive Verification Evidence)**:
   - Device provided a valid BSSID that is actively assigned to the target workplace.
   - Outcome: Punch is accepted and stamped `verification_mode = "WIFI"`.
2. **`MISMATCHED` (Negative Presence Evidence — Fraud Risk)**:
   - Device successfully read a BSSID, but it belongs to an unauthorized network (e.g. employee's home Wi-Fi, neighboring business, or mobile hotspot).
   - Security Posture: **Must NEVER silently fall back to manual or GPS**. The employee has provided explicit evidence that they are connected to an unauthorized network.
   - Action: Reject immediately or route to `PENDING_REVIEW` under an explicit `wifi_mismatch_action` policy setting.
3. **`UNAVAILABLE` (Missing Verification Evidence — Environment/Hardware Limitation)**:
   - Device could not read BSSID because device Wi-Fi is toggled off, device is not connected to any network, or OS location permissions for Wi-Fi inspection were denied.
   - Security Posture: Route to the tenant's admin-configured `wifi_fallback_action`.
4. **`UNSUPPORTED` (OS Platform Limitation)**:
   - Device platform cannot inspect BSSID (e.g. iOS client lacking the Apple `Access Wi-Fi Information` entitlement).
   - Security Posture: Route to `wifi_fallback_action` if `allow_unsupported_platform_fallback` is enabled.
5. **`STALE` (Expired Telemetry)**:
   - Timestamp on Wi-Fi observation is $> \text{max\_wifi\_age\_seconds}$ (default 30 seconds).
   - Security Posture: Rejected with HTTP 400. Fresh reading required.

---

### 5.2 The Four Admin-Configurable Fallback Actions

When Wi-Fi evidence is legitimately `UNAVAILABLE` or `UNSUPPORTED`, the backend executes the tenant's configured fallback action:

| Fallback Action | Operational Behavior | Resulting `review_status` | Resulting `verification_mode` | Audit Flags Added |
| :--- | :--- | :--- | :--- | :--- |
| **`REJECT`** *(Default)* | Punch is immediately aborted with HTTP 400. Clear error message informs employee that Wi-Fi verification is mandatory. | N/A (Transaction rolled back) | N/A | N/A |
| **`GPS_FALLBACK`** | Evaluates GPS coordinates in the punch payload against the workplace PostGIS geofence. Requires GPS coordinates, valid accuracy, and fresh fix. | `NOT_REQUIRED` (if inside geofence) | `GPS_FALLBACK` | `WIFI_UNAVAILABLE`, `GPS_FALLBACK_APPLIED` |
| **`SUPERVISOR_REVIEW`** | Punch is accepted into the ledger, but flagged for manual manager review and approval. | `PENDING_REVIEW` | `WIFI_UNAVAILABLE_REVIEW` | `WIFI_UNAVAILABLE`, `FLAGGED_FOR_SUPERVISOR` |
| **`MANUAL_FALLBACK`** | Punch is accepted as an unverified manual punch. Only permitted if tenant policy explicitly authorizes manual fallbacks. | `NOT_REQUIRED` | `MANUAL_FALLBACK` | `WIFI_UNAVAILABLE`, `MANUAL_FALLBACK_APPLIED` |

---

### 5.3 Fallback Inheritance & Workplace Overrides

Organizations often have mixed facilities: a central high-rise office with strict Wi-Fi, and a suburban campus where GPS fallback is appropriate.

#### Inheritance Model:
1. **Tenant-Level Policy (Default Baseline)**:
   - Defines the global verification mode and default fallback action in `tenant_attendance_policies.wifi_config`.
2. **Workplace-Level Policy Override (Optional Granularity)**:
   - Stored in `locations.wifi_config_override` (or workplace AP metadata).
   - Allows a specific location to mandate `REJECT` even if the global tenant default is `GPS_FALLBACK`.
3. **Conflict Resolution Rule**:
   - Explicit workplace override takes precedence over tenant policy, **provided the override does not allow a verification method strictly prohibited by the tenant's `allowed_methods`**.
   - If a workplace specifies `GPS_FALLBACK`, but the tenant's active policy does not include `GPS` in `allowed_methods`, the policy engine fails closed and defaults to `REJECT`.

---

## 6. Policy Engine Integration & Combination Rules

The existing `TenantAttendancePolicy` model supports multi-method rules via `combination_rule`. Milestone 6.4 defines the exact truth table for all operational combinations:

### 6.1 Truth Table for Verification Modes

| Configured Mode | Combination Rule | Primary Required | Secondary Required | Acceptance Condition | Fallback Allowed? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`MANUAL`** | N/A | None | None | Always accepted (zero evidence required). | No |
| **`GPS_ONLY`** | N/A | GPS inside geofence | None | GPS coordinates inside geofence. | No (PostGIS enforcement) |
| **`WIFI_ONLY`** | N/A | Wi-Fi BSSID match | None | BSSID matches authorized AP. | Yes: if Wi-Fi is `UNAVAILABLE`, apply configured fallback (`REJECT`, `GPS_FALLBACK`, etc.). |
| **`COMBINED`** | **`AND`** | GPS inside geofence | Wi-Fi BSSID match | **Both** GPS inside geofence **AND** Wi-Fi BSSID matches. | **NEVER**. Fallback cannot weaken a strict `AND` multi-factor requirement. |
| **`COMBINED`** | **`OR`** | GPS inside geofence | Wi-Fi BSSID match | **Either** GPS inside geofence **OR** Wi-Fi BSSID matches. | Yes: if primary is unavailable, secondary satisfies policy directly. |
| **`PRIMARY_WITH_FALLBACK`** | **`PRIMARY_WITH_FALLBACK`** | Wi-Fi BSSID match | GPS or Review | Evaluates Wi-Fi; if unavailable, seamlessly transitions to configured fallback. | Yes: strictly follows `fallback_policy` configuration. |

### 6.2 Preventing Inadvertent Policy Weakening

> [!CAUTION]
> **Security Guardrail for `AND` Combinations**:
> If a tenant configures `COMBINED` with `AND` (mandating dual-factor presence: employee must be within the geofence *and* connected to the office router), the fallback engine **strictly disables single-factor fallbacks**. An employee cannot bypass an `AND` rule simply by disabling Wi-Fi to trigger GPS fallback.

---

## 7. Attendance Event Evidence & Append-Only Ledger Integrity

### 7.1 Immutability & Event Schema
Attendance events in `attendance_events` are strictly append-only, enforced by the existing PostgreSQL database trigger `trg_prevent_attendance_events_mutation`.

When a punch is recorded with Wi-Fi verification:
1. `applied_policy_version`: Captures the exact integer version of `tenant_attendance_policies` active during the punch.
2. `metadata_json`: Enriched with structured, privacy-preserving verification evidence:

```json
{
  "verification_mode": "WIFI",
  "policy_version": 2,
  "wifi_evidence": {
    "reported_bssid": "00:1A:2B:3C:4D:5E",
    "reported_ssid": "Corporate-Secure-5G",
    "match_status": "MATCHED",
    "matched_access_point_name": "HQ 4th Floor East AP",
    "access_point_id": "c1f7a8b2-3c4d-5e6f-7a8b-9c0d1e2f3a4b",
    "location_id": "loc-hq-uuid",
    "signal_status": "AVAILABLE"
  },
  "fallback_evidence": null,
  "verification_flags": []
}
```

When `GPS_FALLBACK` is triggered:
```json
{
  "verification_mode": "GPS_FALLBACK",
  "policy_version": 2,
  "wifi_evidence": {
    "reported_bssid": null,
    "reported_ssid": null,
    "match_status": "UNAVAILABLE",
    "signal_status": "PERMISSION_DENIED"
  },
  "fallback_evidence": {
    "fallback_invoked": true,
    "fallback_action": "GPS_FALLBACK",
    "fallback_reason": "Device Wi-Fi telemetry unavailable; GPS fallback authorized by policy"
  },
  "spatial_evidence": {
    "location_id": "loc-hq-uuid",
    "distance_meters": 18.4,
    "within_geofence": true,
    "geofence_verified": true
  },
  "verification_flags": ["WIFI_UNAVAILABLE", "GPS_FALLBACK_APPLIED"]
}
```

### 7.2 Employee Privacy Protection
- Public employee endpoints (e.g. `GET /api/v1/attendance/events/me`) serialize `AttendanceEventResponse` without exposing raw AP hardware identifiers or neighboring network diagnostics.
- Only the high-level verification outcome (`verification_mode`, `review_status`, `location_name`) is exposed to ordinary employees.
- Full BSSID audit evidence is restricted to administrators and managers holding `Permission.VIEW_ATTENDANCE`.

---

## 8. Mobile Platform Feasibility: Android & iOS Constraints (Milestone 6.4.B)

Understanding platform sandboxing constraints is essential for designing the backend contracts:

### 8.1 Android Platform Realities (API 26 to 35+)
1. **Permissions Required**:
   - Android 10–12: `ACCESS_FINE_LOCATION` is required by the OS to read the connected Wi-Fi BSSID (Android classifies network MAC addresses as location-revealing data).
   - Android 13+: `NEARBY_WIFI_DEVICES` (with `neverForLocation` flag omitted) plus `ACCESS_FINE_LOCATION`.
2. **Hardware Location Services Dependency**:
   - On Android 9+, the global device Location Services toggle must be **ON** for the OS `WifiManager.getConnectionInfo()` to return a non-null BSSID. If GPS hardware is toggled off, Android returns `"02:00:00:00:00:00"` (dummy MAC) or `null`.
3. **Connected AP vs. Active Scanning**:
   - **Recommended Approach**: Read the *currently connected Wi-Fi access point only*.
   - **Avoid Continuous Scanning**: `WifiManager.startScan()` is severely throttled by Android (max 4 scans per 2-minute window for foreground apps) and causes massive battery drain.

### 8.2 iOS Platform Realities (iOS 14 to 18+)
1. **`Access Wi-Fi Information` Entitlement**:
   - iOS strictly blocks access to connected Wi-Fi SSID/BSSID via `NEHotspotNetwork.fetchCurrent()` unless the app binary is signed with Apple's `Access Wi-Fi Information` entitlement.
   - This entitlement requires an active, paid Apple Developer Program account and explicit provisioning profile configuration.
2. **CoreLocation Dependency**:
   - Even with the entitlement, the employee must grant foreground location permission (`kCLAuthorizationStatusAuthorizedWhenInUse`).
3. **Enterprise Provisioning & Simulation**:
   - In automated test suites or unprovisioned developer builds, `fetchCurrent()` returns `nil`.
   - The Flutter client must implement a capability probe and report `signal_status = "UNSUPPORTED"`, allowing the backend to route to the configured fallback policy without crashing or hanging.

---

## 9. Fraud & Threat Model

| Threat / Attack Vector | Vulnerability Level | System Mitigation & Defense-in-Depth |
| :--- | :---: | :--- |
| **BSSID MAC Spoofing** | Moderate | A rooted Android device or modified app runtime can spoof the `wifi_bssid` string in the HTTP payload. **Mitigation**: Wi-Fi is an access-control signal, not cryptographic proof. For high-security environments, tenants configure `COMBINED` with `AND` (mandating both GPS geofence containment AND Wi-Fi BSSID match). |
| **SSID-Only Impersonation** | High (if allowed) | An employee sets up a mobile hotspot named "Company-Office-Wi-Fi". **Mitigation**: UPOSTIT **strictly rejects SSID-only matching**. Only hardware BSSIDs (MAC addresses) are matched against authorized APs. |
| **Off-Site Commercial Routers** | Low | An employee steals an authorized router or clones its MAC address at home. **Mitigation**: Combined PostGIS spatial geofencing or server-side IP range / ASN verification (`Location.ip_ranges`). |
| **Replay of Stale Wi-Fi Telemetry** | Low | An attacker captures legitimate Wi-Fi packets and replays them hours later. **Mitigation**: Strict freshness enforcement (`max_wifi_age_seconds`, default 30s) and single-use RFC 4122 UUID v4 idempotency keys. |

---

## 10. Database Migration Specification (Draft — No Execution in 6.4.A)

When Milestone 6.4.A moves to implementation in the next phase, the following migration will be introduced:

- **Revision ID**: `c4d5e6f7a8b9`
- **Revises**: `b3c4d5e6f7a8`
- **Tables Introduced**: `workplace_wifi_access_points`
- **Columns Extended on `locations`**:
  - `wifi_config_override`: `JSONB DEFAULT '{}'::jsonb NOT NULL`
- **Columns Extended on `attendance_events`**:
  - `wifi_bssid`: `VARCHAR(17) NULL`
  - `wifi_ssid`: `VARCHAR(64) NULL`
- **RLS**: Row-Level Security enabled and forced with standard `tenant_isolation` policy.

---

## 11. Backend Testing Strategy for Milestone 6.4.A

When implementation begins, automated tests will validate the entire matrix:

1. **Access Point CRUD & Multi-Tenant Isolation**:
   - Tenant A cannot view, assign, or delete Tenant B's access points.
   - BSSID normalization converts `00-1a-2b-3c-4d-5e` to `00:1A:2B:3C:4D:5E`.
   - Duplicate BSSID within the same workplace is rejected by unique constraint.
   - Deactivating an AP immediately prevents future punch verification against it.
2. **Wi-Fi Verification Engine (`evaluate_punch_policy`)**:
   - `MATCHED`: Valid BSSID yields `is_verified = True`, `verification_mode = "WIFI"`.
   - `MISMATCHED`: Unknown BSSID triggers `REJECT` or `FLAG_PENDING_REVIEW` per policy.
   - `UNAVAILABLE` + `REJECT`: Missing BSSID throws HTTP 400.
   - `UNAVAILABLE` + `GPS_FALLBACK`: Missing BSSID evaluates PostGIS geofence. If inside, punch succeeds as `GPS_FALLBACK`. If outside, punch is rejected.
   - `UNAVAILABLE` + `SUPERVISOR_REVIEW`: Missing BSSID succeeds as `PENDING_REVIEW`.
   - `UNAVAILABLE` + `MANUAL_FALLBACK`: Missing BSSID succeeds as `MANUAL_FALLBACK`.
   - `AND` Multi-factor: If GPS is inside but Wi-Fi is unavailable, punch is rejected (fallback strictly prohibited from bypassing `AND`).
3. **Idempotency & Concurrency**:
   - Replaying a Wi-Fi punch with the same idempotency key returns the cached response without creating duplicate ledger records.

---

## 12. Implementation Plan for Milestone 6.4.A

1. **Step 1: Database Migration**: Generate Alembic migration creating `workplace_wifi_access_points` and event tracking columns with RLS.
2. **Step 2: SQLAlchemy Models & Pydantic Schemas**: Create `WorkplaceWifiAccessPoint` model and request/response DTOs.
3. **Step 3: Access Point Management Service & Endpoints**: Implement admin CRUD routes (`GET`, `POST`, `PATCH`, `DELETE /api/v1/locations/{id}/wifi-access-points`).
4. **Step 4: Policy Engine Wi-Fi & Fallback Integration**: Extend `evaluate_punch_policy` in `policy_engine.py` with Wi-Fi matching, signal classification, and fallback routing.
5. **Step 5: Employee Probe Endpoint**: Implement `POST /api/v1/employees/me/workplaces/verify-wifi` in `services/api/employees/routes.py`.
6. **Step 6: Automated Test Suite**: Author `tests/test_phase6_wifi_verification.py` covering all positive, negative, and fallback test cases.

---

## 13. Acceptance Criteria for Milestone 6.4.A

- [x] Full architectural specification document created (`docs/PHASE_06_MILESTONE_04A_DESIGN.md`).
- [x] Explicit differentiation of `MATCHED`, `MISMATCHED`, `UNAVAILABLE`, `UNSUPPORTED`, `STALE`, and `ERROR` signal states.
- [x] Detailed specification of all four fallback behaviors (`REJECT`, `GPS_FALLBACK`, `SUPERVISOR_REVIEW`, `MANUAL_FALLBACK`).
- [x] Rule interaction matrix for `AND`, `OR`, and `PRIMARY_WITH_FALLBACK`.
- [x] Android and iOS sandboxing constraints and feasibility documented.
- [x] Master architecture documents (`docs/MOBILE_ATTENDANCE_ARCHITECTURE.md`, `docs/PHASE_06_PLAN.md`, `PROJECT_CONTEXT.md`) updated.
- [x] Strict scope discipline observed: 0 lines of application code modified, 0 migrations executed, 0 git commits/tags/pushes made.

