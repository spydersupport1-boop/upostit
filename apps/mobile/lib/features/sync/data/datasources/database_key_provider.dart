import 'dart:math';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/errors/app_exception.dart';

/// Contract for supplying cryptographically secure encryption keys for local databases.
abstract class DatabaseKeyProvider {
  /// Obtains the 256-bit encryption key for the local queue database.
  Future<String> getEncryptionKey({required bool databaseExists});

  /// Backward-compatible alias for first-time creation.
  Future<String> getOrCreateEncryptionKey();

  /// Retrieves the existing key if present; returns null otherwise.
  Future<String?> getExistingKey();

  /// Clears stored key material (strictly for testing).
  Future<void> clearKeyForTesting();
}

/// Extended contract for formal key lifecycle management, versioning, and rotation.
abstract class DatabaseKeyLifecycleProvider implements DatabaseKeyProvider {
  /// Returns current active key version (default: 1).
  Future<int> getKeyVersion();

  /// Returns current rotation status ('IDLE', 'IN_PROGRESS', 'FAILED').
  Future<String> getRotationStatus();

  /// Prepares a staging key for rotation and returns the new 256-bit hex key.
  Future<String> prepareRotationKey();

  /// Atomically commits rotated key into secure storage, updating version and resetting rotation status.
  Future<void> commitRotatedKey({required String newKey, required int newVersion});

  /// Aborts pending rotation and purges staging key material.
  Future<void> abortRotation();
}

/// Production implementation backed by platform hardware keyrings via [FlutterSecureStorage].
class FlutterSecureStorageDatabaseKeyProvider implements DatabaseKeyLifecycleProvider {
  final FlutterSecureStorage _storage;

  static const String keyStorageIdentifier = 'upostit_offline_db_key_v1';
  static const String keyVersionIdentifier = 'upostit_key_version';
  static const String rotationStatusIdentifier = 'upostit_key_rotation_status';
  static const String pendingKeyIdentifier = 'upostit_pending_key';
  static const String pendingVersionIdentifier = 'upostit_pending_version';

  FlutterSecureStorageDatabaseKeyProvider({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(
                encryptedSharedPreferences: true,
              ),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  @override
  Future<String> getEncryptionKey({required bool databaseExists}) async {
    final String? existingKey;
    final String? rotationStatus;
    try {
      existingKey = await _storage.read(key: keyStorageIdentifier);
      rotationStatus = await _storage.read(key: rotationStatusIdentifier);
    } catch (e, stackTrace) {
      throw DatabaseEncryptionException(
        'Inaccessible secure storage: failed to read database encryption key: $e',
        e,
        stackTrace,
      );
    }

    final trimmed = existingKey?.trim();

    // 1. Existing database recovery branch (FAIL-CLOSED)
    if (databaseExists) {
      // Check if an interrupted rotation left a pending key that might be active
      if (rotationStatus == 'IN_PROGRESS') {
        final pendingKey = (await _storage.read(key: pendingKeyIdentifier))?.trim();
        if (pendingKey != null &&
            pendingKey.length == 64 &&
            RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(pendingKey)) {
          return trimmed ?? pendingKey;
        }
      }

      if (trimmed == null || trimmed.isEmpty) {
        throw const DatabaseEncryptionException(
          'Encrypted database file exists on disk, but its encryption key is missing from secure storage. '
          'Refusing to generate a new key to prevent permanent data loss or silent file corruption.',
        );
      }
      if (trimmed.length != 64 ||
          !RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(trimmed)) {
        throw const DatabaseEncryptionException(
          'Encrypted database file exists on disk, but its encryption key in secure storage is malformed. '
          'Refusing to regenerate or overwrite the key to preserve encrypted attendance evidence.',
        );
      }
      return trimmed;
    }

    // 2. Genuinely new database initialization branch
    if (trimmed != null &&
        trimmed.length == 64 &&
        RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(trimmed)) {
      return trimmed;
    }

    try {
      final random = Random.secure();
      final bytes = List<int>.generate(32, (_) => random.nextInt(256));
      final hexKey =
          bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

      await _storage.write(key: keyStorageIdentifier, value: hexKey);
      await _storage.write(key: keyVersionIdentifier, value: '1');
      await _storage.write(key: rotationStatusIdentifier, value: 'IDLE');
      return hexKey;
    } catch (e, stackTrace) {
      throw DatabaseEncryptionException(
        'Failed to securely generate and persist new 256-bit database encryption key: $e',
        e,
        stackTrace,
      );
    }
  }

  @override
  Future<String> getOrCreateEncryptionKey() =>
      getEncryptionKey(databaseExists: false);

  @override
  Future<String?> getExistingKey() async {
    try {
      return await _storage.read(key: keyStorageIdentifier);
    } catch (e, stackTrace) {
      throw DatabaseEncryptionException(
        'Failed to read existing database key from secure storage: $e',
        e,
        stackTrace,
      );
    }
  }

  @override
  Future<int> getKeyVersion() async {
    try {
      final raw = await _storage.read(key: keyVersionIdentifier);
      return raw != null ? int.tryParse(raw) ?? 1 : 1;
    } catch (_) {
      return 1;
    }
  }

  @override
  Future<String> getRotationStatus() async {
    try {
      return (await _storage.read(key: rotationStatusIdentifier)) ?? 'IDLE';
    } catch (_) {
      return 'IDLE';
    }
  }

  @override
  Future<String> prepareRotationKey() async {
    try {
      final random = Random.secure();
      final bytes = List<int>.generate(32, (_) => random.nextInt(256));
      final hexKey =
          bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

      final currentVersion = await getKeyVersion();
      final nextVersion = currentVersion + 1;

      await _storage.write(key: rotationStatusIdentifier, value: 'IN_PROGRESS');
      await _storage.write(key: pendingKeyIdentifier, value: hexKey);
      await _storage.write(key: pendingVersionIdentifier, value: nextVersion.toString());

      return hexKey;
    } catch (e, stackTrace) {
      throw DatabaseEncryptionException(
        'Failed staging rotation key in secure storage: $e',
        e,
        stackTrace,
      );
    }
  }

  @override
  Future<void> commitRotatedKey({required String newKey, required int newVersion}) async {
    try {
      await _storage.write(key: keyStorageIdentifier, value: newKey);
      await _storage.write(key: keyVersionIdentifier, value: newVersion.toString());
      await _storage.write(key: rotationStatusIdentifier, value: 'IDLE');
      await _storage.delete(key: pendingKeyIdentifier);
      await _storage.delete(key: pendingVersionIdentifier);
    } catch (e, stackTrace) {
      throw DatabaseEncryptionException(
        'Failed committing rotated key to secure storage: $e',
        e,
        stackTrace,
      );
    }
  }

  @override
  Future<void> abortRotation() async {
    try {
      await _storage.write(key: rotationStatusIdentifier, value: 'IDLE');
      await _storage.delete(key: pendingKeyIdentifier);
      await _storage.delete(key: pendingVersionIdentifier);
    } catch (_) {}
  }

  @override
  Future<void> clearKeyForTesting() async {
    try {
      await _storage.delete(key: keyStorageIdentifier);
      await _storage.delete(key: keyVersionIdentifier);
      await _storage.delete(key: rotationStatusIdentifier);
      await _storage.delete(key: pendingKeyIdentifier);
      await _storage.delete(key: pendingVersionIdentifier);
    } catch (_) {}
  }
}
