import 'package:equatable/equatable.dart';
import 'local_queue_item.dart';

/// Review status of a local conflict bundle.
enum ConflictSubmissionStatus {
  notSubmitted,
  pendingReview,
  approved,
  rejected;

  String toDisplayString() {
    switch (this) {
      case ConflictSubmissionStatus.notSubmitted:
        return 'Not Submitted';
      case ConflictSubmissionStatus.pendingReview:
        return 'Pending Review';
      case ConflictSubmissionStatus.approved:
        return 'Approved';
      case ConflictSubmissionStatus.rejected:
        return 'Rejected';
    }
  }

  static ConflictSubmissionStatus fromBackendString(String? status) {
    switch (status?.toUpperCase()) {
      case 'PENDING_REVIEW':
        return ConflictSubmissionStatus.pendingReview;
      case 'APPROVED':
        return ConflictSubmissionStatus.approved;
      case 'REJECTED':
        return ConflictSubmissionStatus.rejected;
      default:
        return ConflictSubmissionStatus.notSubmitted;
    }
  }
}

/// Represents a packaged multi-event attendance session conflict for supervisor review.
class OfflineSequenceConflictBundle extends Equatable {
  final String bundleId;
  final String? sessionId;
  final String tenantId;
  final String userId;
  final LocalQueueItem primaryRejectedEvent;
  final List<LocalQueueItem> dependentEvents;
  final String? employeeNotes;
  final ConflictSubmissionStatus submissionStatus;
  final String? incidentId;
  final String? supervisorDecision;
  final String? supervisorDecisionReason;
  final DateTime? submittedAt;
  final DateTime? decidedAt;

  const OfflineSequenceConflictBundle({
    required this.bundleId,
    this.sessionId,
    required this.tenantId,
    required this.userId,
    required this.primaryRejectedEvent,
    this.dependentEvents = const [],
    this.employeeNotes,
    this.submissionStatus = ConflictSubmissionStatus.notSubmitted,
    this.incidentId,
    this.supervisorDecision,
    this.supervisorDecisionReason,
    this.submittedAt,
    this.decidedAt,
  });

  int get totalEventsCount => 1 + dependentEvents.length;

  bool get isSubmitted =>
      submissionStatus != ConflictSubmissionStatus.notSubmitted;

  bool get isPending =>
      submissionStatus == ConflictSubmissionStatus.pendingReview;

  bool get isApproved => submissionStatus == ConflictSubmissionStatus.approved;

  bool get isRejected => submissionStatus == ConflictSubmissionStatus.rejected;

  OfflineSequenceConflictBundle copyWith({
    String? bundleId,
    String? sessionId,
    String? tenantId,
    String? userId,
    LocalQueueItem? primaryRejectedEvent,
    List<LocalQueueItem>? dependentEvents,
    String? employeeNotes,
    ConflictSubmissionStatus? submissionStatus,
    String? incidentId,
    String? supervisorDecision,
    String? supervisorDecisionReason,
    DateTime? submittedAt,
    DateTime? decidedAt,
  }) {
    return OfflineSequenceConflictBundle(
      bundleId: bundleId ?? this.bundleId,
      sessionId: sessionId ?? this.sessionId,
      tenantId: tenantId ?? this.tenantId,
      userId: userId ?? this.userId,
      primaryRejectedEvent: primaryRejectedEvent ?? this.primaryRejectedEvent,
      dependentEvents: dependentEvents ?? this.dependentEvents,
      employeeNotes: employeeNotes ?? this.employeeNotes,
      submissionStatus: submissionStatus ?? this.submissionStatus,
      incidentId: incidentId ?? this.incidentId,
      supervisorDecision: supervisorDecision ?? this.supervisorDecision,
      supervisorDecisionReason:
          supervisorDecisionReason ?? this.supervisorDecisionReason,
      submittedAt: submittedAt ?? this.submittedAt,
      decidedAt: decidedAt ?? this.decidedAt,
    );
  }

  @override
  List<Object?> get props => [
        bundleId,
        sessionId,
        tenantId,
        userId,
        primaryRejectedEvent,
        dependentEvents,
        employeeNotes,
        submissionStatus,
        incidentId,
        supervisorDecision,
        supervisorDecisionReason,
        submittedAt,
        decidedAt,
      ];
}
