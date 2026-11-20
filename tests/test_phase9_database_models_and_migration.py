"""Comprehensive automated test suite for Phase 9 Milestone 9.1:
Database Architecture, Models & Alembic Migration.

Validates:
1. Alembic migration chain integrity and dependency on Phase 8 head e7f8a9b0c1d2.
2. Upgrade and downgrade callables.
3. SQLAlchemy models for all 7 Phase 9 entities:
   - LeaveType (leave_types)
   - LeaveBalance (leave_balances)
   - LeaveRequest (leave_requests)
   - HolidayCalendar (holiday_calendars)
   - Holiday (holidays)
   - OvertimeRule (overtime_rules)
   - OvertimeRecord (overtime_records)
4. Multi-tenant composite foreign keys, unique constraints, and check constraints.
5. Leave balance availability invariant: Available = allocation + carried + accrued - used - pending.
6. Leave request half-day period rules and status transitions.
7. Holiday calendar location/department overrides and holiday types.
8. Overtime multiplier validation and record relationships.
9. Verification of model registration in Base.metadata.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from database.migrations.versions import f2a3b4c5d6e7_phase_09_leave_holidays_overtime as m91
from services.api.database import Base
from services.api.leave.models import (
    Holiday,
    HolidayCalendar,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    OvertimeRecord,
    OvertimeRule,
)


class TestAlembicMigrationIntegrity:
    """Validates Alembic migration chain and script metadata."""

    def test_migration_revision_and_down_revision(self):
        """Revision must be unique and down_revision must match Phase 8 head e7f8a9b0c1d2."""
        assert m91.revision == "f2a3b4c5d6e7"
        assert m91.down_revision == "e7f8a9b0c1d2"
        assert m91.branch_labels is None
        assert m91.depends_on is None

    def test_upgrade_and_downgrade_callables_exist(self):
        """upgrade() and downgrade() functions must be defined and callable."""
        assert callable(m91.upgrade)
        assert callable(m91.downgrade)


class TestLeaveTypeModel:
    """Validates LeaveType SQLAlchemy model structure and constraints."""

    def test_table_name_and_primary_key(self):
        assert LeaveType.__tablename__ == "leave_types"
        pk_cols = [col.name for col in LeaveType.__table__.primary_key.columns]
        assert pk_cols == ["id"]

    def test_required_columns_and_nullability(self):
        cols = LeaveType.__table__.columns
        assert not cols["id"].nullable
        assert not cols["tenant_id"].nullable
        assert not cols["code"].nullable
        assert not cols["name"].nullable
        assert not cols["is_paid"].nullable
        assert not cols["requires_approval"].nullable
        assert not cols["allow_half_day"].nullable
        assert not cols["carry_forward_limit"].nullable
        assert not cols["is_active"].nullable
        assert not cols["created_at"].nullable
        assert not cols["updated_at"].nullable

        # Optional
        assert cols["description"].nullable
        assert cols["max_consecutive_days"].nullable

    def test_unique_constraints(self):
        table = LeaveType.__table__
        unique_constraints = {
            c.name: [col.name for col in c.columns]
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_leave_types_tenant_id" in unique_constraints
        assert unique_constraints["uq_leave_types_tenant_id"] == ["tenant_id", "id"]
        assert "uq_leave_types_tenant_code" in unique_constraints
        assert unique_constraints["uq_leave_types_tenant_code"] == ["tenant_id", "code"]

    def test_check_constraints(self):
        table = LeaveType.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_leave_types_carry_forward" in check_constraints
        assert "carry_forward_limit >= 0" in check_constraints["chk_leave_types_carry_forward"]
        assert "chk_leave_types_max_consecutive" in check_constraints

    def test_model_construction(self):
        t_id = uuid.uuid4()
        lt = LeaveType(
            id=uuid.uuid4(),
            tenant_id=t_id,
            code="CL",
            name="Casual Leave",
            is_paid=True,
            requires_approval=True,
            allow_half_day=True,
            carry_forward_limit=Decimal("5.0"),
            is_active=True,
        )
        assert lt.code == "CL"
        assert lt.is_paid is True
        assert lt.carry_forward_limit == Decimal("5.0")


class TestLeaveBalanceModel:
    """Validates LeaveBalance model structure, foreign keys, and invariants."""

    def test_table_name_and_primary_key(self):
        assert LeaveBalance.__tablename__ == "leave_balances"
        pk_cols = [col.name for col in LeaveBalance.__table__.primary_key.columns]
        assert pk_cols == ["id"]

    def test_composite_foreign_keys(self):
        table = LeaveBalance.__table__
        fk_constraints = {
            c.name: ([col.name for col in c.columns], [target.target_fullname for target in c.elements])
            for c in table.constraints
            if isinstance(c, ForeignKeyConstraint)
        }
        assert "fk_leave_balances_employee" in fk_constraints
        cols, targets = fk_constraints["fk_leave_balances_employee"]
        assert cols == ["tenant_id", "employee_id"]
        assert targets == ["employees.tenant_id", "employees.id"]

        assert "fk_leave_balances_leave_type" in fk_constraints
        cols, targets = fk_constraints["fk_leave_balances_leave_type"]
        assert cols == ["tenant_id", "leave_type_id"]
        assert targets == ["leave_types.tenant_id", "leave_types.id"]

    def test_unique_constraints(self):
        table = LeaveBalance.__table__
        unique_constraints = {
            c.name: [col.name for col in c.columns]
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_leave_balances_tenant_id" in unique_constraints
        assert "uq_leave_balances_tenant_emp_type_year" in unique_constraints
        assert unique_constraints["uq_leave_balances_tenant_emp_type_year"] == [
            "tenant_id",
            "employee_id",
            "leave_type_id",
            "year",
        ]

    def test_check_constraints(self):
        table = LeaveBalance.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_leave_balances_non_negative" in check_constraints
        sql = check_constraints["chk_leave_balances_non_negative"]
        assert "annual_allocation >= 0" in sql
        assert "used >= 0" in sql
        assert "pending_approval >= 0" in sql

    def test_available_balance_invariant(self):
        """Available = annual_allocation + carried_forward + accrued - used - pending_approval."""
        bal = LeaveBalance(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            leave_type_id=uuid.uuid4(),
            year=2026,
            annual_allocation=Decimal("12.00"),
            carried_forward=Decimal("3.00"),
            accrued=Decimal("2.00"),
            used=Decimal("4.00"),
            pending_approval=Decimal("1.50"),
        )
        # 12 + 3 + 2 - 4 - 1.5 = 11.5
        assert bal.available_balance == Decimal("11.50")


class TestLeaveRequestModel:
    """Validates LeaveRequest model, constraints, half-day logic, and approval states."""

    def test_table_name_and_primary_key(self):
        assert LeaveRequest.__tablename__ == "leave_requests"
        pk_cols = [col.name for col in LeaveRequest.__table__.primary_key.columns]
        assert pk_cols == ["id"]

    def test_composite_foreign_keys(self):
        table = LeaveRequest.__table__
        fk_constraints = {
            c.name: ([col.name for col in c.columns], [target.target_fullname for target in c.elements])
            for c in table.constraints
            if isinstance(c, ForeignKeyConstraint)
        }
        assert "fk_leave_requests_employee" in fk_constraints
        assert "fk_leave_requests_leave_type" in fk_constraints
        assert "fk_leave_requests_reviewer" in fk_constraints

    def test_check_constraints(self):
        table = LeaveRequest.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_leave_requests_date_range" in check_constraints
        assert "end_date >= start_date" in check_constraints["chk_leave_requests_date_range"]

        assert "chk_leave_requests_total_days" in check_constraints
        assert "total_days > 0" in check_constraints["chk_leave_requests_total_days"]

        assert "chk_leave_requests_status" in check_constraints
        sql_status = check_constraints["chk_leave_requests_status"]
        for s in ("PENDING_APPROVAL", "APPROVED", "REJECTED", "CANCELLED"):
            assert s in sql_status

        assert "chk_leave_requests_half_day" in check_constraints
        assert "chk_leave_requests_decision" in check_constraints

    def test_full_day_request_construction(self):
        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 3),
            is_half_day=False,
            half_day_period=None,
            total_days=Decimal("3.00"),
            reason="Family vacation",
            status="PENDING_APPROVAL",
        )
        assert req.total_days == Decimal("3.00")
        assert req.is_half_day is False
        assert req.status == "PENDING_APPROVAL"

    def test_half_day_request_construction(self):
        req = LeaveRequest(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            leave_type_id=uuid.uuid4(),
            start_date=date(2026, 12, 5),
            end_date=date(2026, 12, 5),
            is_half_day=True,
            half_day_period="FIRST_HALF",
            total_days=Decimal("0.50"),
            reason="Doctor visit morning",
            status="PENDING_APPROVAL",
        )
        assert req.is_half_day is True
        assert req.half_day_period == "FIRST_HALF"
        assert req.total_days == Decimal("0.50")


class TestHolidayCalendarAndHolidayModels:
    """Validates HolidayCalendar and Holiday models, overrides, and foreign keys."""

    def test_holiday_calendar_table(self):
        assert HolidayCalendar.__tablename__ == "holiday_calendars"
        cols = HolidayCalendar.__table__.columns
        assert not cols["id"].nullable
        assert not cols["tenant_id"].nullable
        assert not cols["year"].nullable
        assert not cols["name"].nullable
        assert not cols["is_default"].nullable
        assert cols["location_id"].nullable
        assert cols["department_id"].nullable

    def test_holiday_calendar_foreign_keys(self):
        table = HolidayCalendar.__table__
        fk_constraints = {
            c.name: ([col.name for col in c.columns], [target.target_fullname for target in c.elements])
            for c in table.constraints
            if isinstance(c, ForeignKeyConstraint)
        }
        assert "fk_holiday_calendars_location" in fk_constraints
        assert "fk_holiday_calendars_department" in fk_constraints

    def test_holiday_table_and_constraints(self):
        assert Holiday.__tablename__ == "holidays"
        table = Holiday.__table__

        unique_constraints = {
            c.name: [col.name for col in c.columns]
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_holidays_tenant_id" in unique_constraints
        assert "uq_holidays_tenant_calendar_date" in unique_constraints
        assert unique_constraints["uq_holidays_tenant_calendar_date"] == [
            "tenant_id",
            "calendar_id",
            "holiday_date",
        ]

        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_holidays_type" in check_constraints
        sql_type = check_constraints["chk_holidays_type"]
        assert "PUBLIC" in sql_type
        assert "COMPANY" in sql_type
        assert "OPTIONAL" in sql_type


class TestOvertimeRuleAndRecordModels:
    """Validates OvertimeRule and OvertimeRecord models, multipliers, and relationships."""

    def test_overtime_rule_table_and_constraints(self):
        assert OvertimeRule.__tablename__ == "overtime_rules"
        table = OvertimeRule.__table__

        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_overtime_rules_min_threshold" in check_constraints
        assert "chk_overtime_rules_max_daily" in check_constraints
        assert "chk_overtime_rules_multipliers" in check_constraints
        sql_mult = check_constraints["chk_overtime_rules_multipliers"]
        assert "workday_multiplier >= 1.00" in sql_mult
        assert "weekend_multiplier >= 1.00" in sql_mult
        assert "holiday_multiplier >= 1.00" in sql_mult

    def test_overtime_record_table_and_foreign_keys(self):
        assert OvertimeRecord.__tablename__ == "overtime_records"
        table = OvertimeRecord.__table__

        fk_constraints = {
            c.name: ([col.name for col in c.columns], [target.target_fullname for target in c.elements])
            for c in table.constraints
            if isinstance(c, ForeignKeyConstraint)
        }
        assert "fk_overtime_records_employee" in fk_constraints
        assert "fk_overtime_records_attendance_day" in fk_constraints
        assert "fk_overtime_records_reviewer" in fk_constraints

        unique_constraints = {
            c.name: [col.name for col in c.columns]
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_overtime_records_tenant_id" in unique_constraints
        assert "uq_overtime_records_tenant_emp_date" in unique_constraints
        assert unique_constraints["uq_overtime_records_tenant_emp_date"] == [
            "tenant_id",
            "employee_id",
            "attendance_date",
        ]

    def test_overtime_record_check_constraints(self):
        table = OvertimeRecord.__table__
        check_constraints = {
            c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        }
        assert "chk_overtime_records_minutes_positive" in check_constraints
        assert "chk_overtime_records_multiplier" in check_constraints
        assert "chk_overtime_records_type" in check_constraints
        assert "chk_overtime_records_status" in check_constraints
        assert "chk_overtime_records_decision" in check_constraints


class TestModelRegistrationInMetadata:
    """Verifies that all 7 Phase 9 models are registered on Base.metadata."""

    def test_all_phase9_tables_registered(self):
        tables = Base.metadata.tables
        expected_tables = {
            "leave_types",
            "leave_balances",
            "leave_requests",
            "holiday_calendars",
            "holidays",
            "overtime_rules",
            "overtime_records",
        }
        for table in expected_tables:
            assert table in tables, f"Expected table '{table}' to be registered in Base.metadata"
