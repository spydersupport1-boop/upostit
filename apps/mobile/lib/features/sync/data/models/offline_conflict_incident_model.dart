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
  final String? conflictCode;
  final String severity;
  final String classification;
  final String? employeeClarification;
  final DateTime? clarificationRequestedAt;
  final DateTime? clarificationSubmittedAt;
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
    this.conflictCode,
    this.severity = 'MEDIUM',
    this.classification = 'NEEDS_MANAGER_REVIEW',
    this.employeeClarification,
    this.clarificationRequestedAt,
    this.clarificationSubmittedAt,
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
      conflictCode: json['conflict_code'] as String?,
      severity: (json['severity'] as String?) ?? 'MEDIUM',
      classification: (json['classification'] as String?) ?? 'NEEDS_MANAGER_REVIEW',
      employeeClarification: json['employee_clarification'] as String?,
      clarificationRequestedAt: json['clarification_requested_at'] != null
          ? DateTime.parse(json['clarification_requested_at'] as String)
          : null,
      clarificationSubmittedAt: json['clarification_submitted_at'] != null
          ? DateTime.parse(json['clarification_submitted_at'] as String)
          : null,
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
