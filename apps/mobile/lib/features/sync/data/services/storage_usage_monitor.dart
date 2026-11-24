import 'dart:io';
import 'package:sqflite_sqlcipher/sqflite.dart';
import '../datasources/local_queue_database.dart';
import 'queue_retention_manager.dart';

/// Detailed storage usage snapshot.
class StorageUsageSnapshot {
  final int databaseSizeBytes;
  final int walSizeBytes;
  final int totalSizeBytes;
  final int totalQueueRecords;
  final int unacknowledgedRecords;
  final bool isThresholdExceeded;
  final DateTime measuredAt;

  const StorageUsageSnapshot({
    required this.databaseSizeBytes,
    required this.walSizeBytes,
    required this.totalSizeBytes,
    required this.totalQueueRecords,
    required this.unacknowledgedRecords,
    required this.isThresholdExceeded,
    required this.measuredAt,
  });

  double get totalSizeMegabytes => totalSizeBytes / (1024 * 1024);
}

/// Monitors offline database file sizes on the filesystem and checks storage threshold limits.
class StorageUsageMonitor {
  static const int defaultSizeWarningBytes = 50 * 1024 * 1024; // 50 MB

  final LocalQueueDatabase _database;
  final QueueRetentionManager _retentionManager;
  final DatabaseFactory? _factory;
  final String? _customPath;

  /// Exposes underlying database instance for diagnostics.
  LocalQueueDatabase get database => _database;

  StorageUsageMonitor({
    required LocalQueueDatabase database,
    required QueueRetentionManager retentionManager,
    DatabaseFactory? factory,
    String? customPath,
  })  : _database = database,
        _retentionManager = retentionManager,
        _factory = factory,
        _customPath = customPath;

  /// Inspects storage footprint on disk and queue metrics.
  Future<StorageUsageSnapshot> getStorageUsage() async {
    final now = DateTime.now().toUtc();
    final String basePath;

    final customPath = _customPath;
    if (customPath != null) {
      basePath = customPath;
    } else {
      final factory = _factory;
      final String dbDir = factory != null
          ? await factory.getDatabasesPath()
          : await getDatabasesPath();
      basePath = '$dbDir/${LocalQueueDatabase.databaseName}';
    }

    int dbSize = 0;
    int walSize = 0;

    if (basePath != inMemoryDatabasePath) {
      try {
        final dbFile = File(basePath);
        if (await dbFile.exists()) {
          dbSize = await dbFile.length();
        }

        final walFile = File('$basePath-wal');
        if (await walFile.exists()) {
          walSize = await walFile.length();
        }
      } catch (_) {}
    }

    final totalSize = dbSize + walSize;
    final health = await _retentionManager.getQueueHealth();

    final isExceeded = totalSize >= defaultSizeWarningBytes ||
        health.isCapacityWarningActive;

    return StorageUsageSnapshot(
      databaseSizeBytes: dbSize,
      walSizeBytes: walSize,
      totalSizeBytes: totalSize,
      totalQueueRecords: health.totalCount,
      unacknowledgedRecords: health.unacknowledgedCount,
      isThresholdExceeded: isExceeded,
      measuredAt: now,
    );
  }
}
