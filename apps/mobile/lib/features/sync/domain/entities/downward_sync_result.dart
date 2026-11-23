/// Result entity representing the status and metrics of a downward synchronization cycle.
class DownwardSyncResult {
  final bool isSuccess;
  final String syncType; // FULL, DELTA, OFFLINE
  final int itemsSynced;
  final bool isOffline;
  final String? errorMessage;
  final DateTime completedAt;

  const DownwardSyncResult({
    required this.isSuccess,
    required this.syncType,
    required this.itemsSynced,
    this.isOffline = false,
    this.errorMessage,
    required this.completedAt,
  });

  factory DownwardSyncResult.success({
    required String syncType,
    required int itemsSynced,
  }) {
    return DownwardSyncResult(
      isSuccess: true,
      syncType: syncType,
      itemsSynced: itemsSynced,
      completedAt: DateTime.now().toUtc(),
    );
  }

  factory DownwardSyncResult.offline({int cachedItems = 0}) {
    return DownwardSyncResult(
      isSuccess: true,
      syncType: 'OFFLINE',
      itemsSynced: cachedItems,
      isOffline: true,
      completedAt: DateTime.now().toUtc(),
    );
  }

  factory DownwardSyncResult.failure(String error) {
    return DownwardSyncResult(
      isSuccess: false,
      syncType: 'UNKNOWN',
      itemsSynced: 0,
      errorMessage: error,
      completedAt: DateTime.now().toUtc(),
    );
  }
}

