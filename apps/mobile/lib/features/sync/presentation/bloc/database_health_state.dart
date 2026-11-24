import 'package:equatable/equatable.dart';
import '../../data/services/database_recovery_coordinator.dart';
import '../../data/services/queue_retention_manager.dart';
import '../../data/services/storage_usage_monitor.dart';

abstract class DatabaseHealthState extends Equatable {
  const DatabaseHealthState();

  @override
  List<Object?> get props => [];
}

class DatabaseHealthInitial extends DatabaseHealthState {
  const DatabaseHealthInitial();
}

class DatabaseHealthChecking extends DatabaseHealthState {
  const DatabaseHealthChecking();
}

class DatabaseHealthLoaded extends DatabaseHealthState {
  final DatabaseRecoveryReport recoveryReport;
  final QueueHealthMetrics queueMetrics;
  final StorageUsageSnapshot storageSnapshot;

  const DatabaseHealthLoaded({
    required this.recoveryReport,
    required this.queueMetrics,
    required this.storageSnapshot,
  });

  @override
  List<Object?> get props => [recoveryReport, queueMetrics, storageSnapshot];
}

class DatabaseHealthActionInProgress extends DatabaseHealthState {
  final String actionDescription;

  const DatabaseHealthActionInProgress(this.actionDescription);

  @override
  List<Object?> get props => [actionDescription];
}

class DatabaseHealthActionSuccess extends DatabaseHealthState {
  final String successMessage;

  const DatabaseHealthActionSuccess(this.successMessage);

  @override
  List<Object?> get props => [successMessage];
}

class DatabaseHealthError extends DatabaseHealthState {
  final String errorMessage;

  const DatabaseHealthError(this.errorMessage);

  @override
  List<Object?> get props => [errorMessage];
}
