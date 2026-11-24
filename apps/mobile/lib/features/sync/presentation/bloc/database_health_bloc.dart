import 'package:flutter_bloc/flutter_bloc.dart';
import '../../data/services/database_recovery_coordinator.dart';
import '../../data/services/queue_retention_manager.dart';
import '../../data/services/storage_usage_monitor.dart';
import 'database_health_event.dart';
import 'database_health_state.dart';

class DatabaseHealthBloc
    extends Bloc<DatabaseHealthEvent, DatabaseHealthState> {
  final DatabaseRecoveryCoordinator _recoveryCoordinator;
  final QueueRetentionManager _retentionManager;
  final StorageUsageMonitor _storageMonitor;

  DatabaseHealthBloc({
    required DatabaseRecoveryCoordinator recoveryCoordinator,
    required QueueRetentionManager retentionManager,
    required StorageUsageMonitor storageMonitor,
  })  : _recoveryCoordinator = recoveryCoordinator,
        _retentionManager = retentionManager,
        _storageMonitor = storageMonitor,
        super(const DatabaseHealthInitial()) {
    on<DatabaseHealthCheckRequested>(_onCheckRequested);
    on<DatabaseHealthRotateKeyRequested>(_onRotateKeyRequested);
    on<DatabaseHealthQuarantineRequested>(_onQuarantineRequested);
    on<DatabaseHealthEvictionRequested>(_onEvictionRequested);
  }

  Future<void> _onCheckRequested(
    DatabaseHealthCheckRequested event,
    Emitter<DatabaseHealthState> emit,
  ) async {
    emit(const DatabaseHealthChecking());
    try {
      final report = await _recoveryCoordinator.assessHealth();
      final metrics = await _retentionManager.getQueueHealth();
      final storage = await _storageMonitor.getStorageUsage();

      emit(DatabaseHealthLoaded(
        recoveryReport: report,
        queueMetrics: metrics,
        storageSnapshot: storage,
      ));
    } catch (e) {
      emit(DatabaseHealthError('Failed to inspect database health: $e'));
    }
  }

  Future<void> _onRotateKeyRequested(
    DatabaseHealthRotateKeyRequested event,
    Emitter<DatabaseHealthState> emit,
  ) async {
    emit(const DatabaseHealthActionInProgress('Rotating database encryption key...'));
    try {
      await _recoveryCoordinator.executeKeyRotation();
      emit(const DatabaseHealthActionSuccess('Key rotated successfully.'));
      add(const DatabaseHealthCheckRequested());
    } catch (e) {
      emit(DatabaseHealthError('Key rotation failed: $e'));
    }
  }

  Future<void> _onQuarantineRequested(
    DatabaseHealthQuarantineRequested event,
    Emitter<DatabaseHealthState> emit,
  ) async {
    emit(const DatabaseHealthActionInProgress('Quarantining corrupted database...'));
    try {
      final report =
          await _recoveryCoordinator.quarantineAndPrepareFreshDatabase();
      emit(DatabaseHealthActionSuccess(
        'Database safely quarantined to ${report.quarantinedFilePath ?? 'backup'}.',
      ));
      add(const DatabaseHealthCheckRequested());
    } catch (e) {
      emit(DatabaseHealthError('Failed quarantining database: $e'));
    }
  }

  Future<void> _onEvictionRequested(
    DatabaseHealthEvictionRequested event,
    Emitter<DatabaseHealthState> emit,
  ) async {
    emit(const DatabaseHealthActionInProgress('Evicting aged synchronized punches...'));
    try {
      final result = await _retentionManager.executeEviction(
        retentionWindow:
            event.retentionWindow ?? QueueRetentionManager.defaultRetentionDuration,
      );
      emit(DatabaseHealthActionSuccess(
        'Safely evicted ${result.evictedCount} acknowledged events. '
        'Preserved ${result.preservedPendingCount} pending items.',
      ));
      add(const DatabaseHealthCheckRequested());
    } catch (e) {
      emit(DatabaseHealthError('Eviction failed: $e'));
    }
  }
}
