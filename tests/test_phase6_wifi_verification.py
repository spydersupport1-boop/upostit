"""Comprehensive tests for Phase 6 Milestone 6.4.A:
Backend Wi-Fi Attendance Verification & Admin-Configurable Fallback.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import (
    TenantAttendancePolicy,
)
from services.api.attendance.policy_engine import (
    evaluate_punch_policy,
    verify_employee_wifi,
)
from services.api.attendance.schemas import (
    EmployeeWifiVerifyRequest,
    PunchRequest,
    WifiMatchStatus,
)
from services.api.attendance.service import compute_request_fingerprint
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.locations.models import EmployeeLocation, Location, WorkplaceWifiAccessPoint
from services.api.locations.schemas import (
    WorkplaceWifiAccessPointCreateRequest,
    WorkplaceWifiAccessPointUpdateRequest,
)
from services.api.locations.wifi_service import (
    create_workplace_wifi_access_point,
    deactivate_workplace_wifi_access_point,
    update_workplace_wifi_access_point,
)
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _mock_context(
    role: str,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"test_{role.lower()}@company.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Wi-Fi Corp",
        slug=f"wifi-{tid.hex[:6]}",
        company_email="admin@wifi.test",
        country_code="IN",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _create_mock_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Employee:
    return Employee(
        id=employee_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid.uuid4(),
        employee_id="EMP-WIFI-001",
        first_name="Bob",
        last_name="Network",
        work_email="bob.network@wifi.test",
        employment_type="full_time",
        status="active",
    )


def _create_mock_location(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    name: str = "Engineering Office",
    code: str = "ENG-HQ",
    latitude: Decimal = Decimal("12.9715987"),
    longitude: Decimal = Decimal("77.5945627"),
    radius_meters: int = 100,
    is_active: bool = True,
    wifi_config_override: dict | None = None,
) -> Location:
    return Location(
        id=location_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        code=code,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        is_active=is_active,
        wifi_config_override=wifi_config_override or {},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _create_mock_access_point(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    ap_id: uuid.UUID | None = None,
    friendly_name: str = "HQ 4th Floor Main AP",
    bssid: str = "00:1A:2B:3C:4D:5E",
    ssid: str = "Corp-Secure-5G",
    is_active: bool = True,
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> WorkplaceWifiAccessPoint:
    return WorkplaceWifiAccessPoint(
        id=ap_id or uuid.uuid4(),
        tenant_id=tenant_id,
        location_id=location_id,
        friendly_name=friendly_name,
        bssid=bssid,
        ssid=ssid,
        is_active=is_active,
        effective_from=effective_from or date.today() - timedelta(days=10),
        effective_to=effective_to,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ==============================================================================
# Unit Tests: Workplace Wi-Fi Access Point Service & DTOs
# ==============================================================================


@pytest.mark.asyncio
async def test_bssid_normalization_and_validation():
    """Verify BSSID format validator accepts standard variations and normalizes to uppercase colons."""
    # Hyphens to colons & lower to uppercase
    req = WorkplaceWifiAccessPointCreateRequest(
        friendly_name="AP 1",
        bssid="00-1a-2b-3c-4d-5e",
        ssid="TestNet",
    )
    assert req.bssid == "00:1A:2B:3C:4D:5E"

    # Invalid length/format rejected
    with pytest.raises(ValueError):
        WorkplaceWifiAccessPointCreateRequest(
            friendly_name="Bad AP",
            bssid="INVALID_BSSID",
        )

    # Date validation: effective_to < effective_from rejected
    with pytest.raises(ValueError):
        WorkplaceWifiAccessPointCreateRequest(
            friendly_name="Bad Dates",
            bssid="00:11:22:33:44:55",
            effective_from=date(2026, 12, 1),
            effective_to=date(2026, 11, 1),
        )


@pytest.mark.asyncio
async def test_create_workplace_wifi_access_point_service():
    """Verify AP creation checks location existence and rejects duplicate BSSID."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_session = AsyncMock()

    # 1. Location exists, no duplicate BSSID
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc_id
    mock_dup_res = MagicMock()
    mock_dup_res.scalar_one_or_none.return_value = None
    mock_session.execute.side_effect = [mock_loc_res, mock_dup_res]

    create_data = WorkplaceWifiAccessPointCreateRequest(
        friendly_name="Zone A Router",
        bssid="AA:BB:CC:DD:EE:01",
        ssid="CorpNet",
    )
    ap = await create_workplace_wifi_access_point(
        session=mock_session,
        tenant_id=tenant_id,
        location_id=loc_id,
        user_id=user_id,
        data=create_data,
    )
    assert ap.bssid == "AA:BB:CC:DD:EE:01"
    assert ap.friendly_name == "Zone A Router"
    assert ap.is_active is True

    # 2. Duplicate BSSID rejected with 409
    mock_session.execute.side_effect = [mock_loc_res, mock_loc_res]  # second query finds duplicate
    with pytest.raises(HTTPException) as exc_info:
        await create_workplace_wifi_access_point(
            session=mock_session,
            tenant_id=tenant_id,
            location_id=loc_id,
            user_id=user_id,
            data=create_data,
        )
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "already registered" in exc_info.value.detail


@pytest.mark.asyncio
async def test_deactivate_workplace_wifi_access_point_soft_deletes():
    """Verify deactivation sets is_active to False without deleting row."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    mock_ap = _create_mock_access_point(tenant_id, loc_id, is_active=True)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_ap
    mock_session.execute.return_value = mock_res

    updated_ap = await deactivate_workplace_wifi_access_point(
        session=mock_session,
        tenant_id=tenant_id,
        location_id=loc_id,
        ap_id=mock_ap.id,
    )
    assert updated_ap.is_active is False


# ==============================================================================
# Unit Tests: Employee Wi-Fi Verification Probe Endpoint
# ==============================================================================


@pytest.mark.asyncio
async def test_verify_employee_wifi_matched():
    """Verify probe returns MATCHED when connected BSSID is in authorized APs."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(tenant_id, location_id=loc_id)
    ap = _create_mock_access_point(tenant_id, loc_id, bssid="00:1A:2B:3C:4D:5E")
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    # Mock execute returns:
    # 1. emp_stmt -> emp
    # 2. assignment_stmt -> assignment
    # 3. loc_stmt -> loc
    # 4. policy_stmt -> default policy
    # 5. ap_stmt -> ap
    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp
    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_policy_res = MagicMock()
    mock_policy_res.scalar_one_or_none.return_value = None  # fallback policy
    mock_ap_res = MagicMock()
    mock_ap_res.scalar_one_or_none.return_value = ap

    mock_session.execute.side_effect = [
        mock_emp_res,
        mock_assign_res,
        mock_loc_res,
        mock_policy_res,
        mock_ap_res,
    ]

    req = EmployeeWifiVerifyRequest(
        location_id=loc_id,
        bssid="00:1A:2B:3C:4D:5E",
        ssid="Corp-Secure-5G",
        signal_status="AVAILABLE",
        device_reported_at=datetime.now(UTC),
    )

    resp = await verify_employee_wifi(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        req=req,
    )
    assert resp.match_status == WifiMatchStatus.MATCHED
    assert resp.is_verified is True
    assert resp.matched_access_point_name == ap.friendly_name
    assert resp.freshness_acceptable is True


@pytest.mark.asyncio
async def test_verify_employee_wifi_mismatched():
    """Verify probe returns MISMATCHED when device connects to unauthorized router."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp
    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_policy_res = MagicMock()
    mock_policy_res.scalar_one_or_none.return_value = None
    mock_ap_res = MagicMock()
    mock_ap_res.scalar_one_or_none.return_value = None  # No matching AP

    mock_session.execute.side_effect = [
        mock_emp_res,
        mock_assign_res,
        mock_loc_res,
        mock_policy_res,
        mock_ap_res,
    ]

    req = EmployeeWifiVerifyRequest(
        location_id=loc_id,
        bssid="99:88:77:66:55:44",
        ssid="Home-Wifi-Unauthorized",
        signal_status="AVAILABLE",
    )

    resp = await verify_employee_wifi(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        req=req,
    )
    assert resp.match_status == WifiMatchStatus.MISMATCHED
    assert resp.is_verified is False
    assert resp.matched_access_point_name is None


@pytest.mark.asyncio
async def test_verify_employee_wifi_unavailable_and_unsupported():
    """Verify probe returns UNAVAILABLE or UNSUPPORTED with applicable fallback action."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(
        tenant_id,
        location_id=loc_id,
        wifi_config_override={"fallback_action": "GPS_FALLBACK"},
    )
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp
    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_policy_res = MagicMock()
    mock_policy_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_emp_res,
        mock_assign_res,
        mock_loc_res,
        mock_policy_res,
    ]

    # Device on iOS without entitlement -> UNSUPPORTED
    req = EmployeeWifiVerifyRequest(
        location_id=loc_id,
        bssid=None,
        signal_status="UNSUPPORTED",
    )
    resp = await verify_employee_wifi(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        req=req,
    )
    assert resp.match_status == WifiMatchStatus.UNSUPPORTED
    assert resp.is_verified is False
    assert resp.applicable_fallback == "GPS_FALLBACK"


# ==============================================================================
# Policy Engine Tests: Wi-Fi Matching, Negative Evidence & Fallbacks
# ==============================================================================


@pytest.mark.asyncio
async def test_punch_policy_wifi_only_positive():
    """Verify WIFI_ONLY punch succeeds with authorized BSSID."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    ap = _create_mock_access_point(tenant_id, loc_id, bssid="00:1A:2B:3C:4D:5E")
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"fallback_action": "REJECT"},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_ap_res = MagicMock()
    mock_ap_res.scalar_one_or_none.return_value = ap

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
        mock_ap_res,
    ]

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        device_reported_at=datetime.now(UTC),
        active_policy=policy,
        wifi_bssid="00:1A:2B:3C:4D:5E",
        wifi_ssid="CorpNet",
        wifi_signal_status="AVAILABLE",
    )

    assert outcome.is_verified is True
    assert outcome.verification_mode == "WIFI"
    assert outcome.review_status == "NOT_REQUIRED"
    assert outcome.wifi_evidence["match_status"] == "MATCHED"


@pytest.mark.asyncio
async def test_punch_policy_wifi_mismatched_negative_presence_rejected():
    """Verify connecting to an unauthorized Wi-Fi router is strictly rejected."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI", "GPS"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"mismatch_action": "REJECT"},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_ap_res = MagicMock()
    mock_ap_res.scalar_one_or_none.return_value = None  # Mismatched router

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
        mock_ap_res,
    ]

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=Decimal("12.9715987"),
            longitude=Decimal("77.5945627"),
            accuracy_meters=Decimal("10"),
            device_reported_at=datetime.now(UTC),
            active_policy=policy,
            wifi_bssid="AA:BB:CC:99:88:77",
            wifi_ssid="Rogue-Hotspot",
            wifi_signal_status="AVAILABLE",
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "not an authorized access point" in exc_info.value.detail


@pytest.mark.asyncio
async def test_punch_policy_wifi_gps_fallback_applied_when_inside_geofence():
    """Verify GPS_FALLBACK is seamlessly applied when Wi-Fi is unavailable and GPS is inside."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI", "GPS"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"fallback_action": "GPS_FALLBACK"},
        gps_config={"max_accuracy_meters": 100, "max_location_age_seconds": 30},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc

    # Mock spatial query returning inside geofence (dist: 12.5m, within: True)
    mock_spatial_row = (loc_id, loc.name, loc.code, 100, loc.latitude, loc.longitude, 12.5, True)
    mock_spatial_res = MagicMock()
    mock_spatial_res.first.return_value = mock_spatial_row

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
        mock_spatial_res,
    ]

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("15"),
        device_reported_at=datetime.now(UTC),
        active_policy=policy,
        wifi_bssid=None,  # Telemetry unavailable
        wifi_signal_status="UNAVAILABLE",
    )

    assert outcome.is_verified is True
    assert outcome.verification_mode == "GPS_FALLBACK"
    assert "GPS_FALLBACK_APPLIED" in outcome.verification_flags
    assert outcome.fallback_evidence["fallback_action"] == "GPS_FALLBACK"


@pytest.mark.asyncio
async def test_punch_policy_supervisor_review_fallback():
    """Verify SUPERVISOR_REVIEW fallback accepts punch as PENDING_REVIEW."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"fallback_action": "SUPERVISOR_REVIEW"},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
    ]

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        device_reported_at=datetime.now(UTC),
        active_policy=policy,
        wifi_bssid=None,
        wifi_signal_status="UNAVAILABLE",
    )

    assert outcome.is_verified is False
    assert outcome.review_status == "PENDING_REVIEW"
    assert outcome.verification_mode == "WIFI_UNAVAILABLE_REVIEW"
    assert "FLAGGED_FOR_SUPERVISOR" in outcome.verification_flags


@pytest.mark.asyncio
async def test_punch_policy_manual_fallback():
    """Verify MANUAL_FALLBACK succeeds when authorized by allowed_methods."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI", "MANUAL"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"fallback_action": "MANUAL_FALLBACK"},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
    ]

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        device_reported_at=datetime.now(UTC),
        active_policy=policy,
        wifi_bssid=None,
        wifi_signal_status="UNAVAILABLE",
    )

    assert outcome.is_verified is True
    assert outcome.verification_mode == "MANUAL_FALLBACK"
    assert outcome.review_status == "NOT_REQUIRED"
    assert "MANUAL_FALLBACK_APPLIED" in outcome.verification_flags


# ==============================================================================
# Security Guardrail Tests: AND & Workplace Overrides
# ==============================================================================


@pytest.mark.asyncio
async def test_punch_policy_combined_and_guardrail_prevents_fallback():
    """Verify dual-factor AND policy strictly prevents fallback when Wi-Fi is unavailable."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    loc = _create_mock_location(tenant_id, location_id=loc_id)
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    # Policy mandating COMBINED with AND
    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=3,
        is_active=True,
        default_mode="COMBINED",
        allowed_methods=["GPS", "WIFI"],
        required_methods=["GPS", "WIFI"],
        combination_rule="AND",
        wifi_config={"fallback_action": "GPS_FALLBACK"},  # Attempted bypass
        gps_config={"max_accuracy_meters": 100},
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
    ]

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=Decimal("12.9715987"),
            longitude=Decimal("77.5945627"),
            accuracy_meters=Decimal("10"),
            device_reported_at=datetime.now(UTC),
            active_policy=policy,
            wifi_bssid=None,  # Wi-Fi turned off by employee
            wifi_signal_status="UNAVAILABLE",
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Fallback is disabled for AND rules" in exc_info.value.detail


@pytest.mark.asyncio
async def test_punch_policy_location_level_override_precedence():
    """Verify workplace-level override in locations.wifi_config_override takes precedence over tenant policy."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    # Location strictly mandates REJECT even though tenant default is MANUAL_FALLBACK
    loc = _create_mock_location(
        tenant_id,
        location_id=loc_id,
        wifi_config_override={"fallback_action": "REJECT"},
    )
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI", "MANUAL"],
        required_methods=["WIFI"],
        combination_rule="OR",
        wifi_config={"fallback_action": "MANUAL_FALLBACK"},  # Tenant allows manual fallback
        created_at=datetime.now(UTC),
    )

    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc

    mock_session.execute.side_effect = [
        mock_assign_res,
        mock_loc_res,
    ]

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=None,
            longitude=None,
            accuracy_meters=None,
            device_reported_at=datetime.now(UTC),
            active_policy=policy,
            wifi_bssid=None,
            wifi_signal_status="UNAVAILABLE",
        )
    # The location's REJECT override took precedence!
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Wi-Fi verification required" in exc_info.value.detail


# ==============================================================================
# End-to-End API Integration Tests via AsyncClient
# ==============================================================================


@pytest.mark.asyncio
async def test_api_admin_can_manage_wifi_access_points():
    """Verify company administrator can CRUD workplace Wi-Fi access points."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    admin_ctx = _mock_context("admin", tenant_id, user_id)
    mock_session = AsyncMock()

    ap = _create_mock_access_point(tenant_id, loc_id, bssid="00:1A:2B:3C:4D:5E")

    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc_id
    mock_dup_res = MagicMock()
    mock_dup_res.scalar_one_or_none.return_value = None
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1
    mock_list_res = MagicMock()
    mock_list_res.scalars.return_value.all.return_value = [ap]

    mock_session.execute.side_effect = [
        mock_loc_res,
        mock_dup_res,
        mock_loc_res,
        mock_count_res,
        mock_list_res,
    ]

    async def override_get_authenticated_context():
        return admin_ctx

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_authenticated_context] = override_get_authenticated_context
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register AP
            post_resp = await client.post(
                f"/api/v1/locations/{loc_id}/wifi-access-points",
                json={
                    "friendly_name": "Main Office AP",
                    "bssid": "00:1A:2B:3C:4D:5E",
                    "ssid": "Corp-5G",
                },
            )
            assert post_resp.status_code == status.HTTP_201_CREATED
            data = post_resp.json()
            assert data["bssid"] == "00:1A:2B:3C:4D:5E"
            assert data["friendly_name"] == "Main Office AP"

            # 2. List APs
            list_resp = await client.get(
                f"/api/v1/locations/{loc_id}/wifi-access-points",
            )
            assert list_resp.status_code == status.HTTP_200_OK
            list_data = list_resp.json()
            assert list_data["total"] == 1
            assert len(list_data["items"]) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_employee_wifi_probe_endpoint():
    """Verify employee can probe their Wi-Fi connection status via API."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_ctx = _mock_context("employee", tenant_id, user_id)
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, user_id=user_id)
    loc = _create_mock_location(tenant_id, location_id=loc_id)
    ap = _create_mock_access_point(tenant_id, loc_id, bssid="00:1A:2B:3C:4D:5E")
    assignment = EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp.id,
        location_id=loc_id,
        effective_from=date.today() - timedelta(days=1),
    )

    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp
    mock_assign_res = MagicMock()
    mock_assign_res.scalar_one_or_none.return_value = assignment
    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc
    mock_policy_res = MagicMock()
    mock_policy_res.scalar_one_or_none.return_value = None
    mock_ap_res = MagicMock()
    mock_ap_res.scalar_one_or_none.return_value = ap

    mock_session.execute.side_effect = [
        mock_emp_res,
        mock_assign_res,
        mock_loc_res,
        mock_policy_res,
        mock_ap_res,
    ]

    async def override_get_authenticated_context():
        return emp_ctx

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_authenticated_context] = override_get_authenticated_context
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/employees/me/workplaces/verify-wifi",
                json={
                    "location_id": str(loc_id),
                    "bssid": "00:1A:2B:3C:4D:5E",
                    "ssid": "Corp-5G",
                    "signal_status": "AVAILABLE",
                },
            )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["match_status"] == "MATCHED"
            assert data["is_verified"] is True
            assert data["matched_access_point_name"] == ap.friendly_name
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Regression Tests for Audit Fixes: AP Persistence & Idempotency Fingerprint
# ==============================================================================


@pytest.mark.asyncio
async def test_create_workplace_wifi_access_point_commits_and_refreshes():
    """Fix 1: Verify create_workplace_wifi_access_point commits transaction to persist."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_session = AsyncMock()

    mock_loc_res = MagicMock()
    mock_loc_res.scalar_one_or_none.return_value = loc_id
    mock_dup_res = MagicMock()
    mock_dup_res.scalar_one_or_none.return_value = None
    mock_session.execute.side_effect = [mock_loc_res, mock_dup_res]

    create_data = WorkplaceWifiAccessPointCreateRequest(
        friendly_name="Zone A Router",
        bssid="AA:BB:CC:DD:EE:01",
        ssid="CorpNet",
    )
    ap = await create_workplace_wifi_access_point(
        session=mock_session,
        tenant_id=tenant_id,
        location_id=loc_id,
        user_id=user_id,
        data=create_data,
    )
    assert ap.bssid == "AA:BB:CC:DD:EE:01"
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(ap)


@pytest.mark.asyncio
async def test_update_workplace_wifi_access_point_commits_and_refreshes():
    """Fix 1: Verify update_workplace_wifi_access_point commits transaction to persist."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    ap_id = uuid.uuid4()
    mock_session = AsyncMock()

    existing_ap = _create_mock_access_point(tenant_id, loc_id, ap_id=ap_id, friendly_name="Old Name")
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_ap
    mock_session.execute.return_value = mock_res

    update_data = WorkplaceWifiAccessPointUpdateRequest(
        friendly_name="Updated Router Name",
        ssid="New-SSID",
    )
    updated_ap = await update_workplace_wifi_access_point(
        session=mock_session,
        tenant_id=tenant_id,
        location_id=loc_id,
        ap_id=ap_id,
        data=update_data,
    )
    assert updated_ap.friendly_name == "Updated Router Name"
    assert updated_ap.ssid == "New-SSID"
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(updated_ap)


@pytest.mark.asyncio
async def test_deactivate_workplace_wifi_access_point_commits_and_refreshes():
    """Fix 1: Verify deactivate_workplace_wifi_access_point commits transaction to persist."""
    tenant_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    ap_id = uuid.uuid4()
    mock_session = AsyncMock()

    existing_ap = _create_mock_access_point(tenant_id, loc_id, ap_id=ap_id, is_active=True)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_ap
    mock_session.execute.return_value = mock_res

    deactivated_ap = await deactivate_workplace_wifi_access_point(
        session=mock_session,
        tenant_id=tenant_id,
        location_id=loc_id,
        ap_id=ap_id,
    )
    assert deactivated_ap.is_active is False
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(deactivated_ap)


@pytest.mark.asyncio
async def test_fingerprint_includes_wifi_evidence_deterministically():
    """Fix 2: Verify same idempotency key + identical Wi-Fi evidence computes identical fingerprint."""
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    req1 = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-wifi-123",
        location_id=loc_id,
        wifi_bssid="aa:bb:cc:dd:ee:01",
        wifi_ssid="CorpNet",
        wifi_signal_status="AVAILABLE",
    )
    req2 = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-wifi-123",
        location_id=loc_id,
        wifi_bssid="AA:BB:CC:DD:EE:01",  # Uppercase format
        wifi_ssid="CorpNet",
        wifi_signal_status="AVAILABLE",
    )
    fp1 = compute_request_fingerprint(req1, emp_id)
    fp2 = compute_request_fingerprint(req2, emp_id)
    assert fp1 == fp2
    assert len(fp1) == 64


@pytest.mark.asyncio
async def test_fingerprint_changes_on_changed_bssid():
    """Fix 2: Verify changing Wi-Fi BSSID produces a different fingerprint (preventing silent replay)."""
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    base_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-wifi-123",
        location_id=loc_id,
        wifi_bssid="AA:BB:CC:DD:EE:01",
        wifi_ssid="CorpNet",
        wifi_signal_status="AVAILABLE",
    )
    base_fp = compute_request_fingerprint(base_req, emp_id)

    changed_bssid_req = base_req.model_copy(update={"wifi_bssid": "99:88:77:66:55:44"})
    assert compute_request_fingerprint(changed_bssid_req, emp_id) != base_fp


@pytest.mark.asyncio
async def test_fingerprint_changes_on_changed_ssid():
    """Fix 2: Verify changing Wi-Fi SSID produces a different fingerprint."""
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    base_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-wifi-123",
        location_id=loc_id,
        wifi_bssid="AA:BB:CC:DD:EE:01",
        wifi_ssid="CorpNet-5G",
        wifi_signal_status="AVAILABLE",
    )
    base_fp = compute_request_fingerprint(base_req, emp_id)

    changed_ssid_req = base_req.model_copy(update={"wifi_ssid": "CorpNet-2.4G"})
    assert compute_request_fingerprint(changed_ssid_req, emp_id) != base_fp


@pytest.mark.asyncio
async def test_fingerprint_changes_on_changed_signal_status():
    """Fix 2: Verify changing Wi-Fi signal status produces a different fingerprint."""
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    base_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-wifi-123",
        location_id=loc_id,
        wifi_signal_status="AVAILABLE",
    )
    base_fp = compute_request_fingerprint(base_req, emp_id)

    unavail_req = base_req.model_copy(update={"wifi_signal_status": "UNAVAILABLE"})
    assert compute_request_fingerprint(unavail_req, emp_id) != base_fp

    perm_denied_req = base_req.model_copy(update={"wifi_signal_status": "PERMISSION_DENIED"})
    assert compute_request_fingerprint(perm_denied_req, emp_id) != base_fp


@pytest.mark.asyncio
async def test_existing_gps_and_manual_fingerprints_remain_deterministic():
    """Fix 2: Verify existing GPS-only and pure manual punches remain deterministic and unaffected."""
    emp_id = uuid.uuid4()
    manual_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-manual-999",
    )
    fp_manual1 = compute_request_fingerprint(manual_req, emp_id)
    fp_manual2 = compute_request_fingerprint(manual_req, emp_id)
    assert fp_manual1 == fp_manual2

    gps_req = PunchRequest(
        event_type="CHECK_IN",
        idempotency_key="idemp-key-gps-888",
        latitude=Decimal("12.9716000"),
        longitude=Decimal("77.5946000"),
        accuracy_meters=Decimal("15.0"),
    )
    fp_gps1 = compute_request_fingerprint(gps_req, emp_id)
    fp_gps2 = compute_request_fingerprint(gps_req, emp_id)
    assert fp_gps1 == fp_gps2
    assert fp_gps1 != fp_manual1

