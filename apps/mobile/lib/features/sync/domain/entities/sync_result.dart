import 'package:equatable/equatable.dart';

/// Summary of a synchronization execution run.
class SyncResult extends Equatable {
  final int syncedCount;
  final int permanentlyRejectedCount;
  final int quarantinedCount;
  final int retryableFailureCount;
  final bool isCompleted;
  final bool isAuthRequired;
  final String? errorMessage;
  final int? retryAfterSeconds;

  const SyncResult({
    this.syncedCount = 0,
    this.permanentlyRejectedCount = 0,
    this.quarantinedCount = 0,
    this.retryableFailureCount = 0,
    this.isCompleted = true,
    this.isAuthRequired = false,
    this.errorMessage,
    this.retryAfterSeconds,
  });

  bool get hasErrors =>
      permanentlyRejectedCount > 0 ||
      retryableFailureCount > 0 ||
      errorMessage != null;

  SyncResult copyWith({
    int? syncedCount,
    int? permanentlyRejectedCount,
    int? quarantinedCount,
    int? retryableFailureCount,
    bool? isCompleted,
    bool? isAuthRequired,
    String? errorMessage,
    int? retryAfterSeconds,
  }) {
    return SyncResult(
      syncedCount: syncedCount ?? this.syncedCount,
      permanentlyRejectedCount:
          permanentlyRejectedCount ?? this.permanentlyRejectedCount,
      quarantinedCount: quarantinedCount ?? this.quarantinedCount,
      retryableFailureCount:
          retryableFailureCount ?? this.retryableFailureCount,
      isCompleted: isCompleted ?? this.isCompleted,
      isAuthRequired: isAuthRequired ?? this.isAuthRequired,
      errorMessage: errorMessage ?? this.errorMessage,
      retryAfterSeconds: retryAfterSeconds ?? this.retryAfterSeconds,
    );
  }

  @override
  List<Object?> get props => [
        syncedCount,
        permanentlyRejectedCount,
        quarantinedCount,
        retryableFailureCount,
        isCompleted,
        isAuthRequired,
        errorMessage,
        retryAfterSeconds,
      ];
}
