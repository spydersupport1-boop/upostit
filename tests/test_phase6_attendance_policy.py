"""Comprehensive tests for Phase 6 Milestone 6.3.A:
Backend Attendance Policy Engine & GPS Geofence Enforcement.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import (
    AttendanceIdempotencyRecord,
    TenantAttendancePolicy,
)
from services.api.attendance.policy_engine import (
    create_new_policy_version,
    evaluate_punch_policy,
    get_active_tenant_policy,
    verify_employee_coordinates,
    verify_employee_workplace_assignment,
)
from services.api.attendance.schemas import (
    AttendanceCombinationRule,
    AttendancePolicyMethod,
    AttendancePolicyMode,
    EmployeeGeofenceVerifyRequest,
    PunchRequest,
    TenantAttendancePolicyCreateRequest,
)
from services.api.attendance.service import record_punch
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.locations.models import EmployeeLocation, Location
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
        name="Test Policy Corp",
        slug=f"policy-{tid.hex[:6]}",
        company_email="admin@policy.test",
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
        employee_id="EMP-POL-001",
        first_name="Alice",
        last_name="Geofence",
        work_email="alice.geo@policy.test",
        employment_type="full_time",
        status="active",
    )


def _create_mock_location(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    name: str = "Headquarters",
    code: str = "HQ-MAIN",
    latitude: Decimal = Decimal("12.9715987"),
    longitude: Decimal = Decimal("77.5945627"),
    radius_meters: int = 100,
    is_active: bool = True,
) -> Location:
    return Location(
        id=location_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        code=code,
        address_line1="123 Tech Park",
        city="Bengaluru",
        country_code="IN",
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        is_active=is_active,
    )


def _create_mock_assignment(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    location_id: uuid.UUID,
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
    is_primary: bool = True,
) -> EmployeeLocation:
    return EmployeeLocation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        location_id=location_id,
        is_primary=is_primary,
        effective_from=effective_from,
        effective_to=effective_to,
        created_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. Policy Model & Versioning Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_policy_defaults_to_manual_when_no_active_row():
    """Verify get_active_tenant_policy returns default version 1 MANUAL policy."""
    tenant_id = uuid.uuid4()
    mock_session = AsyncMock()
    # Executing query returns None -> returns default policy
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = res_mock

    policy = await get_active_tenant_policy(mock_session, tenant_id)
    assert policy.version == 1
    assert policy.default_mode == "MANUAL"
    assert policy.allowed_methods == ["MANUAL"]
    assert policy.required_methods == ["MANUAL"]
    assert policy.combination_rule == "OR"
    assert policy.is_active is True


@pytest.mark.asyncio
async def test_policy_create_new_version_increments_and_deactivates_previous():
    """Verify create_new_policy_version deactivates active versions and increments version."""
    tenant_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    mock_session = AsyncMock()

    old_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        allowed_methods=["MANUAL"],
        required_methods=["MANUAL"],
        combination_rule="OR",
        gps_config={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # 1. active policies query (locked for update) -> [old_policy]
    # 2. max version query -> 1
    res_active = MagicMock()
    res_active.scalars.return_value.all.return_value = [old_policy]
    res_max = MagicMock()
    res_max.scalar.return_value = 1

    mock_session.execute.side_effect = [res_active, res_max]

    req = TenantAttendancePolicyCreateRequest(
        default_mode=AttendancePolicyMode.GPS_ONLY,
        allowed_methods=[AttendancePolicyMethod.MANUAL, AttendancePolicyMethod.GPS],
        required_methods=[AttendancePolicyMethod.GPS],
        combination_rule=AttendanceCombinationRule.OR,
        gps_config={
            "max_accuracy_meters": 50,
            "max_location_age_seconds": 20,
            "enforce_assigned_workplace": True,
            "out_of_geofence_action": "REJECT",
        },
    )

    new_policy = await create_new_policy_version(
        session=mock_session,
        tenant_id=tenant_id,
        creator_user_id=creator_id,
        data=req,
    )

    assert old_policy.is_active is False
    assert new_policy.version == 2
    assert new_policy.is_active is True
    assert new_policy.default_mode == "GPS_ONLY"
    assert new_policy.required_methods == ["GPS"]
    assert new_policy.created_by_user_id == creator_id
    assert mock_session.add.called


# ==============================================================================
# 2. Unsupported Future Methods Safe Failure Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_wifi_policy_missing_location_id_rejected_400():
    """Verify that a WIFI policy with missing workplace location_id is rejected with 400."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    mock_session = AsyncMock()

    wifi_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="WIFI_ONLY",
        allowed_methods=["WIFI"],
        required_methods=["WIFI"],
        combination_rule="OR",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=None,
            latitude=None,
            longitude=None,
            accuracy_meters=None,
            device_reported_at=None,
            active_policy=wifi_policy,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Workplace location identifier is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_unsupported_future_method_biometric_fails_safely():
    """Verify that a policy requiring unimplemented BIOMETRIC fails safely with 422."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    mock_session = AsyncMock()

    bio_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=3,
        is_active=True,
        default_mode="BIOMETRIC_ONLY",
        allowed_methods=["BIOMETRIC"],
        required_methods=["BIOMETRIC"],
        combination_rule="OR",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=None,
            latitude=None,
            longitude=None,
            accuracy_meters=None,
            device_reported_at=None,
            active_policy=bio_policy,
        )
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "BIOMETRIC" in exc_info.value.detail


# ==============================================================================
# 3. Policy Evaluation: MANUAL vs GPS Modes
# ==============================================================================


@pytest.mark.asyncio
async def test_manual_policy_punch_without_coordinates_succeeds():
    """Verify MANUAL policy allows punch without any GPS coordinates."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    mock_session = AsyncMock()

    manual_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        allowed_methods=["MANUAL"],
        required_methods=["MANUAL"],
        combination_rule="OR",
        created_at=datetime.now(UTC),
    )

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=None,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        device_reported_at=None,
        active_policy=manual_policy,
    )

    assert outcome.is_verified is True
    assert outcome.verification_mode == "MANUAL"
    assert outcome.review_status == "NOT_REQUIRED"
    assert outcome.policy_version == 1


@pytest.mark.asyncio
async def test_manual_policy_optional_coordinates_do_not_gate_or_reject():
    """Verify MANUAL policy treats coordinates as optional telemetry without geofence enforcement."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    manual_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        allowed_methods=["MANUAL"],
        required_methods=["MANUAL"],
        combination_rule="OR",
        created_at=datetime.now(UTC),
    )

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("20.0"),
        device_reported_at=None,
        active_policy=manual_policy,
    )

    assert outcome.is_verified is True
    assert outcome.verification_mode == "MANUAL"
    assert outcome.spatial_evidence.get("telemetry_only") is True
    assert outcome.spatial_evidence.get("location_id") == str(loc_id)


@pytest.mark.asyncio
async def test_gps_policy_missing_coordinates_rejected_400():
    """Verify GPS policy strictly rejects punches missing location evidence."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={"max_accuracy_meters": 100},
        created_at=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=None,
            latitude=None,
            longitude=None,
            accuracy_meters=None,
            device_reported_at=None,
            active_policy=gps_policy,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Location evidence" in exc_info.value.detail


@pytest.mark.asyncio
async def test_gps_policy_insufficient_accuracy_rejected_400():
    """Verify GPS policy rejects fixes with accuracy worse than allowable threshold."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={"max_accuracy_meters": 50},
        created_at=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=Decimal("12.9715987"),
            longitude=Decimal("77.5945627"),
            accuracy_meters=Decimal("120.0"),  # Worse than 50m
            device_reported_at=datetime.now(UTC),
            active_policy=gps_policy,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "accuracy" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gps_policy_stale_coordinates_rejected_400():
    """Verify GPS policy rejects readings older than max_location_age_seconds."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={"max_accuracy_meters": 100, "max_location_age_seconds": 30},
        created_at=datetime.now(UTC),
    )

    stale_time = datetime.now(UTC) - timedelta(seconds=120)

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=Decimal("12.9715987"),
            longitude=Decimal("77.5945627"),
            accuracy_meters=Decimal("20.0"),
            device_reported_at=stale_time,
            active_policy=gps_policy,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "stale" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gps_policy_unassigned_workplace_forbidden_403():
    """Verify GPS policy rejects employee punch at an unassigned workplace."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    # Query for assignment returns None
    res_assign = MagicMock()
    res_assign.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = res_assign

    with pytest.raises(HTTPException) as exc_info:
        await verify_employee_workplace_assignment(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            location_id=loc_id,
            target_date=date.today(),
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "not actively assigned" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gps_policy_outside_geofence_reject_action_400():
    """Verify punch outside geofence with action REJECT raises 400."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={
            "max_accuracy_meters": 100,
            "max_location_age_seconds": 30,
            "enforce_assigned_workplace": False,
            "out_of_geofence_action": "REJECT",
        },
        created_at=datetime.now(UTC),
    )

    # PostGIS query result: outside geofence (within_geofence = False, distance = 350.0m, radius = 100m)
    row_mock = (loc_id, "Office HQ", "HQ", 100, 12.9715987, 77.5945627, 350.0, False)
    res_spatial = MagicMock()
    res_spatial.first.return_value = row_mock
    mock_session.execute.return_value = res_spatial

    with pytest.raises(HTTPException) as exc_info:
        await evaluate_punch_policy(
            session=mock_session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            event_type="CHECK_IN",
            location_id=loc_id,
            latitude=Decimal("12.9750000"),
            longitude=Decimal("77.5990000"),
            accuracy_meters=Decimal("15.0"),
            device_reported_at=datetime.now(UTC),
            active_policy=gps_policy,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "outside workplace geofence" in exc_info.value.detail.lower()
    assert "350" in exc_info.value.detail


@pytest.mark.asyncio
async def test_gps_policy_outside_geofence_flag_pending_review():
    """Verify punch outside geofence with action FLAG_PENDING_REVIEW is accepted with PENDING_REVIEW."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={
            "max_accuracy_meters": 100,
            "max_location_age_seconds": 30,
            "enforce_assigned_workplace": False,
            "out_of_geofence_action": "FLAG_PENDING_REVIEW",
        },
        created_at=datetime.now(UTC),
    )

    row_mock = (loc_id, "Office HQ", "HQ", 100, 12.9715987, 77.5945627, 280.0, False)
    res_spatial = MagicMock()
    res_spatial.first.return_value = row_mock
    mock_session.execute.return_value = res_spatial

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=Decimal("12.9750000"),
        longitude=Decimal("77.5990000"),
        accuracy_meters=Decimal("15.0"),
        device_reported_at=datetime.now(UTC),
        active_policy=gps_policy,
    )

    assert outcome.is_verified is False
    assert outcome.review_status == "PENDING_REVIEW"
    assert "OUT_OF_GEOFENCE" in outcome.verification_flags
    assert outcome.spatial_evidence.get("within_geofence") is False
    assert outcome.spatial_evidence.get("distance_meters") == 280.0


@pytest.mark.asyncio
async def test_gps_policy_inside_geofence_succeeds_with_evidence():
    """Verify punch inside geofence succeeds with complete spatial verification evidence."""
    tenant_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    gps_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={
            "max_accuracy_meters": 100,
            "max_location_age_seconds": 30,
            "enforce_assigned_workplace": False,
            "out_of_geofence_action": "REJECT",
        },
        created_at=datetime.now(UTC),
    )

    row_mock = (loc_id, "Office HQ", "HQ", 100, 12.9715987, 77.5945627, 18.5, True)
    res_spatial = MagicMock()
    res_spatial.first.return_value = row_mock
    mock_session.execute.return_value = res_spatial

    outcome = await evaluate_punch_policy(
        session=mock_session,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        location_id=loc_id,
        latitude=Decimal("12.9716000"),
        longitude=Decimal("77.5945700"),
        accuracy_meters=Decimal("8.0"),
        device_reported_at=datetime.now(UTC),
        active_policy=gps_policy,
    )

    assert outcome.is_verified is True
    assert outcome.review_status == "NOT_REQUIRED"
    assert outcome.verification_mode == "GPS"
    assert outcome.spatial_evidence.get("within_geofence") is True
    assert outcome.spatial_evidence.get("distance_meters") == 18.5


# ==============================================================================
# 4. Employee Geofence Coordinate Verification Probe Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_verify_employee_coordinates_inside_geofence():
    """Verify POST verify-coordinates probe returns can_punch=True when inside geofence."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    assign = _create_mock_assignment(tenant_id, emp_id, loc_id)
    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        gps_config={"max_accuracy_meters": 100, "max_location_age_seconds": 30},
        created_at=datetime.now(UTC),
    )

    # 1. Employee query -> emp
    # 2. Assignment query -> assign
    # 3. Policy query -> policy
    # 4. PostGIS query -> inside geofence
    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_assign = MagicMock()
    res_assign.scalar_one_or_none.return_value = assign
    res_policy = MagicMock()
    res_policy.scalar_one_or_none.return_value = policy
    res_spatial = MagicMock()
    res_spatial.first.return_value = ("Central Tech Park", "CTP-01", 150.0, 24.3, True)

    mock_session.execute.side_effect = [res_emp, res_assign, res_policy, res_spatial]

    req = EmployeeGeofenceVerifyRequest(
        location_id=loc_id,
        latitude=Decimal("12.9715987"),
        longitude=Decimal("77.5945627"),
        accuracy_meters=Decimal("12.0"),
        device_reported_at=datetime.now(UTC),
    )

    res = await verify_employee_coordinates(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        req=req,
    )

    assert res.is_inside is True
    assert res.accuracy_acceptable is True
    assert res.freshness_acceptable is True
    assert res.can_punch is True
    assert res.distance_meters == 24.3
    assert res.radius_meters == 150.0
    assert "Verification successful" in res.message


@pytest.mark.asyncio
async def test_verify_employee_coordinates_outside_geofence():
    """Verify POST verify-coordinates probe returns can_punch=False when outside geofence."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    loc_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)
    assign = _create_mock_assignment(tenant_id, emp_id, loc_id)
    policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        gps_config={"max_accuracy_meters": 100, "max_location_age_seconds": 30},
        created_at=datetime.now(UTC),
    )

    res_emp = MagicMock()
    res_emp.scalar_one_or_none.return_value = emp
    res_assign = MagicMock()
    res_assign.scalar_one_or_none.return_value = assign
    res_policy = MagicMock()
    res_policy.scalar_one_or_none.return_value = policy
    res_spatial = MagicMock()
    res_spatial.first.return_value = ("Central Tech Park", "CTP-01", 100.0, 420.5, False)

    mock_session.execute.side_effect = [res_emp, res_assign, res_policy, res_spatial]

    req = EmployeeGeofenceVerifyRequest(
        location_id=loc_id,
        latitude=Decimal("12.9800000"),
        longitude=Decimal("77.6000000"),
        accuracy_meters=Decimal("15.0"),
        device_reported_at=datetime.now(UTC),
    )

    res = await verify_employee_coordinates(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        req=req,
    )

    assert res.is_inside is False
    assert res.can_punch is False
    assert res.distance_meters == 420.5
    assert "Outside geofence" in res.message


# ==============================================================================
# 5. API Endpoints Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_api_get_my_policy_employee_safe():
    """Verify GET /attendance/policy/me returns sanitized employee policy fields."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_ctx = _mock_context("EMPLOYEE", tenant_id=tenant_id, user_id=user_id)
    mock_session = AsyncMock()

    active_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=2,
        is_active=True,
        default_mode="GPS_ONLY",
        allowed_methods=["MANUAL", "GPS"],
        required_methods=["GPS"],
        combination_rule="OR",
        gps_config={"max_accuracy_meters": 80, "max_location_age_seconds": 25},
        created_by_user_id=uuid.uuid4(),  # Admin ID (must NOT leak to employee)
        created_at=datetime.now(UTC),
    )

    res_policy = MagicMock()
    res_policy.scalar_one_or_none.return_value = active_policy
    mock_session.execute.return_value = res_policy

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/attendance/policy/me")
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["version"] == 2
            assert data["default_mode"] == "GPS_ONLY"
            assert data["requires_gps"] is True
            assert data["max_accuracy_meters"] == 80
            assert data["max_location_age_seconds"] == 25
            # Ensure admin internals are not leaked
            assert "created_by_user_id" not in data
            assert "fallback_policy" not in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_admin_can_create_policy_version():
    """Verify POST /attendance/policy allows Owner/Admin to create a new version."""
    tenant_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    mock_ctx = _mock_context("ADMIN", tenant_id=tenant_id, user_id=admin_id)
    mock_session = AsyncMock()

    old_policy = TenantAttendancePolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        version=1,
        is_active=True,
        default_mode="MANUAL",
        allowed_methods=["MANUAL"],
        required_methods=["MANUAL"],
        combination_rule="OR",
        created_at=datetime.now(UTC),
    )

    res_active = MagicMock()
    res_active.scalars.return_value.all.return_value = [old_policy]
    res_max = MagicMock()
    res_max.scalar.return_value = 1
    mock_session.execute.side_effect = [res_active, res_max]

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "default_mode": "GPS_ONLY",
        "allowed_methods": ["MANUAL", "GPS"],
        "required_methods": ["GPS"],
        "combination_rule": "OR",
        "gps_config": {
            "max_accuracy_meters": 60,
            "max_location_age_seconds": 20,
            "enforce_assigned_workplace": True,
            "out_of_geofence_action": "REJECT",
        },
    }

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/attendance/policy", json=payload)
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["version"] == 2
            assert data["is_active"] is True
            assert data["default_mode"] == "GPS_ONLY"
            assert mock_session.commit.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_employee_cannot_manage_policy():
    """Verify employee role receives 403 Forbidden on POST /attendance/policy."""
    tenant_id = uuid.uuid4()
    emp_user_id = uuid.uuid4()
    mock_ctx = _mock_context("EMPLOYEE", tenant_id=tenant_id, user_id=emp_user_id)
    mock_session = AsyncMock()

    app.dependency_overrides[get_authenticated_context] = lambda: mock_ctx
    app.dependency_overrides[get_db] = lambda: mock_session

    payload = {
        "default_mode": "MANUAL",
        "allowed_methods": ["MANUAL"],
        "required_methods": ["MANUAL"],
        "combination_rule": "OR",
    }

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/attendance/policy", json=payload)
            assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 6. Idempotency & Immutability Under Policy Evolution
# ==============================================================================


@pytest.mark.asyncio
async def test_idempotency_replay_preserves_original_policy_version():
    """Verify that a policy change after the initial punch does not alter the replayed result."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    mock_session = AsyncMock()

    emp = _create_mock_employee(tenant_id, employee_id=emp_id, user_id=user_id)

    # Cached response from Version 1 punch
    cached_event = {
        "id": str(uuid.uuid4()),
        "tenant_id": str(tenant_id),
        "employee_id": str(emp_id),
        "event_type": "CHECK_IN",
        "event_category": "STANDARD",
        "supersedes_event_id": None,
        "correction_reason": None,
        "server_received_at": datetime.now(UTC).isoformat(),
        "device_reported_at": datetime.now(UTC).isoformat(),
        "effective_at": datetime.now(UTC).isoformat(),
        "clock_drift_seconds": "0.000",
        "source": "WEB",
        "device_id": None,
        "timestamp_verification_status": "SERVER_AUTHORITATIVE",
        "review_status": "NOT_REQUIRED",
        "applied_policy_version": 1,
        "idempotency_key": "punch-immutable-policy-v1",
        "location_id": None,
        "latitude": None,
        "longitude": None,
        "accuracy_meters": None,
        "metadata_json": {"policy_version": 1},
        "created_at": datetime.now(UTC).isoformat(),
    }
    cached_payload = {
        "event": cached_event,
        "additional_events": [],
        "idempotent_replay": False,
    }

    from services.api.attendance.service import compute_request_fingerprint

    req = PunchRequest(event_type="CHECK_IN", idempotency_key="punch-immutable-policy-v1")
    fingerprint = compute_request_fingerprint(req, emp_id)

    completed_idem = AttendanceIdempotencyRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=emp_id,
        idempotency_key="punch-immutable-policy-v1",
        request_fingerprint=fingerprint,
        status="COMPLETED",
        response_code=201,
        response_payload=cached_payload,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )

    # 1. user_emp query -> emp
    # 2. lock emp query -> emp
    # 3. idem query -> completed_idem (returns cached response immediately)
    res_user_emp = MagicMock()
    res_user_emp.scalar_one_or_none.return_value = emp
    res_lock_emp = MagicMock()
    res_lock_emp.scalar_one_or_none.return_value = emp
    res_idem = MagicMock()
    res_idem.scalar_one_or_none.return_value = completed_idem

    mock_session.execute.side_effect = [res_user_emp, res_lock_emp, res_idem]

    resp = await record_punch(
        session=mock_session,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role="employee",
        payload=req,
    )

    assert resp.idempotent_replay is True
    assert resp.event.applied_policy_version == 1
    assert resp.event.idempotency_key == "punch-immutable-policy-v1"
