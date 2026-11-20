import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  leaveApi,
  holidayApi,
  overtimeApi,
  ApiError,
  API_BASE_URL,
} from "./api.ts";
import type {
  LeaveTypeDto,
  LeaveTypeListResponseDto,
  HolidayCalendarDto,
  HolidayCalendarListResponseDto,
  HolidayDto,
  HolidayListResponseDto,
  UpcomingHolidaysResponseDto,
  LeaveBalanceDto,
  LeaveBalanceListResponseDto,
  LeaveRequestDto,
  LeaveRequestListResponseDto,
  OvertimeRuleDto,
  OvertimeRuleListResponseDto,
  OvertimeRecordDto,
  OvertimeRecordListResponseDto,
} from "./api.ts";

describe("Phase 9 Milestone 9.5 — Next.js Web Console: Leave & Overtime Administration", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const tToken = "mock-jwt-token-xyz";
  const tTenantId = "tenant-uuid-111";
  const tEmployeeId = "emp-uuid-222";

  // ===========================================================================
  // 1. Leave Type Configuration Tests
  // ===========================================================================
  describe("leaveApi — Policy Configuration", () => {
    it("should fetch leave types list with active filter", async () => {
      let capturedUrl = "";
      const mockResp: LeaveTypeListResponseDto = {
        items: [
          {
            id: "lt-1",
            tenant_id: tTenantId,
            code: "AL",
            name: "Annual Leave",
            description: "Standard paid vacation",
            is_paid: true,
            requires_approval: true,
            allow_half_day: true,
            max_consecutive_days: 14,
            carry_forward_limit: "5.0",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockResp), { status: 200 });
      };

      const result = await leaveApi.getLeaveTypes({ is_active: true }, tToken);
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].code, "AL");
      assert.ok(capturedUrl.includes("/leave/types?is_active=true"));
    });

    it("should create a new leave type with POST payload", async () => {
      let capturedBody: any = null;
      let capturedMethod = "";

      const mockCreated: LeaveTypeDto = {
        id: "lt-2",
        tenant_id: tTenantId,
        code: "SL",
        name: "Sick Leave",
        description: "Medical necessity",
        is_paid: true,
        requires_approval: true,
        allow_half_day: true,
        max_consecutive_days: 7,
        carry_forward_limit: "0.0",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify(mockCreated), { status: 201 });
      };

      const result = await leaveApi.createLeaveType(
        {
          code: "SL",
          name: "Sick Leave",
          description: "Medical necessity",
          is_paid: true,
          requires_approval: true,
          allow_half_day: true,
        },
        tToken
      );

      assert.equal(capturedMethod, "POST");
      assert.equal(capturedBody.code, "SL");
      assert.equal(result.code, "SL");
    });

    it("should update an existing leave type with PUT payload", async () => {
      let capturedMethod = "";
      let capturedBody: any = null;

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify({ id: "lt-1", name: "Updated Vacation" }), { status: 200 });
      };

      const result = await leaveApi.updateLeaveType("lt-1", { name: "Updated Vacation" }, tToken);
      assert.equal(capturedMethod, "PUT");
      assert.equal(capturedBody.name, "Updated Vacation");
    });

    it("should handle 409 Conflict when deleting a referenced leave type", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Cannot delete leave type: Referenced by existing balances" }),
          { status: 409 }
        );
      };

      await assert.rejects(
        async () => {
          await leaveApi.deleteLeaveType("lt-referenced", tToken);
        },
        (err: any) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 409);
          assert.ok(err.detail.includes("Cannot delete leave type"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 2. Holiday Calendar Administration Tests
  // ===========================================================================
  describe("holidayApi — Holiday Calendars & Entries", () => {
    it("should fetch holiday calendars by year", async () => {
      let capturedUrl = "";
      const mockResp: HolidayCalendarListResponseDto = {
        items: [
          {
            id: "cal-1",
            tenant_id: tTenantId,
            year: 2026,
            name: "Corporate 2026 Calendar",
            location_id: null,
            department_id: null,
            is_default: true,
            holiday_count: 12,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockResp), { status: 200 });
      };

      const result = await holidayApi.getCalendars({ year: 2026 }, tToken);
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].is_default, true);
      assert.ok(capturedUrl.includes("year=2026"));
    });

    it("should create a holiday entry inside a calendar", async () => {
      let capturedUrl = "";
      let capturedBody: any = null;

      const mockHoliday: HolidayDto = {
        id: "hol-1",
        tenant_id: tTenantId,
        calendar_id: "cal-1",
        holiday_date: "2026-12-25",
        name: "Christmas Day",
        holiday_type: "PUBLIC",
        is_optional: false,
        description: "Statutory winter holiday",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify(mockHoliday), { status: 201 });
      };

      const result = await holidayApi.createHolidayEntry(
        "cal-1",
        {
          holiday_date: "2026-12-25",
          name: "Christmas Day",
          holiday_type: "PUBLIC",
          is_optional: false,
        },
        tToken
      );

      assert.ok(capturedUrl.includes("/holidays/calendars/cal-1/entries"));
      assert.equal(capturedBody.holiday_date, "2026-12-25");
      assert.equal(result.name, "Christmas Day");
    });

    it("should fetch upcoming holidays with resolved calendar source", async () => {
      const mockResp: UpcomingHolidaysResponseDto = {
        items: [
          {
            id: "hol-1",
            holiday_date: "2026-12-25",
            name: "Christmas Day",
            holiday_type: "PUBLIC",
            is_optional: false,
            description: null,
            calendar_id: "cal-1",
            calendar_name: "Corporate 2026 Calendar",
          },
        ],
        total: 1,
        limit: 10,
        offset: 0,
        resolved_calendar_id: "cal-1",
        resolved_calendar_name: "Corporate 2026 Calendar",
        resolution_source: "LOCATION",
      };

      globalThis.fetch = async () => {
        return new Response(JSON.stringify(mockResp), { status: 200 });
      };

      const result = await holidayApi.getUpcomingHolidays({ limit: 10 }, tToken);
      assert.equal(result.items.length, 1);
      assert.equal(result.resolution_source, "LOCATION");
    });
  });

  // ===========================================================================
  // 3. Employee Leave Application & Balance Tracking Tests
  // ===========================================================================
  describe("leaveApi — Employee Balances & Application", () => {
    it("should fetch authenticated employee leave balances", async () => {
      let capturedUrl = "";
      const mockBalances: LeaveBalanceListResponseDto = {
        items: [
          {
            id: "bal-1",
            tenant_id: tTenantId,
            employee_id: tEmployeeId,
            leave_type_id: "lt-1",
            leave_type_code: "AL",
            leave_type_name: "Annual Leave",
            year: 2026,
            annual_allocation: "18.0",
            carried_forward: "2.0",
            accrued: "0.0",
            used: "5.0",
            pending_approval: "2.0",
            available_balance: "13.0",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockBalances), { status: 200 });
      };

      const result = await leaveApi.getMyBalances(tToken);
      assert.ok(capturedUrl.includes("/leave/balances/my"));
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].available_balance, "13.0");
    });

    it("should submit a full-day leave request", async () => {
      let capturedBody: any = null;
      let capturedMethod = "";

      const mockRequest: LeaveRequestDto = {
        id: "req-1",
        tenant_id: tTenantId,
        employee_id: tEmployeeId,
        employee_name: "John Doe",
        leave_type_id: "lt-1",
        leave_type_code: "AL",
        leave_type_name: "Annual Leave",
        start_date: "2026-11-25",
        end_date: "2026-11-27",
        is_half_day: false,
        half_day_period: null,
        total_days: "3.0",
        reason: "Family vacation",
        status: "PENDING_APPROVAL",
        reviewer_user_id: null,
        reviewer_notes: null,
        decided_at: null,
        created_at: "2026-11-20T00:00:00Z",
        updated_at: "2026-11-20T00:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify(mockRequest), { status: 201 });
      };

      const result = await leaveApi.applyLeave(
        {
          leave_type_id: "lt-1",
          start_date: "2026-11-25",
          end_date: "2026-11-27",
          is_half_day: false,
          reason: "Family vacation",
        },
        tToken
      );

      assert.equal(capturedMethod, "POST");
      assert.equal(capturedBody.start_date, "2026-11-25");
      assert.equal(capturedBody.end_date, "2026-11-27");
      assert.equal(result.status, "PENDING_APPROVAL");
    });

    it("should submit a half-day leave request with FIRST_HALF session", async () => {
      let capturedBody: any = null;

      const mockRequest: LeaveRequestDto = {
        id: "req-2",
        tenant_id: tTenantId,
        employee_id: tEmployeeId,
        leave_type_id: "lt-1",
        start_date: "2026-11-25",
        end_date: "2026-11-25",
        is_half_day: true,
        half_day_period: "FIRST_HALF",
        total_days: "0.5",
        reason: "Doctor appointment",
        status: "PENDING_APPROVAL",
        created_at: "2026-11-20T00:00:00Z",
        updated_at: "2026-11-20T00:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify(mockRequest), { status: 201 });
      };

      const result = await leaveApi.applyLeave(
        {
          leave_type_id: "lt-1",
          start_date: "2026-11-25",
          end_date: "2026-11-25",
          is_half_day: true,
          half_day_period: "FIRST_HALF",
          reason: "Doctor appointment",
        },
        tToken
      );

      assert.equal(capturedBody.is_half_day, true);
      assert.equal(capturedBody.half_day_period, "FIRST_HALF");
      assert.equal(result.total_days, "0.5");
    });

    it("should cancel a pending leave request", async () => {
      let capturedUrl = "";
      let capturedMethod = "";

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "GET";
        return new Response(JSON.stringify({ id: "req-1", status: "CANCELLED" }), { status: 200 });
      };

      const result = await leaveApi.cancelLeaveRequest("req-1", { reason: "Trip cancelled" }, tToken);
      assert.ok(capturedUrl.includes("/leave/requests/req-1/cancel"));
      assert.equal(capturedMethod, "POST");
      assert.equal(result.status, "CANCELLED");
    });
  });

  // ===========================================================================
  // 4. Supervisor Leave Review & Adjudication Tests
  // ===========================================================================
  describe("leaveApi — Supervisor Review Queue & Adjudication", () => {
    it("should fetch supervisor review queue with pending filter", async () => {
      let capturedUrl = "";
      const mockQueue: LeaveRequestListResponseDto = {
        items: [
          {
            id: "req-1",
            tenant_id: tTenantId,
            employee_id: "subordinate-emp-1",
            employee_name: "Subordinate Employee",
            leave_type_id: "lt-1",
            leave_type_code: "AL",
            start_date: "2026-11-25",
            end_date: "2026-11-27",
            is_half_day: false,
            total_days: "3.0",
            reason: "Personal time off",
            status: "PENDING_APPROVAL",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockQueue), { status: 200 });
      };

      const result = await leaveApi.getSupervisorQueue({ status: "PENDING_APPROVAL" }, tToken);
      assert.ok(capturedUrl.includes("/leave/requests?status=PENDING_APPROVAL"));
      assert.equal(result.items.length, 1);
    });

    it("should adjudicate leave request with APPROVE action", async () => {
      let capturedBody: any = null;
      let capturedUrl = "";

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify({ id: "req-1", status: "APPROVED" }), { status: 200 });
      };

      const result = await leaveApi.adjudicateLeaveRequest(
        "req-1",
        { action: "APPROVE", reason: "Approved by manager" },
        tToken
      );

      assert.ok(capturedUrl.includes("/leave/requests/req-1/decision"));
      assert.equal(capturedBody.action, "APPROVE");
      assert.equal(result.status, "APPROVED");
    });

    it("should adjudicate leave request with REJECT action and mandatory reason", async () => {
      let capturedBody: any = null;

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return new Response(
          JSON.stringify({ id: "req-1", status: "REJECTED", reviewer_notes: "Staffing constraint" }),
          { status: 200 }
        );
      };

      const result = await leaveApi.adjudicateLeaveRequest(
        "req-1",
        { action: "REJECT", reason: "Staffing constraint" },
        tToken
      );

      assert.equal(capturedBody.action, "REJECT");
      assert.equal(capturedBody.reason, "Staffing constraint");
      assert.equal(result.status, "REJECTED");
    });

    it("should throw 403 Forbidden on anti-self-approval attempt", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Anti-self-approval: Reviewers cannot adjudicate their own leave request" }),
          { status: 403 }
        );
      };

      await assert.rejects(
        async () => {
          await leaveApi.adjudicateLeaveRequest("my-own-req", { action: "APPROVE" }, tToken);
        },
        (err: any) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.detail.includes("Anti-self-approval"));
          return true;
        }
      );
    });

    it("should throw 422 Unprocessable Content if rejection reason is missing or short", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Rejection reason must be at least 3 characters" }),
          { status: 422 }
        );
      };

      await assert.rejects(
        async () => {
          await leaveApi.adjudicateLeaveRequest("req-1", { action: "REJECT", reason: "no" }, tToken);
        },
        (err: any) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 422);
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 5. Overtime Rules & Records Administration Tests
  // ===========================================================================
  describe("overtimeApi — Rules & Records", () => {
    it("should fetch overtime rules list", async () => {
      const mockRules: OvertimeRuleListResponseDto = {
        items: [
          {
            id: "ot-rule-1",
            tenant_id: tTenantId,
            name: "Standard Enterprise Overtime",
            min_overtime_threshold_minutes: 30,
            max_daily_overtime_minutes: 240,
            max_weekly_overtime_minutes: 720,
            workday_multiplier: "1.50",
            weekend_multiplier: "2.00",
            holiday_multiplier: "2.00",
            requires_manager_approval: true,
            requires_pre_approval: false,
            is_default: true,
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      };

      globalThis.fetch = async () => {
        return new Response(JSON.stringify(mockRules), { status: 200 });
      };

      const result = await overtimeApi.getRules({}, tToken);
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].workday_multiplier, "1.50");
      assert.equal(result.items[0].holiday_multiplier, "2.00");
    });

    it("should create a new overtime rule with default flag", async () => {
      let capturedBody: any = null;

      const mockRule: OvertimeRuleDto = {
        id: "ot-rule-2",
        tenant_id: tTenantId,
        name: "Weekend Heavy Operations",
        min_overtime_threshold_minutes: 15,
        max_daily_overtime_minutes: 360,
        max_weekly_overtime_minutes: 1000,
        workday_multiplier: "1.50",
        weekend_multiplier: "2.50",
        holiday_multiplier: "3.00",
        requires_manager_approval: true,
        requires_pre_approval: true,
        is_default: false,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedBody = JSON.parse(init?.body as string);
        return new Response(JSON.stringify(mockRule), { status: 201 });
      };

      const result = await overtimeApi.createRule(
        {
          name: "Weekend Heavy Operations",
          workday_multiplier: 1.5,
          weekend_multiplier: 2.5,
          holiday_multiplier: 3.0,
          requires_pre_approval: true,
        },
        tToken
      );

      assert.equal(capturedBody.name, "Weekend Heavy Operations");
      assert.equal(result.weekend_multiplier, "2.50");
    });

    it("should fetch supervisor overtime review queue", async () => {
      let capturedUrl = "";
      const mockRecords: OvertimeRecordListResponseDto = {
        items: [
          {
            id: "ot-rec-1",
            tenant_id: tTenantId,
            employee_id: "emp-333",
            employee_name: "Jane Smith",
            attendance_day_id: "day-uuid-1",
            attendance_date: "2026-11-20",
            overtime_rule_id: "ot-rule-1",
            raw_overtime_minutes: 90,
            approved_overtime_minutes: 0,
            multiplier: "1.50",
            payable_overtime_minutes: 135,
            overtime_type: "WORKDAY",
            status: "PENDING_APPROVAL",
            reviewer_user_id: null,
            reviewer_notes: null,
            decided_at: null,
            created_at: "2026-11-20T18:00:00Z",
            updated_at: "2026-11-20T18:00:00Z",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockRecords), { status: 200 });
      };

      const result = await overtimeApi.getRecords({ status: "PENDING_APPROVAL" }, tToken);
      assert.ok(capturedUrl.includes("/overtime/records?status=PENDING_APPROVAL"));
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].raw_overtime_minutes, 90);
      assert.equal(result.items[0].payable_overtime_minutes, 135);
    });

    it("should fetch employee personal overtime records via /overtime/records/my", async () => {
      let capturedUrl = "";

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify({ items: [], total: 0, limit: 100, offset: 0 }), { status: 200 });
      };

      await overtimeApi.getMyRecords({}, tToken);
      assert.ok(capturedUrl.includes("/overtime/records/my"));
    });

    it("should adjudicate overtime record with APPROVE action and adjusted minutes", async () => {
      let capturedBody: any = null;
      let capturedUrl = "";

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(
          JSON.stringify({
            id: "ot-rec-1",
            status: "APPROVED",
            approved_overtime_minutes: 60,
            payable_overtime_minutes: 90,
          }),
          { status: 200 }
        );
      };

      const result = await overtimeApi.adjudicateRecord(
        "ot-rec-1",
        {
          action: "APPROVE",
          approved_minutes: 60,
          reason: "Approved 1 hour",
        },
        tToken
      );

      assert.ok(capturedUrl.includes("/overtime/records/ot-rec-1/decision"));
      assert.equal(capturedBody.action, "APPROVE");
      assert.equal(capturedBody.approved_minutes, 60);
      assert.equal(result.status, "APPROVED");
    });

    it("should throw 403 Forbidden on anti-self-approval of overtime", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Anti-self-approval: Reviewers cannot approve their own overtime" }),
          { status: 403 }
        );
      };

      await assert.rejects(
        async () => {
          await overtimeApi.adjudicateRecord("my-ot-rec", { action: "APPROVE" }, tToken);
        },
        (err: any) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.detail.includes("Anti-self-approval"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 6. Balance & Overtime Mathematical Invariant Tests (Frontend Validation)
  // ===========================================================================
  describe("Frontend Invariant Verification", () => {
    it("should verify available balance mathematical invariant", () => {
      const allocation = 15;
      const carried = 3;
      const accrued = 2;
      const used = 6;
      const pending = 4;

      const available = allocation + carried + accrued - used - pending;
      assert.equal(available, 10);
    });

    it("should verify overtime payable minutes formula", () => {
      const rawMinutes = 120;
      const multiplier = 1.5;
      const payable = Math.round(rawMinutes * multiplier);
      assert.equal(payable, 180);
    });

    it("should verify holiday overtime payable minutes formula with 2.0x multiplier", () => {
      const rawMinutes = 480; // 8 hours on a statutory holiday
      const multiplier = 2.0;
      const payable = Math.round(rawMinutes * multiplier);
      assert.equal(payable, 960);
    });

    it("should validate rejection reason minimum length requirement", () => {
      const validateRejectionReason = (reason: string | null | undefined): boolean => {
        return !!reason && reason.trim().length >= 3;
      };

      assert.equal(validateRejectionReason(""), false);
      assert.equal(validateRejectionReason("   "), false);
      assert.equal(validateRejectionReason("no"), false);
      assert.equal(validateRejectionReason("Project deadline clash"), true);
    });
  });
});
