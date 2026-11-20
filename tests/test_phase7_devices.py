"""Comprehensive automated test suite for Phase 7 Milestone 7.1:
Device Binding Subsystem, Registration, Revocation, and Replacement.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import Permission, UserRole, has_permission
from services.api.database import get_db
from services.api.devices.models import Device
from services.api.devices.schemas import (
    DevicePlatform,
    DeviceRegisterRequest,
)
from services.api.devices.service import (
    approve_device_replacement,
    hash_device_id,
    register_device,
    revoke_device,
    validate_device_for_punch,
)
from services.api.employees.models import Employee
from services.api.main import app
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Contexts & Entities
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
        email=f"test_{role.lower()}@devices.test",
        password_hash="argon2id$mock",
        role=role.lower(),
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Device Binding Corp",
        slug=f"dev-{tid.hex[:6]}",
        company_email="admin@dev.test",
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
        first_name="Alice",
        last_name="Engineer",
        work_email="alice@devices.test",
        status="active",
    )


def _create_mock_device(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_id_hash: str,
    status: str = "ACTIVE",
    device_id: uuid.UUID | None = None,
    platform: str = "ANDROID",
    replacement_for_device_id: uuid.UUID | None = None,
) -> Device:
    now = datetime.now(UTC)
    return Device(
        id=device_id or uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        device_id_hash=device_id_hash,
        platform=platform,
        device_model="Pixel 8 Pro",
        os_name="Android",
        os_version="14.0",
        app_version="1.0.0",
        status=status,
        registered_at=now,
        last_seen_at=now,
        replacement_for_device_id=replacement_for_device_id,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# Unit Tests: RBAC Permissions for Devices
# ==============================================================================


class TestDeviceRBACPermissions:
    """Validates granular role-based permissions for device management."""

    def test_owner_permissions(self):
        assert has_permission(UserRole.OWNER, Permission.VIEW_DEVICES) is True
        assert has_permission(UserRole.OWNER, Permission.MANAGE_DEVICES) is True

    def test_admin_permissions(self):
        assert has_permission(UserRole.ADMIN, Permission.VIEW_DEVICES) is True
        assert has_permission(UserRole.ADMIN, Permission.MANAGE_DEVICES) is True

    def test_hr_permissions(self):
        assert has_permission(UserRole.HR, Permission.VIEW_DEVICES) is True
        assert has_permission(UserRole.HR, Permission.MANAGE_DEVICES) is True

    def test_manager_permissions_denied(self):
        assert has_permission(UserRole.MANAGER, Permission.VIEW_DEVICES) is False
        assert has_permission(UserRole.MANAGER, Permission.MANAGE_DEVICES) is False

    def test_employee_permissions_denied(self):
        assert has_permission(UserRole.EMPLOYEE, Permission.VIEW_DEVICES) is False
        assert has_permission(UserRole.EMPLOYEE, Permission.MANAGE_DEVICES) is False


# ==============================================================================
# Unit Tests: Device Identifier Hashing
# ==============================================================================


class TestDeviceHashing:
    """Validates HMAC-SHA256 device identifier salting and hashing."""

    def test_hashing_consistency(self):
        tenant_id = uuid.uuid4()
        raw_id = "device-hardware-uuid-12345"
        hash1 = hash_device_id(tenant_id, raw_id)
        hash2 = hash_device_id(tenant_id, raw_id)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string

    def test_tenant_salt_isolation(self):
        t1 = uuid.uuid4()
        t2 = uuid.uuid4()
        raw_id = "device-hardware-uuid-12345"
        h1 = hash_device_id(t1, raw_id)
        h2 = hash_device_id(t2, raw_id)
        assert h1 != h2, "Identical device ID must produce different hashes across tenants"

    def test_whitespace_normalization(self):
        tenant_id = uuid.uuid4()
        h1 = hash_device_id(tenant_id, "my-device-id")
        h2 = hash_device_id(tenant_id, "  my-device-id  ")
        assert h1 == h2


# ==============================================================================
# Unit Tests: Service Logic (Registration, Revocation, Replacement)
# ==============================================================================


@pytest.mark.asyncio
class TestDeviceServiceLogic:
    """Tests the business logic of device registration, binding, and replacement."""

    async def test_initial_device_registration_succeeds_active(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        emp = _create_mock_employee(tenant_id, employee_id)

        session = AsyncMock()
        # Mock 1: emp_stmt -> emp found
        # Mock 2: active_stmt -> None
        # Mock 3: revoked_stmt -> None
        # Mock 4: conflict_stmt -> None
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = None

        mock_revoked_res = MagicMock()
        mock_revoked_res.scalar_one_or_none.return_value = None

        mock_conflict_res = MagicMock()
        mock_conflict_res.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp_res,
            mock_active_res,
            mock_revoked_res,
            mock_conflict_res,
        ]

        payload = DeviceRegisterRequest(
            device_id="hardware-pixel-8-unique-uuid",
            platform=DevicePlatform.ANDROID,
            device_model="Pixel 8",
            os_name="Android",
            os_version="14.0",
            app_version="1.0.0",
        )

        resp = await register_device(session, tenant_id, employee_id, payload)
        assert resp.requires_approval is False
        assert resp.device.status == "ACTIVE"
        assert resp.device.device_model == "Pixel 8"
        assert session.add.called

    async def test_duplicate_registration_is_idempotent(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_id = "hardware-pixel-8-unique-uuid"
        dev_hash = hash_device_id(tenant_id, raw_id)

        emp = _create_mock_employee(tenant_id, employee_id)
        existing_device = _create_mock_device(tenant_id, employee_id, dev_hash, status="ACTIVE")

        session = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = existing_device

        session.execute.side_effect = [mock_emp_res, mock_active_res]

        payload = DeviceRegisterRequest(
            device_id=raw_id,
            platform=DevicePlatform.ANDROID,
            device_model="Pixel 8 Updated",
            os_version="14.1",
        )

        resp = await register_device(session, tenant_id, employee_id, payload)
        assert resp.requires_approval is False
        assert resp.device.status == "ACTIVE"
        assert resp.message == "Device is already registered and active."
        assert existing_device.device_model == "Pixel 8 Updated"

    async def test_registering_new_device_triggers_replacement_workflow(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        old_hash = hash_device_id(tenant_id, "old-phone-uuid")
        new_raw_id = "new-phone-uuid-9999"

        emp = _create_mock_employee(tenant_id, employee_id)
        old_device = _create_mock_device(tenant_id, employee_id, old_hash, status="ACTIVE")

        session = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = old_device

        mock_pending_res = MagicMock()
        mock_pending_res.scalar_one_or_none.return_value = None

        session.execute.side_effect = [mock_emp_res, mock_active_res, mock_pending_res]

        payload = DeviceRegisterRequest(
            device_id=new_raw_id,
            platform=DevicePlatform.IOS,
            device_model="iPhone 15",
            os_name="iOS",
            os_version="17.4",
        )

        resp = await register_device(session, tenant_id, employee_id, payload)
        assert resp.requires_approval is True
        assert resp.device.status == "PENDING_APPROVAL"
        assert resp.device.replacement_for_device_id == old_device.id
        assert "Device replacement request submitted" in resp.message
        assert session.add.called

    async def test_revoked_device_cannot_be_re_registered(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_id = "stolen-device-uuid"
        dev_hash = hash_device_id(tenant_id, raw_id)

        emp = _create_mock_employee(tenant_id, employee_id)
        revoked_device = _create_mock_device(tenant_id, employee_id, dev_hash, status="REVOKED")

        session = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = None

        mock_revoked_res = MagicMock()
        mock_revoked_res.scalar_one_or_none.return_value = revoked_device

        session.execute.side_effect = [mock_emp_res, mock_active_res, mock_revoked_res]

        payload = DeviceRegisterRequest(
            device_id=raw_id,
            platform=DevicePlatform.ANDROID,
        )

        with pytest.raises(HTTPException) as exc_info:
            await register_device(session, tenant_id, employee_id, payload)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "previously revoked" in exc_info.value.detail

    async def test_revoke_device_success(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        actor_user_id = uuid.uuid4()
        device = _create_mock_device(tenant_id, employee_id, "hash1", status="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = device
        session.execute.return_value = mock_res

        revoked = await revoke_device(
            session=session,
            tenant_id=tenant_id,
            device_id=device.id,
            actor_user_id=actor_user_id,
            reason="Device lost by employee on commute",
        )
        assert revoked.status == "REVOKED"
        assert revoked.revocation_reason == "Device lost by employee on commute"
        assert revoked.revoked_by_user_id == actor_user_id
        assert revoked.revoked_at is not None

    async def test_revoke_already_revoked_device_raises_400(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        actor_user_id = uuid.uuid4()
        device = _create_mock_device(tenant_id, employee_id, "hash1", status="REVOKED")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = device
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc_info:
            await revoke_device(
                session=session,
                tenant_id=tenant_id,
                device_id=device.id,
                actor_user_id=actor_user_id,
                reason="Duplicate revocation attempt",
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "already revoked" in exc_info.value.detail

    async def test_approve_replacement_success_rotates_active_device(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        actor_user_id = uuid.uuid4()

        old_active = _create_mock_device(tenant_id, employee_id, "old-hash", status="ACTIVE")
        new_pending = _create_mock_device(
            tenant_id,
            employee_id,
            "new-hash",
            status="PENDING_APPROVAL",
            replacement_for_device_id=old_active.id,
        )

        session = AsyncMock()
        mock_target_res = MagicMock()
        mock_target_res.scalar_one_or_none.return_value = new_pending

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = old_active

        session.execute.side_effect = [mock_target_res, mock_active_res]

        approved, replaced = await approve_device_replacement(
            session=session,
            tenant_id=tenant_id,
            device_id=new_pending.id,
            actor_user_id=actor_user_id,
            notes="Employee presented police report for stolen phone",
        )

        assert approved.status == "ACTIVE"
        assert approved.replacement_approved_by_user_id == actor_user_id
        assert approved.replacement_approved_at is not None
        assert replaced.status == "REPLACED"

    async def test_approve_replacement_on_non_pending_raises_400(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        actor_user_id = uuid.uuid4()
        already_active = _create_mock_device(tenant_id, employee_id, "hash", status="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = already_active
        session.execute.return_value = mock_res

        with pytest.raises(HTTPException) as exc_info:
            await approve_device_replacement(
                session=session,
                tenant_id=tenant_id,
                device_id=already_active.id,
                actor_user_id=actor_user_id,
            )
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot be approved for replacement" in exc_info.value.detail


# ==============================================================================
# Unit Tests: Attendance Validation Helper
# ==============================================================================


@pytest.mark.asyncio
class TestValidateDeviceForPunch:
    """Validates the device check helper prepared for punch authorization."""

    async def test_no_device_id_supplied(self):
        session = AsyncMock()
        res = await validate_device_for_punch(
            session=session,
            tenant_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            raw_device_id=None,
        )
        assert res.is_authorized is False
        assert res.status == "NO_DEVICE_SUPPLIED"

    async def test_active_device_authorized(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_id = "device-pixel-8-abc"
        dev_hash = hash_device_id(tenant_id, raw_id)
        device = _create_mock_device(tenant_id, employee_id, dev_hash, status="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = device
        session.execute.return_value = mock_res

        res = await validate_device_for_punch(
            session=session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            raw_device_id=raw_id,
        )
        assert res.is_authorized is True
        assert res.status == "ACTIVE"
        assert res.device_id == device.id

    async def test_revoked_device_rejected(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_id = "device-pixel-8-revoked"
        dev_hash = hash_device_id(tenant_id, raw_id)
        device = _create_mock_device(tenant_id, employee_id, dev_hash, status="REVOKED")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = device
        session.execute.return_value = mock_res

        res = await validate_device_for_punch(
            session=session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            raw_device_id=raw_id,
        )
        assert res.is_authorized is False
        assert res.status == "REVOKED"
        assert "revoked" in res.reason.lower()

    async def test_unregistered_device_rejected(self):
        tenant_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        raw_id = "device-unknown-xyz"

        session = AsyncMock()
        mock_device_res = MagicMock()
        mock_device_res.scalar_one_or_none.return_value = None

        mock_active_res = MagicMock()
        mock_active_res.scalar_one_or_none.return_value = uuid.uuid4()

        session.execute.side_effect = [mock_device_res, mock_active_res]

        res = await validate_device_for_punch(
            session=session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            raw_device_id=raw_id,
        )
        assert res.is_authorized is False
        assert res.status == "UNREGISTERED"


# ==============================================================================
# Integration Tests: Device API Endpoints & RBAC Routing
# ==============================================================================


@pytest.mark.asyncio
class TestDeviceAPIEndpoints:
    """End-to-end HTTP API tests with mocked database session and auth dependencies."""

    async def test_employee_registers_device_success(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        ctx = _mock_context("EMPLOYEE", tenant_id, user_id)
        emp = _create_mock_employee(tenant_id, employee_id, user_id)

        session = AsyncMock()
        # 1. routes.py: resolve employee
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        # 2. service.py: emp_stmt
        mock_svc_emp = MagicMock()
        mock_svc_emp.scalar_one_or_none.return_value = emp
        # 3. service.py: active_stmt -> None
        mock_active = MagicMock()
        mock_active.scalar_one_or_none.return_value = None
        # 4. service.py: revoked_stmt -> None
        mock_revoked = MagicMock()
        mock_revoked.scalar_one_or_none.return_value = None
        # 5. service.py: conflict_stmt -> None
        mock_conflict = MagicMock()
        mock_conflict.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            mock_emp_res,
            mock_svc_emp,
            mock_active,
            mock_revoked,
            mock_conflict,
        ]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/devices/register",
                    json={
                        "device_id": "phone-install-id-12345678",
                        "platform": "ANDROID",
                        "device_model": "Pixel 8",
                        "os_name": "Android",
                        "os_version": "14",
                        "app_version": "1.0.0",
                    },
                )
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["requires_approval"] is False
            assert data["device"]["status"] == "ACTIVE"
            assert data["device"]["device_model"] == "Pixel 8"
        finally:
            app.dependency_overrides.clear()

    async def test_employee_view_own_device_status(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        ctx = _mock_context("EMPLOYEE", tenant_id, user_id)
        emp = _create_mock_employee(tenant_id, employee_id, user_id)
        dev = _create_mock_device(tenant_id, employee_id, "hash1", status="ACTIVE")

        session = AsyncMock()
        # 1. routes.py: resolve emp
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = emp
        # 2. service.py: get_employee_device_status
        mock_dev_res = MagicMock()
        mock_dev_res.scalar_one_or_none.return_value = dev

        session.execute.side_effect = [mock_emp_res, mock_dev_res]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/devices/me")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["is_bound"] is True
            assert data["status"] == "ACTIVE"
            assert data["device"]["id"] == str(dev.id)
        finally:
            app.dependency_overrides.clear()

    async def test_hr_list_devices_authorized(self):
        tenant_id = uuid.uuid4()
        ctx = _mock_context("HR", tenant_id)
        dev1 = _create_mock_device(tenant_id, uuid.uuid4(), "hash1")
        dev2 = _create_mock_device(tenant_id, uuid.uuid4(), "hash2")

        session = AsyncMock()
        # count query
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        # list query
        mock_items = MagicMock()
        mock_items.scalars.return_value.all.return_value = [dev1, dev2]

        session.execute.side_effect = [mock_count, mock_items]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/devices")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["total"] == 2
            assert len(data["items"]) == 2
        finally:
            app.dependency_overrides.clear()

    async def test_employee_list_devices_forbidden(self):
        tenant_id = uuid.uuid4()
        ctx = _mock_context("EMPLOYEE", tenant_id)
        session = AsyncMock()

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/devices")
            assert res.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    async def test_admin_revokes_device_success(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        ctx = _mock_context("ADMIN", tenant_id, user_id)
        dev = _create_mock_device(tenant_id, employee_id, "hash1", status="ACTIVE")

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = dev
        session.execute.return_value = mock_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/devices/{dev.id}/revoke",
                    json={"reason": "Compromised phone reported by security"},
                )
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["status"] == "REVOKED"
            assert data["revocation_reason"] == "Compromised phone reported by security"
        finally:
            app.dependency_overrides.clear()

    async def test_manager_revoke_forbidden(self):
        tenant_id = uuid.uuid4()
        ctx = _mock_context("MANAGER", tenant_id)
        dev_id = uuid.uuid4()
        session = AsyncMock()

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/devices/{dev_id}/revoke",
                    json={"reason": "Manager attempted revocation"},
                )
            assert res.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    async def test_admin_approves_device_replacement_success(self):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        ctx = _mock_context("ADMIN", tenant_id, user_id)

        old_active = _create_mock_device(tenant_id, employee_id, "old-hash", status="ACTIVE")
        new_pending = _create_mock_device(
            tenant_id,
            employee_id,
            "new-hash",
            status="PENDING_APPROVAL",
            replacement_for_device_id=old_active.id,
        )

        session = AsyncMock()
        mock_target = MagicMock()
        mock_target.scalar_one_or_none.return_value = new_pending
        mock_old = MagicMock()
        mock_old.scalar_one_or_none.return_value = old_active

        session.execute.side_effect = [mock_target, mock_old]

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/devices/{new_pending.id}/approve-replacement",
                    json={"notes": "Approved by IT Security"},
                )
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["status"] == "ACTIVE"
        finally:
            app.dependency_overrides.clear()

    async def test_register_device_unauthenticated_returns_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/devices/register",
                json={
                    "device_id": "phone-install-id-12345678",
                    "platform": "ANDROID",
                },
            )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_register_device_invalid_payload_returns_422(self):
        ctx = _mock_context("EMPLOYEE")
        session = AsyncMock()

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # device_id too short (< 8 chars)
                res = await client.post(
                    "/api/v1/devices/register",
                    json={
                        "device_id": "short",
                        "platform": "ANDROID",
                    },
                )
            assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        finally:
            app.dependency_overrides.clear()

    async def test_register_device_user_without_employee_profile_returns_400(self):
        ctx = _mock_context("EMPLOYEE")
        session = AsyncMock()
        mock_emp_res = MagicMock()
        mock_emp_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_emp_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/devices/register",
                    json={
                        "device_id": "phone-install-id-12345678",
                        "platform": "ANDROID",
                    },
                )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert "No employee profile" in res.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    async def test_revoke_device_short_reason_returns_422(self):
        ctx = _mock_context("ADMIN")
        session = AsyncMock()
        dev_id = uuid.uuid4()

        app.dependency_overrides[get_authenticated_context] = lambda: ctx
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/devices/{dev_id}/revoke",
                    json={"reason": "ab"},  # min_length is 3
                )
            assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        finally:
            app.dependency_overrides.clear()

    async def test_cross_tenant_device_access_returns_404(self):
        tenant_a = uuid.uuid4()
        ctx_a = _mock_context("ADMIN", tenant_a)
        dev_b_id = uuid.uuid4()

        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # Filtered out by tenant_a query
        session.execute.return_value = mock_res

        app.dependency_overrides[get_authenticated_context] = lambda: ctx_a
        app.dependency_overrides[get_db] = lambda: session

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/devices/{dev_b_id}")
            assert res.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

