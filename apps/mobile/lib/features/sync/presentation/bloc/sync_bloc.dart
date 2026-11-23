import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/errors/app_exception.dart';
import '../../../attendance/data/datasources/attendance_remote_data_source.dart';
import '../../data/models/offline_conflict_bundle_submit_request_model.dart';
import '../../data/services/unified_sync_coordinator.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';
import '../../domain/entities/sync_queue_summary.dart';
import '../../domain/entities/sync_result.dart';
import '../../domain/entities/sync_status.dart';
import '../../domain/repositories/local_queue_dao.dart';
import '../../domain/repositories/network_connectivity_service.dart';
import '../../domain/repositories/sync_worker.dart';
import 'sync_event.dart';
import 'sync_state.dart';

/// BLoC orchestrating offline attendance queue synchronization, metrics, and connectivity UI state.
class SyncBloc extends Bloc<SyncEvent, SyncState> {
  final LocalQueueDao _localQueueDao;
  final SyncWorker _syncWorker;
  final NetworkConnectivityService? _connectivityService;
  final AttendanceRemoteDataSource? _remoteDataSource;
  final UnifiedSyncCoordinator? _unifiedCoordinator;

  StreamSubscription<bool>? _connectivitySub;
  StreamSubscription<SyncResult>? _syncResultSub;
  StreamSubscription<UnifiedSyncProgress>? _unifiedProgressSub;

  String? _activeTenantId;
  String? _activeUserId;

  SyncBloc({
    required LocalQueueDao localQueueDao,
    required SyncWorker syncWorker,
    NetworkConnectivityService? connectivityService,
    AttendanceRemoteDataSource? remoteDataSource,
    UnifiedSyncCoordinator? unifiedCoordinator,
  })  : _localQueueDao = localQueueDao,
        _syncWorker = syncWorker,
        _connectivityService = connectivityService,
        _remoteDataSource = remoteDataSource,
        _unifiedCoordinator = unifiedCoordinator,
        super(const SyncState()) {
    on<SyncSummaryRequested>(_onSummaryRequested);
    on<SyncNowRequested>(_onSyncNowRequested);
    on<SyncConnectivityChanged>(_onConnectivityChanged);
    on<SyncCompletedResultReceived>(_onSyncCompletedResultReceived);
    on<SyncConflictBundlesRequested>(_onConflictBundlesRequested);
    on<SyncSubmitConflictBundleRequested>(_onSubmitConflictBundleRequested);
    on<SyncRefreshConflictStatusRequested>(_onRefreshConflictStatusRequested);
    on<SyncUnifiedProgressReceived>(_onUnifiedProgressReceived);

    // 1. Initial connectivity check
    final connectivity = _connectivityService;
    if (connectivity != null) {
      connectivity.isConnected().then((connected) {
        if (!isClosed) {
          try {
            add(SyncConnectivityChanged(isConnected: connected));
          } catch (_) {}
        }
      });

      // 2. Listen to network restoration stream
      _connectivitySub = connectivity.onConnectivityRestored.listen((restored) {
        if (!isClosed) {
          try {
            add(SyncConnectivityChanged(isConnected: restored));
          } catch (_) {}
        }
      });
    }

    // 3. Listen to synchronization worker results
    _syncResultSub = _syncWorker.syncResults.listen((result) {
      if (!isClosed) {
        try {
          add(SyncCompletedResultReceived(
            result,
            tenantId: _activeTenantId,
            userId: _activeUserId,
          ));
        } catch (_) {}
      }
    });

    // 4. Listen to unified coordinator progress stream if provided
    final coordinator = _unifiedCoordinator;
    if (coordinator != null) {
      _unifiedProgressSub = coordinator.progressStream.listen((progress) {
        if (!isClosed) {
          try {
            add(SyncUnifiedProgressReceived(progress));
          } catch (_) {}
        }
      });
    }
  }

  Future<void> _onSummaryRequested(
    SyncSummaryRequested event,
    Emitter<SyncState> emit,
  ) async {
    _activeTenantId = event.tenantId;
    _activeUserId = event.userId;

    emit(state.copyWith(isLoading: true, clearError: true));

    try {
      final summary = await _localQueueDao.getQueueSummary(
        tenantId: event.tenantId,
        userId: event.userId,
      );

      final events = await _localQueueDao.getHistoryEvents(
        tenantId: event.tenantId,
        userId: event.userId,
        limit: 100,
      );

      List<OfflineSequenceConflictBundle> conflictBundles = const [];
      try {
        conflictBundles = await _localQueueDao.getConflictBundles(
          tenantId: event.tenantId,
          userId: event.userId,
        );
      } catch (_) {}

      final isWorkerSyncing =
          _syncWorker.isSyncing(event.tenantId, event.userId);

      emit(state.copyWith(
        isLoading: false,
        isSyncing: isWorkerSyncing,
        summary: summary,
        events: events,
        conflictBundles: conflictBundles,
        clearError: true,
      ));
    } catch (e) {
      // Do NOT overwrite summary with zero; report actual database error
      emit(state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to read offline queue: ${e.toString()}',
      ));
    }
  }

  Future<void> _onSyncNowRequested(
    SyncNowRequested event,
    Emitter<SyncState> emit,
  ) async {
    if (state.isSyncing ||
        _syncWorker.isSyncing(event.tenantId, event.userId)) {
      return;
    }

    _activeTenantId = event.tenantId;
    _activeUserId = event.userId;

    // Verify network reachability before triggering sync
    if (_connectivityService != null) {
      final isConnected = await _connectivityService.isConnected();
      if (!isConnected) {
        emit(state.copyWith(
          isConnected: false,
          errorMessage: 'Cannot synchronize: No internet connection.',
          clearSuccess: true,
        ));
        return;
      }
    }

    emit(state.copyWith(
      isSyncing: true,
      clearError: true,
      clearSuccess: true,
    ));

    final coordinator = _unifiedCoordinator;
    final SyncResult result;
    if (coordinator != null) {
      final unifiedRes = await coordinator.synchronizeAll(
        tenantId: event.tenantId,
        userId: event.userId,
      );
      result = unifiedRes.upwardResult ??
          SyncResult(
            isCompleted: unifiedRes.isCompleted,
            errorMessage: unifiedRes.errorMessage,
            isAuthRequired: unifiedRes.isAuthRequired,
          );
    } else {
      result = await _syncWorker.synchronizeQueue(
        tenantId: event.tenantId,
        userId: event.userId,
      );
    }

    // Refresh queue summary and history after sync run completes
    try {
      final summary = await _localQueueDao.getQueueSummary(
        tenantId: event.tenantId,
        userId: event.userId,
      );
      final events = await _localQueueDao.getHistoryEvents(
        tenantId: event.tenantId,
        userId: event.userId,
        limit: 100,
      );

      String? successMessage;
      if (result.syncedCount > 0) {
        successMessage =
            'Successfully synchronized ${result.syncedCount} attendance event${result.syncedCount > 1 ? 's' : ''}.';
      }

      emit(state.copyWith(
        isSyncing: false,
        summary: summary,
        events: events,
        lastResult: result,
        successMessage: successMessage,
        errorMessage: result.errorMessage,
      ));
    } catch (e) {
      emit(state.copyWith(
        isSyncing: false,
        lastResult: result,
        errorMessage: 'Sync completed, but failed to refresh status: $e',
      ));
    }
  }

  void _onConnectivityChanged(
    SyncConnectivityChanged event,
    Emitter<SyncState> emit,
  ) {
    emit(state.copyWith(isConnected: event.isConnected));

    // If connectivity restored and we have an active session, refresh summary
    if (event.isConnected && _activeTenantId != null && _activeUserId != null) {
      add(SyncSummaryRequested(
        tenantId: _activeTenantId!,
        userId: _activeUserId!,
      ));
    }
  }

  Future<void> _onSyncCompletedResultReceived(
    SyncCompletedResultReceived event,
    Emitter<SyncState> emit,
  ) async {
    final tenantId = event.tenantId ?? _activeTenantId;
    final userId = event.userId ?? _activeUserId;

    if (tenantId != null && userId != null) {
      try {
        final summary = await _localQueueDao.getQueueSummary(
          tenantId: tenantId,
          userId: userId,
        );
        final events = await _localQueueDao.getHistoryEvents(
          tenantId: tenantId,
          userId: userId,
          limit: 100,
        );
        List<OfflineSequenceConflictBundle> conflictBundles = const [];
        try {
          conflictBundles = await _localQueueDao.getConflictBundles(
            tenantId: tenantId,
            userId: userId,
          );
        } catch (_) {}

        String? successMessage;
        if (event.result.syncedCount > 0) {
          successMessage =
              'Synchronized ${event.result.syncedCount} punch${event.result.syncedCount > 1 ? 'es' : ''}.';
        }

        emit(state.copyWith(
          isSyncing: false,
          summary: summary,
          events: events,
          conflictBundles: conflictBundles,
          lastResult: event.result,
          successMessage: successMessage,
          errorMessage: event.result.errorMessage,
        ));
        return;
      } catch (_) {}
    }

    emit(state.copyWith(
      isSyncing: false,
      lastResult: event.result,
    ));
  }

  Future<void> _onConflictBundlesRequested(
    SyncConflictBundlesRequested event,
    Emitter<SyncState> emit,
  ) async {
    _activeTenantId = event.tenantId;
    _activeUserId = event.userId;
    try {
      final bundles = await _localQueueDao.getConflictBundles(
        tenantId: event.tenantId,
        userId: event.userId,
      );
      emit(state.copyWith(
        conflictBundles: bundles,
        clearError: true,
      ));
    } catch (e) {
      emit(state.copyWith(
        conflictActionError: 'Failed to load conflict bundles: $e',
      ));
    }
  }

  Future<void> _onSubmitConflictBundleRequested(
    SyncSubmitConflictBundleRequested event,
    Emitter<SyncState> emit,
  ) async {
    final remoteDs = _remoteDataSource;
    if (remoteDs == null) {
      emit(state.copyWith(
        conflictActionError: 'Remote submission not configured on device.',
      ));
      return;
    }

    emit(state.copyWith(
      isSubmittingConflict: true,
      submittingBundleId: event.bundleId,
      clearConflictActionError: true,
      clearConflictActionSuccess: true,
    ));

    try {
      OfflineSequenceConflictBundle? targetBundle;
      for (final b in state.conflictBundles) {
        if (b.bundleId == event.bundleId) {
          targetBundle = b;
          break;
        }
      }
      if (targetBundle == null &&
          _activeTenantId != null &&
          _activeUserId != null) {
        final bundles = await _localQueueDao.getConflictBundles(
          tenantId: _activeTenantId!,
          userId: _activeUserId!,
        );
        for (final b in bundles) {
          if (b.bundleId == event.bundleId) {
            targetBundle = b;
            break;
          }
        }
      }

      if (targetBundle == null) {
        emit(state.copyWith(
          isSubmittingConflict: false,
          clearSubmittingBundleId: true,
          conflictActionError: 'Conflict bundle not found.',
        ));
        return;
      }

      final request = OfflineConflictBundleSubmitRequestModel.fromBundle(
        targetBundle,
        notes: event.employeeNotes,
      );

      final incident = await remoteDs.submitConflictBundle(request);

      await _localQueueDao.saveConflictBundleSubmission(
        bundleId: targetBundle.bundleId,
        incidentId: incident.id,
        status: incident.status,
        decision: incident.decision,
        decisionReason: incident.decisionReason,
        submittedAt: incident.submittedAt,
        decidedAt: incident.decidedAt,
        employeeNotes: incident.employeeNotes ?? event.employeeNotes,
      );

      if (incident.status.toUpperCase() == 'APPROVED') {
        await _localQueueDao.markConflictBundleResolved(
          bundleId: targetBundle.bundleId,
          status: SyncStatus.synced,
        );
      }

      List<OfflineSequenceConflictBundle> updatedBundles =
          state.conflictBundles;
      SyncQueueSummary? updatedSummary = state.summary;
      if (_activeTenantId != null && _activeUserId != null) {
        updatedBundles = await _localQueueDao.getConflictBundles(
          tenantId: _activeTenantId!,
          userId: _activeUserId!,
        );
        updatedSummary = await _localQueueDao.getQueueSummary(
          tenantId: _activeTenantId!,
          userId: _activeUserId!,
        );
      }

      emit(state.copyWith(
        isSubmittingConflict: false,
        clearSubmittingBundleId: true,
        conflictBundles: updatedBundles,
        summary: updatedSummary,
        conflictActionSuccess:
            'Conflict bundle submitted successfully for supervisor review.',
      ));
    } on ServerException catch (se) {
      emit(state.copyWith(
        isSubmittingConflict: false,
        clearSubmittingBundleId: true,
        conflictActionError: se.message,
      ));
    } on NetworkException catch (ne) {
      emit(state.copyWith(
        isSubmittingConflict: false,
        clearSubmittingBundleId: true,
        conflictActionError: 'Network error submitting conflict: ${ne.message}',
      ));
    } catch (e) {
      emit(state.copyWith(
        isSubmittingConflict: false,
        clearSubmittingBundleId: true,
        conflictActionError: 'Submission failed: $e',
      ));
    }
  }

  Future<void> _onRefreshConflictStatusRequested(
    SyncRefreshConflictStatusRequested event,
    Emitter<SyncState> emit,
  ) async {
    final remoteDs = _remoteDataSource;
    if (remoteDs == null) return;

    try {
      final listModel = await remoteDs.getMyConflictIncidents(limit: 50);

      for (final inc in listModel.items) {
        final bundleId = inc.bundleId;
        await _localQueueDao.saveConflictBundleSubmission(
          bundleId: bundleId,
          incidentId: inc.id,
          status: inc.status,
          decision: inc.decision,
          decisionReason: inc.decisionReason,
          submittedAt: inc.submittedAt,
          decidedAt: inc.decidedAt,
          employeeNotes: inc.employeeNotes,
        );

        if (inc.status.toUpperCase() == 'APPROVED') {
          await _localQueueDao.markConflictBundleResolved(
            bundleId: bundleId,
            status: SyncStatus.synced,
          );
        }
      }

      final tenantId = event.tenantId ?? _activeTenantId;
      final userId = event.userId ?? _activeUserId;
      if (tenantId != null && userId != null) {
        final updatedBundles = await _localQueueDao.getConflictBundles(
          tenantId: tenantId,
          userId: userId,
        );
        final updatedSummary = await _localQueueDao.getQueueSummary(
          tenantId: tenantId,
          userId: userId,
        );
        emit(state.copyWith(
          conflictBundles: updatedBundles,
          summary: updatedSummary,
          conflictActionSuccess: 'Conflict status updated from server.',
        ));
      }
    } catch (e) {
      emit(state.copyWith(
        conflictActionError: 'Failed to refresh conflict status: $e',
      ));
    }
  }

  void _onUnifiedProgressReceived(
    SyncUnifiedProgressReceived event,
    Emitter<SyncState> emit,
  ) {
    final p = event.progress;
    final phase = _mapUnifiedPhase(p.phase);
    emit(state.copyWith(
      phase: phase,
      isSyncing: phase == SyncOperationalPhase.uploadingAttendance ||
          phase == SyncOperationalPhase.downloadingReferenceData ||
          phase == SyncOperationalPhase.applyingLocalUpdates ||
          phase == SyncOperationalPhase.checkingConnectivity,
      currentOperation: p.message,
      lastSuccessfulUpload: p.lastSuccessfulUpload ?? state.lastSuccessfulUpload,
      lastSuccessfulDownload:
          p.lastSuccessfulDownload ?? state.lastSuccessfulDownload,
      retryStatus: p.retryAfterSeconds != null
          ? 'Next retry in ${p.retryAfterSeconds}s'
          : null,
      isAuthRequired: phase == SyncOperationalPhase.authenticationRequired,
      hasConflictRequiresReview:
          phase == SyncOperationalPhase.conflictRequiresReview,
      isFatalStorageError: phase == SyncOperationalPhase.fatalLocalStorageError,
    ));
  }

  SyncOperationalPhase _mapUnifiedPhase(UnifiedSyncPhase p) {
    switch (p) {
      case UnifiedSyncPhase.idle:
        return SyncOperationalPhase.idle;
      case UnifiedSyncPhase.checkingConnectivity:
        return SyncOperationalPhase.checkingConnectivity;
      case UnifiedSyncPhase.uploadingAttendance:
        return SyncOperationalPhase.uploadingAttendance;
      case UnifiedSyncPhase.downloadingReferenceData:
        return SyncOperationalPhase.downloadingReferenceData;
      case UnifiedSyncPhase.applyingLocalUpdates:
        return SyncOperationalPhase.applyingLocalUpdates;
      case UnifiedSyncPhase.waitingForRetry:
        return SyncOperationalPhase.waitingForRetry;
      case UnifiedSyncPhase.partiallySynchronized:
        return SyncOperationalPhase.partiallySynchronized;
      case UnifiedSyncPhase.fullySynchronized:
        return SyncOperationalPhase.fullySynchronized;
      case UnifiedSyncPhase.authenticationRequired:
        return SyncOperationalPhase.authenticationRequired;
      case UnifiedSyncPhase.conflictRequiresReview:
        return SyncOperationalPhase.conflictRequiresReview;
      case UnifiedSyncPhase.fatalLocalStorageError:
        return SyncOperationalPhase.fatalLocalStorageError;
    }
  }

  @override
  Future<void> close() {
    _connectivitySub?.cancel();
    _syncResultSub?.cancel();
    _unifiedProgressSub?.cancel();
    return super.close();
  }
}
