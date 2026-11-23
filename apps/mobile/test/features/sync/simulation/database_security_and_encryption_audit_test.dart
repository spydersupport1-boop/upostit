import 'dart:io';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/datasources/sqflite_local_queue_dao.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class MockKeyProvider implements DatabaseKeyProvider {
  String? key;
  bool shouldThrow = false;

  MockKeyProvider({this.key});

  @override
  Future<String> getEncryptionKey({required bool databaseExists}) async {
    if (shouldThrow) {
      throw const DatabaseEncryptionException('KeyStore hardware failure');
    }
    if (databaseExists && (key == null || key!.length != 64)) {
      throw const DatabaseEncryptionException(
          'Missing or malformed key for existing database');
    }
    return key ??
        '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
  }

  @override
  Future<String> getOrCreateEncryptionKey() async =>
      getEncryptionKey(databaseExists: false);

  @override
  Future<String?> getExistingKey() async => key;

  @override
  Future<void> clearKeyForTesting() async {
    key = null;
  }
}

class FakeFlutterSecureStorage extends Fake implements FlutterSecureStorage {
  final Map<String, String> _map = {};

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
    return _map[key];
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
    if (value != null) {
      _map[key] = value;
    } else {
      _map.remove(key);
    }
  }
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
  });

  group('Phase 6.5.D — Database Security & Encryption Audit', () {
    test('1. Encryption key handling: Fail-closed on missing or corrupted key',
        () async {
      final fakeStorage = FakeFlutterSecureStorage();
      final keyProvider =
          FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);

      // Case 1A: Existing database exists, but key is missing
      expect(
        () => keyProvider.getEncryptionKey(databaseExists: true),
        throwsA(isA<DatabaseEncryptionException>().having(
          (e) => e.message,
          'message',
          contains('missing from secure storage'),
        )),
      );

      // Case 1B: Existing database exists, but key is malformed (e.g. truncated / non-hex)
      await fakeStorage.write(
        key: FlutterSecureStorageDatabaseKeyProvider.keyStorageIdentifier,
        value: 'corrupted-short-key',
      );

      expect(
        () => keyProvider.getEncryptionKey(databaseExists: true),
        throwsA(isA<DatabaseEncryptionException>().having(
          (e) => e.message,
          'message',
          contains('malformed'),
        )),
      );

      // Case 1C: LocalQueueDatabase fails closed when key provider fails
      final failingKeyProvider = MockKeyProvider()..shouldThrow = true;
      final failingDb = LocalQueueDatabase(
        keyProvider: failingKeyProvider,
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );

      expect(
        () => failingDb.open(),
        throwsA(isA<DatabaseEncryptionException>()),
      );
      expect(failingDb.isOpen, isFalse);
    });

    test(
        '2. Database content audit: No credentials, tokens, or raw biometric PII',
        () async {
      final db = LocalQueueDatabase(
        keyProvider: MockKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      final rawDb = await db.open();

      // Inspect schema column names
      final List<Map<String, dynamic>> columns = await rawDb.rawQuery(
        'PRAGMA table_info(${LocalQueueDatabase.queueTable});',
      );
      final columnNames =
          columns.map((c) => c['name'].toString().toLowerCase()).toList();

      // Prohibited sensitive token/credential patterns
      const prohibitedTokens = [
        'token',
        'access_token',
        'refresh_token',
        'password',
        'secret',
        'credential',
        'bearer',
        'api_key',
      ];

      for (final forbidden in prohibitedTokens) {
        final matches = columnNames.where((col) => col.contains(forbidden));
        expect(
          matches,
          isEmpty,
          reason:
              'Forbidden security token column detected in offline queue: $matches',
        );
      }

      // Prohibited biometric patterns
      const prohibitedBiometrics = [
        'face_vector',
        'biometric',
        'fingerprint',
        'photo_blob',
        'image_raw',
        'facial_embedding',
      ];

      for (final forbidden in prohibitedBiometrics) {
        final matches = columnNames.where((col) => col.contains(forbidden));
        expect(
          matches,
          isEmpty,
          reason:
              'Forbidden biometric PII column detected in offline queue: $matches',
        );
      }

      // Required telemetry columns must exist
      expect(columnNames, contains('local_id'));
      expect(columnNames, contains('idempotency_key'));
      expect(columnNames, contains('tenant_id'));
      expect(columnNames, contains('user_id'));
      expect(columnNames, contains('employee_id'));
      expect(columnNames, contains('device_reported_at'));
      expect(columnNames, contains('monotonic_boot_time_ms'));
      expect(columnNames, contains('boot_session_id'));
      expect(columnNames, contains('sequence_number'));
      expect(columnNames, contains('sync_status'));

      await db.close();
    });

    test('3. Schema integrity: Atomic user_version and required FIFO indexes',
        () async {
      final db = LocalQueueDatabase(
        keyProvider: MockKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      final rawDb = await db.open();

      // Check PRAGMA user_version matches databaseVersion
      final versionResult = await rawDb.rawQuery('PRAGMA user_version;');
      final userVersion = versionResult.first.values.first as int;
      expect(userVersion, equals(LocalQueueDatabase.databaseVersion));

      // Check metadata engine verification
      final meta = await rawDb.query(
        LocalQueueDatabase.metadataTable,
        where: 'key = ?',
        whereArgs: ['encryption_engine'],
      );
      expect(meta.first['value'], equals('SQLCIPHER_PAGE_AES256'));

      // Check indexes
      final List<Map<String, dynamic>> indexes = await rawDb.rawQuery(
        'PRAGMA index_list(${LocalQueueDatabase.queueTable});',
      );
      final indexNames = indexes.map((idx) => idx['name'].toString()).toList();

      expect(indexNames, contains('idx_local_queue_fifo'));
      expect(indexNames, contains('idx_local_queue_idempotency'));
      expect(indexNames, contains('idx_local_queue_status'));
      expect(indexNames, contains('idx_local_queue_sequence'));
      expect(indexNames, contains('idx_local_queue_session'));
      expect(indexNames, contains('idx_local_queue_created'));

      await db.close();
    });

    test('4. Non-destructive error recovery: Failed punches never purged',
        () async {
      final db = LocalQueueDatabase(
        keyProvider: MockKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      await db.open();
      final dao = SqfliteLocalQueueDao(database: db);

      final item = await dao.insertPendingEvent(
        LocalQueueItem(
          localId: 'loc-recovery-1',
          idempotencyKey: 'idem-recovery-1',
          sessionId: 'session-rec',
          tenantId: 'tenant-rec',
          employeeId: 'emp-rec',
          userId: 'user-rec',
          eventType: AttendanceEventType.checkIn,
          deviceReportedAt: DateTime.utc(2026, 11, 6, 8),
          timezoneOffsetMinutes: 0,
          monotonicBootTimeMs: 1000000,
          bootSessionId: 'boot-rec',
          appliedPolicyVersion: 1,
          appliedPolicyMode: 'MANUAL',
          sequenceNumber: 0,
          syncStatus: SyncStatus.pendingSync,
          createdAt: DateTime.utc(2026, 11, 6, 8),
          updatedAt: DateTime.utc(2026, 11, 6, 8),
        ),
      );

      // Simulate permanent failure marking
      await dao.markPermanentlyRejected(
        localId: item.localId,
        errorMessage: 'Permanent 422 Unprocessable',
        statusCode: 422,
      );

      // Verify the record is STILL physically present in the database
      final fetched = await dao.getEventById(item.localId);
      expect(fetched, isNotNull);
      expect(fetched!.syncStatus, equals(SyncStatus.rejectedPermanent));
      expect(fetched.lastErrorMessage, equals('Permanent 422 Unprocessable'));
      expect(fetched.lastErrorStatusCode, equals(422));
      expect(fetched.idempotencyKey, equals('idem-recovery-1'));

      // Total count remains 1, preserved for audit evidence
      final summary = await dao.getQueueSummary(
        tenantId: 'tenant-rec',
        userId: 'user-rec',
      );
      expect(summary.totalCount, equals(1));
      expect(summary.permanentlyRejectedCount, equals(1));

      await db.close();
    });

    test('5. Static Android Manifest audit: allowBackup is explicitly false',
        () {
      final manifestFile = File('android/app/src/main/AndroidManifest.xml');
      expect(manifestFile.existsSync(), isTrue);

      final content = manifestFile.readAsStringSync();
      expect(
        content.contains('android:allowBackup="false"'),
        isTrue,
        reason:
            'AndroidManifest.xml must set android:allowBackup="false" to prevent cloud backup extraction of encrypted database.',
      );
    });
  });
}
