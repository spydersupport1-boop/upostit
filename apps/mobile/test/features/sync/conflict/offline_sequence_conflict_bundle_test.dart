import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/models/employee_conflict_incident_list_model.dart';
import 'package:mobile/features/sync/data/models/offline_conflict_bundle_submit_request_model.dart';
import 'package:mobile/features/sync/data/models/offline_conflict_incident_model.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/offline_sequence_conflict_bundle.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';

void main() {
  const tTenantId = 'tenant-corp-1';
  const tUserId = 'user-emp-1';
  const tSessionId = 'session-uuid-123';
  const tBundleId = 'bundle-uuid-456';

  final tPrimaryRejected = LocalQueueItem(
    localId: 'loc-1',
    idempotencyKey: 'idemp-1',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkIn,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 8, 0, 0),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1000000,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 1,
    syncStatus: SyncStatus.rejectedPermanent,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Timestamp beyond maximum allowed offline drift window',
    lastErrorStatusCode: 422,
    createdAt: DateTime.utc(2026, 11, 10, 8, 0, 0),
    updatedAt: DateTime.utc(2026, 11, 10, 8, 5, 0),
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_P1',
  );

  final tDependentQuarantined = LocalQueueItem(
    localId: 'loc-2',
    idempotencyKey: 'idemp-2',
    sessionId: tSessionId,
    tenantId: tTenantId,
    employeeId: 'emp-1',
    userId: tUserId,
    eventType: AttendanceEventType.checkOut,
    deviceReportedAt: DateTime.utc(2026, 11, 10, 17, 0, 0),
    timezoneOffsetMinutes: 0,
    monotonicBootTimeMs: 1032400,
    bootSessionId: 'boot-1',
    appliedPolicyVersion: 1,
    appliedPolicyMode: 'NONE',
    sequenceNumber: 2,
    syncStatus: SyncStatus.quarantinedDependentFailure,
    conflictBundleId: tBundleId,
    lastErrorMessage: 'Quarantined due to earlier rejection in session',
    createdAt: DateTime.utc(2026, 11, 10, 17, 0, 0),
    updatedAt: DateTime.utc(2026, 11, 10, 17, 5, 0),
    encryptedPayloadBlob: 'ENCRYPTED_BLOB_D2',
  );

  group('OfflineSequenceConflictBundle Entity Tests', () {
    test(
        'constructs bundle with primary rejected and dependent quarantined events',
        () {
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        dependentEvents: [tDependentQuarantined],
      );

      expect(bundle.bundleId, tBundleId);
      expect(bundle.sessionId, tSessionId);
      expect(bundle.totalEventsCount, 2);
      expect(bundle.submissionStatus, ConflictSubmissionStatus.notSubmitted);
      expect(bundle.isSubmitted, false);
      expect(bundle.isPending, false);
      expect(bundle.isApproved, false);
      expect(bundle.isRejected, false);
    });

    test('state transition getters reflect submissionStatus correctly', () {
      final pendingBundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        submissionStatus: ConflictSubmissionStatus.pendingReview,
      );
      expect(pendingBundle.isSubmitted, true);
      expect(pendingBundle.isPending, true);
      expect(pendingBundle.isApproved, false);

      final approvedBundle = pendingBundle.copyWith(
        submissionStatus: ConflictSubmissionStatus.approved,
        supervisorDecision: 'APPROVE',
      );
      expect(approvedBundle.isApproved, true);
      expect(approvedBundle.isPending, false);

      final rejectedBundle = pendingBundle.copyWith(
        submissionStatus: ConflictSubmissionStatus.rejected,
        supervisorDecision: 'REJECT',
        supervisorDecisionReason:
            'Unverifiable manual offline punch outside shift',
      );
      expect(rejectedBundle.isRejected, true);
      expect(rejectedBundle.isPending, false);
      expect(rejectedBundle.supervisorDecisionReason, contains('Unverifiable'));
    });
  });

  group('OfflineConflictBundleSubmitRequestModel Serialization Tests', () {
    test(
        'serializes bundle and dependent events to backend specification schema',
        () {
      final bundle = OfflineSequenceConflictBundle(
        bundleId: tBundleId,
        sessionId: tSessionId,
        tenantId: tTenantId,
        userId: tUserId,
        primaryRejectedEvent: tPrimaryRejected,
        dependentEvents: [tDependentQuarantined],
      );

      final requestModel = OfflineConflictBundleSubmitRequestModel.fromBundle(
        bundle,
        notes: 'Device clock jumped after battery replacement',
      );

      final json = requestModel.toJson();

      expect(json['bundle_id'], tBundleId);
      expect(json['session_id'], tSessionId);
      expect(json['employee_notes'],
          'Device clock jumped after battery replacement');

      final primary = json['primary_rejected_event'] as Map<String, dynamic>;
      expect(primary['local_id'], 'loc-1');
      expect(primary['idempotency_key'], 'idemp-1');
      expect(primary['event_type'], 'CHECK_IN');
      expect(primary['device_reported_at'], '2026-11-10T08:00:00.000Z');
      expect(primary['server_rejection_reason'],
          'Timestamp beyond maximum allowed offline drift window');
      expect(primary['server_rejection_code'], 422);

      final dependents = json['dependent_events'] as List<dynamic>;
      expect(dependents.length, 1);
      final dep = dependents.first as Map<String, dynamic>;
      expect(dep['local_id'], 'loc-2');
      expect(dep['idempotency_key'], 'idemp-2');
      expect(dep['event_type'], 'CHECK_OUT');
      expect(dep['device_reported_at'], '2026-11-10T17:00:00.000Z');
    });
  });

  group('Backend Response DTO Deserialization Tests', () {
    test('deserializes OfflineConflictIncidentModel from POST /submit response',
        () {
      final json = {
        'id': 'inc-999',
        'tenant_id': tTenantId,
        'employee_id': 'emp-1',
        'user_id': tUserId,
        'bundle_id': tBundleId,
        'session_id': tSessionId,
        'status': 'PENDING_REVIEW',
        'total_events_count': 2,
        'rejection_summary': 'Clock drift check failed',
        'employee_notes': 'Please review battery failure',
        'submitted_at': '2026-11-10T09:00:00.000Z',
        'decision': null,
        'decision_reason': null,
        'decided_at': null,
        'resolved_correction_event_ids': [],
        'idempotent_replay': false,
      };

      final model = OfflineConflictIncidentModel.fromJson(json);

      expect(model.id, 'inc-999');
      expect(model.bundleId, tBundleId);
      expect(model.status, 'PENDING_REVIEW');
      expect(model.totalEventsCount, 2);
      expect(model.idempotentReplay, false);
      expect(model.employeeNotes, 'Please review battery failure');
    });

    test('deserializes EmployeeConflictIncidentListModel from GET /my response',
        () {
      final json = {
        'items': [
          {
            'id': 'inc-999',
            'bundle_id': tBundleId,
            'session_id': tSessionId,
            'status': 'APPROVED',
            'total_events_count': 2,
            'primary_event_type': 'CHECK_IN',
            'primary_event_timestamp': '2026-11-10T08:00:00.000Z',
            'rejection_summary': 'Clock drift check failed',
            'employee_notes': 'Battery failure',
            'submitted_at': '2026-11-10T09:00:00.000Z',
            'decision': 'APPROVE',
            'decision_reason': 'Verified on-site by supervisor',
            'decided_at': '2026-11-10T11:00:00.000Z',
            'resolved_events_count': 2,
          }
        ],
        'total': 1,
        'limit': 50,
        'offset': 0,
      };

      final listModel = EmployeeConflictIncidentListModel.fromJson(json);

      expect(listModel.total, 1);
      expect(listModel.items.length, 1);
      final item = listModel.items.first;
      expect(item.id, 'inc-999');
      expect(item.bundleId, tBundleId);
      expect(item.status, 'APPROVED');
      expect(item.decision, 'APPROVE');
      expect(item.decisionReason, 'Verified on-site by supervisor');
      expect(item.resolvedEventsCount, 2);
    });
  });
}
