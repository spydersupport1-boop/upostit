import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class MockKeyProvider implements DatabaseKeyProvider {
  String? key =
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
  bool throwError = false;

  @override
  Future<String> getEncryptionKey({required bool databaseExists}) async {
    if (throwError) {
      throw const DatabaseEncryptionException(
        'Inaccessible secure storage: Keystore hardware fault',
      );
    }
    if (databaseExists && (key == null || key!.isEmpty)) {
      throw const DatabaseEncryptionException(
        'Encrypted database file exists on disk, but its encryption key is missing from secure storage.',
      );
    }
    if (databaseExists && key != null && key!.length != 64) {
      throw const DatabaseEncryptionException(
        'Encrypted database file exists on disk, but its encryption key in secure storage is malformed.',
      );
    }
    return key ?? '';
  }

  @override
  Future<String> getOrCreateEncryptionKey() =>
      getEncryptionKey(databaseExists: false);

  @override
  Future<String?> getExistingKey() async => key;

  @override
  Future<void> clearKeyForTesting() async => key = null;
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
  });

  group('LocalQueueDatabase', () {
    late MockKeyProvider keyProvider;
    late DatabaseFactory ffiFactory;

    setUp(() {
      keyProvider = MockKeyProvider();
      ffiFactory = databaseFactoryFfi;
    });

    test('opens successfully and initializes metadata and queue table',
        () async {
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );

      final db = await dbHelper.open();
      expect(dbHelper.isOpen, isTrue);
      expect(db.isOpen, isTrue);

      // Verify metadata table contents
      final metadata = await db.query(LocalQueueDatabase.metadataTable);
      expect(metadata, isNotEmpty);
      final engineRow = metadata.firstWhere(
        (m) => m['key'] == 'encryption_engine',
        orElse: () => {},
      );
      expect(engineRow['value'], equals('SQLCIPHER_PAGE_AES256'));

      final versionRow = metadata.firstWhere(
        (m) => m['key'] == 'schema_version',
        orElse: () => {},
      );
      expect(versionRow['value'], equals(LocalQueueDatabase.databaseVersion.toString()));

      // Verify queue table exists
      final queueRows = await db.query(LocalQueueDatabase.queueTable);
      expect(queueRows, isEmpty);

      await dbHelper.close();
      expect(dbHelper.isOpen, isFalse);
    });

    test('database getter throws DatabaseEncryptionException when closed', () {
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );

      expect(
        () => dbHelper.database,
        throwsA(isA<DatabaseEncryptionException>()),
      );
    });

    test('re-opening an already open database returns existing instance',
        () async {
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );

      final db1 = await dbHelper.open();
      final db2 = await dbHelper.open();
      expect(identical(db1, db2), isTrue);

      await dbHelper.close();
    });

    test('fail-closed: throws DatabaseEncryptionException when key is empty',
        () async {
      keyProvider.key = '';
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );

      await expectLater(
        dbHelper.open(),
        throwsA(isA<DatabaseEncryptionException>()),
      );
      expect(dbHelper.isOpen, isFalse);
    });

    test(
        'fail-closed: throws DatabaseEncryptionException when existing DB key is missing',
        () async {
      final tempDir = Directory.systemTemp.createTempSync('upostit_test_');
      final dbPath = '${tempDir.path}/existing_db.db';

      // 1. Initialize existing database
      final initHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );
      final _ = await initHelper.open();
      await initHelper.close();

      // Verify file exists
      expect(File(dbPath).existsSync(), isTrue);

      // 2. Clear key from provider to simulate lost keystore entry
      keyProvider.key = null;

      final failingHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );

      await expectLater(
        failingHelper.open(),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('missing from secure storage'),
          ),
        ),
      );

      // 3. Verify existing database file was PRESERVED and not deleted or overwritten
      expect(File(dbPath).existsSync(), isTrue);

      tempDir.deleteSync(recursive: true);
    });

    test(
        'fail-closed: throws DatabaseEncryptionException when existing DB key is malformed',
        () async {
      final tempDir = Directory.systemTemp.createTempSync('upostit_test_');
      final dbPath = '${tempDir.path}/existing_db_malformed.db';

      // 1. Initialize existing database
      final initHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );
      final _ = await initHelper.open();
      await initHelper.close();

      // 2. Set malformed key (too short)
      keyProvider.key = 'too-short-bad-key';

      final failingHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );

      await expectLater(
        failingHelper.open(),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('malformed'),
          ),
        ),
      );

      // 3. Verify existing database file is preserved
      expect(File(dbPath).existsSync(), isTrue);

      tempDir.deleteSync(recursive: true);
    });

    test('fail-closed: throws DatabaseEncryptionException when keystore throws',
        () async {
      keyProvider.throwError = true;
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );

      await expectLater(
        dbHelper.open(),
        throwsA(isA<DatabaseEncryptionException>()),
      );
      expect(dbHelper.isOpen, isFalse);
    });

    test(
        'fail-closed: throws DatabaseEncryptionException if metadata is corrupt',
        () async {
      final tempDir = Directory.systemTemp.createTempSync('upostit_test_');
      final dbPath = '${tempDir.path}/corrupt.db';

      // 1. First initialize a valid database
      final initHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );
      final db = await initHelper.open();

      // 2. Corrupt the engine metadata
      await db.update(
        LocalQueueDatabase.metadataTable,
        {'value': 'PLAINTEXT_INSECURE'},
        where: 'key = ?',
        whereArgs: ['encryption_engine'],
      );
      await initHelper.close();

      // 3. Opening corrupted database must fail closed and throw DatabaseEncryptionException
      final failingHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: dbPath,
      );

      await expectLater(
        failingHelper.open(),
        throwsA(isA<DatabaseEncryptionException>()),
      );
      expect(failingHelper.isOpen, isFalse);

      tempDir.deleteSync(recursive: true);
    });

    test('enforces unique idempotency_key constraint in queue table', () async {
      final dbHelper = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: ffiFactory,
        customPath: inMemoryDatabasePath,
      );
      final db = await dbHelper.open();

      final row1 = {
        'local_id': 'loc-1',
        'idempotency_key': 'same-idempotency-key',
        'session_id': 'sess-1',
        'tenant_id': 'tenant-1',
        'employee_id': 'emp-1',
        'user_id': 'usr-1',
        'event_type': 'CHECK_IN',
        'device_reported_at': DateTime.now().toUtc().toIso8601String(),
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'boot-1',
        'is_reboot_detected': 0,
        'wifi_signal_status': 'AVAILABLE',
        'applied_policy_version': 1,
        'applied_policy_mode': 'MANUAL',
        'metadata_json': '{}',
        'sequence_number': 1,
        'sync_status': 'PENDING_SYNC',
        'retry_count': 0,
        'created_at': DateTime.now().toUtc().toIso8601String(),
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      };

      await db.insert(LocalQueueDatabase.queueTable, row1);

      final row2 = Map<String, dynamic>.from(row1);
      row2['local_id'] = 'loc-2';

      expect(
        () => db.insert(LocalQueueDatabase.queueTable, row2),
        throwsA(isA<DatabaseException>()),
      );

      await dbHelper.close();
    });
  });
}
