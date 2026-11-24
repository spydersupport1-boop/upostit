import 'package:flutter/foundation.dart';
import '../../domain/entities/sync_status.dart';
import '../datasources/local_queue_database.dart';

/// Structured outcome of a queue eviction execution.
class QueueEvictionResult {
  final int evictedCount;
  final int preservedPendingCount;
  final int preservedReviewCount;
  final int preservedRejectedCount;
  final int remainingSyncedCount;
  final DateTime executedAt;

  const QueueEvictionResult({
    required this.evictedCount,
    required this.preservedPendingCount,
    required this.preservedReviewCount,
    required this.preservedRejectedCount,
    required this.remainingSyncedCount,
    required this.executedAt,
  });
}

/// Diagnostic health summary of the local offline queue.
class QueueHealthMetrics {
  final int pendingSyncCount;
  final int syncingCount;
  final int quarantinedFailureCount;
  final int flaggedReviewCount;
  final int rejectedPermanentCount;
  final int syncedCount;
  final int totalCount;
  final DateTime? oldestPendingTimestamp;
  final bool isCapacityWarningActive;

  const QueueHealthMetrics({
    required this.pendingSyncCount,
    required this.syncingCount,
    required this.quarantinedFailureCount,
    required this.flaggedReviewCount,
    required this.rejectedPermanentCount,
    required this.syncedCount,
    required this.totalCount,
    this.oldestPendingTimestamp,
    required this.isCapacityWarningActive,
  });

  int get unacknowledgedCount =>
      pendingSyncCount + syncingCount + quarantinedFailureCount;
}

/// Enforces the mandatory offline queue retention and eviction policies:
/// 1. NEVER evict unsynchronized attendance events.
/// 2. NEVER evict unresolved conflict evidence.
/// 3. NEVER delete records requiring supervisor review.
/// 4. Only remove locally retained records when backend acknowledged safe receipt
///    ('SYNCED') and retention conditions (default 30 days) are satisfied.
class QueueRetentionManager {
  static const Duration defaultRetentionDuration = Duration(days: 30);
  static const int capacityWarningThreshold = 400; // 80% of 500 max capacity

  final LocalQueueDatabase _database;

  QueueRetentionManager({required LocalQueueDatabase database})
      : _database = database;

  /// Inspects the breakdown of all queue items by lifecycle status.
  Future<QueueHealthMetrics> getQueueHealth() async {
    final db = _database.database;
    final rows = await db.rawQuery('''
      SELECT sync_status, COUNT(*) AS count
      FROM ${LocalQueueDatabase.queueTable}
      GROUP BY sync_status
    ''');

    int pending = 0;
    int syncing = 0;
    int quarantined = 0;
    int flagged = 0;
    int rejected = 0;
    int synced = 0;

    for (final r in rows) {
      final statusStr = r['sync_status'] as String? ?? '';
      final count = (r['count'] as int?) ?? 0;
      if (statusStr == SyncStatus.pendingSync.toDbString()) {
        pending = count;
      } else if (statusStr == SyncStatus.syncing.toDbString()) {
        syncing = count;
      } else if (statusStr ==
          SyncStatus.quarantinedDependentFailure.toDbString()) {
        quarantined = count;
      } else if (statusStr == SyncStatus.flaggedPendingReview.toDbString()) {
        flagged = count;
      } else if (statusStr == SyncStatus.rejectedPermanent.toDbString()) {
        rejected = count;
      } else if (statusStr == SyncStatus.synced.toDbString()) {
        synced = count;
      }
    }

    final total = pending + syncing + quarantined + flagged + rejected + synced;
    final unacknowledged = pending + syncing + quarantined;

    // Query oldest pending timestamp
    DateTime? oldestPending;
    final oldestRows = await db.rawQuery('''
      SELECT device_reported_at
      FROM ${LocalQueueDatabase.queueTable}
      WHERE sync_status IN (?, ?, ?)
      ORDER BY device_reported_at ASC
      LIMIT 1
    ''', [
      SyncStatus.pendingSync.toDbString(),
      SyncStatus.syncing.toDbString(),
      SyncStatus.quarantinedDependentFailure.toDbString(),
    ]);

    if (oldestRows.isNotEmpty) {
      final raw = oldestRows.first['device_reported_at'] as String?;
      if (raw != null) {
        oldestPending = DateTime.tryParse(raw);
      }
    }

    return QueueHealthMetrics(
      pendingSyncCount: pending,
      syncingCount: syncing,
      quarantinedFailureCount: quarantined,
      flaggedReviewCount: flagged,
      rejectedPermanentCount: rejected,
      syncedCount: synced,
      totalCount: total,
      oldestPendingTimestamp: oldestPending,
      isCapacityWarningActive: unacknowledged >= capacityWarningThreshold,
    );
  }

  /// Safely evicts only acknowledged ('SYNCED') attendance events older than [retentionWindow].
  ///
  /// Guarantees that unsynchronized, pending review, and rejected conflict records
  /// are strictly preserved.
  Future<QueueEvictionResult> executeEviction({
    Duration retentionWindow = defaultRetentionDuration,
  }) async {
    final db = _database.database;
    final now = DateTime.now().toUtc();
    final threshold = now.subtract(retentionWindow).toIso8601String();

    // 1. Delete ONLY SYNCED items older than retention threshold
    final evictedCount = await db.delete(
      LocalQueueDatabase.queueTable,
      where: 'sync_status = ? AND updated_at < ?',
      whereArgs: [SyncStatus.synced.toDbString(), threshold],
    );

    // 2. Query remaining breakdown
    final health = await getQueueHealth();

    debugPrint(
      'QueueRetentionManager: Evicted $evictedCount acknowledged punches older than $retentionWindow. '
      'Preserved: ${health.unacknowledgedCount} unacknowledged, ${health.flaggedReviewCount} review, '
      '${health.rejectedPermanentCount} rejected, ${health.syncedCount} recent synced.',
    );

    return QueueEvictionResult(
      evictedCount: evictedCount,
      preservedPendingCount: health.unacknowledgedCount,
      preservedReviewCount: health.flaggedReviewCount,
      preservedRejectedCount: health.rejectedPermanentCount,
      remainingSyncedCount: health.syncedCount,
      executedAt: now,
    );
  }
}
