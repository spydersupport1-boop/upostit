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

describe("Phase 8 Milestone 8.6 — Web Supervisor Console & Adjudication Chaos Simulation", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const tToken = "mock-supervisor-token-xyz";
  const tIncidentId = "550e8400-e29b-41d4-a716-446655440000";
  const tBundleId = "bundle-uuid-8888";
  const tSessionId = "sess-uuid-7777";
  const tOverrideLocationId = "loc-override-uuid-9999";

  const mockIncidentDetail: AttendanceConflictIncidentDetailDto = {
    id: tIncidentId,
    tenant_id: "tenant-uuid-1",
    bundle_id: tBundleId,
    session_id: tSessionId,
    status: "PENDING_REVIEW",
    employee: {
      id: "emp-uuid-1",
      employee_code: "EMP-100",
      first_name: "Jane",
      last_name: "Doe",
      work_email: "jane.doe@e2e.test",
      department_name: "Operations",
      reporting_manager_id: "mgr-uuid-1",
    },
    primary_rejected_event: {
      event_id: "evt-rejected-1",
      client_timestamp: "2026-11-20T08:00:00.000Z",
      event_type: "CHECK_IN",
      latitude: 40.7128,
      longitude: -74.0060,
      accuracy_meters: 12.5,
      is_mock_location: false,
      wifi_ssid: "HQ_Staff_5G",
      wifi_bssid: "00:11:22:33:44:55",
      device_model: "Pixel 8",
      os_version: "Android 15",
      rejection_code: 422,
      rejection_reason: "Reported GPS location was 250m outside workplace geofence",
    },
    dependent_events: [
      {
        event_id: "evt-quarantined-2",
        client_timestamp: "2026-11-20T12:00:00.000Z",
        event_type: "BREAK_START",
        latitude: 40.7128,
        longitude: -74.0060,
        accuracy_meters: 10.0,
        is_mock_location: false,
      },
      {
        event_id: "evt-quarantined-3",
        client_timestamp: "2026-11-20T12:30:00.000Z",
        event_type: "BREAK_END",
        latitude: 40.7128,
        longitude: -74.0060,
        accuracy_meters: 10.0,
        is_mock_location: false,
      },
      {
        event_id: "evt-quarantined-4",
        client_timestamp: "2026-11-20T17:00:00.000Z",
        event_type: "CHECK_OUT",
        latitude: 40.7128,
        longitude: -74.0060,
        accuracy_meters: 11.2,
        is_mock_location: false,
      },
    ],
    total_events_count: 4,
    rejection_summary: "Reported GPS location was 250m outside workplace geofence",
    employee_notes: "Dispatched to secondary facility by shift lead",
    submitted_at: "2026-11-20T17:30:00.000Z",
    bundle_fingerprint: "sha256:7d8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a",
    created_at: "2026-11-20T17:30:00.000Z",
    updated_at: "2026-11-20T17:30:00.000Z",
  };

  describe("End-to-End Web Supervisor Workflow", () => {
    it("simulates full review lifecycle: queue fetch -> detail modal inspection -> approve with location override", async () => {
      let step = 0;

      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        step++;
        const url = String(input);

        if (step === 1) {
          // 1. Supervisor loads queue
          assert.ok(url.includes("/api/v1/attendance/offline-conflicts"));
          assert.ok(url.includes("status=PENDING_REVIEW"));

          const queueResponse: SupervisorConflictQueueListResponseDto = {
            items: [
              {
                id: tIncidentId,
                tenant_id: "tenant-uuid-1",
                employee_id: "emp-uuid-1",
                employee_name: "Jane Doe",
                employee_code: "EMP-100",
                department_name: "Operations",
                bundle_id: tBundleId,
                session_id: tSessionId,
                status: "PENDING_REVIEW",
                total_events_count: 4,
                dependent_count: 3,
                primary_event_type: "CHECK_IN",
                primary_device_reported_at: "2026-11-20T08:00:00.000Z",
                rejection_summary: "Reported GPS location was 250m outside workplace geofence",
                submitted_at: "2026-11-20T17:30:00.000Z",
              },
            ],
            total: 1,
            limit: 50,
            has_more: false,
          };
          return new Response(JSON.stringify(queueResponse), { status: 200 });
        }

        if (step === 2) {
          // 2. Supervisor opens forensic detail modal
          assert.ok(url.endsWith(`/api/v1/attendance/offline-conflicts/${tIncidentId}`));
          return new Response(JSON.stringify(mockIncidentDetail), { status: 200 });
        }

        if (step === 3) {
          // 3. Supervisor submits APPROVE decision with location override
          assert.ok(url.endsWith(`/api/v1/attendance/offline-conflicts/${tIncidentId}/decision`));
          assert.equal(init?.method, "POST");

          const body = JSON.parse(String(init?.body));
          assert.equal(body.action, "APPROVE");
          assert.equal(body.override_location_id, tOverrideLocationId);
          assert.ok(body.reason.length >= 3);

          const decisionResponse: AttendanceConflictDecisionResponseDto = {
            id: tIncidentId,
            tenant_id: "tenant-uuid-1",
            employee_id: "emp-uuid-1",
            bundle_id: tBundleId,
            session_id: tSessionId,
            status: "APPROVED",
            decision: "APPROVED",
            decision_reason: body.reason,
            reviewer_user_id: "mgr-uuid-1",
            decided_at: "2026-11-20T18:00:00.000Z",
            resolved_correction_event_ids: ["corr-1", "corr-2", "corr-3", "corr-4"],
            affected_attendance_dates: ["2026-11-20"],
            recalculated_days_count: 1,
          };
          return new Response(JSON.stringify(decisionResponse), { status: 200 });
        }

        throw new Error(`Unexpected step: ${step}`);
      };

      // Execute Step 1
      const queue = await conflictApi.getSupervisorQueue({ status: "PENDING_REVIEW" }, tToken);
      assert.equal(queue.total, 1);
      assert.equal(queue.items[0].primary_event_type, "CHECK_IN");
      assert.equal(queue.items[0].dependent_count, 3);

      // Execute Step 2
      const detail = await conflictApi.getIncidentDetail(tIncidentId, tToken);
      assert.equal(detail.id, tIncidentId);
      assert.equal(detail.bundle_fingerprint, "sha256:7d8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a");
      assert.equal(detail.dependent_events.length, 3);
      assert.equal(detail.primary_rejected_event.rejection_code, 422);

      // Execute Step 3
      const decision = await conflictApi.adjudicateIncident(
        tIncidentId,
        {
          action: "APPROVE",
          reason: "Confirmed off-site dispatch with operations supervisor",
          override_location_id: tOverrideLocationId,
        },
        tToken
      );

      assert.equal(decision.status, "APPROVED");
      assert.equal(decision.resolved_correction_event_ids.length, 4);
      assert.equal(decision.recalculated_days_count, 1);
      assert.deepEqual(decision.affected_attendance_dates, ["2026-11-20"]);
    });

    it("simulates rejection workflow: leaves ledger untouched and updates status to REJECTED", async () => {
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const body = JSON.parse(String(init?.body));
        assert.equal(body.action, "REJECT");
        assert.equal(body.override_location_id, undefined);

        const decisionResponse: AttendanceConflictDecisionResponseDto = {
          id: tIncidentId,
          tenant_id: "tenant-uuid-1",
          employee_id: "emp-uuid-1",
          bundle_id: tBundleId,
          session_id: tSessionId,
          status: "REJECTED",
          decision: "REJECTED",
          decision_reason: body.reason,
          reviewer_user_id: "mgr-uuid-1",
          decided_at: "2026-11-20T18:00:00.000Z",
          resolved_correction_event_ids: [],
          affected_attendance_dates: [],
          recalculated_days_count: 0,
        };
        return new Response(JSON.stringify(decisionResponse), { status: 200 });
      };

      const decision = await conflictApi.adjudicateIncident(
        tIncidentId,
        {
          action: "REJECT",
          reason: "Vehicle tracker confirms worker was not on duty at designated client facility",
        },
        tToken
      );

      assert.equal(decision.status, "REJECTED");
      assert.equal(decision.decision, "REJECTED");
      assert.deepEqual(decision.resolved_correction_event_ids, []);
      assert.deepEqual(decision.affected_attendance_dates, []);
      assert.equal(decision.recalculated_days_count, 0);
    });
  });

  describe("Chaos and Edge-Case Handling in Web Client", () => {
    it("handles concurrency collision: 409 Conflict when incident already adjudicated by another supervisor", async () => {
      globalThis.fetch = async (): Promise<Response> => {
        return new Response(
          JSON.stringify({
            detail: "Conflict incident has already been resolved (APPROVED).",
          }),
          { status: 409, statusText: "Conflict" }
        );
      };

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            {
              action: "APPROVE",
              reason: "Concurrent attempt to approve",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 409);
          assert.ok(err.message.includes("already been resolved"));
          return true;
        }
      );
    });

    it("handles anti-self-approval rejection: 403 Forbidden when reviewer attempts to approve own conflict", async () => {
      globalThis.fetch = async (): Promise<Response> => {
        return new Response(
          JSON.stringify({
            detail: "Reviewers cannot adjudicate their own attendance conflicts.",
          }),
          { status: 403, statusText: "Forbidden" }
        );
      };

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            {
              action: "APPROVE",
              reason: "Attempting self-approval of missed punch",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.message.includes("cannot adjudicate their own"));
          return true;
        }
      );
    });

    it("handles manager scoping violation: 403 Forbidden when accessing non-direct report", async () => {
      globalThis.fetch = async (): Promise<Response> => {
        return new Response(
          JSON.stringify({
            detail: "Managers may only adjudicate attendance conflicts for their direct reports.",
          }),
          { status: 403, statusText: "Forbidden" }
        );
      };

      await assert.rejects(
        async () => {
          await conflictApi.adjudicateIncident(
            tIncidentId,
            {
              action: "APPROVE",
              reason: "Attempting to approve non-direct report",
            },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.message.includes("direct reports"));
          return true;
        }
      );
    });

    it("handles 404 Not Found for non-existent or cross-tenant incidents", async () => {
      globalThis.fetch = async (): Promise<Response> => {
        return new Response(
          JSON.stringify({
            detail: "Attendance conflict incident not found.",
          }),
          { status: 404, statusText: "Not Found" }
        );
      };

      await assert.rejects(
        async () => {
          await conflictApi.getIncidentDetail("non-existent-uuid", tToken);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 404);
          assert.ok(err.message.includes("not found"));
          return true;
        }
      );
    });

    it("enforces client-side validation invariant: reason must have at least 3 non-whitespace characters", () => {
      const validateReason = (r: string): boolean => r.trim().length >= 3;

      assert.equal(validateReason(""), false);
      assert.equal(validateReason("   "), false);
      assert.equal(validateReason("ok"), false);
      assert.equal(validateReason("  ab  "), false);
      assert.equal(validateReason("yes"), true);
      assert.equal(validateReason("Approved after facility log check"), true);
    });
  });
});
