import 'dart:math';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/errors/app_exception.dart';

/// Contract for supplying cryptographically secure encryption keys for local databases.
abstract class DatabaseKeyProvider {
  /// Obtains the 256-bit encryption key for the local queue database.
  ///
  /// If [databaseExists] is true, the key MUST already exist and be valid in secure storage.
  /// If [databaseExists] is true and the key is missing, empty, or malformed, throws [DatabaseEncryptionException].
  ///
  /// A fresh 256-bit key is generated and persisted ONLY when [databaseExists] is false
  /// (genuinely new database initialization).
  Future<String> getEncryptionKey({required bool databaseExists});

  /// Backward-compatible alias for first-time creation.
  Future<String> getOrCreateEncryptionKey();

  /// Retrieves the existing key if present; returns null otherwise.
  Future<String?> getExistingKey();

  /// Clears stored key material (strictly for testing).
  Future<void> clearKeyForTesting();
}

/// Production implementation backed by platform hardware keyrings via [FlutterSecureStorage].
class FlutterSecureStorageDatabaseKeyProvider implements DatabaseKeyProvider {
  final FlutterSecureStorage _storage;
  static const String keyStorageIdentifier = 'upostit_offline_db_key_v1';

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
    try {
      existingKey = await _storage.read(key: keyStorageIdentifier);
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
  Future<void> clearKeyForTesting() async {
    try {
      await _storage.delete(key: keyStorageIdentifier);
    } catch (_) {}
  }
}
