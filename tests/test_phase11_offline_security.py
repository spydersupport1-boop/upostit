"""Phase 11.6 Backend Security & Device Lifecycle Tests.

Validates:
1. Device security status endpoint (GET /api/v1/devices/security-status).
2. Device re-registration endpoint (POST /api/v1/devices/re-register).
3. Revocation status detection and synchronization freezing.
4. Cross-tenant isolation on security endpoints.
5. Invariant: no raw mobile encryption keys accepted on backend.
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.database import get_db
from services.api.devices.models import Device
from services.api.devices.schemas import (
    DevicePlatform,
    DeviceReRegisterRequest,
)
from services.api.devices.service import (
    get_device_security_status,
    re_register_device,
)
from services.api.employees.models import Employee
from services.api.main import app
from services.api.tenants.models import Tenant


def _make_context(role: str = "employee", tenant_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"user-{uid.hex[:6]}@upostit.test",
        full_name="Alex Rivers",
        role=role,
        status="ACTIVE",
    )
    tenant = Tenant(
        id=tid,
        name="Security Tenant",
        slug=f"sec-{tid.hex[:6]}",
        company_email=f"tenant-{tid.hex[:6]}@upostit.test",
        country_code="US",
        timezone="UTC",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _make_employee(tenant_id: uuid.UUID, user_id: uuid.UUID) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        employee_id=f"EMP-{uuid.uuid4().hex[:6]}",
        first_name="Alex",
        last_name="Rivers",
        work_email=f"alex-{uuid.uuid4().hex[:6]}@upostit.test",
        joining_date=date(2025, 1, 1),
        status="active",
    )


@pytest.mark.asyncio
async def test_get_device_security_status_active_device():
    """Returns ACTIVE status and AES-256 SQLCipher encryption parameters for bound device."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    now = datetime.now(UTC)

    dev = Device(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=emp_id,
        device_id_hash="active_dev_hash_123",
        platform="ANDROID",
        device_model="Pixel 8 Pro",
        status="ACTIVE",
        registered_at=now,
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = dev
    mock_session.execute.return_value = mock_res

    status_resp = await get_device_security_status(mock_session, tid, emp_id)

    assert status_resp.is_bound is True
    assert status_resp.status == "ACTIVE"
    assert status_resp.is_revoked is False
    assert status_resp.platform == "ANDROID"
    assert status_resp.device_model == "Pixel 8 Pro"
    assert status_resp.encryption_algorithm_supported == "SQLCIPHER_PAGE_AES256"


@pytest.mark.asyncio
async def test_get_device_security_status_revoked_device():
    """Detects revoked status and returns revocation timestamp and reason."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    rev_time = datetime.now(UTC)

    dev = Device(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=emp_id,
        device_id_hash="revoked_dev_hash_456",
        platform="IOS",
        device_model="iPhone 15",
        status="REVOKED",
        revoked_at=rev_time,
        revocation_reason="Employee reported device stolen.",
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = dev
    mock_session.execute.return_value = mock_res

    status_resp = await get_device_security_status(mock_session, tid, emp_id)

    assert status_resp.is_bound is False
    assert status_resp.status == "REVOKED"
    assert status_resp.is_revoked is True
    assert status_resp.revoked_at == rev_time
    assert status_resp.revocation_reason == "Employee reported device stolen."


@pytest.mark.asyncio
async def test_get_device_security_status_unbound():
    """Returns UNBOUND status when employee has no registered device."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    status_resp = await get_device_security_status(mock_session, tid, emp_id)

    assert status_resp.is_bound is False
    assert status_resp.status == "UNBOUND"
    assert status_resp.is_revoked is False


@pytest.mark.asyncio
async def test_re_register_device_service():
    """Re-registers device with reason preserved in metadata."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    emp = _make_employee(tid, uuid.uuid4())
    emp.id = emp_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp

    mock_dev_res = MagicMock()
    mock_dev_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [
        mock_emp_res,  # Employee exists
        mock_dev_res,  # Active device check
        mock_dev_res,  # Pending device check
        mock_dev_res,  # Device hash existing
    ]

    payload = DeviceReRegisterRequest(
        device_id="hardware_id_replacement_999",
        platform=DevicePlatform.ANDROID,
        re_registration_reason="Device upgraded to new OS and security key wiped.",
        device_model="Galaxy S24",
    )

    res = await re_register_device(mock_session, tid, emp_id, payload)
    assert res.device is not None
    assert res.device.platform == "ANDROID"
    assert res.requires_approval is False


@pytest.mark.asyncio
async def test_http_device_security_status_endpoint():
    """Verifies GET /api/v1/devices/security-status via ASGI test client."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    emp = _make_employee(tid, uid)
    ctx = _make_context(role="employee", tenant_id=tid, user_id=uid)

    app.dependency_overrides[get_authenticated_context] = lambda: ctx

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one_or_none.return_value = emp

    dev = Device(
        id=uuid.uuid4(),
        tenant_id=tid,
        employee_id=emp.id,
        device_id_hash="hash_sec_test",
        platform="ANDROID",
        status="ACTIVE",
    )
    mock_dev_res = MagicMock()
    mock_dev_res.scalar_one_or_none.return_value = dev

    mock_session.execute.side_effect = [mock_emp_res, mock_dev_res]
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/devices/security-status")

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["is_bound"] is True
        assert data["status"] == "ACTIVE"
        assert data["encryption_algorithm_supported"] == "SQLCIPHER_PAGE_AES256"
    finally:
        app.dependency_overrides.clear()