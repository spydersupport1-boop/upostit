"""Business logic service for employee invitations and account activation."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.models import User
from services.api.auth.permissions import UserRole
from services.api.auth.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_strength,
)
from services.api.common.email import email_service
from services.api.config import settings
from services.api.database import set_tenant_context
from services.api.employees.invitation_schemas import (
    ActivateAccountRequest,
    ActivateAccountResponse,
    InvitationListResponse,
    InvitationResponse,
    ValidateInvitationResponse,
)
from services.api.employees.models import Employee, EmployeeInvitation
from services.api.tenants.models import Tenant

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5


def _to_invitation_response(
    invitation: EmployeeInvitation,
    raw_token: str | None = None,
) -> InvitationResponse:
    """Formats an EmployeeInvitation into an InvitationResponse, attaching preview URL only in dev/test."""
    now = datetime.now(UTC)
    preview_url = None
    if raw_token and settings.ENVIRONMENT != "production":
        preview_url = f"{settings.FRONTEND_URL}/activate?token={raw_token}"

    return InvitationResponse(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        employee_id=invitation.employee_id,
        invited_by_user_id=invitation.invited_by_user_id,
        email=invitation.email,
        status=invitation.status or "pending",
        delivery_status=invitation.delivery_status or "pending",
        delivery_error=invitation.delivery_error,
        attempt_count=invitation.attempt_count or 0,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at or now,
        updated_at=invitation.updated_at or now,
        preview_url=preview_url,
    )


async def create_employee_invitation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> InvitationResponse:
    """
    Creates and dispatches an invitation link for an existing employee.
    Enforces tenant scoping, active employment, and single active invitation uniqueness.
    """
    # 1. Verify employee exists within current tenant
    emp_res = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
        )
    )
    employee = emp_res.scalar_one_or_none()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found in your organization",
        )

    # 2. Prevent inviting terminated employees
    if employee.status == "terminated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send an invitation to a terminated employee",
        )

    # 3. Check if employee already has an active user account
    if employee.user_id is not None:
        user_res = await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == employee.user_id,
            )
        )
        existing_user = user_res.scalar_one_or_none()
        if existing_user and existing_user.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee profile is already linked to an active user account",
            )

    # 4. Check for existing pending invitation
    existing_inv_res = await session.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.tenant_id == tenant_id,
            EmployeeInvitation.employee_id == employee_id,
            EmployeeInvitation.status == "pending",
        )
    )
    existing_inv = existing_inv_res.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing_inv:
        if existing_inv.expires_at <= now:
            existing_inv.status = "expired"
            await session.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active invitation already exists for this employee. Use resend or revoke.",
            )

    # 5. Generate secure random token and SHA-256 hash
    raw_token = generate_secure_token()
    token_hash_val = hash_token(raw_token)
    expires_at = now + timedelta(hours=settings.INVITATION_TOKEN_EXPIRE_HOURS)

    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=employee_id,
        invited_by_user_id=current_user_id,
        email=employee.work_email,
        token_hash=token_hash_val,
        status="pending",
        delivery_status="pending",
        attempt_count=0,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.flush()

    # 6. Retrieve company name for email template
    tenant_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    company_name = tenant.name if tenant else "Your Organization"

    # 7. Dispatch invitation email
    activation_url = f"{settings.FRONTEND_URL}/activate?token={raw_token}"
    recipient_name = f"{employee.first_name} {employee.last_name}".strip()

    delivery_result = await email_service.send_invitation_email(
        recipient_email=employee.work_email,
        recipient_name=recipient_name,
        company_name=company_name,
        raw_token=raw_token,
        activation_url=activation_url,
    )
    invitation.delivery_status = delivery_result.status
    invitation.delivery_error = delivery_result.error_message

    await session.commit()
    await session.refresh(invitation)

    return _to_invitation_response(invitation, raw_token)


async def list_invitations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    status_filter: str | None = None,
    employee_id_filter: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> InvitationListResponse:
    """Lists employee invitations for the current tenant with optional filtering."""
    base_query = select(EmployeeInvitation).where(EmployeeInvitation.tenant_id == tenant_id)

    if status_filter:
        base_query = base_query.where(EmployeeInvitation.status == status_filter)
    if employee_id_filter:
        base_query = base_query.where(EmployeeInvitation.employee_id == employee_id_filter)

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    count_res = await session.execute(count_query)
    total = count_res.scalar_one() or 0

    # Paginate
    paged_query = (
        base_query.order_by(EmployeeInvitation.created_at.desc()).offset(skip).limit(limit)
    )
    result = await session.execute(paged_query)
    invitations = result.scalars().all()

    items = [_to_invitation_response(inv) for inv in invitations]
    return InvitationListResponse(items=items, total=total, skip=skip, limit=limit)


async def get_invitation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> InvitationResponse:
    """Retrieves a single invitation by ID within the current tenant."""
    res = await session.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.tenant_id == tenant_id,
            EmployeeInvitation.id == invitation_id,
        )
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    return _to_invitation_response(invitation)


async def resend_invitation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> InvitationResponse:
    """
    Regenerates token and dispatches a fresh invitation email for an unaccepted invitation.
    Resets expiration time and failed attempt counter.
    """
    res = await session.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.tenant_id == tenant_id,
            EmployeeInvitation.id == invitation_id,
        )
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resend an already accepted invitation",
        )

    # Verify employee profile eligibility
    emp_res = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == invitation.employee_id,
        )
    )
    employee = emp_res.scalar_one_or_none()
    if not employee or employee.status == "terminated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee profile is no longer active or eligible for invitation",
        )

    if employee.user_id is not None:
        user_res = await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == employee.user_id,
            )
        )
        existing_user = user_res.scalar_one_or_none()
        if existing_user and existing_user.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee profile is already linked to an active user account",
            )

    now = datetime.now(UTC)
    raw_token = generate_secure_token()
    invitation.token_hash = hash_token(raw_token)
    invitation.expires_at = now + timedelta(hours=settings.INVITATION_TOKEN_EXPIRE_HOURS)
    invitation.status = "pending"
    invitation.attempt_count = 0
    invitation.revoked_at = None
    invitation.invited_by_user_id = current_user_id

    # Retrieve company name
    tenant_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    company_name = tenant.name if tenant else "Your Organization"

    activation_url = f"{settings.FRONTEND_URL}/activate?token={raw_token}"
    recipient_name = f"{employee.first_name} {employee.last_name}".strip()

    delivery_result = await email_service.send_invitation_email(
        recipient_email=employee.work_email,
        recipient_name=recipient_name,
        company_name=company_name,
        raw_token=raw_token,
        activation_url=activation_url,
    )
    invitation.delivery_status = delivery_result.status
    invitation.delivery_error = delivery_result.error_message

    await session.commit()
    await session.refresh(invitation)

    return _to_invitation_response(invitation, raw_token)


async def revoke_invitation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user_id: uuid.UUID,  # noqa: ARG001
) -> InvitationResponse:
    """Revokes an outstanding invitation, preventing future activation."""
    res = await session.execute(
        select(EmployeeInvitation).where(
            EmployeeInvitation.tenant_id == tenant_id,
            EmployeeInvitation.id == invitation_id,
        )
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke an already accepted invitation",
        )

    invitation.status = "revoked"
    invitation.revoked_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(invitation)

    return _to_invitation_response(invitation)


async def validate_public_invitation_token(
    session: AsyncSession,
    raw_token: str,
) -> ValidateInvitationResponse:
    """
    Public validation endpoint.
    Verifies that the invitation token is active, non-expired, and under attempt limits.
    Never exposes internal IDs, hashes, or passwords.
    """
    if not raw_token or len(raw_token) < 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation token format",
        )

    token_hash_val = hash_token(raw_token)
    res = await session.execute(
        select(EmployeeInvitation).where(EmployeeInvitation.token_hash == token_hash_val)
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation token",
        )

    if invitation.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has been revoked by your administrator",
        )

    if invitation.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been accepted and cannot be reused",
        )

    if invitation.attempt_count >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum activation attempts exceeded. This invitation is locked. Contact your administrator.",
        )

    now = datetime.now(UTC)
    if invitation.expires_at <= now:
        if invitation.status == "pending":
            invitation.status = "expired"
            await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired. Please request a new invitation.",
        )

    # Retrieve employee and tenant details for public confirmation UI
    emp_res = await session.execute(
        select(Employee).where(
            Employee.tenant_id == invitation.tenant_id,
            Employee.id == invitation.employee_id,
        )
    )
    employee = emp_res.scalar_one_or_none()
    tenant_res = await session.execute(
        select(Tenant).where(Tenant.id == invitation.tenant_id)
    )
    tenant = tenant_res.scalar_one_or_none()

    if not employee or employee.status == "terminated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee profile is no longer eligible for activation",
        )

    return ValidateInvitationResponse(
        valid=True,
        email=invitation.email,
        employee_name=f"{employee.first_name} {employee.last_name}".strip(),
        company_name=tenant.name if tenant else "Your Organization",
        expires_at=invitation.expires_at,
    )


async def activate_account(
    session: AsyncSession,
    req: ActivateAccountRequest,
) -> ActivateAccountResponse:
    """
    Atomically activates an account via invitation token:
    1. Validates token with row lock.
    2. Enforces attempt lockout (max 5).
    3. Validates and hashes password using enterprise Argon2id.
    4. Creates or updates user record under the invitation's tenant.
    5. Links employee.user_id.
    6. Marks invitation as accepted and revokes other pending invitations.
    """
    token_hash_val = hash_token(req.token)

    # 1. Lock invitation row for concurrency safety
    res = await session.execute(
        select(EmployeeInvitation)
        .where(EmployeeInvitation.token_hash == token_hash_val)
        .with_for_update()
    )
    invitation = res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation token",
        )

    # 2. Check failed attempt limits
    if invitation.attempt_count >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum activation attempts exceeded. This invitation is locked. Contact your administrator.",
        )

    # 3. Status checks
    if invitation.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been accepted and cannot be reused",
        )
    if invitation.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has been revoked",
        )
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation state",
        )

    # 4. Expiration check
    now = datetime.now(UTC)
    if invitation.expires_at <= now:
        invitation.status = "expired"
        invitation.attempt_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    # 5. Check password matching and strength (failures increment attempt count)
    if req.password != req.password_confirm:
        invitation.attempt_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirmation do not match",
        )

    try:
        validate_password_strength(req.password)
    except HTTPException as e:
        invitation.attempt_count += 1
        await session.commit()
        raise e

    # 6. Set tenant context to invitation's tenant for isolated execution
    await set_tenant_context(session, str(invitation.tenant_id))

    # 7. Lock employee record to prevent concurrent linking race conditions
    emp_res = await session.execute(
        select(Employee)
        .where(
            Employee.tenant_id == invitation.tenant_id,
            Employee.id == invitation.employee_id,
        )
        .with_for_update()
    )
    employee = emp_res.scalar_one_or_none()
    if not employee or employee.status == "terminated":
        invitation.attempt_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee profile is no longer eligible for account activation",
        )

    # 8. Prevent email spoofing: email must match employee record
    if employee.work_email.lower().strip() != invitation.email.lower().strip():
        invitation.attempt_count += 1
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email mismatch between employee record and invitation",
        )

    # 9. Verify employee does not already have an active linked user
    if employee.user_id is not None:
        user_res = await session.execute(
            select(User).where(
                User.tenant_id == invitation.tenant_id,
                User.id == employee.user_id,
            )
        )
        existing_user = user_res.scalar_one_or_none()
        if existing_user and existing_user.status == "active":
            invitation.status = "revoked"
            invitation.revoked_at = now
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee profile is already linked to an active user account",
            )

    # 10. Hash password using Argon2id
    password_hash_val = hash_password(req.password)

    # 11. Find or create user account within the tenant
    user_res = await session.execute(
        select(User).where(
            User.tenant_id == invitation.tenant_id,
            User.email == invitation.email.lower().strip(),
        )
    )
    user = user_res.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            tenant_id=invitation.tenant_id,
            full_name=f"{employee.first_name} {employee.last_name}".strip(),
            email=invitation.email.lower().strip(),
            password_hash=password_hash_val,
            role=UserRole.EMPLOYEE.value,
            status="active",
            email_verified_at=now,
        )
        session.add(user)
        await session.flush()
    else:
        user.password_hash = password_hash_val
        user.status = "active"
        user.email_verified_at = now

    # 12. Atomically link employee to user account
    employee.user_id = user.id

    # 13. Mark invitation as accepted
    invitation.status = "accepted"
    invitation.accepted_at = now

    # 14. Invalidate/revoke any other outstanding invitations for this employee
    await session.execute(
        update(EmployeeInvitation)
        .where(
            EmployeeInvitation.tenant_id == invitation.tenant_id,
            EmployeeInvitation.employee_id == invitation.employee_id,
            EmployeeInvitation.id != invitation.id,
            EmployeeInvitation.status == "pending",
        )
        .values(status="revoked", revoked_at=now)
    )

    await session.commit()

    logger.info(
        "Successfully activated employee account %s (user_id: %s) for tenant %s",
        employee.id,
        user.id,
        invitation.tenant_id,
    )

    return ActivateAccountResponse(
        success=True,
        message="Account activated successfully. You may now sign in.",
        user_id=user.id,
        email=user.email,
    )
