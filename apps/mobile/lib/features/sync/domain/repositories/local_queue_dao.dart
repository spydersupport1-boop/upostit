import '../entities/local_queue_item.dart';
import '../entities/offline_sequence_conflict_bundle.dart';
import '../entities/sync_queue_summary.dart';
import '../entities/sync_status.dart';

/// Contract for durable local storage of offline attendance queue events.
abstract class LocalQueueDao {
  /// Inserts a newly recorded attendance punch into the offline queue.
  ///
  /// Atomically assigns a monotonic sequence number within the user's session.
  /// Throws [QueueCapacityExceededException] if the 500-pending-event threshold is reached.
  Future<LocalQueueItem> insertPendingEvent(LocalQueueItem item);

  /// Retrieves pending events in strict chronological FIFO order.
  /// Ordered by `sequence_number ASC, device_reported_at ASC`.
  Future<List<LocalQueueItem>> getPendingEventsFifo({
    required String tenantId,
    required String userId,
    int limit = 50,
  });

  /// Retrieves a specific queue record by local UUID.
  Future<LocalQueueItem?> getEventById(String localId);

  /// Retrieves a specific queue record by its unique server idempotency key.
  Future<LocalQueueItem?> getEventByIdempotencyKey(String idempotencyKey);

  /// Updates the synchronization status and server identifiers for an item.
  Future<void> updateSyncStatus({
    required String localId,
    required SyncStatus status,
    String? serverEventId,
    String? errorMessage,
    int? statusCode,
  });

  /// Marks an event as permanently rejected by server domain rules.
  Future<void> markPermanentlyRejected({
    required String localId,
    required String errorMessage,
    int? statusCode,
  });

  /// Quarantines all subsequent dependent events in the same active session
  /// when an earlier punch (e.g. CHECK_IN) fails permanently.
  Future<int> quarantineDependentEvents({
    required String tenantId,
    required String userId,
    required String conflictBundleId,
    required String fromLocalId,
  });

  /// Returns the current count of unresolved events (pending, syncing, and quarantined)
  /// that consume the local 500-event offline queue capacity.
  Future<int> getUnresolvedCount({
    required String tenantId,
    required String userId,
  });

  /// Returns the current count of pending/syncing events for the authenticated account.
  Future<int> getPendingCount({
    required String tenantId,
    required String userId,
  });

  /// Returns a statistical breakdown of offline queue records for the authenticated user.
  Future<SyncQueueSummary> getQueueSummary({
    required String tenantId,
    required String userId,
  });

  /// Retrieves historical events (synced and pending) for offline presence history UI.
  Future<List<LocalQueueItem>> getHistoryEvents({
    required String tenantId,
    required String userId,
    int limit = 50,
  });

  /// Prunes successfully synchronized records older than [age].
  /// Never deletes pending or rejected records.
  Future<int> deleteSyncedEventsOlderThan({required Duration age});

  /// Resets zombie items stranded in SYNCING state for longer than [timeout].
  Future<int> resetZombieSyncingItems({
    Duration timeout = const Duration(seconds: 120),
  });

  /// Extracts deterministic offline attendance conflict bundles for the user.
  /// Collects primary permanently rejected events and their dependent quarantined punches.
  Future<List<OfflineSequenceConflictBundle>> getConflictBundles({
    required String tenantId,
    required String userId,
  });

  /// Persists local metadata tracking conflict bundle submission and review status.
  Future<void> saveConflictBundleSubmission({
    required String bundleId,
    required String incidentId,
    required String status,
    String? decision,
    String? decisionReason,
    DateTime? submittedAt,
    DateTime? decidedAt,
    String? employeeNotes,
  });

  /// Retrieves local submission metadata for a bundle ID.
  Future<Map<String, dynamic>?> getConflictBundleSubmission(String bundleId);

  /// Updates all local events associated with a conflict bundle when resolved.
  Future<void> markConflictBundleResolved({
    required String bundleId,
    required SyncStatus status,
  });
}
