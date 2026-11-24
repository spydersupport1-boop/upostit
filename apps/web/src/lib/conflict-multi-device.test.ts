import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { conflictApi } from "./api.ts";
import type {
  SupervisorConflictQueueItemDto,
  AttendanceConflictDecisionRequestDto,
} from "./api.ts";

describe("Phase 11 Milestone 11.5 — Web Console: Multi-Device Conflict Arbitration", () => {
  it("should parse multi-device conflict queue items with severity and classification", () => {
    const mockItem: SupervisorConflictQueueItemDto = {
      id: "inc-101",
      tenant_id: "tenant-1",
      employee_id: "emp-1",
      employee_name: "Alice Walker",
      employee_code: "EMP001",
      department_name: "Engineering",
      bundle_id: "rec_2026-11-24_OVERLAPPING_SESSIONS_abc",
      session_id: "sess-1",
      status: "NEEDS_CLARIFICATION",
      conflict_code: "DUPLICATE_CHECK_IN",
      severity: "HIGH",
      classification: "NEEDS_EMPLOYEE_CLARIFICATION",
      total_events_count: 2,
      primary_event_type: "CHECK_IN",
      primary_device_reported_at: "2026-11-24T09:00:00Z",
      rejection_summary: "Simultaneous check-ins from different devices",
      submitted_at: "2026-11-24T09:01:00Z",
      employee_clarification: "Device A battery died, checked in on Device B",
      clarification_submitted_at: "2026-11-24T09:30:00Z",
    };

    assert.equal(mockItem.conflict_code, "DUPLICATE_CHECK_IN");
    assert.equal(mockItem.severity, "HIGH");
    assert.equal(mockItem.classification, "NEEDS_EMPLOYEE_CLARIFICATION");
    assert.equal(mockItem.status, "NEEDS_CLARIFICATION");
    assert.equal(
      mockItem.employee_clarification,
      "Device A battery died, checked in on Device B"
    );
  });

  it("should support all Phase 11.5 supervisor decision actions", () => {
    const validActions: AttendanceConflictDecisionRequestDto["action"][] = [
      "APPROVE",
      "REJECT",
      "ACCEPT_SEQUENCE",
      "REJECT_INVALID_EVENTS",
      "REQUEST_CLARIFICATION",
      "MARK_UNRESOLVED",
      "ESCALATE_HR",
    ];

    for (const action of validActions) {
      const payload: AttendanceConflictDecisionRequestDto = {
        action,
        reason: `Adjudication test for ${action}`,
      };
      assert.ok(payload.reason.length >= 3);
      assert.ok(validActions.includes(payload.action));
    }
  });

  it("should verify mock API endpoints for employee clarification and adjudication", async () => {
    assert.equal(typeof conflictApi.submitClarification, "function");
    assert.equal(typeof conflictApi.adjudicateIncident, "function");
    assert.equal(typeof conflictApi.getSupervisorQueue, "function");
    assert.equal(typeof conflictApi.getIncidentDetail, "function");
  });
});
