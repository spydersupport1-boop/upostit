import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  conflictApi,
  apiFetch,
  ApiError,
  API_BASE_URL,
} from "./api.ts";
import type {
  SupervisorConflictQueueListResponseDto,
  AttendanceConflictIncidentDetailDto,
  AttendanceConflictDecisionResponseDto,
  EmployeeConflictIncidentListResponseDto,
} from "./api.ts";

describe("Phase 8 Milestone 8.5 — Offline Conflict Supervisor Console & API Integration", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const tToken = "mock-supervisor-token-abc";
  const tIncidentId = "550e8400-e29b-41d4-a716-446655440000";

  describe("conflictApi.getSupervisorQueue", () => {
    it("should fetch supervisor review queue with query parameters", async () => {
      let capturedUrl = "";
      let capturedHeaders: Record<string, string> = {};

      const mockResponse: SupervisorConflictQueueListResponseDto = {
        items: [
          {
            id: tIncidentId,
            tenant_id: "tenant-uuid-1",
            employee_id: "emp-uuid-1",
            employee_name: "John Doe",
            employee_code: "EMP-001",
            department_name: "Field Operations",
            bundle_id: "bundle-uuid-123",
            session_id: "sess-uuid-456",
            status: "PENDING_REVIEW",
            total_events_count: 2,
            primary_event_type: "CHECK_IN",
            primary_device_reported_at: "2026-11-10T08:00:00.000Z",
            rejection_summary: "Timestamp beyond maximum drift window (422)",
            employee_notes: "Cell battery died overnight",
            submitted_at: "2026-11-10T09:00:00.000Z",
            resolved_correction_event_ids: [],
          },
        ],
        total: 1,
        limit: 50,
        cursor: null,
        has_more: false,
      };

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedHeaders = (init?.headers as Record<string, string>) || {};
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await conflictApi.getSupervisorQueue(
        {
          status: "PENDING_REVIEW",
          start_date: "2026-11-01",
          end_date: "2026-11-15",
          limit: 50,
        },
        tToken
      );

      assert.ok(capturedUrl.startsWith(`${API_BASE_URL}/api/v1/attendance/offline-conflicts`));
      assert.ok(capturedUrl.includes("status=PENDING_REVIEW"));
      assert.ok(capturedUrl.includes("start_date=2026-11-01"));
      assert.ok(capturedUrl.includes("end_date=2026-11-15"));
      assert.ok(capturedUrl.includes("limit=50"));
      assert.equal(capturedHeaders["Authorization"], `Bearer ${tToken}`);

      assert.equal(result.total, 1);
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].id, tIncidentId);
      assert.equal(result.items[0].status, "PENDING_REVIEW");
      assert.equal(result.items[0].employee_name, "John Doe");
      assert.equal(result.items[0].total_events_count, 2);
    });
  });

  describe("conflictApi.getIncidentDetail", () => {
    it("should fetch complete forensic incident detail by ID", async () => {
      let capturedUrl = "";

      const mockDetail: AttendanceConflictIncidentDetailDto = {
        id: tIncidentId,
        tenant_id: "tenant-uuid-1",
        bundle_id: "bundle-uuid-123",
        session_id: "sess-uuid-456",
        status: "PENDING_REVIEW",
        employee: {
          id: "emp-uuid-1",
          employee_code: "EMP-001",
          first_name: "John",
          last_name: "Doe",
          work_email: "john.doe@enterprise.com",
          department_name: "Engineering",
          reporting_manager_id: "mgr-uuid-1",
        },
        primary_rejected_event: {
          local_id: "loc-1",
          idempotency_key: "idemp-p1",
          event_type: "CHECK_IN",
          device_reported_at: "2026-11-10T08:00:00.000Z",
          latitude: 12.9716,
          longitude: 77.5946,
          accuracy_meters: 10.5,
          is_mock_location: false,
          server_rejection_code: 422,
          server_rejection_reason: "Clock drift beyond tenant threshold",
        },
        dependent_events: [
          {
            local_id: "loc-2",
            idempotency_key: "idemp-d2",
            event_type: "CHECK_OUT",
            device_reported_at: "2026-11-10T17:00:00.000Z",
            latitude: 12.972,
            longitude: 77.595,
            accuracy_meters: 15.0,
            is_mock_location: false,
          },
        ],
        total_events_count: 2,
        rejection_summary: "Clock drift beyond tenant threshold",
        employee_notes: "Phone date was wrong",
        submitted_at: "2026-11-10T09:00:00.000Z",
        resolved_correction_event_ids: [],
        metadata_json: {},
        created_at: "2026-11-10T09:00:00.000Z",
        updated_at: "2026-11-10T09:00:00.000Z",
      };

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockDetail), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await conflictApi.getIncidentDetail(tIncidentId, tToken);

      assert.equal(capturedUrl, `${API_BASE_URL}/api/v1/attendance/offline-conflicts/${tIncidentId}`);
      assert.equal(result.id, tIncidentId);
      assert.equal(result.employee.first_name, "John");
      assert.equal(result.primary_rejected_event.event_type, "CHECK_IN");
      assert.equal(result.dependent_events.length, 1);
      assert.equal(result.dependent_events[0].event_type, "CHECK_OUT");
      assert.equal(result.primary_rejected_event.is_mock_location, false);
    });
  });

  describe("conflictApi.adjudicateIncident", () => {
    it("should submit APPROVE decision with mandatory reason and optional location override", async () => {
      let capturedUrl = "";
      let capturedMethod = "";
      let capturedBody: Record<string, unknown> = {};

      const mockDecisionResp: AttendanceConflictDecisionResponseDto = {
        id: tIncidentId,
        tenant_id: "tenant-uuid-1",
        employee_id: "emp-uuid-1",
        bundle_id: "bundle-uuid-123",
        status: "APPROVED",
        decision: "APPROVE",
        decision_reason: "Verified work attendance on-site",
        reviewer_user_id: "supervisor-uuid-9",
        decided_at: "2026-11-10T10:00:00.000Z",
        resolved_correction_event_ids: ["corr-evt-1", "corr-evt-2"],
        affected_attendance_dates: ["2026-11-10"],
        recalculated_days_count: 1,
      };

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "GET";
        capturedBody = JSON.parse((init?.body as string) || "{}");
        return new Response(JSON.stringify(mockDecisionResp), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await conflictApi.adjudicateIncident(
        tIncidentId,
        {
          action: "APPROVE",
          reason: "Verified work attendance on-site",
          override_location_id: "loc-override-uuid-77",
        },
        tToken
      );

      assert.equal(
        capturedUrl,
        `${API_BASE_URL}/api/v1/attendance/offline-conflicts/${tIncidentId}/decision`
      );
      assert.equal(capturedMethod, "POST");
      assert.equal(capturedBody["action"], "APPROVE");
      assert.equal(capturedBody["reason"], "Verified work attendance on-site");
      assert.equal(capturedBody["override_location_id"], "loc-override-uuid-77");

      assert.equal(result.status, "APPROVED");
      assert.equal(result.decision, "APPROVE");
      assert.equal(result.recalculated_days_count, 1);
      assert.equal(result.resolved_correction_event_ids.length, 2);
    });

    it("should submit REJECT decision leaving attendance ledger untouched", async () => {
      let capturedBody: Record<string, unknown> = {};

      const mockRejectResp: AttendanceConflictDecisionResponseDto = {
        id: tIncidentId,
        tenant_id: "tenant-uuid-1",
        employee_id: "emp-uuid-1",
        bundle_id: "bundle-uuid-123",
        status: "REJECTED",
        decision: "REJECT",
        decision_reason: "Punch evidence does not match facility badge log",
        reviewer_user_id: "supervisor-uuid-9",
        decided_at: "2026-11-10T10:05:00.000Z",
        resolved_correction_event_ids: [],
        affected_attendance_dates: [],
        recalculated_days_count: 0,
      };

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedBody = JSON.parse((init?.body as string) || "{}");
        return new Response(JSON.stringify(mockRejectResp), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await conflictApi.adjudicateIncident(
        tIncidentId,
        {
          action: "REJECT",
          reason: "Punch evidence does not match facility badge log",
        },
        tToken
      );

      assert.equal(capturedBody["action"], "REJECT");
      assert.equal(capturedBody["reason"], "Punch evidence does not match facility badge log");
      assert.equal(result.status, "REJECTED");
      assert.equal(result.decision, "REJECT");
      assert.equal(result.recalculated_days_count, 0);
      assert.equal(result.resolved_correction_event_ids.length, 0);
    });
  });

  describe("conflictApi.getMyConflicts", () => {
    it("should fetch personal conflict incidents via /my endpoint", async () => {
      let capturedUrl = "";

      const mockList: EmployeeConflictIncidentListResponseDto = {
        items: [
          {
            id: tIncidentId,
            bundle_id: "bundle-uuid-123",
            session_id: "sess-uuid-456",
            status: "APPROVED",
            total_events_count: 2,
            primary_event_type: "CHECK_IN",
            primary_event_timestamp: "2026-11-10T08:00:00.000Z",
            rejection_summary: "Drift error",
            employee_notes: "Battery issue",
            submitted_at: "2026-11-10T09:00:00.000Z",
            decision: "APPROVE",
            decision_reason: "Approved by manager",
            decided_at: "2026-11-10T11:00:00.000Z",
            resolved_events_count: 2,
          },
        ],
        total: 1,
        limit: 20,
        cursor: null,
        has_more: false,
      };

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify(mockList), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await conflictApi.getMyConflicts({ status: "APPROVED" }, tToken);

      assert.ok(capturedUrl.includes("/attendance/offline-conflicts/my"));
      assert.ok(capturedUrl.includes("status=APPROVED"));
      assert.equal(result.total, 1);
      assert.equal(result.items[0].status, "APPROVED");
    });
  });

  describe("Error Handling & Invariants", () => {
    it("should throw ApiError with status 403 on anti-self-approval violation", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            detail: "Anti-self-approval policy violation: supervisors cannot adjudicate their own attendance conflicts.",
          }),
          {
            status: 403,
            headers: { "Content-Type": "application/json" },
          }
        );
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            { action: "APPROVE", reason: "Approving my own punch" },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.detail.includes("Anti-self-approval"));
          return true;
        }
      );
    });

    it("should throw ApiError with status 409 when incident is already resolved", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            detail: "Conflict incident 550e8400 has already been adjudicated with status 'APPROVED'.",
          }),
          {
            status: 409,
            headers: { "Content-Type": "application/json" },
          }
        );
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            { action: "REJECT", reason: "Attempting late rejection" },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 409);
          assert.ok(err.detail.includes("already been adjudicated"));
          return true;
        }
      );
    });

    it("should throw ApiError with status 422 when decision reason is under 3 characters", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            detail: "Decision reason must contain at least 3 non-whitespace characters.",
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          }
        );
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            { action: "APPROVE", reason: "ok" },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 422);
          assert.ok(err.detail.includes("at least 3 non-whitespace characters"));
          return true;
        }
      );
    });

    it("should throw ApiError with status 404 when incident does not exist or is cross-tenant", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            detail: "Attendance conflict incident not found or inaccessible.",
          }),
          {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }
        );
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await conflictApi.getIncidentDetail("non-existent-id", tToken);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 404);
          return true;
        }
      );
    });
  });

  describe("Decision Validation Invariants (Frontend Client-Side)", () => {
    it("should validate reason length >= 3 non-whitespace characters", () => {
      const validate = (reason: string): boolean => {
        return (reason || "").trim().length >= 3;
      };

      assert.equal(validate(""), false);
      assert.equal(validate("  "), false);
      assert.equal(validate("ok"), false);
      assert.equal(validate("  a  "), false);
      assert.equal(validate("yes"), true);
      assert.equal(validate("Approved by supervisor"), true);
    });

    it("should normalize action strings to uppercase APPROVE or REJECT", () => {
      const normalize = (action: string): string => {
        const clean = (action || "").trim().toUpperCase();
        if (clean === "APPROVE" || clean === "APPROVED") return "APPROVE";
        if (clean === "REJECT" || clean === "REJECTED") return "REJECT";
        throw new Error(`Invalid action: ${action}`);
      };

      assert.equal(normalize("approve"), "APPROVE");
      assert.equal(normalize("APPROVED"), "APPROVE");
      assert.equal(normalize("reject"), "REJECT");
      assert.equal(normalize("REJECTED"), "REJECT");
      assert.throws(() => normalize("INVALID"));
    });
  });
});
