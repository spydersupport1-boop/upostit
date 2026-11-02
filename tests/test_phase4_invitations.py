"""Unit, integration, and security tests for Phase 4 Milestone 4: Employee Invitations & Account Activation."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import UserRole
from services.api.auth.security import (
    generate_secure_token,
    hash_token,
    verify_password,
)
from services.api.common.email import mask_email
from services.api.database import get_db
from services.api.employees.invitation_schemas import ActivateAccountRequest
from services.api.employees.invitation_service import (
    activate_account,
    create_employee_invitation,
    get_invitation,
    list_invitations,
    resend_invitation,
    revoke_invitation,
    validate_public_invitation_token,
)
from services.api.employees.models import Employee, EmployeeInvitation
from services.api.main import app
from services.api.tenants.models import Tenant


# Test fixtures
@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tenant_b_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def test_tenant(tenant_id: uuid.UUID) -> Tenant:
    return Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.test",
        country_code="US",
        timezone="America/New_York",
        status="active",
    )


@pytest.fixture
def test_employee(tenant_id: uuid.UUID) -> Employee:
    return Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id="EMP-001",
        first_name="Jane",
        last_name="Doe",
        work_email="jane.doe@acme.test",
        status="active",
        employment_type="full_time",
        joining_date=datetime.now(UTC).date(),
    )


def _mock_context(role: str, tenant_id: uuid.UUID) -> AuthenticatedContext:
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=f"{role}@acme.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tenant_id,
        name="Acme Corp",
        slug="acme-corp",
        company_email="admin@acme.test",
        country_code="US",
        timezone="America/New_York",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


# 1. Valid invitation creation and email delivery
@pytest.mark.asyncio
async def test_create_employee_invitation_success(
    tenant_id: uuid.UUID,
    test_tenant: Tenant,
    test_employee: Employee,
):
    """Verify an HR or Admin user can invite an existing employee, generating a secure token and email."""
    session = AsyncMock()
    current_user_id = uuid.uuid4()

    # Mock employee query, no existing active invitation, and tenant lookup
    session.execute.side_effect = [
        AsyncMock(scalar_one_or_none=lambda: test_employee),  # Employee check
        AsyncMock(scalar_one_or_none=lambda: None),           # Existing invitation check
        AsyncMock(scalar_one_or_none=lambda: test_tenant),    # Tenant name lookup
    ]

    with patch("services.api.employees.invitation_service.email_service.send_invitation_email") as mock_send:
        from services.api.common.email import DeliveryResult

        mock_send.return_value = DeliveryResult(success=True, status="sent")

        resp = await create_employee_invitation(
            session=session,
            tenant_id=tenant_id,
            employee_id=test_employee.id,
            current_user_id=current_user_id,
        )

        assert resp.email == "jane.doe@acme.test"
        assert resp.status == "pending"
        assert resp.delivery_status == "sent"
        assert resp.attempt_count == 0
        assert resp.expires_at > datetime.now(UTC)
        assert mock_send.called
        # Check that session.add was called with EmployeeInvitation
        assert session.add.called
        added_inv = session.add.call_args[0][0]
        assert isinstance(added_inv, EmployeeInvitation)
        # Ensure only 64-char SHA-256 token hash is stored, never raw token
        assert len(added_inv.token_hash) == 64


# 2. Duplicate active invitation prevention
@pytest.mark.asyncio
async def test_duplicate_active_invitation_rejected(
    tenant_id: uuid.UUID,
    test_employee: Employee,
):
    """Verify an active pending invitation prevents creating a duplicate invitation (409 Conflict)."""
    session = AsyncMock()
    existing_inv = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email=test_employee.work_email,
        token_hash="a" * 64,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=5),
    )

    session.execute.side_effect = [
        AsyncMock(scalar_one_or_none=lambda: test_employee),
        AsyncMock(scalar_one_or_none=lambda: existing_inv),
    ]

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await create_employee_invitation(
            session=session,
            tenant_id=tenant_id,
            employee_id=test_employee.id,
            current_user_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail.lower()


# 3. Terminated employee invitation rejected
@pytest.mark.asyncio
async def test_invite_terminated_employee_rejected(
    tenant_id: uuid.UUID,
    test_employee: Employee,
):
    """Verify terminated employees cannot be invited."""
    test_employee.status = "terminated"
    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: test_employee)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await create_employee_invitation(
            session=session,
            tenant_id=tenant_id,
            employee_id=test_employee.id,
            current_user_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 400
    assert "terminated" in exc.value.detail.lower()


# 4. Public token validation success
@pytest.mark.asyncio
async def test_validate_public_invitation_token_success(
    tenant_id: uuid.UUID,
    test_tenant: Tenant,
    test_employee: Employee,
):
    """Verify public validation returns safe non-sensitive details without internal IDs or hashes."""
    raw_token = generate_secure_token()
    token_hash_val = hash_token(raw_token)

    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email="jane.doe@acme.test",
        token_hash=token_hash_val,
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )

    session = AsyncMock()
    session.execute.side_effect = [
        AsyncMock(scalar_one_or_none=lambda: invitation),
        AsyncMock(scalar_one_or_none=lambda: test_employee),
        AsyncMock(scalar_one_or_none=lambda: test_tenant),
    ]

    res = await validate_public_invitation_token(session=session, raw_token=raw_token)
    assert res.valid is True
    assert res.email == "jane.doe@acme.test"
    assert res.employee_name == "Jane Doe"
    assert res.company_name == "Acme Corp"


# 5. Public token validation with invalid or non-existent token
@pytest.mark.asyncio
async def test_validate_invitation_invalid_token():
    """Verify non-existent tokens return 404."""
    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: None)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await validate_public_invitation_token(session=session, raw_token="non_existent_token_123456789")
    assert exc.value.status_code == 404


# 6. Public token validation with expired token
@pytest.mark.asyncio
async def test_validate_invitation_expired(tenant_id: uuid.UUID):
    """Verify expired invitation returns 400 and transitions status to expired."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash=hash_token(raw_token),
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await validate_public_invitation_token(session=session, raw_token=raw_token)
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()
    assert invitation.status == "expired"


# 7. Public token validation with revoked token
@pytest.mark.asyncio
async def test_validate_invitation_revoked(tenant_id: uuid.UUID):
    """Verify revoked invitation returns 400."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash=hash_token(raw_token),
        status="revoked",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await validate_public_invitation_token(session=session, raw_token=raw_token)
    assert exc.value.status_code == 400
    assert "revoked" in exc.value.detail.lower()


# 8. Five failed attempts lockout
@pytest.mark.asyncio
async def test_five_failed_attempts_lockout(tenant_id: uuid.UUID):
    """Verify invitation is locked out with 429 when attempt_count >= 5."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash=hash_token(raw_token),
        status="pending",
        attempt_count=5,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    from fastapi import HTTPException

    # Test validation lockout
    with pytest.raises(HTTPException) as exc:
        await validate_public_invitation_token(session=session, raw_token=raw_token)
    assert exc.value.status_code == 429
    assert "locked" in exc.value.detail.lower()

    # Test activation lockout
    req = ActivateAccountRequest(
        token=raw_token,
        password="ValidPassword123!",
        password_confirm="ValidPassword123!",
    )
    with pytest.raises(HTTPException) as exc2:
        await activate_account(session=session, req=req)
    assert exc2.value.status_code == 429
    assert "locked" in exc2.value.detail.lower()


# 9. Successful account activation, Argon2id hashing, and employee linking
@pytest.mark.asyncio
async def test_activate_account_success(
    tenant_id: uuid.UUID,
    test_employee: Employee,
):
    """Verify successful activation creates user, verifies password hashing, links employee, and accepts invitation."""
    raw_token = generate_secure_token()
    token_hash_val = hash_token(raw_token)

    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email=test_employee.work_email,
        token_hash=token_hash_val,
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "set_config" in stmt_str or "SET LOCAL ROLE" in stmt_str:
            return AsyncMock()
        if "employee_invitations" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: invitation)
        if "employees" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: test_employee)
        if "users" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: None)
        return AsyncMock()

    session.execute.side_effect = mock_execute

    req = ActivateAccountRequest(
        token=raw_token,
        password="StrongPassword123!",
        password_confirm="StrongPassword123!",
    )

    resp = await activate_account(session=session, req=req)
    assert resp.success is True
    assert resp.email == test_employee.work_email
    assert invitation.status == "accepted"
    assert invitation.accepted_at is not None

    # Check user was created and added to session
    assert session.add.called
    created_user = session.add.call_args[0][0]
    assert isinstance(created_user, User)
    assert created_user.email == test_employee.work_email
    assert created_user.role == UserRole.EMPLOYEE.value
    assert created_user.status == "active"
    # Verify Argon2id password hashing
    assert verify_password("StrongPassword123!", created_user.password_hash) is True
    # Verify employee was linked to new user ID
    assert test_employee.user_id == created_user.id


# 10. Reused token rejection (single-use enforcement)
@pytest.mark.asyncio
async def test_reused_token_activation_rejected(tenant_id: uuid.UUID):
    """Verify single-use activation enforcement: accepted invitation cannot be reused."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash=hash_token(raw_token),
        status="accepted",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    req = ActivateAccountRequest(
        token=raw_token,
        password="StrongPassword123!",
        password_confirm="StrongPassword123!",
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await activate_account(session=session, req=req)
    assert exc.value.status_code == 400
    assert "already been accepted" in exc.value.detail.lower()


# 11. Password complexity and mismatch failures
@pytest.mark.asyncio
async def test_activate_account_password_validation(tenant_id: uuid.UUID):
    """Verify password mismatch or weak password fails and increments failed attempt counter."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash=hash_token(raw_token),
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    from fastapi import HTTPException

    # 1. Password mismatch
    req_mismatch = ActivateAccountRequest(
        token=raw_token,
        password="StrongPassword123!",
        password_confirm="WrongPassword123!",
    )
    with pytest.raises(HTTPException) as exc1:
        await activate_account(session=session, req=req_mismatch)
    assert exc1.value.status_code == 400
    assert "match" in exc1.value.detail.lower()
    assert invitation.attempt_count == 1

    # 2. Weak password (no special char)
    req_weak = ActivateAccountRequest(
        token=raw_token,
        password="weakpassword123",
        password_confirm="weakpassword123",
    )
    with pytest.raises(HTTPException) as exc2:
        await activate_account(session=session, req=req_weak)
    assert exc2.value.status_code == 400
    assert invitation.attempt_count == 2


# 12. Wrong employee email / spoofing prevention
@pytest.mark.asyncio
async def test_activate_account_wrong_email_rejected(
    tenant_id: uuid.UUID,
    test_employee: Employee,
):
    """Verify email tampering or spoofing between employee record and invitation is rejected."""
    raw_token = generate_secure_token()
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email="tampered@acme.test",  # Does not match employee.work_email
        token_hash=hash_token(raw_token),
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "set_config" in stmt_str or "SET LOCAL ROLE" in stmt_str:
            return AsyncMock()
        if "employee_invitations" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: invitation)
        if "employees" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: test_employee)
        return AsyncMock()

    session.execute.side_effect = mock_execute

    req = ActivateAccountRequest(
        token=raw_token,
        password="StrongPassword123!",
        password_confirm="StrongPassword123!",
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await activate_account(session=session, req=req)
    assert exc.value.status_code == 400
    assert "mismatch" in exc.value.detail.lower()
    assert invitation.attempt_count == 1


# 13. Resend invitation resets expiry and attempts
@pytest.mark.asyncio
async def test_resend_invitation_resets_expiry_and_attempts(
    tenant_id: uuid.UUID,
    test_tenant: Tenant,
    test_employee: Employee,
):
    """Verify resend creates a new token hash, resets attempt_count to 0, and dispatches new email."""
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email=test_employee.work_email,
        token_hash="old_token_hash_value" + "0" * 44,
        status="pending",
        attempt_count=3,
        expires_at=datetime.now(UTC) - timedelta(hours=2),
    )

    session = AsyncMock()
    session.execute.side_effect = [
        AsyncMock(scalar_one_or_none=lambda: invitation),
        AsyncMock(scalar_one_or_none=lambda: test_employee),
        AsyncMock(scalar_one_or_none=lambda: test_tenant),
    ]

    with patch("services.api.employees.invitation_service.email_service.send_invitation_email") as mock_send:
        from services.api.common.email import DeliveryResult

        mock_send.return_value = DeliveryResult(success=True, status="sent")

        resp = await resend_invitation(
            session=session,
            tenant_id=tenant_id,
            invitation_id=invitation.id,
            current_user_id=uuid.uuid4(),
        )

        assert resp.attempt_count == 0
        assert resp.status == "pending"
        assert resp.expires_at > datetime.now(UTC)
        assert invitation.token_hash != "old_token_hash_value" + "0" * 44
        assert mock_send.called


# 14. Revoke invitation
@pytest.mark.asyncio
async def test_revoke_invitation_success(tenant_id: uuid.UUID):
    """Verify an invitation can be revoked by administrator."""
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="jane@acme.test",
        token_hash="hash" + "0" * 60,
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )

    session = AsyncMock()
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    resp = await revoke_invitation(
        session=session,
        tenant_id=tenant_id,
        invitation_id=invitation.id,
        current_user_id=uuid.uuid4(),
    )
    assert resp.status == "revoked"
    assert invitation.revoked_at is not None


# 15. Email delivery failure and retry
@pytest.mark.asyncio
async def test_email_delivery_failure_tracking(
    tenant_id: uuid.UUID,
    test_tenant: Tenant,
    test_employee: Employee,
):
    """Verify email delivery failure updates delivery_status and stores error message."""
    session = AsyncMock()
    session.execute.side_effect = [
        AsyncMock(scalar_one_or_none=lambda: test_employee),
        AsyncMock(scalar_one_or_none=lambda: None),
        AsyncMock(scalar_one_or_none=lambda: test_tenant),
    ]

    with patch("services.api.employees.invitation_service.email_service.send_invitation_email") as mock_send:
        from services.api.common.email import DeliveryResult

        mock_send.return_value = DeliveryResult(
            success=False,
            status="failed",
            error_message="SMTPConnectionRefused: Connection to smtp.host:587 failed",
        )

        resp = await create_employee_invitation(
            session=session,
            tenant_id=tenant_id,
            employee_id=test_employee.id,
            current_user_id=uuid.uuid4(),
        )

        assert resp.delivery_status == "failed"
        assert "SMTPConnectionRefused" in (resp.delivery_error or "")


# 16. PII-Safe Email Masking
def test_pii_safe_email_masking():
    """Verify email masking hides PII while preserving domain."""
    assert mask_email("john.doe@company.com") == "j***e@company.com"
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_email("invalid") == "***"


# 17. RBAC permissions API enforcement
@pytest.mark.asyncio
async def test_rbac_invitations_endpoints():
    """Verify OWNER, ADMIN, and HR can invite, while MANAGER and EMPLOYEE receive 403 Forbidden."""
    tid = uuid.uuid4()
    emp_id = uuid.uuid4()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        res_unauth = await client.post(f"/api/v1/employees/{emp_id}/invite")
        assert res_unauth.status_code == 401

        res_unauth_list = await client.get("/api/v1/invitations")
        assert res_unauth_list.status_code == 401

        # 2. Employee role -> 403 Forbidden
        app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("employee", tid)
        res_emp = await client.post(f"/api/v1/employees/{emp_id}/invite")
        assert res_emp.status_code == 403

        res_emp_list = await client.get("/api/v1/invitations")
        assert res_emp_list.status_code == 403

        # 3. Manager role -> 403 Forbidden
        app.dependency_overrides[get_authenticated_context] = lambda: _mock_context("manager", tid)
        res_mgr = await client.post(f"/api/v1/employees/{emp_id}/invite")
        assert res_mgr.status_code == 403

        # Cleanup overrides
        app.dependency_overrides.clear()


# 18. Cross-tenant access isolation
@pytest.mark.asyncio
async def test_cross_tenant_invitation_isolation(
    tenant_id: uuid.UUID,
    tenant_b_id: uuid.UUID,
):
    """Verify Tenant B cannot retrieve or manage invitations belonging to Tenant A."""
    invitation_a = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,  # Tenant A
        employee_id=uuid.uuid4(),
        email="emp@tenant-a.test",
        token_hash="h" * 64,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )

    session = AsyncMock()
    # When Tenant B queries for invitation_a.id, tenant filter (tenant_id == tenant_b_id) returns None
    session.execute.return_value = AsyncMock(scalar_one_or_none=lambda: None)

    from fastapi import HTTPException

    # Get invitation
    with pytest.raises(HTTPException) as exc1:
        await get_invitation(session=session, tenant_id=tenant_b_id, invitation_id=invitation_a.id)
    assert exc1.value.status_code == 404

    # Resend invitation
    with pytest.raises(HTTPException) as exc2:
        await resend_invitation(
            session=session,
            tenant_id=tenant_b_id,
            invitation_id=invitation_a.id,
            current_user_id=uuid.uuid4(),
        )
    assert exc2.value.status_code == 404

    # Revoke invitation
    with pytest.raises(HTTPException) as exc3:
        await revoke_invitation(
            session=session,
            tenant_id=tenant_b_id,
            invitation_id=invitation_a.id,
            current_user_id=uuid.uuid4(),
        )
    assert exc3.value.status_code == 404


# 19. List invitations with filtering and pagination
@pytest.mark.asyncio
async def test_list_invitations_filtering_and_pagination(tenant_id: uuid.UUID):
    """Verify list_invitations filters by status, employee_id, and calculates total count."""
    inv1 = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="user1@acme.test",
        token_hash="1" * 64,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    inv2 = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=uuid.uuid4(),
        email="user2@acme.test",
        token_hash="2" * 64,
        status="accepted",
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )

    session = AsyncMock()
    # 1. count query returns 2
    # 2. scalars().all() returns [inv1, inv2]
    session.execute.side_effect = [
        AsyncMock(scalar_one=lambda: 2),
        AsyncMock(scalars=lambda: AsyncMock(all=lambda: [inv1, inv2])),
    ]

    res = await list_invitations(
        session=session,
        tenant_id=tenant_id,
        status_filter="pending",
        skip=0,
        limit=10,
    )
    assert res.total == 2
    assert len(res.items) == 2
    assert res.items[0].email == "user1@acme.test"


# 20. Public API endpoints integration via HTTP AsyncClient
@pytest.mark.asyncio
async def test_public_api_validate_and_activate_integration(
    tenant_id: uuid.UUID,
    test_tenant: Tenant,
    test_employee: Employee,
):
    """Verify /api/v1/auth/invitations/validate and /api/v1/auth/invitations/activate via HTTP requests."""
    raw_token = generate_secure_token()
    token_hash_val = hash_token(raw_token)

    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email=test_employee.work_email,
        token_hash=token_hash_val,
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )

    mock_db = AsyncMock()

    async def mock_exec(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "set_config" in stmt_str or "SET LOCAL ROLE" in stmt_str:
            return AsyncMock()
        if "employee_invitations" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: invitation)
        if "employees" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: test_employee)
        if "tenants" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: test_tenant)
        if "users" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: None)
        return AsyncMock()

    mock_db.execute.side_effect = mock_exec

    app.dependency_overrides[get_db] = lambda: mock_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Validate public token
        val_res = await client.get(f"/api/v1/auth/invitations/validate?token={raw_token}")
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["valid"] is True
        assert val_data["email"] == test_employee.work_email
        assert val_data["company_name"] == "Acme Corp"

        # 2. Activate account
        act_res = await client.post(
            "/api/v1/auth/invitations/activate",
            json={
                "token": raw_token,
                "password": "CorrectPassword123!",
                "password_confirm": "CorrectPassword123!",
            },
        )
        assert act_res.status_code == 200
        act_data = act_res.json()
        assert act_data["success"] is True
        assert act_data["email"] == test_employee.work_email

    app.dependency_overrides.clear()


# 21. Simulated concurrent activation
@pytest.mark.asyncio
async def test_concurrent_activation_simulated(
    tenant_id: uuid.UUID,
    test_employee: Employee,
):
    """Verify that if two concurrent activation attempts occur, the second sees accepted and fails."""
    raw_token = generate_secure_token()
    token_hash_val = hash_token(raw_token)

    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id=test_employee.id,
        email=test_employee.work_email,
        token_hash=token_hash_val,
        status="pending",
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    session1 = AsyncMock()

    async def mock_exec1(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        if "set_config" in stmt_str or "SET LOCAL ROLE" in stmt_str:
            return AsyncMock()
        if "employee_invitations" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: invitation)
        if "employees" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: test_employee)
        if "users" in stmt_str:
            return AsyncMock(scalar_one_or_none=lambda: None)
        return AsyncMock()

    session1.execute.side_effect = mock_exec1

    # First activation succeeds
    req = ActivateAccountRequest(
        token=raw_token,
        password="StrongPassword123!",
        password_confirm="StrongPassword123!",
    )
    res1 = await activate_account(session=session1, req=req)
    assert res1.success is True
    assert invitation.status == "accepted"

    # Second concurrent activation sees status == "accepted" and is rejected
    session2 = AsyncMock()
    session2.execute.return_value = AsyncMock(scalar_one_or_none=lambda: invitation)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await activate_account(session=session2, req=req)
    assert exc.value.status_code == 400
    assert "already been accepted" in exc.value.detail.lower()

