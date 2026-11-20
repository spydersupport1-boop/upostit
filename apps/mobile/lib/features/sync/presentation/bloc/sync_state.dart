import 'package:equatable/equatable.dart';
import '../../domain/entities/local_queue_item.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';
import '../../domain/entities/sync_queue_summary.dart';
import '../../domain/entities/sync_result.dart';

/// Represents the UI state of the offline synchronization engine.
class SyncState extends Equatable {
  final bool isConnected;
  final bool isSyncing;
  final bool isLoading;
  final SyncQueueSummary summary;
  final List<LocalQueueItem> events;
  final List<OfflineSequenceConflictBundle> conflictBundles;
  final bool isSubmittingConflict;
  final String? submittingBundleId;
  final SyncResult? lastResult;
  final String? errorMessage;
  final String? successMessage;
  final String? conflictActionError;
  final String? conflictActionSuccess;

  const SyncState({
    this.isConnected = true,
    this.isSyncing = false,
    this.isLoading = false,
    this.summary = const SyncQueueSummary(),
    this.events = const [],
    this.conflictBundles = const [],
    this.isSubmittingConflict = false,
    this.submittingBundleId,
    this.lastResult,
    this.errorMessage,
    this.successMessage,
    this.conflictActionError,
    this.conflictActionSuccess,
  });

  int get pendingCount => summary.pendingCount;
  int get syncingCount => summary.syncingCount;
  int get syncedCount => summary.syncedCount;
  int get permanentlyRejectedCount => summary.permanentlyRejectedCount;
  int get quarantinedCount => summary.quarantinedCount;
  int get flaggedCount => summary.flaggedCount;
  int get unresolvedCount => summary.unresolvedCount;
  int get totalCount => summary.totalCount;
  DateTime? get lastSyncedAt => summary.lastSyncedAt;

  SyncState copyWith({
    bool? isConnected,
    bool? isSyncing,
    bool? isLoading,
    SyncQueueSummary? summary,
    List<LocalQueueItem>? events,
    List<OfflineSequenceConflictBundle>? conflictBundles,
    bool? isSubmittingConflict,
    String? submittingBundleId,
    SyncResult? lastResult,
    String? errorMessage,
    String? successMessage,
    String? conflictActionError,
    String? conflictActionSuccess,
    bool clearError = false,
    bool clearSuccess = false,
    bool clearConflictActionError = false,
    bool clearConflictActionSuccess = false,
    bool clearSubmittingBundleId = false,
  }) {
    return SyncState(
      isConnected: isConnected ?? this.isConnected,
      isSyncing: isSyncing ?? this.isSyncing,
      isLoading: isLoading ?? this.isLoading,
      summary: summary ?? this.summary,
      events: events ?? this.events,
      conflictBundles: conflictBundles ?? this.conflictBundles,
      isSubmittingConflict: isSubmittingConflict ?? this.isSubmittingConflict,
      submittingBundleId: clearSubmittingBundleId
          ? null
          : (submittingBundleId ?? this.submittingBundleId),
      lastResult: lastResult ?? this.lastResult,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      successMessage:
          clearSuccess ? null : (successMessage ?? this.successMessage),
      conflictActionError: clearConflictActionError
          ? null
          : (conflictActionError ?? this.conflictActionError),
      conflictActionSuccess: clearConflictActionSuccess
          ? null
          : (conflictActionSuccess ?? this.conflictActionSuccess),
    );
  }

  @override
  List<Object?> get props => [
        isConnected,
        isSyncing,
        isLoading,
        summary,
        events,
        conflictBundles,
        isSubmittingConflict,
        submittingBundleId,
        lastResult,
        errorMessage,
        successMessage,
        conflictActionError,
        conflictActionSuccess,
      ];
}
