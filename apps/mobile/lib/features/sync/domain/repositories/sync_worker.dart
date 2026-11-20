import 'dart:async';
import '../entities/sync_result.dart';

/// Contract for the strict FIFO attendance synchronization worker.
abstract class SyncWorker {
  /// Stream emitting results of completed synchronization runs.
  Stream<SyncResult> get syncResults;

  /// Returns whether synchronization is actively executing for [tenantId] and [userId].
  bool isSyncing(String tenantId, String userId);

  /// Synchronizes all pending/eligible offline punches for [tenantId] and [userId] in strict FIFO sequence.
  ///
  /// Guarantees that only ONE worker processes the queue for an account at a time.
  /// If a run is already active, returns immediately with an active result.
  Future<SyncResult> synchronizeQueue({
    required String tenantId,
    required String userId,
  });

  /// Starts listening to network connectivity events and automatically triggers
  /// synchronization when connectivity returns.
  void startAutoSync({
    required String tenantId,
    required String userId,
  });

  /// Stops automatic synchronization triggers and disposes background listeners.
  void stopAutoSync();

  /// Triggers a synchronization attempt when the application returns to the foreground.
  Future<SyncResult?> onAppForegrounded();

  /// Disposes the worker, timers, and controllers.
  void dispose();
}
