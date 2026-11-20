/// Response DTO from POST /api/v1/attendance/offline-conflicts/submit.
class OfflineConflictIncidentModel {
  final String id;
  final String tenantId;
  final String employeeId;
  final String userId;
  final String bundleId;
  final String? sessionId;
  final String status;
  final int totalEventsCount;
  final String? rejectionSummary;
  final String? employeeNotes;
  final DateTime submittedAt;
  final String? decision;
  final String? decisionReason;
  final DateTime? decidedAt;
  final List<String> resolvedCorrectionEventIds;
  final bool idempotentReplay;

  OfflineConflictIncidentModel({
    required this.id,
    required this.tenantId,
    required this.employeeId,
    required this.userId,
    required this.bundleId,
    this.sessionId,
    required this.status,
    required this.totalEventsCount,
    this.rejectionSummary,
    this.employeeNotes,
    required this.submittedAt,
    this.decision,
    this.decisionReason,
    this.decidedAt,
    this.resolvedCorrectionEventIds = const [],
    this.idempotentReplay = false,
  });

  factory OfflineConflictIncidentModel.fromJson(Map<String, dynamic> json) {
    return OfflineConflictIncidentModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      employeeId: json['employee_id'] as String,
      userId: json['user_id'] as String,
      bundleId: json['bundle_id'] as String,
      sessionId: json['session_id'] as String?,
      status: json['status'] as String,
      totalEventsCount: (json['total_events_count'] as num).toInt(),
      rejectionSummary: json['rejection_summary'] as String?,
      employeeNotes: json['employee_notes'] as String?,
      submittedAt: DateTime.parse(json['submitted_at'] as String),
      decision: json['decision'] as String?,
      decisionReason: json['decision_reason'] as String?,
      decidedAt: json['decided_at'] != null
          ? DateTime.parse(json['decided_at'] as String)
          : null,
      resolvedCorrectionEventIds:
          (json['resolved_correction_event_ids'] as List?)
                  ?.map((e) => e.toString())
                  .toList() ??
              const [],
      idempotentReplay: json['idempotent_replay'] == true,
    );
  }
}
