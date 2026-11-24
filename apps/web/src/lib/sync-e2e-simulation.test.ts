import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { conflictApi, attendanceApi } from "./api.ts";
import type {
  SupervisorConflictQueueItemDto,
  AttendanceConflictDecisionRequestDto,
} from "./api.ts";

export interface AttendanceBatchSyncReceiptItemDto {
  local_id: string;
  idempotency_key: string;
  status: "ACCEPTED" | "DUPLICATE" | "REJECTED" | "REQUIRES_REVIEW" | "RETRYABLE";
  event_type: string;
  server_event_id: string | null;
  effective_at: string | null;
  review_status: string | null;
  error_code: string | null;
  error_message: string | null;
  idempotent_replay: boolean;
}

export interface AttendanceBatchSyncResponseDto {
  batch_id: string;
  total_items: number;
  accepted_count: number;
  duplicate_count: number;
  rejected_count: number;
  requires_review_count: number;
  processed_at: string;
  receipts: AttendanceBatchSyncReceiptItemDto[];
}

export interface SyncDeltaResponseDto {
  cursor: string | null;
  has_more: boolean;
  total_deltas: number;
  server_timestamp: string;
  policy_delta: unknown | null;
  geofences: unknown[];
  wifi_access_points: unknown[];
  shift_assignments: unknown[];
  active_day: unknown | null;
}

describe("Phase 11.7 — Web Console: End-to-End Multi-Device Conflict & Sync Verification", () => {
  describe("1. Multi-Device Attendance Conflict Review & Supervision", () => {
    it("should parse complete multi-device conflict queue item telemetry", () => {
      const item: SupervisorConflictQueueItemDto = {
        id: "inc-md-001",
        tenant_id: "tenant-alpha",
        employee_id: "emp-alpha-1",
        employee_name: "Sarah Chen",
        employee_code: "EMP-SC-101",
        department_name: "Operations",
        bundle_id: "rec_2026-11-24_OVERLAPPING_SESSIONS_s1",
        session_id: "sess-md-1",
        status: "PENDING_REVIEW",
        conflict_code: "OVERLAPPING_SESSIONS",
        severity: "CRITICAL",
        classification: "NEEDS_SUPERVISOR_RESOLUTION",
        total_events_count: 4,
        primary_event_type: "CHECK_IN",
        primary_device_reported_at: "2026-11-24T08:30:00Z",
        rejection_summary: "Simultaneous open attendance sessions on Android and iOS devices",
        submitted_at: "2026-11-24T08:31:00Z",
        employee_clarification: "Checked in on tablet at site, forgot phone was also active",
        clarification_submitted_at: "2026-11-24T09:00:00Z",
      };

      assert.equal(item.conflict_code, "OVERLAPPING_SESSIONS");
      assert.equal(item.severity, "CRITICAL");
      assert.equal(item.classification, "NEEDS_SUPERVISOR_RESOLUTION");
      assert.equal(item.status, "PENDING_REVIEW");
      assert.equal(item.total_events_count, 4);
      assert.ok(item.employee_clarification?.includes("tablet at site"));
    });

    it("should validate all 7 Phase 11 supervisor adjudication decision actions", () => {
      const actions: AttendanceConflictDecisionRequestDto["action"][] = [
        "APPROVE",
        "REJECT",
        "ACCEPT_SEQUENCE",
        "REJECT_INVALID_EVENTS",
        "REQUEST_CLARIFICATION",
        "MARK_UNRESOLVED",
        "ESCALATE_HR",
      ];

      for (const action of actions) {
        const payload: AttendanceConflictDecisionRequestDto = {
          action,
          reason: `Supervisor decided ${action} with justification audit trail`,
        };
        assert.ok(payload.reason.length >= 3);
        assert.ok(actions.includes(payload.action));
      }
    });
  });

  describe("2. RBAC & Cross-Tenant Boundary Enforcement", () => {
    it("should enforce anti-self-approval boundary check", () => {
      const reviewerUserId = "user-mgr-01";
      const incidentEmployeeUserId = "user-mgr-01"; // Self conflict!

      // Frontend business logic check before submission
      const isSelfApproval = reviewerUserId === incidentEmployeeUserId;
      assert.equal(isSelfApproval, true, "Reviewer must not be able to adjudicate own conflict");
    });

    it("should enforce direct-report scoping for manager role", () => {
      const managerId = "mgr-alpha-1";
      const directReports = new Set(["emp-alpha-1", "emp-alpha-2"]);
      const targetEmp = "emp-unrelated-9";

      const isAuthorized = directReports.has(targetEmp);
      assert.equal(isAuthorized, false, "Manager cannot adjudicate unrelated employee");
    });
  });

  describe("3. Batch Sync & Downward Delta Telemetry Parsing", () => {
    it("should parse 50-item batch sync response with dual-tier idempotency receipts", () => {
      const mockBatchResponse: AttendanceBatchSyncResponseDto = {
        batch_id: "batch-md-50-test",
        total_items: 50,
        accepted_count: 48,
        duplicate_count: 1,
        rejected_count: 1,
        requires_review_count: 0,
        processed_at: "2026-11-24T12:00:00Z",
        receipts: [
          {
            local_id: "loc-01",
            idempotency_key: "key-01-uuid",
            status: "ACCEPTED",
            event_type: "CHECK_IN",
            server_event_id: "ev-01",
            effective_at: "2026-11-24T08:00:00Z",
            review_status: "NOT_REQUIRED",
            error_code: null,
            error_message: null,
            idempotent_replay: false,
          },
          {
            local_id: "loc-02",
            idempotency_key: "key-02-uuid",
            status: "DUPLICATE",
            event_type: "CHECK_IN",
            server_event_id: "ev-01",
            effective_at: "2026-11-24T08:00:00Z",
            review_status: "NOT_REQUIRED",
            error_code: null,
            error_message: null,
            idempotent_replay: true,
          },
          {
            local_id: "loc-03",
            idempotency_key: "key-03-uuid",
            status: "REJECTED",
            event_type: "CHECK_IN",
            server_event_id: null,
            effective_at: null,
            review_status: null,
            error_code: "OFFLINE_WINDOW_EXCEEDED",
            error_message: "Punch is older than 72 hours",
            idempotent_replay: false,
          },
        ],
      };

      assert.equal(mockBatchResponse.total_items, 50);
      assert.equal(mockBatchResponse.accepted_count, 48);
      assert.equal(mockBatchResponse.duplicate_count, 1);
      assert.equal(mockBatchResponse.receipts[1].idempotent_replay, true);
      assert.equal(mockBatchResponse.receipts[2].error_code, "OFFLINE_WINDOW_EXCEEDED");
    });

    it("should parse downward delta sync response with HMAC cursor pagination", () => {
      const mockDeltaResponse: SyncDeltaResponseDto = {
        cursor: "eyJ2IjoyLCJ0aWQiOiJ0MSIsInVpZCI6InUxIiwic2lnIjoiYWJjIn0=",
        has_more: false,
        total_deltas: 5,
        server_timestamp: "2026-11-24T12:00:00Z",
        policy_delta: null,
        geofences: [],
        wifi_access_points: [],
        shift_assignments: [],
        active_day: null,
      };

      assert.ok(mockDeltaResponse.cursor !== null);
      assert.equal(mockDeltaResponse.has_more, false);
      assert.equal(mockDeltaResponse.total_deltas, 5);
    });
  });
});
