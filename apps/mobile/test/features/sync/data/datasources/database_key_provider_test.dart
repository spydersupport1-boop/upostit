import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';

class FakeFlutterSecureStorage extends Fake implements FlutterSecureStorage {
  final Map<String, String> _data = {};
  bool throwOnRead = false;
  bool throwOnWrite = false;

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (throwOnRead) {
      throw Exception('Secure hardware element unreachable');
    }
    return _data[key];
  }

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (throwOnWrite) {
      throw Exception('Write permission denied by KeyStore');
    }
    if (value != null) {
      _data[key] = value;
    } else {
      _data.remove(key);
    }
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    _data.remove(key);
  }
}

void main() {
  group('FlutterSecureStorageDatabaseKeyProvider', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider provider;

    setUp(() {
      fakeStorage = FakeFlutterSecureStorage();
      provider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
    });

    test(
        'generates and stores 256-bit (64 hex chars) key on new database initialization',
        () async {
      final key = await provider.getEncryptionKey(databaseExists: false);

      expect(key, isNotEmpty);
      expect(key.length, 64);
      expect(RegExp(r'^[0-9a-f]{64}$').hasMatch(key), isTrue);

      final storedKey = await fakeStorage.read(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
      );
      expect(storedKey, equals(key));
    });

    test('returns existing key when valid key is present for existing database',
        () async {
      const existingKey =
          '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
      await fakeStorage.write(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
        value: existingKey,
      );

      final key = await provider.getEncryptionKey(databaseExists: true);

      expect(key, equals(existingKey));
    });

    test(
        'fail-closed: throws DatabaseEncryptionException when existing DB key is missing',
        () async {
      // Database file exists on disk, but secure storage has no key
      expect(
        provider.getEncryptionKey(databaseExists: true),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('missing from secure storage'),
          ),
        ),
      );

      // Verify no key was generated or written
      final storedKey = await fakeStorage.read(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
      );
      expect(storedKey, isNull);
    });

    test(
        'fail-closed: throws DatabaseEncryptionException when existing DB key is malformed',
        () async {
      await fakeStorage.write(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
        value: 'corrupted-short-key',
      );

      expect(
        provider.getEncryptionKey(databaseExists: true),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('malformed'),
          ),
        ),
      );

      // Verify the malformed key was NOT overwritten (to prevent destroying evidence)
      final storedKey = await fakeStorage.read(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
      );
      expect(storedKey, equals('corrupted-short-key'));
    });

    test(
        'fail-closed: throws DatabaseEncryptionException when secure storage is inaccessible',
        () async {
      fakeStorage.throwOnRead = true;

      expect(
        provider.getEncryptionKey(databaseExists: true),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('Inaccessible secure storage'),
          ),
        ),
      );
    });

    test('never silently replaces existing valid key on subsequent calls',
        () async {
      const existingKey =
          'aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899';
      await fakeStorage.write(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
        value: existingKey,
      );

      final key1 = await provider.getEncryptionKey(databaseExists: false);
      final key2 = await provider.getEncryptionKey(databaseExists: true);

      expect(key1, equals(existingKey));
      expect(key2, equals(existingKey));
    });

    test('getExistingKey returns null when key does not exist', () async {
      final key = await provider.getExistingKey();
      expect(key, isNull);
    });

    test('getExistingKey returns stored key when key exists', () async {
      const existingKey =
          'aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899';
      await fakeStorage.write(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
        value: existingKey,
      );

      final key = await provider.getExistingKey();
      expect(key, equals(existingKey));
    });

    test('clearKeyForTesting removes key from storage', () async {
      await provider.getEncryptionKey(databaseExists: false);
      expect(await provider.getExistingKey(), isNotNull);

      await provider.clearKeyForTesting();
      expect(await provider.getExistingKey(), isNull);
    });
  });
}
