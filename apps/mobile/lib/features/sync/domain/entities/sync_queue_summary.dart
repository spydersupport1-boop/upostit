import 'package:equatable/equatable.dart';

/// Aggregated statistical summary of offline attendance records for an authenticated user.
class SyncQueueSummary extends Equatable {
  final int pendingCount;
  final int syncingCount;
  final int syncedCount;
  final int permanentlyRejectedCount;
  final int quarantinedCount;
  final int flaggedCount;
  final DateTime? lastSyncedAt;

  /// Total count of unresolved events consuming the offline queue threshold (pending + syncing + quarantined).
  int get unresolvedCount => pendingCount + syncingCount + quarantinedCount;

  /// Total count of all records stored locally across all statuses for this account.
  int get totalCount =>
      pendingCount +
      syncingCount +
      syncedCount +
      permanentlyRejectedCount +
      quarantinedCount +
      flaggedCount;

  const SyncQueueSummary({
    this.pendingCount = 0,
    this.syncingCount = 0,
    this.syncedCount = 0,
    this.permanentlyRejectedCount = 0,
    this.quarantinedCount = 0,
    this.flaggedCount = 0,
    this.lastSyncedAt,
  });

  @override
  List<Object?> get props => [
        pendingCount,
        syncingCount,
        syncedCount,
        permanentlyRejectedCount,
        quarantinedCount,
        flaggedCount,
        lastSyncedAt,
      ];
}
