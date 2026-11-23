import 'package:equatable/equatable.dart';
import '../../domain/entities/local_queue_item.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';
import '../../domain/entities/sync_queue_summary.dart';
import '../../domain/entities/sync_result.dart';

/// Operational phases of the sync engine matching Phase 11.4 BLoC architecture.
enum SyncOperationalPhase {
  idle,
  checkingConnectivity,
  uploadingAttendance,
  downloadingReferenceData,
  applyingLocalUpdates,
  waitingForRetry,
  partiallySynchronized,
  fullySynchronized,
  authenticationRequired,
  conflictRequiresReview,
  fatalLocalStorageError,
}

/// Represents the UI state of the offline synchronization engine.
class SyncState extends Equatable {
  final SyncOperationalPhase phase;
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
  final DateTime? lastSuccessfulUpload;
  final DateTime? lastSuccessfulDownload;
  final String? currentOperation;
  final String? retryStatus;
  final String? lastSyncError;
  final bool isAuthRequired;
  final bool isFatalStorageError;
  final bool hasConflictRequiresReview;

  const SyncState({
    this.phase = SyncOperationalPhase.idle,
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
    this.lastSuccessfulUpload,
    this.lastSuccessfulDownload,
    this.currentOperation,
    this.retryStatus,
    this.lastSyncError,
    this.isAuthRequired = false,
    this.isFatalStorageError = false,
    this.hasConflictRequiresReview = false,
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
    SyncOperationalPhase? phase,
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
    DateTime? lastSuccessfulUpload,
    DateTime? lastSuccessfulDownload,
    String? currentOperation,
    String? retryStatus,
    String? lastSyncError,
    bool? isAuthRequired,
    bool? isFatalStorageError,
    bool? hasConflictRequiresReview,
    bool clearError = false,
    bool clearSuccess = false,
    bool clearConflictActionError = false,
    bool clearConflictActionSuccess = false,
    bool clearSubmittingBundleId = false,
    bool clearOperation = false,
  }) {
    return SyncState(
      phase: phase ?? this.phase,
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
      lastSuccessfulUpload: lastSuccessfulUpload ?? this.lastSuccessfulUpload,
      lastSuccessfulDownload:
          lastSuccessfulDownload ?? this.lastSuccessfulDownload,
      currentOperation: clearOperation
          ? null
          : (currentOperation ?? this.currentOperation),
      retryStatus: retryStatus ?? this.retryStatus,
      lastSyncError: lastSyncError ?? this.lastSyncError,
      isAuthRequired: isAuthRequired ?? this.isAuthRequired,
      isFatalStorageError: isFatalStorageError ?? this.isFatalStorageError,
      hasConflictRequiresReview:
          hasConflictRequiresReview ?? this.hasConflictRequiresReview,
    );
  }

  @override
  List<Object?> get props => [
        phase,
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
        lastSuccessfulUpload,
        lastSuccessfulDownload,
        currentOperation,
        retryStatus,
        lastSyncError,
        isAuthRequired,
        isFatalStorageError,
        hasConflictRequiresReview,
      ];
}
