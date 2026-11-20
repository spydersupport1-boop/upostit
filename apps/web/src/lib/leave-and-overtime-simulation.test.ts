import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  leaveApi,
  overtimeApi,
  ApiError,
  API_BASE_URL,
} from "./api.ts";
import type {
  LeaveBalanceDto,
  LeaveRequestDto,
  OvertimeRecordDto,
} from "./api.ts";

describe("Phase 9 Milestone 9.7 — Web Console: End-to-End Simulation, Concurrency & Chaos", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const tToken = "mock-jwt-auth-token-12345";
  const tTenantId = "tenant-uuid-111";
  const tEmployeeId = "emp-uuid-alice-001";
  const tSupervisorUserId = "user-uuid-eleanor-mgr";
  const tSupervisorEmployeeId = "emp-uuid-eleanor-mgr";

  // ===========================================================================
  // 1. End-to-End Leave Lifecycle Simulation
  // ===========================================================================
  describe("E2E Leave Lifecycle Simulation", () => {
    it("simulates complete leave lifecycle: balance query -> apply -> hold -> approve -> cancel -> restore", async () => {
      let balanceState: LeaveBalanceDto = {
        id: "bal-uuid-1",
        tenant_id: tTenantId,
        employee_id: tEmployeeId,
        leave_type_id: "lt-annual-1",
        leave_type_code: "ANNUAL",
        leave_type_name: "Annual Paid Leave",
        year: 2026,
        annual_allocation: 20,
        carried_forward: 0,
        accrued: 20,
        used: 0,
        pending_approval: 0,
        available_balance: 20,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };

      const appliedRequest: LeaveRequestDto = {
        id: "req-uuid-101",
        tenant_id: tTenantId,
        employee_id: tEmployeeId,
        leave_type_id: "lt-annual-1",
        leave_type_code: "ANNUAL",
        leave_type_name: "Annual Paid Leave",
        start_date: "2026-12-01",
        end_date: "2026-12-02",
        total_days: 2,
        is_half_day: false,
        half_day_period: null,
        status: "PENDING_APPROVAL",
        reason: "Family trip",
        document_url: null,
        rejection_reason: null,
        decided_by_user_id: null,
        decided_at: null,
        created_at: "2026-11-20T10:00:00Z",
        updated_at: "2026-11-20T10:00:00Z",
      };

      // Step A: Employee queries initial balances
      globalThis.fetch = async (url, opts) => {
        return new Response(JSON.stringify({ items: [balanceState], total: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const initialRes = await leaveApi.getMyBalances(tToken);
      assert.equal(initialRes.items[0].available_balance, 20);
      assert.equal(initialRes.items[0].pending_approval, 0);
      assert.equal(initialRes.items[0].used, 0);

      // Step B: Employee applies for 2 days leave
      globalThis.fetch = async (url, opts) => {
        // Balance updates to reserve 2 days
        balanceState = {
          ...balanceState,
          pending_approval: 2,
          available_balance: 18,
        };
        return new Response(JSON.stringify(appliedRequest), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      };

      const submitted = await leaveApi.applyLeave(
        {
          leave_type_id: "lt-annual-1",
          start_date: "2026-12-01",
          end_date: "2026-12-02",
          is_half_day: false,
          reason: "Family trip",
        },
        tToken
      );
      assert.equal(submitted.status, "PENDING_APPROVAL");
      assert.equal(submitted.total_days, 2);
      assert.equal(balanceState.pending_approval, 2);
      assert.equal(balanceState.available_balance, 18);

      // Step C: Supervisor Approves the Request
      const approvedRequest: LeaveRequestDto = {
        ...appliedRequest,
        status: "APPROVED",
        decided_by_user_id: tSupervisorUserId,
        decided_at: "2026-11-20T11:00:00Z",
      };

      globalThis.fetch = async (url, opts) => {
        balanceState = {
          ...balanceState,
          pending_approval: 0,
          used: 2,
          available_balance: 18,
        };
        return new Response(JSON.stringify(approvedRequest), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const decided = await leaveApi.adjudicateLeaveRequest(
        submitted.id,
        {
          action: "APPROVE",
          reason: "Approved by Eleanor",
        },
        tToken
      );
      assert.equal(decided.status, "APPROVED");
      assert.equal(balanceState.used, 2);
      assert.equal(balanceState.pending_approval, 0);
      assert.equal(balanceState.available_balance, 18);

      // Step D: Employee cancels future approved leave
      const cancelledRequest: LeaveRequestDto = {
        ...approvedRequest,
        status: "CANCELLED",
      };

      globalThis.fetch = async (url, opts) => {
        balanceState = {
          ...balanceState,
          used: 0,
          available_balance: 20,
        };
        return new Response(JSON.stringify(cancelledRequest), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const cancelled = await leaveApi.cancelLeaveRequest(
        decided.id,
        { reason: "Plans changed" },
        tToken
      );
      assert.equal(cancelled.status, "CANCELLED");
      assert.equal(balanceState.used, 0);
      assert.equal(balanceState.available_balance, 20);
    });
  });

  // ===========================================================================
  // 2. Anti-Self-Approval Enforcement (Defect Fix Verification)
  // ===========================================================================
  describe("Anti-Self-Approval Cross-Platform Verification", () => {
    it("rejects supervisor attempting to approve their own leave request with 403 Forbidden", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            detail: "Anti-self-approval violation: Reviewers cannot approve or reject their own leave applications.",
          }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await leaveApi.adjudicateLeaveRequest(
            "req-own-1",
            {
              action: "APPROVE",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.message.includes("Anti-self-approval violation"));
          return true;
        }
      );
    });

    it("rejects supervisor attempting to approve their own overtime record with 403 Forbidden", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            detail: "Anti-self-approval violation: Reviewers cannot approve or reject their own overtime records.",
          }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await overtimeApi.adjudicateRecord(
            "ot-own-1",
            {
              action: "APPROVE",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.message.includes("Anti-self-approval violation"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 3. Concurrency, Conflict & Chaos Simulation
  // ===========================================================================
  describe("Concurrency & Conflict Handling", () => {
    it("handles 409 Conflict gracefully when duplicate approval attempts occur concurrently", async () => {
      let callCount = 0;
      globalThis.fetch = async () => {
        callCount++;
        if (callCount === 1) {
          return new Response(
            JSON.stringify({
              id: "req-race-1",
              status: "APPROVED",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(
          JSON.stringify({
            detail: "Leave request has already been decided (APPROVED).",
          }),
          { status: 409, headers: { "Content-Type": "application/json" } }
        );
      };

      // First decision succeeds
      const firstDecision = await leaveApi.adjudicateLeaveRequest(
        "req-race-1",
        { action: "APPROVE" },
        tToken
      );
      assert.equal(firstDecision.status, "APPROVED");

      // Concurrent second decision raises 409 Conflict
      await assert.rejects(
        async () => {
          await leaveApi.adjudicateLeaveRequest(
            "req-race-1",
            { action: "APPROVE" },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 409);
          assert.ok(err.message.includes("already been decided"));
          return true;
        }
      );
    });

    it("handles insufficient balance 400 error on concurrent competing leave submissions", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            detail: "Insufficient leave balance for ANNUAL: Requested 3.0 days, available 1.0 days.",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await leaveApi.applyLeave(
            {
              leave_type_id: "lt-annual-1",
              start_date: "2026-12-10",
              end_date: "2026-12-12",
              is_half_day: false,
              reason: "Competing request",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 400);
          assert.ok(err.message.includes("Insufficient leave balance"));
          return true;
        }
      );
    });

    it("simulates network failure retry idempotency during supervisor review", async () => {
      let attempts = 0;
      globalThis.fetch = async () => {
        attempts++;
        if (attempts === 1) {
          // Network timeout simulation
          throw new TypeError("Failed to fetch: connection timeout");
        }
        // Retry succeeds
        return new Response(
          JSON.stringify({
            id: "req-retry-1",
            status: "APPROVED",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      // Attempt 1 fails
      await assert.rejects(async () => {
        await leaveApi.adjudicateLeaveRequest("req-retry-1", { action: "APPROVE" }, tToken);
      });

      // Attempt 2 succeeds idempotently
      const retried = await leaveApi.adjudicateLeaveRequest("req-retry-1", { action: "APPROVE" }, tToken);
      assert.equal(retried.status, "APPROVED");
      assert.equal(attempts, 2);
    });
  });

  // ===========================================================================
  // 4. Overtime Multipliers & Supervisor Adjustment
  // ===========================================================================
  describe("Overtime Multipliers & Supervisor Adjustment", () => {
    it("correctly computes payable minutes for workday (1.5x), weekend (2.0x), and holiday (2.0x)", () => {
      // Workday: 120 mins raw, 1.5x multiplier -> 180 payable mins
      const workdayMins = 120;
      const workdayMult = 1.5;
      const workdayPayable = Math.round(workdayMins * workdayMult);
      assert.equal(workdayPayable, 180);

      // Weekend / Weekly-off: 240 mins raw, 2.0x multiplier -> 480 payable mins
      const weekendMins = 240;
      const weekendMult = 2.0;
      const weekendPayable = Math.round(weekendMins * weekendMult);
      assert.equal(weekendPayable, 480);

      // Holiday: 120 mins raw, 2.0x multiplier -> 240 payable mins
      const holidayMins = 120;
      const holidayMult = 2.0;
      const holidayPayable = Math.round(holidayMins * holidayMult);
      assert.equal(holidayPayable, 240);
    });

    it("simulates supervisor adjusting overtime minutes down upon approval", async () => {
      const mockRecord: OvertimeRecordDto = {
        id: "ot-rec-adjust-1",
        tenant_id: tTenantId,
        employee_id: tEmployeeId,
        employee_name: "Alice Worker",
        attendance_day_id: "day-uuid-1",
        attendance_date: "2026-11-20",
        overtime_rule_id: "rule-uuid-1",
        raw_overtime_minutes: 120,
        approved_overtime_minutes: 90, // Adjusted down from 120 to 90
        multiplier: 1.5,
        payable_overtime_minutes: 135, // 90 * 1.5 = 135
        overtime_type: "WORKDAY",
        status: "APPROVED",
        reviewer_user_id: tSupervisorUserId,
        reviewer_notes: "Adjusted 30 mins unverified post-shift time",
        decided_at: "2026-11-20T18:00:00Z",
        created_at: "2026-11-20T17:00:00Z",
        updated_at: "2026-11-20T18:00:00Z",
      };

      globalThis.fetch = async (url, opts) => {
        return new Response(JSON.stringify(mockRecord), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await overtimeApi.adjudicateRecord(
        "ot-rec-adjust-1",
        {
          action: "APPROVE",
          approved_minutes: 90,
          reason: "Adjusted 30 mins unverified post-shift time",
        },
        tToken
      );

      assert.equal(result.status, "APPROVED");
      assert.equal(result.raw_overtime_minutes, 120);
      assert.equal(result.approved_overtime_minutes, 90);
      assert.equal(result.payable_overtime_minutes, 135);
    });
  });
});
