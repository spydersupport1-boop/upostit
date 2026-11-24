import 'package:equatable/equatable.dart';
import '../../data/services/unified_sync_coordinator.dart';
import '../../domain/entities/sync_result.dart';

abstract class SyncEvent extends Equatable {
  const SyncEvent();

  @override
  List<Object?> get props => [];
}

/// Dispatched to refresh local queue statistics and history records.
class SyncSummaryRequested extends SyncEvent {
  final String tenantId;
  final String userId;

  const SyncSummaryRequested({
    required this.tenantId,
    required this.userId,
  });

  @override
  List<Object?> get props => [tenantId, userId];
}

/// Dispatched by the user tapping "Sync Now".
class SyncNowRequested extends SyncEvent {
  final String tenantId;
  final String userId;

  const SyncNowRequested({
    required this.tenantId,
    required this.userId,
  });

  @override
  List<Object?> get props => [tenantId, userId];
}

/// Dispatched when the network interface or reachability state transitions.
class SyncConnectivityChanged extends SyncEvent {
  final bool isConnected;

  const SyncConnectivityChanged({required this.isConnected});

  @override
  List<Object?> get props => [isConnected];
}

/// Dispatched when a background or manual sync execution finishes.
class SyncCompletedResultReceived extends SyncEvent {
  final SyncResult result;
  final String? tenantId;
  final String? userId;

  const SyncCompletedResultReceived(
    this.result, {
    this.tenantId,
    this.userId,
  });

  @override
  List<Object?> get props => [result, tenantId, userId];
}

/// Dispatched to load detected conflict bundles for the authenticated user.
class SyncConflictBundlesRequested extends SyncEvent {
  final String tenantId;
  final String userId;

  const SyncConflictBundlesRequested({
    required this.tenantId,
    required this.userId,
  });

  @override
  List<Object?> get props => [tenantId, userId];
}

/// Dispatched by the user tapping "Submit for Supervisor Review" on a conflict bundle.
class SyncSubmitConflictBundleRequested extends SyncEvent {
  final String bundleId;
  final String? employeeNotes;

  const SyncSubmitConflictBundleRequested({
    required this.bundleId,
    this.employeeNotes,
  });

  @override
  List<Object?> get props => [bundleId, employeeNotes];
}

/// Dispatched by the employee submitting clarification notes on an incident in NEEDS_CLARIFICATION status.
class SyncSubmitConflictClarificationRequested extends SyncEvent {
  final String incidentId;
  final String clarificationNotes;

  const SyncSubmitConflictClarificationRequested({
    required this.incidentId,
    required this.clarificationNotes,
  });

  @override
  List<Object?> get props => [incidentId, clarificationNotes];
}

/// Dispatched to refresh conflict review status from GET /offline-conflicts/my.
class SyncRefreshConflictStatusRequested extends SyncEvent {
  final String? tenantId;
  final String? userId;

  const SyncRefreshConflictStatusRequested({
    this.tenantId,
    this.userId,
  });

  @override
  List<Object?> get props => [tenantId, userId];
}

/// Dispatched when the unified coordinator reports operational progress.
class SyncUnifiedProgressReceived extends SyncEvent {
  final UnifiedSyncProgress progress;

  const SyncUnifiedProgressReceived(this.progress);

  @override
  List<Object?> get props => [progress];
}
