import 'package:flutter/foundation.dart';
import '../../../../core/errors/app_exception.dart';
import '../datasources/database_key_provider.dart';
import '../datasources/local_queue_database.dart';

/// Diagnostic status for encrypted local database health.
enum DatabaseHealthStatus {
  healthy,
  missingKey,
  corruptedKey,
  corruptedDatabase,
  rotationInterrupted,
  quarantined,
  needsReauthentication,
}

/// Comprehensive health and recovery report.
class DatabaseRecoveryReport {
  final DatabaseHealthStatus status;
  final String message;
  final int keyVersion;
  final String rotationStatus;
  final bool integrityPassed;
  final String? quarantinedFilePath;
  final DateTime timestamp;

  const DatabaseRecoveryReport({
    required this.status,
    required this.message,
    required this.keyVersion,
    required this.rotationStatus,
    required this.integrityPassed,
    this.quarantinedFilePath,
    required this.timestamp,
  });

  bool get isOperational => status == DatabaseHealthStatus.healthy;
}

/// Coordinates fail-closed recovery, health checks, and corruption handling
/// for encrypted local attendance databases.
class DatabaseRecoveryCoordinator {
  final LocalQueueDatabase _database;
  final DatabaseKeyProvider _keyProvider;

  DatabaseRecoveryCoordinator({
    required LocalQueueDatabase database,
    required DatabaseKeyProvider keyProvider,
  })  : _database = database,
        _keyProvider = keyProvider;

  /// Inspects database health, secure-storage key status, and structural integrity.
  Future<DatabaseRecoveryReport> assessHealth() async {
    final now = DateTime.now().toUtc();
    final provider = _keyProvider;
    final int keyVersion;
    final String rotationStatus;
    if (provider is DatabaseKeyLifecycleProvider) {
      keyVersion = await provider.getKeyVersion();
      rotationStatus = await provider.getRotationStatus();
    } else {
      keyVersion = 1;
      rotationStatus = 'IDLE';
    }

    // Check if key is available in secure storage
    final existingKey = await _keyProvider.getExistingKey();
    if (existingKey == null || existingKey.trim().isEmpty) {
      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.missingKey,
        message: 'Database key is missing from secure platform keystore/keychain.',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: false,
        timestamp: now,
      );
    }

    if (existingKey.trim().length != 64 ||
        !RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(existingKey.trim())) {
      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.corruptedKey,
        message: 'Database key in secure storage is malformed or invalid length.',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: false,
        timestamp: now,
      );
    }

    if (rotationStatus == 'IN_PROGRESS') {
      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.rotationInterrupted,
        message: 'A previous key rotation crashed mid-flight. Recovery required.',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: false,
        timestamp: now,
      );
    }

    // Attempt to open and verify integrity
    try {
      if (!_database.isOpen) {
        await _database.open();
      }
      final passed = await _database.verifyDatabaseIntegrity();
      if (!passed) {
        return DatabaseRecoveryReport(
          status: DatabaseHealthStatus.corruptedDatabase,
          message: 'Database opened, but failed PRAGMA integrity_check.',
          keyVersion: keyVersion,
          rotationStatus: rotationStatus,
          integrityPassed: false,
          timestamp: now,
        );
      }

      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.healthy,
        message: 'Encrypted local database is healthy, verified, and operational.',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: true,
        timestamp: now,
      );
    } on DatabaseEncryptionException catch (e) {
      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.corruptedDatabase,
        message: 'Database could not be decrypted or initialized: ${e.message}',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: false,
        timestamp: now,
      );
    } catch (e) {
      return DatabaseRecoveryReport(
        status: DatabaseHealthStatus.corruptedDatabase,
        message: 'Unexpected error assessing database health: $e',
        keyVersion: keyVersion,
        rotationStatus: rotationStatus,
        integrityPassed: false,
        timestamp: now,
      );
    }
  }

  /// Quarantines an unrecoverable database file by renaming it, purges invalid keys,
  /// and prepares the environment for safe reauthentication and re-registration.
  ///
  /// Enforces rule: NEVER silently delete or overwrite raw database evidence.
  Future<DatabaseRecoveryReport> quarantineAndPrepareFreshDatabase() async {
    final now = DateTime.now().toUtc();
    final quarantinedPath = await _database.quarantineCorruptedDatabase();
    await _keyProvider.clearKeyForTesting();

    debugPrint('DatabaseRecoveryCoordinator: Quarantined database to: $quarantinedPath');

    return DatabaseRecoveryReport(
      status: DatabaseHealthStatus.quarantined,
      message: 'Unreadable database preserved as backup. Device requires re-authentication.',
      keyVersion: 1,
      rotationStatus: 'IDLE',
      integrityPassed: false,
      quarantinedFilePath: quarantinedPath,
      timestamp: now,
    );
  }

  /// Executes controlled key rotation with error handling.
  Future<void> executeKeyRotation() async {
    await _database.rotateKey();
  }
}
