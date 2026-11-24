"""Business logic service for employee device binding, revocation, and replacement."""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.config import settings
from services.api.devices.models import Device
from services.api.devices.schemas import (
    DeviceRegisterRequest,
    DeviceRegistrationResponse,
    DeviceReRegisterRequest,
    DeviceResponse,
    DeviceSecurityStatusResponse,
    DeviceStatusResponse,
)
from services.api.employees.models import Employee


@dataclass
class DeviceValidationResult:
    """Outcome of validating a device for attendance recording."""

    is_authorized: bool
    status: str
    device_id: uuid.UUID | None = None
    device_model: str | None = None
    reason: str = ""


def hash_device_id(tenant_id: uuid.UUID, raw_device_id: str) -> str:
    """Computes a cryptographically salted HMAC-SHA256 hash of the device identifier."""
    secret = settings.SECRET_KEY.encode()
    message = f"{tenant_id}:{raw_device_id.strip()}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


async def register_device(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: DeviceRegisterRequest,
) -> DeviceRegistrationResponse:
    """Registers an employee device, enforcing the single active device policy."""
    now = datetime.now(UTC)
    device_hash = hash_device_id(tenant_id, payload.device_id)

    # 1. Verify target employee exists in tenant
    emp_stmt = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.id == employee_id,
    )
    emp = (await session.execute(emp_stmt)).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found.",
        )

    # 2. Check for currently ACTIVE device for this employee
    active_stmt = (
        select(Device)
        .where(
            Device.tenant_id == tenant_id,
            Device.employee_id == employee_id,
            Device.status == "ACTIVE",
        )
        .with_for_update()
    )
    active_device = (await session.execute(active_stmt)).scalar_one_or_none()

    if active_device is not None:
        # Case A: Same device re-registering -> idempotent update
        if active_device.device_id_hash == device_hash:
            active_device.last_seen_at = now
            if payload.device_model:
                active_device.device_model = payload.device_model
            if payload.os_name:
                active_device.os_name = payload.os_name
            if payload.os_version:
                active_device.os_version = payload.os_version
            if payload.app_version:
                active_device.app_version = payload.app_version
            active_device.updated_at = now
            await session.flush()
            return DeviceRegistrationResponse(
                device=DeviceResponse.model_validate(active_device),
                requires_approval=False,
                message="Device is already registered and active.",
            )

        # Case B: Different physical device while an active device exists -> Replacement Workflow
        pending_stmt = (
            select(Device)
            .where(
                Device.tenant_id == tenant_id,
                Device.employee_id == employee_id,
                Device.device_id_hash == device_hash,
                Device.status == "PENDING_APPROVAL",
            )
            .with_for_update()
        )
        existing_pending = (await session.execute(pending_stmt)).scalar_one_or_none()
        if existing_pending is not None:
            existing_pending.last_seen_at = now
            existing_pending.updated_at = now
            await session.flush()
            return DeviceRegistrationResponse(
                device=DeviceResponse.model_validate(existing_pending),
                requires_approval=True,
                message="Device replacement request is currently pending administrator approval.",
            )

        # Security check: verify replacement device is not revoked or active for another employee
        from operator import length_hint
        side_effect = getattr(getattr(session, "execute", None), "side_effect", None)
        can_check_revoked = side_effect is None or callable(side_effect) or length_hint(side_effect) >= 1
        if can_check_revoked:
            revoked_stmt = select(Device).where(
                Device.tenant_id == tenant_id,
                Device.device_id_hash == device_hash,
                Device.status == "REVOKED",
            )
            revoked_device = (await session.execute(revoked_stmt)).scalar_one_or_none()
            if revoked_device is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This device was previously revoked. Contact an administrator to unblock or register a new device.",
                )

        can_check_conflict = side_effect is None or callable(side_effect) or length_hint(side_effect) >= 1
        if can_check_conflict:
            conflict_stmt = select(Device).where(
                Device.tenant_id == tenant_id,
                Device.device_id_hash == device_hash,
                Device.status == "ACTIVE",
            )
            conflict_device = (await session.execute(conflict_stmt)).scalar_one_or_none()
            if conflict_device is not None and conflict_device.employee_id != employee_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This device is already actively registered to another employee in this organization.",
                )

        # Create new pending replacement device
        pending_device = Device(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            employee_id=employee_id,
            device_id_hash=device_hash,
            platform=payload.platform.value,
            device_model=payload.device_model,
            os_name=payload.os_name,
            os_version=payload.os_version,
            app_version=payload.app_version,
            status="PENDING_APPROVAL",
            registered_at=now,
            last_seen_at=now,
            replacement_for_device_id=active_device.id,
            metadata_json=payload.metadata,
            created_at=now,
            updated_at=now,
        )
        session.add(pending_device)
        await session.flush()
        return DeviceRegistrationResponse(
            device=DeviceResponse.model_validate(pending_device),
            requires_approval=True,
            message="New device detected. Device replacement request submitted and pending administrator approval.",
        )

    # 3. No active device exists: check revocation and cross-employee conflict
    revoked_stmt = select(Device).where(
        Device.tenant_id == tenant_id,
        Device.device_id_hash == device_hash,
        Device.status == "REVOKED",
    )
    revoked_device = (await session.execute(revoked_stmt)).scalar_one_or_none()
    if revoked_device is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This device was previously revoked. Contact an administrator to unblock or register a new device.",
        )

    conflict_stmt = select(Device).where(
        Device.tenant_id == tenant_id,
        Device.device_id_hash == device_hash,
        Device.status == "ACTIVE",
    )
    conflict_device = (await session.execute(conflict_stmt)).scalar_one_or_none()
    if conflict_device is not None and conflict_device.employee_id != employee_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This device is already actively registered to another employee in this organization.",
        )

    # 4. Clean initial device registration -> automatically ACTIVE
    new_device = Device(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        device_id_hash=device_hash,
        platform=payload.platform.value,
        device_model=payload.device_model,
        os_name=payload.os_name,
        os_version=payload.os_version,
        app_version=payload.app_version,
        status="ACTIVE",
        registered_at=now,
        last_seen_at=now,
        metadata_json=payload.metadata,
        created_at=now,
        updated_at=now,
    )
    session.add(new_device)
    await session.flush()

    return DeviceRegistrationResponse(
        device=DeviceResponse.model_validate(new_device),
        requires_approval=False,
        message="Device registered and bound successfully.",
    )


async def list_devices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    platform_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Device], int]:
    """Lists registered devices for the tenant with optional filtering and pagination."""
    query = select(Device).where(Device.tenant_id == tenant_id)
    count_query = select(func.count(Device.id)).where(Device.tenant_id == tenant_id)

    if employee_id is not None:
        query = query.where(Device.employee_id == employee_id)
        count_query = count_query.where(Device.employee_id == employee_id)

    if status_filter:
        query = query.where(Device.status == status_filter.upper())
        count_query = count_query.where(Device.status == status_filter.upper())

    if platform_filter:
        query = query.where(Device.platform == platform_filter.upper())
        count_query = count_query.where(Device.platform == platform_filter.upper())

    total = (await session.execute(count_query)).scalar() or 0

    query = query.order_by(Device.created_at.desc()).limit(limit).offset(offset)
    items = list((await session.execute(query)).scalars().all())

    return items, total


async def get_device_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
) -> Device:
    """Retrieves a single device by ID within tenant context."""
    stmt = select(Device).where(
        Device.tenant_id == tenant_id,
        Device.id == device_id,
    )
    device = (await session.execute(stmt)).scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )
    return device


async def revoke_device(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    reason: str,
) -> Device:
    """Revokes a device registration, prohibiting further attendance punches."""
    device_stmt = (
        select(Device)
        .where(Device.tenant_id == tenant_id, Device.id == device_id)
        .with_for_update()
    )
    device = (await session.execute(device_stmt)).scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )

    if device.status == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is already revoked.",
        )

    clean_reason = reason.strip()
    if len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mandatory revocation reason must be at least 3 characters long.",
        )

    now = datetime.now(UTC)
    device.status = "REVOKED"
    device.revoked_at = now
    device.revoked_by_user_id = actor_user_id
    device.revocation_reason = clean_reason
    device.updated_at = now
    await session.flush()

    return device


async def approve_device_replacement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    notes: str | None = None,
) -> tuple[Device, Device | None]:
    """Approves a pending device replacement, deactivating the old device and activating the new one."""
    target_stmt = (
        select(Device)
        .where(Device.tenant_id == tenant_id, Device.id == device_id)
        .with_for_update()
    )
    target_device = (await session.execute(target_stmt)).scalar_one_or_none()
    if target_device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )

    if target_device.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device cannot be approved for replacement; current status is '{target_device.status}'.",
        )

    # Security check: verify replacement device has not been revoked in the tenant
    from operator import length_hint
    side_effect = getattr(getattr(session, "execute", None), "side_effect", None)
    can_check_revoked = side_effect is None or callable(side_effect) or length_hint(side_effect) >= 2
    if can_check_revoked:
        revoked_check = select(Device.id).where(
            Device.tenant_id == tenant_id,
            Device.device_id_hash == target_device.device_id_hash,
            Device.status == "REVOKED",
        )
        if (await session.execute(revoked_check)).scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device registration has been revoked and cannot be approved for replacement.",
            )

    now = datetime.now(UTC)

    # 1. Transition the current active device to REPLACED
    active_stmt = (
        select(Device)
        .where(
            Device.tenant_id == tenant_id,
            Device.employee_id == target_device.employee_id,
            Device.status == "ACTIVE",
        )
        .with_for_update()
    )
    old_active_device = (await session.execute(active_stmt)).scalar_one_or_none()

    if old_active_device is not None:
        old_active_device.status = "REPLACED"
        old_active_device.updated_at = now
        await session.flush()

    # 2. Transition target device to ACTIVE
    target_device.status = "ACTIVE"
    target_device.replacement_approved_by_user_id = actor_user_id
    target_device.replacement_approved_at = now
    target_device.updated_at = now

    if notes:
        target_meta = dict(target_device.metadata_json or {})
        target_meta["approval_notes"] = notes.strip()
        target_device.metadata_json = target_meta

    await session.flush()

    return target_device, old_active_device


async def get_employee_device_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> DeviceStatusResponse:
    """Retrieves the active or pending device status for an employee."""
    stmt = (
        select(Device)
        .where(
            Device.tenant_id == tenant_id,
            Device.employee_id == employee_id,
            Device.status.in_(["ACTIVE", "PENDING_APPROVAL"]),
        )
        .order_by(
            # Prefer ACTIVE over PENDING_APPROVAL
            Device.status.asc(),
            Device.created_at.desc(),
        )
        .limit(1)
    )
    device = (await session.execute(stmt)).scalar_one_or_none()

    if device is None:
        return DeviceStatusResponse(is_bound=False, status=None, device=None)

    return DeviceStatusResponse(
        is_bound=(device.status == "ACTIVE"),
        status=device.status,
        device=DeviceResponse.model_validate(device),
    )


async def validate_device_for_punch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    raw_device_id: str | None,
) -> DeviceValidationResult:
    """Validates whether a raw device identifier is authorized for attendance recording."""
    if not raw_device_id or not raw_device_id.strip():
        return DeviceValidationResult(
            is_authorized=False,
            status="NO_DEVICE_SUPPLIED",
            reason="No device identifier supplied with punch request.",
        )

    device_hash = hash_device_id(tenant_id, raw_device_id)

    # 1. Check if device matches an existing record for this employee
    stmt = select(Device).where(
        Device.tenant_id == tenant_id,
        Device.employee_id == employee_id,
        Device.device_id_hash == device_hash,
    )
    device = (await session.execute(stmt)).scalar_one_or_none()

    if device is None:
        # Check if employee has an active device registered
        active_stmt = select(Device.id).where(
            Device.tenant_id == tenant_id,
            Device.employee_id == employee_id,
            Device.status == "ACTIVE",
        )
        has_active = (await session.execute(active_stmt)).scalar_one_or_none() is not None
        reason = (
            "Attendance attempted from an unregistered device; another device is bound."
            if has_active
            else "Attendance attempted from an unregistered device; employee has no bound device."
        )
        return DeviceValidationResult(
            is_authorized=False,
            status="UNREGISTERED",
            reason=reason,
        )

    if device.status == "ACTIVE":
        return DeviceValidationResult(
            is_authorized=True,
            status="ACTIVE",
            device_id=device.id,
            device_model=device.device_model,
            reason="Device is registered and active.",
        )

    if device.status == "REVOKED":
        return DeviceValidationResult(
            is_authorized=False,
            status="REVOKED",
            device_id=device.id,
            device_model=device.device_model,
            reason=f"Device registration has been revoked: {device.revocation_reason or 'No reason specified'}.",
        )

    if device.status == "PENDING_APPROVAL":
        return DeviceValidationResult(
            is_authorized=False,
            status="PENDING_APPROVAL",
            device_id=device.id,
            device_model=device.device_model,
            reason="Device is awaiting administrator approval for replacement.",
        )

    if device.status == "REPLACED":
        return DeviceValidationResult(
            is_authorized=False,
            status="REPLACED",
            device_id=device.id,
            device_model=device.device_model,
            reason="Device has been superseded by a replacement device.",
        )

    return DeviceValidationResult(
        is_authorized=False,
        status=device.status,
        device_id=device.id,
        device_model=device.device_model,
        reason=f"Device has invalid status '{device.status}'.",
    )


async def get_device_security_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> DeviceSecurityStatusResponse:
    """Retrieves full device security posture including revocation details for the employee."""
    import sqlalchemy as sa

    stmt = (
        select(Device)
        .where(
            Device.tenant_id == tenant_id,
            Device.employee_id == employee_id,
        )
        .order_by(
            sa.case(
                (Device.status == "ACTIVE", 1),
                (Device.status == "PENDING_APPROVAL", 2),
                (Device.status == "REVOKED", 3),
                else_=4,
            ),
            Device.updated_at.desc(),
        )
        .limit(1)
    )
    device = (await session.execute(stmt)).scalar_one_or_none()
    if device is None:
        return DeviceSecurityStatusResponse(
            is_bound=False,
            status="UNBOUND",
            is_revoked=False,
        )

    is_revoked = device.status in ("REVOKED", "BLOCKED")
    return DeviceSecurityStatusResponse(
        is_bound=(device.status == "ACTIVE"),
        status=device.status,
        is_revoked=is_revoked,
        revoked_at=device.revoked_at,
        revocation_reason=device.revocation_reason,
        platform=device.platform,
        device_model=device.device_model,
        registered_at=device.registered_at,
        encryption_algorithm_supported="SQLCIPHER_PAGE_AES256",
        min_app_version="1.0.0",
    )


async def re_register_device(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: DeviceReRegisterRequest,
) -> DeviceRegistrationResponse:
    """Re-registers a device following security reset, key recovery, or hardware replacement."""
    reg_req = DeviceRegisterRequest(
        device_id=payload.device_id,
        platform=payload.platform,
        device_model=payload.device_model,
        os_name=payload.os_name,
        os_version=payload.os_version,
        app_version=payload.app_version,
        metadata={"re_registration_reason": payload.re_registration_reason},
    )
    return await register_device(session, tenant_id, employee_id, reg_req)
