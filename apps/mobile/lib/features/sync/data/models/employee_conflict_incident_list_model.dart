/// Individual conflict incident summary from GET /api/v1/attendance/offline-conflicts/my.
class EmployeeConflictIncidentItemModel {
  final String id;
  final String bundleId;
  final String? sessionId;
  final String status;
  final int totalEventsCount;
  final String primaryEventType;
  final DateTime primaryEventTimestamp;
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
  final int resolvedEventsCount;

  EmployeeConflictIncidentItemModel({
    required this.id,
    required this.bundleId,
    this.sessionId,
    required this.status,
    required this.totalEventsCount,
    required this.primaryEventType,
    required this.primaryEventTimestamp,
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
    this.resolvedEventsCount = 0,
  });

  factory EmployeeConflictIncidentItemModel.fromJson(
      Map<String, dynamic> json) {
    return EmployeeConflictIncidentItemModel(
      id: json['id'] as String,
      bundleId: json['bundle_id'] as String,
      sessionId: json['session_id'] as String?,
      status: json['status'] as String,
      totalEventsCount: (json['total_events_count'] as num).toInt(),
      primaryEventType: json['primary_event_type'] as String,
      primaryEventTimestamp:
          DateTime.parse(json['primary_event_timestamp'] as String),
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
      resolvedEventsCount:
          (json['resolved_events_count'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Paginated list response from GET /api/v1/attendance/offline-conflicts/my.
class EmployeeConflictIncidentListModel {
  final List<EmployeeConflictIncidentItemModel> items;
  final int total;
  final int limit;
  final String? cursor;
  final bool hasMore;

  EmployeeConflictIncidentListModel({
    required this.items,
    required this.total,
    required this.limit,
    this.cursor,
    this.hasMore = false,
  });

  factory EmployeeConflictIncidentListModel.fromJson(
      Map<String, dynamic> json) {
    return EmployeeConflictIncidentListModel(
      items: (json['items'] as List?)
              ?.map((e) => EmployeeConflictIncidentItemModel.fromJson(
                  e as Map<String, dynamic>))
              .toList() ??
          const [],
      total: (json['total'] as num).toInt(),
      limit: (json['limit'] as num).toInt(),
      cursor: json['cursor'] as String?,
      hasMore: json['has_more'] == true,
    );
  }
}
