"""Comprehensive automated test suite for Phase 7 Milestone 7.4:
HR Fraud Review Queue, Decision Workflows & Audit Ledger.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from services.api.attendance.models import AttendanceEvent
from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.auth.permissions import UserRole
from services.api.database import get_db
from services.api.employees.models import Employee
from services.api.fraud.models import FraudFlag
from services.api.fraud.review_service import (
    adjudicate_fraud_event,
    get_fraud_event_review_detail,
)
from services.api.fraud.rules_service import list_fraud_flags
from services.api.fraud.schemas import (
    FraudReviewDecisionRequest,
)
from services.api.locations.models import Location
from services.api.main import app
from services.api.organization.models import Department
from services.api.tenants.models import Tenant

# ==============================================================================
# Helper Mock Factories
# ==============================================================================


def _mock_context(role: str = "admin") -> AuthenticatedContext:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"{role}@example.com",
        full_name=f"Test {role.capitalize()}",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tenant_id,
        name="Test Tenant",
        slug=f"test-{uuid.uuid4().hex[:6]}",
        company_email="admin@example.com",
        country_code="US",
        timezone="UTC",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _mock_attendance_event(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
    review_status: str = "PENDING_REVIEW",
    risk_score: int = 75,
    risk_category: str = "HIGH_RISK",
    device_id: str | None = "test-device-uuid-1",
    location_id: uuid.UUID | None = None,
) -> AttendanceEvent:
    ev_id = event_id or uuid.uuid4()
    now = datetime.now(UTC)
    return AttendanceEvent(
        id=ev_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        event_type="CHECK_IN",
        event_category="STANDARD",
        supersedes_event_id=None,
        server_received_at=now,
        effective_at=now,
        clock_drift_seconds=Decimal("1.250"),
        source="MOBILE",
        device_id=device_id,
        timestamp_verification_status="SERVER_AUTHORITATIVE",
        review_status=review_status,
        idempotency_key=f"idem-{ev_id}",
        location_id=location_id,
        latitude=Decimal("37.7749000"),
        longitude=Decimal("-122.4194000"),
        accuracy_meters=Decimal("15.50"),
        is_mock_location=False,
        metadata_json={
            "risk_score": risk_score,
            "risk_category": risk_category,
            "spatial_evidence": {
                "distance_to_location_meters": 45.2,
                "geofence_matched": True,
            },
        },
        created_at=now,
    )


# ==============================================================================
# Unit Tests: get_fraud_event_review_detail
# ==============================================================================


class TestFraudReviewDetailService:
    @pytest.mark.asyncio
    async def test_get_review_detail_success_admin(self):
        """Admin can retrieve full forensic detail of a flagged attendance event."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()
        loc_id = uuid.uuid4()
        dept_id = uuid.uuid4()
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@test.com",
            full_name="Admin Reviewer",
            role=UserRole.ADMIN.value,
            status="active",
        )

        event = _mock_attendance_event(
            tenant_id=tenant_id,
            employee_id=emp_id,
            event_id=event_id,
            location_id=loc_id,
        )
        emp = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            employee_id="EMP-001",
            first_name="Jane",
            last_name="Doe",
            work_email="jane@test.com",
            department_id=dept_id,
            status="active",
        )
        dept = Department(id=dept_id, tenant_id=tenant_id, name="Engineering")
        loc = Location(id=loc_id, tenant_id=tenant_id, name="HQ Office")
        flag = FraudFlag(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            attendance_event_id=event_id,
            employee_id=emp_id,
            signal_code="MOCK_LOCATION_DETECTED",
            severity="HIGH",
            risk_weight=50,
            description="Mock GPS spoofing detected",
            evidence_json={"mock": True},
            detected_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        session = AsyncMock()

        # Mock query sequence:
        # 1. event
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        # 2. employee
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp
        # 3. department name
        mock_dept = MagicMock()
        mock_dept.scalar_one_or_none.return_value = dept.name
        # 4. location
        mock_loc = MagicMock()
        mock_loc.scalar_one_or_none.return_value = loc
        # 5. shift assignment
        mock_shift = MagicMock()
        mock_shift.first.return_value = None
        # 6. flags
        mock_flags = MagicMock()
        mock_flags.scalars.return_value.all.return_value = [flag]
        # 7. reviews
        mock_revs = MagicMock()
        mock_revs.all.return_value = []

        session.execute.side_effect = [
            mock_ev,
            mock_emp,
            mock_dept,
            mock_loc,
            mock_shift,
            mock_flags,
            mock_revs,
        ]

        detail = await get_fraud_event_review_detail(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            reviewer_user=admin_user,
            reviewer_role=UserRole.ADMIN,
        )

        assert detail.attendance_event_id == event_id
        assert detail.employee_name == "Jane Doe"
        assert detail.employee_code == "EMP-001"
        assert detail.employee_department == "Engineering"
        assert detail.review_status == "PENDING_REVIEW"
        assert detail.risk_score == 75
        assert detail.risk_category == "HIGH_RISK"
        assert detail.location is not None
        assert detail.location["location_name"] == "HQ Office"
        assert len(detail.signals) == 1
        assert detail.signals[0].signal_code == "MOCK_LOCATION_DETECTED"
        assert detail.review_history == []

    @pytest.mark.asyncio
    async def test_get_review_detail_event_not_found(self):
        """Requesting non-existent event ID raises 404 Not Found."""
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@test.com",
            full_name="Admin",
            role="admin",
            status="active",
        )
        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_ev

        with pytest.raises(HTTPException) as exc:
            await get_fraud_event_review_detail(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                reviewer_user=admin_user,
                reviewer_role=UserRole.ADMIN,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_manager_visibility_success_direct_report(self):
        """Manager can view review detail for an employee who is their direct report."""
        tenant_id = uuid.uuid4()
        manager_user_id = uuid.uuid4()
        manager_emp_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()

        manager_user = User(
            id=manager_user_id,
            tenant_id=tenant_id,
            email="manager@test.com",
            full_name="Team Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )
        manager_emp = Employee(
            id=manager_emp_id,
            tenant_id=tenant_id,
            user_id=manager_user_id,
            employee_id="MGR-001",
            first_name="Boss",
            last_name="Manager",
            work_email="manager@test.com",
            department_id=uuid.uuid4(),
            status="active",
        )
        employee = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            employee_id="EMP-002",
            first_name="Report",
            last_name="One",
            work_email="report@test.com",
            reporting_manager_id=manager_emp_id,  # Direct report!
            department_id=uuid.uuid4(),
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = employee
        mock_mgr_emp = MagicMock()
        mock_mgr_emp.scalar_one_or_none.return_value = manager_emp
        mock_dept = MagicMock()
        mock_dept.scalar_one_or_none.return_value = None
        mock_shift = MagicMock()
        mock_shift.first.return_value = None
        mock_flags = MagicMock()
        mock_flags.scalars.return_value.all.return_value = []
        mock_revs = MagicMock()
        mock_revs.all.return_value = []

        session.execute.side_effect = [
            mock_ev,
            mock_emp,
            mock_mgr_emp,
            mock_dept,
            mock_shift,
            mock_flags,
            mock_revs,
        ]

        detail = await get_fraud_event_review_detail(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            reviewer_user=manager_user,
            reviewer_role=UserRole.MANAGER,
        )
        assert detail.employee_name == "Report One"

    @pytest.mark.asyncio
    async def test_manager_visibility_forbidden_outside_hierarchy(self):
        """Manager receives 403 Forbidden when attempting to view an employee outside department/reports."""
        tenant_id = uuid.uuid4()
        manager_user_id = uuid.uuid4()
        manager_emp_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()

        manager_user = User(
            id=manager_user_id,
            tenant_id=tenant_id,
            email="manager@test.com",
            full_name="Team Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )
        manager_emp = Employee(
            id=manager_emp_id,
            tenant_id=tenant_id,
            user_id=manager_user_id,
            employee_id="MGR-001",
            first_name="Boss",
            last_name="Manager",
            work_email="manager@test.com",
            department_id=uuid.uuid4(),
            status="active",
        )
        employee = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            employee_id="EMP-999",
            first_name="Other",
            last_name="Dept",
            work_email="other@test.com",
            reporting_manager_id=uuid.uuid4(),  # Different manager
            department_id=uuid.uuid4(),  # Different department
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = employee
        mock_mgr_emp = MagicMock()
        mock_mgr_emp.scalar_one_or_none.return_value = manager_emp

        session.execute.side_effect = [mock_ev, mock_emp, mock_mgr_emp]

        with pytest.raises(HTTPException) as exc:
            await get_fraud_event_review_detail(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                reviewer_user=manager_user,
                reviewer_role=UserRole.MANAGER,
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "access denied" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_manager_visibility_success_same_department(self):
        """Manager can view review detail for an employee in the same department."""
        tenant_id = uuid.uuid4()
        dept_id = uuid.uuid4()
        manager_user_id = uuid.uuid4()
        manager_emp_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()

        manager_user = User(
            id=manager_user_id,
            tenant_id=tenant_id,
            email="manager@test.com",
            full_name="Dept Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )
        manager_emp = Employee(
            id=manager_emp_id,
            tenant_id=tenant_id,
            user_id=manager_user_id,
            employee_id="MGR-002",
            first_name="Dept",
            last_name="Head",
            work_email="manager@test.com",
            department_id=dept_id,  # Matching department!
            status="active",
        )
        employee = Employee(
            id=emp_id,
            tenant_id=tenant_id,
            employee_id="EMP-003",
            first_name="Dept",
            last_name="Member",
            work_email="member@test.com",
            reporting_manager_id=uuid.uuid4(),  # Different reporting manager
            department_id=dept_id,  # Same department!
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = employee
        mock_mgr_emp = MagicMock()
        mock_mgr_emp.scalar_one_or_none.return_value = manager_emp
        mock_dept = MagicMock()
        mock_dept.scalar_one_or_none.return_value = "Sales"
        mock_shift = MagicMock()
        mock_shift.first.return_value = None
        mock_flags = MagicMock()
        mock_flags.scalars.return_value.all.return_value = []
        mock_revs = MagicMock()
        mock_revs.all.return_value = []

        session.execute.side_effect = [
            mock_ev,
            mock_emp,
            mock_mgr_emp,
            mock_dept,
            mock_shift,
            mock_flags,
            mock_revs,
        ]

        detail = await get_fraud_event_review_detail(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            reviewer_user=manager_user,
            reviewer_role=UserRole.MANAGER,
        )
        assert detail.employee_name == "Dept Member"
        assert detail.employee_department == "Sales"

    @pytest.mark.asyncio
    async def test_manager_no_linked_profile_forbidden(self):
        """Manager with no linked employee profile receives 403 Forbidden."""
        tenant_id = uuid.uuid4()
        manager_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="unlinked-mgr@test.com",
            full_name="Unlinked Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=uuid.uuid4())
        emp = Employee(id=event.employee_id, tenant_id=tenant_id, employee_id="E1", first_name="A", last_name="B", work_email="a@b.com", status="active")

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_emp = MagicMock()
        mock_emp.scalar_one_or_none.return_value = emp
        mock_mgr_emp = MagicMock()
        mock_mgr_emp.scalar_one_or_none.return_value = None  # No employee profile!

        session.execute.side_effect = [mock_ev, mock_emp, mock_mgr_emp]

        with pytest.raises(HTTPException) as exc:
            await get_fraud_event_review_detail(
                session=session,
                tenant_id=tenant_id,
                event_id=event.id,
                reviewer_user=manager_user,
                reviewer_role=UserRole.MANAGER,
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "no linked employee profile" in exc.value.detail.lower()


# ==============================================================================
# Unit Tests: adjudicate_fraud_event
# ==============================================================================


class TestFraudAdjudicationService:
    @pytest.mark.asyncio
    @patch("services.api.fraud.review_service.determine_shift_date_for_punch")
    @patch("services.api.fraud.review_service.recalculate_attendance_day")
    async def test_adjudicate_approval_success(self, mock_recalc, mock_shift_date):
        """HR approves a flagged event: review status updated to APPROVED and day recalculated."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()

        reviewer_user = User(
            id=reviewer_id,
            tenant_id=tenant_id,
            email="hr@test.com",
            full_name="HR Reviewer",
            role=UserRole.HR.value,
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event

        mock_self = MagicMock()
        mock_self.scalar_one_or_none.return_value = None  # Not self-review

        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"

        session.execute.side_effect = [mock_ev, mock_self, mock_tz]

        mock_shift_date.return_value = date(2026, 11, 19)
        mock_day = MagicMock()
        mock_day.id = uuid.uuid4()
        mock_recalc.return_value = mock_day

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="Verified location with field supervisor via phone.",
            notes="Employee was on sanctioned off-site assignment.",
        )

        res = await adjudicate_fraud_event(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            payload=payload,
            reviewer_user=reviewer_user,
            reviewer_role=UserRole.HR,
        )

        assert res.success is True
        assert res.updated_review_status == "APPROVED"
        assert event.review_status == "APPROVED"
        assert res.review.decision == "APPROVED"
        assert res.review.reason == "Verified location with field supervisor via phone."
        assert res.recalculated_day_id == mock_day.id

        session.add.assert_called_once()
        mock_recalc.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.api.fraud.review_service.determine_shift_date_for_punch")
    @patch("services.api.fraud.review_service.recalculate_attendance_day")
    async def test_adjudicate_rejection_success(self, mock_recalc, mock_shift_date):
        """Admin rejects a flagged punch: review status updated to REJECTED."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@test.com",
            full_name="Admin Reviewer",
            role=UserRole.ADMIN.value,
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_self = MagicMock()
        mock_self.scalar_one_or_none.return_value = None
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"

        session.execute.side_effect = [mock_ev, mock_self, mock_tz]
        mock_shift_date.return_value = date(2026, 11, 19)
        mock_day = MagicMock()
        mock_day.id = uuid.uuid4()
        mock_recalc.return_value = mock_day

        payload = FraudReviewDecisionRequest(
            decision="REJECTED",
            reason="Confirmed device spoofing application active during punch.",
        )

        res = await adjudicate_fraud_event(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            payload=payload,
            reviewer_user=admin_user,
            reviewer_role=UserRole.ADMIN,
        )

        assert res.success is True
        assert res.updated_review_status == "REJECTED"
        assert event.review_status == "REJECTED"
        assert res.review.decision == "REJECTED"

    @pytest.mark.asyncio
    async def test_self_review_prohibited(self):
        """User cannot adjudicate their own attendance fraud review (403 Forbidden)."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        event_id = uuid.uuid4()

        reviewer_user = User(
            id=user_id,
            tenant_id=tenant_id,
            email="hr-employee@test.com",
            full_name="HR and Employee",
            role=UserRole.HR.value,
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_self = MagicMock()
        mock_self.scalar_one_or_none.return_value = emp_id  # Reviewer IS the employee!

        session.execute.side_effect = [mock_ev, mock_self]

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="Approving my own attendance.",
        )

        with pytest.raises(HTTPException) as exc:
            await adjudicate_fraud_event(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                payload=payload,
                reviewer_user=reviewer_user,
                reviewer_role=UserRole.HR,
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "self-review prohibited" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_manager_decision_forbidden(self):
        """Manager role cannot adjudicate fraud reviews (lacks REVIEW_FRAUD_EVENTS permission)."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()

        manager_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="manager@test.com",
            full_name="Manager",
            role=UserRole.MANAGER.value,
            status="active",
        )
        event = _mock_attendance_event(tenant_id=tenant_id, employee_id=emp_id, event_id=event_id)

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        session.execute.return_value = mock_ev

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="Looks good to me.",
        )

        with pytest.raises(HTTPException) as exc:
            await adjudicate_fraud_event(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                payload=payload,
                reviewer_user=manager_user,
                reviewer_role=UserRole.MANAGER,
            )
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_adjudicate_event_not_found(self):
        """Adjudicating non-existent event ID raises 404 Not Found."""
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@test.com",
            full_name="Admin Reviewer",
            role=UserRole.ADMIN.value,
            status="active",
        )
        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_ev

        payload = FraudReviewDecisionRequest(
            decision="APPROVED",
            reason="Approved valid punch.",
        )

        with pytest.raises(HTTPException) as exc:
            await adjudicate_fraud_event(
                session=session,
                tenant_id=tenant_id,
                event_id=event_id,
                payload=payload,
                reviewer_user=admin_user,
                reviewer_role=UserRole.ADMIN,
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    @patch("services.api.fraud.review_service.determine_shift_date_for_punch")
    @patch("services.api.fraud.review_service.recalculate_attendance_day")
    async def test_re_adjudicate_event_creates_audit_trail(self, mock_recalc, mock_shift_date):
        """Re-adjudicating an already decided event creates a second audit entry without overwriting history."""
        tenant_id = uuid.uuid4()
        emp_id = uuid.uuid4()
        event_id = uuid.uuid4()
        admin_user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email="admin@test.com",
            full_name="Admin Reviewer",
            role=UserRole.ADMIN.value,
            status="active",
        )
        # Event is initially APPROVED
        event = _mock_attendance_event(
            tenant_id=tenant_id,
            employee_id=emp_id,
            event_id=event_id,
            review_status="APPROVED",
        )

        session = AsyncMock()
        mock_ev = MagicMock()
        mock_ev.scalar_one_or_none.return_value = event
        mock_self = MagicMock()
        mock_self.scalar_one_or_none.return_value = None
        mock_tz = MagicMock()
        mock_tz.scalar_one_or_none.return_value = "UTC"

        session.execute.side_effect = [mock_ev, mock_self, mock_tz]
        mock_shift_date.return_value = date(2026, 11, 19)
        mock_day = MagicMock()
        mock_day.id = uuid.uuid4()
        mock_recalc.return_value = mock_day

        payload = FraudReviewDecisionRequest(
            decision="REJECTED",
            reason="Subsequent evidence revealed VPN proxy spoofing.",
            notes="Re-adjudicated upon forensic discovery.",
        )

        res = await adjudicate_fraud_event(
            session=session,
            tenant_id=tenant_id,
            event_id=event_id,
            payload=payload,
            reviewer_user=admin_user,
            reviewer_role=UserRole.ADMIN,
        )

        assert res.success is True
        assert res.updated_review_status == "REJECTED"
        assert event.review_status == "REJECTED"
        assert res.review.decision == "REJECTED"
        assert res.review.reason == "Subsequent evidence revealed VPN proxy spoofing."



# ==============================================================================
# Unit Tests: list_fraud_flags Filters
# ==============================================================================


class TestFraudFlagListingFilters:
    @pytest.mark.asyncio
    async def test_list_flags_with_pending_review_filter(self):
        """list_fraud_flags supports review_status filter."""
        tenant_id = uuid.uuid4()
        session = AsyncMock()

        flag = FraudFlag(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            attendance_event_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            signal_code="MOCK_LOCATION_DETECTED",
            severity="HIGH",
            risk_weight=40,
            description="Mock GPS",
            evidence_json={},
            detected_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        mock_count = MagicMock()
        mock_count.scalar.return_value = 1
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [flag]

        session.execute.side_effect = [mock_count, mock_res]

        flags, total = await list_fraud_flags(
            session=session,
            tenant_id=tenant_id,
            review_status="PENDING_REVIEW",
            risk_category="HIGH_RISK",
            min_risk_score=50,
            max_risk_score=90,
        )

        assert total == 1
        assert len(flags) == 1
        assert flags[0].signal_code == "MOCK_LOCATION_DETECTED"


# ==============================================================================
# FastAPI Integration Tests
# ==============================================================================


class TestFraudReviewWorkflowAPI:
    @pytest.mark.asyncio
    async def test_get_review_detail_endpoint_hr_200(self):
        """GET /api/v1/fraud/events/{id}/review returns 200 with review detail for HR user."""
        hr_ctx = _mock_context(role="hr")
        event_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        event = _mock_attendance_event(
            tenant_id=hr_ctx.tenant.id,
            employee_id=emp_id,
            event_id=event_id,
        )
        emp = Employee(
            id=emp_id,
            tenant_id=hr_ctx.tenant.id,
            employee_id="EMP-100",
            first_name="Robert",
            last_name="Smith",
            work_email="robert@test.com",
            status="active",
        )

        app.dependency_overrides[get_authenticated_context] = lambda: hr_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_ev = MagicMock()
            mock_ev.scalar_one_or_none.return_value = event
            mock_emp = MagicMock()
            mock_emp.scalar_one_or_none.return_value = emp
            mock_dept = MagicMock()
            mock_dept.scalar_one_or_none.return_value = None
            mock_shift = MagicMock()
            mock_shift.first.return_value = None
            mock_flags = MagicMock()
            mock_flags.scalars.return_value.all.return_value = []
            mock_revs = MagicMock()
            mock_revs.all.return_value = []

            session.execute.side_effect = [
                mock_ev,
                mock_emp,
                mock_dept,
                mock_shift,
                mock_flags,
                mock_revs,
            ]
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(f"/api/v1/fraud/events/{event_id}/review")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["attendance_event_id"] == str(event_id)
            assert data["employee_name"] == "Robert Smith"
            assert data["review_status"] == "PENDING_REVIEW"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_review_detail_endpoint_employee_forbidden(self):
        """GET /api/v1/fraud/events/{id}/review returns 403 Forbidden for Employee role."""
        emp_ctx = _mock_context(role="employee")
        event_id = uuid.uuid4()

        app.dependency_overrides[get_authenticated_context] = lambda: emp_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(f"/api/v1/fraud/events/{event_id}/review")
            assert res.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    @patch("services.api.fraud.review_service.determine_shift_date_for_punch")
    @patch("services.api.fraud.review_service.recalculate_attendance_day")
    async def test_post_decision_endpoint_admin_approve_200(self, mock_recalc, mock_shift_date):
        """POST /api/v1/fraud/events/{id}/decision returns 200 with approved review."""
        admin_ctx = _mock_context(role="admin")
        event_id = uuid.uuid4()
        emp_id = uuid.uuid4()

        event = _mock_attendance_event(
            tenant_id=admin_ctx.tenant.id,
            employee_id=emp_id,
            event_id=event_id,
        )

        mock_shift_date.return_value = date(2026, 11, 19)
        mock_day = MagicMock()
        mock_day.id = uuid.uuid4()
        mock_recalc.return_value = mock_day

        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_ev = MagicMock()
            mock_ev.scalar_one_or_none.return_value = event
            mock_self = MagicMock()
            mock_self.scalar_one_or_none.return_value = None  # Different employee
            mock_tz = MagicMock()
            mock_tz.scalar_one_or_none.return_value = "UTC"

            session.execute.side_effect = [mock_ev, mock_self, mock_tz]
            yield session

        app.dependency_overrides[get_db] = _mock_db

        payload = {
            "decision": "APPROVED",
            "reason": "Employee had authorized remote punch exemption.",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(f"/api/v1/fraud/events/{event_id}/decision", json=payload)
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["success"] is True
            assert data["updated_review_status"] == "APPROVED"
            assert data["review"]["decision"] == "APPROVED"
            assert data["recalculated_day_id"] == str(mock_day.id)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_post_decision_endpoint_invalid_reason_422(self):
        """POST /api/v1/fraud/events/{id}/decision with short reason (<3 chars) returns 422."""
        admin_ctx = _mock_context(role="admin")
        event_id = uuid.uuid4()

        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        payload = {
            "decision": "APPROVED",
            "reason": "ok",  # Less than 3 characters!
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(f"/api/v1/fraud/events/{event_id}/decision", json=payload)
            assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_review_detail_404(self):
        """Tenant B user cannot view fraud review detail belonging to Tenant A (returns 404)."""
        tenant_b_ctx = _mock_context(role="admin")
        foreign_event_id = uuid.uuid4()

        app.dependency_overrides[get_authenticated_context] = lambda: tenant_b_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_ev = MagicMock()
            mock_ev.scalar_one_or_none.return_value = None  # Tenant isolation filters out event
            session.execute.return_value = mock_ev
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(f"/api/v1/fraud/events/{foreign_event_id}/review")
            assert res.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_decision_404(self):
        """Tenant B user cannot adjudicate a fraud review belonging to Tenant A (returns 404)."""
        tenant_b_ctx = _mock_context(role="admin")
        foreign_event_id = uuid.uuid4()

        app.dependency_overrides[get_authenticated_context] = lambda: tenant_b_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_ev = MagicMock()
            mock_ev.scalar_one_or_none.return_value = None  # Tenant isolation filters out event
            session.execute.return_value = mock_ev
            yield session

        app.dependency_overrides[get_db] = _mock_db

        payload = {
            "decision": "APPROVED",
            "reason": "Attempting cross tenant approval.",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(f"/api/v1/fraud/events/{foreign_event_id}/decision", json=payload)
            assert res.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_flags_endpoint_with_filters_200(self):
        """GET /api/v1/fraud/flags accepts review_status, risk_category, and score filters."""
        admin_ctx = _mock_context(role="admin")
        app.dependency_overrides[get_authenticated_context] = lambda: admin_ctx

        async def _mock_db():
            session = AsyncMock()
            mock_count = MagicMock()
            mock_count.scalar.return_value = 0
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            session.execute.side_effect = [mock_count, mock_res]
            yield session

        app.dependency_overrides[get_db] = _mock_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/v1/fraud/flags",
                params={
                    "review_status": "PENDING_REVIEW",
                    "risk_category": "HIGH_RISK",
                    "min_risk_score": 60,
                    "max_risk_score": 100,
                },
            )
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["total"] == 0
            assert data["items"] == []

        app.dependency_overrides.clear()


