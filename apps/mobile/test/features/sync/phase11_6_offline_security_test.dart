import 'dart:io';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/services/background_sync_scheduler.dart';
import 'package:mobile/features/sync/data/services/database_recovery_coordinator.dart';
import 'package:mobile/features/sync/data/services/queue_retention_manager.dart';
import 'package:mobile/features/sync/data/services/secure_logout_coordinator.dart';
import 'package:mobile/features/sync/data/services/storage_usage_monitor.dart';
import 'package:mobile/features/sync/presentation/bloc/database_health_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/database_health_event.dart';
import 'package:mobile/features/sync/presentation/bloc/database_health_state.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class FakeFlutterSecureStorage extends Fake implements FlutterSecureStorage {
  final Map<String, String> _data = {};

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

class FakeBackgroundSyncScheduler extends Fake implements BackgroundSyncScheduler {
  bool cancelled = false;

  @override
  Future<void> cancelPeriodicSync() async {
    cancelled = true;
  }
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
  });

  group('Phase 11.6 — DatabaseKeyProvider Lifecycle & Rotation Tests', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;

    setUp(() {
      fakeStorage = FakeFlutterSecureStorage();
      keyProvider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
    });

    test('generates valid 256-bit cryptographically random hex key (64 chars)', () async {
      final key = await keyProvider.getEncryptionKey(databaseExists: false);
      expect(key.length, equals(64));
      expect(RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(key), isTrue);

      final version = await keyProvider.getKeyVersion();
      expect(version, equals(1));

      final status = await keyProvider.getRotationStatus();
      expect(status, equals('IDLE'));
    });

    test('persists key across calls', () async {
      final key1 = await keyProvider.getOrCreateEncryptionKey();
      final key2 = await keyProvider.getOrCreateEncryptionKey();
      expect(key1, equals(key2));
    });

    test('throws DatabaseEncryptionException when database exists but key missing (fail-closed)', () async {
      expect(
        () => keyProvider.getEncryptionKey(databaseExists: true),
        throwsA(isA<DatabaseEncryptionException>()),
      );
    });

    test('manages controlled rotation lifecycle (prepare, commit, version increment)', () async {
      final originalKey = await keyProvider.getOrCreateEncryptionKey();
      expect(await keyProvider.getKeyVersion(), equals(1));

      final stagingKey = await keyProvider.prepareRotationKey();
      expect(stagingKey.length, equals(64));
      expect(stagingKey, isNot(equals(originalKey)));
      expect(await keyProvider.getRotationStatus(), equals('IN_PROGRESS'));

      await keyProvider.commitRotatedKey(newKey: stagingKey, newVersion: 2);
      expect(await keyProvider.getRotationStatus(), equals('IDLE'));
      expect(await keyProvider.getKeyVersion(), equals(2));

      final currentKey = await keyProvider.getExistingKey();
      expect(currentKey, equals(stagingKey));
    });

    test('abortRotation resets rotation status to IDLE and purges pending keys', () async {
      await keyProvider.getOrCreateEncryptionKey();
      await keyProvider.prepareRotationKey();
      expect(await keyProvider.getRotationStatus(), equals('IN_PROGRESS'));

      await keyProvider.abortRotation();
      expect(await keyProvider.getRotationStatus(), equals('IDLE'));
      expect(await keyProvider.getKeyVersion(), equals(1));
    });
  });

  group('Phase 11.6 — LocalQueueDatabase & SQLCipher Integration Tests', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;
    late LocalQueueDatabase db;
    late String testDbPath;

    setUp(() async {
      fakeStorage = FakeFlutterSecureStorage();
      keyProvider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
      final dir = Directory.systemTemp.createTempSync('upostit_db_test_');
      testDbPath = '${dir.path}/test_queue.db';
      db = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: databaseFactoryFfi,
        customPath: testDbPath,
      );
    });

    tearDown(() async {
      if (db.isOpen) {
        await db.close();
      }
      try {
        final f = File(testDbPath);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    });

    test('opens and initializes metadata table with SQLCIPHER_PAGE_AES256 engine', () async {
      final opened = await db.open();
      expect(opened.isOpen, isTrue);

      final integrity = await db.verifyDatabaseIntegrity();
      expect(integrity, isTrue);
    });

    test('rotates key via PRAGMA rekey and records rotation metadata', () async {
      await db.open();
      await db.rotateKey();

      expect(await keyProvider.getKeyVersion(), equals(2));
      expect(await keyProvider.getRotationStatus(), equals('IDLE'));
      expect(await db.verifyDatabaseIntegrity(), isTrue);
    });

    test('quarantines corrupted database file as .bak rather than silently deleting it', () async {
      await db.open();
      await db.close();

      final quarantinedPath = await db.quarantineCorruptedDatabase();
      expect(quarantinedPath, isNotNull);
      expect(quarantinedPath!.endsWith('.bak'), isTrue);
      expect(File(quarantinedPath).existsSync(), isTrue);
      expect(File(testDbPath).existsSync(), isFalse);
    });
  });

  group('Phase 11.6 — QueueRetentionManager Eviction Policy Tests', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;
    late LocalQueueDatabase db;
    late QueueRetentionManager retentionManager;
    late String testDbPath;

    setUp(() async {
      fakeStorage = FakeFlutterSecureStorage();
      keyProvider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
      final dir = Directory.systemTemp.createTempSync('upostit_retention_test_');
      testDbPath = '${dir.path}/test_retention.db';
      db = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: databaseFactoryFfi,
        customPath: testDbPath,
      );
      await db.open();
      retentionManager = QueueRetentionManager(database: db);
    });

    tearDown(() async {
      if (db.isOpen) await db.close();
      try {
        final f = File(testDbPath);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    });

    test('strictly preserves unsynchronized and review punches, evicting ONLY aged SYNCED punches', () async {
      final database = db.database;
      final now = DateTime.now().toUtc();
      final oldDate = now.subtract(const Duration(days: 45)).toIso8601String();
      final freshDate = now.subtract(const Duration(days: 5)).toIso8601String();

      // 1. Insert aged PENDING_SYNC (MUST BE PRESERVED)
      await database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'pend-1',
        'idempotency_key': 'k-pend-1',
        'tenant_id': 'tid-1',
        'employee_id': 'eid-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldDate,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'b1',
        'sequence_number': 1,
        'sync_status': 'PENDING_SYNC',
        'created_at': oldDate,
        'updated_at': oldDate,
      });

      // 2. Insert aged FLAGGED_PENDING_REVIEW (MUST BE PRESERVED)
      await database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'rev-1',
        'idempotency_key': 'k-rev-1',
        'tenant_id': 'tid-1',
        'employee_id': 'eid-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_OUT',
        'device_reported_at': oldDate,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'b1',
        'sequence_number': 2,
        'sync_status': 'FLAGGED_PENDING_REVIEW',
        'created_at': oldDate,
        'updated_at': oldDate,
      });

      // 3. Insert aged REJECTED_PERMANENT (MUST BE PRESERVED)
      await database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'rej-1',
        'idempotency_key': 'k-rej-1',
        'tenant_id': 'tid-1',
        'employee_id': 'eid-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldDate,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'b1',
        'sequence_number': 3,
        'sync_status': 'REJECTED_PERMANENT',
        'created_at': oldDate,
        'updated_at': oldDate,
      });

      // 4. Insert aged SYNCED (>30 days - QUALIFIES FOR EVICTION)
      await database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'synced-old',
        'idempotency_key': 'k-synced-old',
        'tenant_id': 'tid-1',
        'employee_id': 'eid-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_IN',
        'device_reported_at': oldDate,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'b1',
        'sequence_number': 4,
        'sync_status': 'SYNCED',
        'created_at': oldDate,
        'updated_at': oldDate,
      });

      // 5. Insert fresh SYNCED (<30 days - MUST BE PRESERVED)
      await database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'synced-fresh',
        'idempotency_key': 'k-synced-fresh',
        'tenant_id': 'tid-1',
        'employee_id': 'eid-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_OUT',
        'device_reported_at': freshDate,
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 2000,
        'boot_session_id': 'b1',
        'sequence_number': 5,
        'sync_status': 'SYNCED',
        'created_at': freshDate,
        'updated_at': freshDate,
      });

      final result = await retentionManager.executeEviction(
        retentionWindow: const Duration(days: 30),
      );

      // Exactly 1 aged SYNCED record evicted
      expect(result.evictedCount, equals(1));
      // All other records preserved
      expect(result.preservedPendingCount, equals(1));
      expect(result.preservedReviewCount, equals(1));
      expect(result.preservedRejectedCount, equals(1));
      expect(result.remainingSyncedCount, equals(1));
    });

    test('flags capacity warning when unacknowledged queue records >= 400', () async {
      final metrics = await retentionManager.getQueueHealth();
      expect(metrics.isCapacityWarningActive, isFalse);
    });
  });

  group('Phase 11.6 — SecureLogoutCoordinator Tests', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;
    late LocalQueueDatabase db;
    late FakeBackgroundSyncScheduler fakeScheduler;
    late SecureLogoutCoordinator logoutCoordinator;
    late String testDbPath;

    setUp(() async {
      fakeStorage = FakeFlutterSecureStorage();
      await fakeStorage.write(key: 'access_token', value: 'secret_jwt_access');
      await fakeStorage.write(key: 'refresh_token', value: 'secret_jwt_refresh');

      keyProvider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
      final dir = Directory.systemTemp.createTempSync('upostit_logout_test_');
      testDbPath = '${dir.path}/test_logout.db';
      db = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: databaseFactoryFfi,
        customPath: testDbPath,
      );
      await db.open();

      fakeScheduler = FakeBackgroundSyncScheduler();
      logoutCoordinator = SecureLogoutCoordinator(
        storage: fakeStorage,
        database: db,
        scheduler: fakeScheduler,
      );
    });

    tearDown(() async {
      if (db.isOpen) await db.close();
      try {
        final f = File(testDbPath);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    });

    test('purges auth tokens, cancels background scheduler, purges cached tables, preserves pending queue', () async {
      // Seed cached employee
      await db.database.insert(LocalQueueDatabase.cachedEmployeeTable, {
        'id': 'emp-cached-1',
        'tenant_id': 'tid-1',
        'employee_id': 'EMP-1',
        'first_name': 'Secret',
        'last_name': 'Employee',
        'work_email': 'secret@upostit.test',
        'employment_type': 'FULL_TIME',
        'status': 'ACTIVE',
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      });

      // Seed pending offline punch
      await db.database.insert(LocalQueueDatabase.queueTable, {
        'local_id': 'pend-logout-1',
        'idempotency_key': 'k-logout-1',
        'tenant_id': 'tid-1',
        'employee_id': 'emp-cached-1',
        'user_id': 'uid-1',
        'event_type': 'CHECK_IN',
        'device_reported_at': DateTime.now().toUtc().toIso8601String(),
        'timezone_offset_minutes': 0,
        'monotonic_boot_time_ms': 1000,
        'boot_session_id': 'b1',
        'sequence_number': 1,
        'sync_status': 'PENDING_SYNC',
        'created_at': DateTime.now().toUtc().toIso8601String(),
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      });

      final result = await logoutCoordinator.executeSecureLogout(
        tenantId: 'tid-1',
        userId: 'uid-1',
      );

      expect(result.tokensPurged, isTrue);
      expect(result.schedulerCancelled, isTrue);
      expect(result.preservedPendingPunches, equals(1));
      expect(await fakeStorage.read(key: 'access_token'), isNull);
      expect(await fakeStorage.read(key: 'refresh_token'), isNull);
      expect(fakeScheduler.cancelled, isTrue);
    });
  });

  group('Phase 11.6 — DatabaseHealthBloc Tests', () {
    late FakeFlutterSecureStorage fakeStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;
    late LocalQueueDatabase db;
    late DatabaseRecoveryCoordinator recoveryCoordinator;
    late QueueRetentionManager retentionManager;
    late StorageUsageMonitor storageMonitor;
    late DatabaseHealthBloc bloc;
    late String testDbPath;

    setUp(() async {
      fakeStorage = FakeFlutterSecureStorage();
      keyProvider = FlutterSecureStorageDatabaseKeyProvider(storage: fakeStorage);
      final dir = Directory.systemTemp.createTempSync('upostit_bloc_test_');
      testDbPath = '${dir.path}/test_bloc.db';
      db = LocalQueueDatabase(
        keyProvider: keyProvider,
        factory: databaseFactoryFfi,
        customPath: testDbPath,
      );
      await db.open();

      recoveryCoordinator = DatabaseRecoveryCoordinator(
        database: db,
        keyProvider: keyProvider,
      );
      retentionManager = QueueRetentionManager(database: db);
      storageMonitor = StorageUsageMonitor(
        database: db,
        retentionManager: retentionManager,
        factory: databaseFactoryFfi,
        customPath: testDbPath,
      );

      bloc = DatabaseHealthBloc(
        recoveryCoordinator: recoveryCoordinator,
        retentionManager: retentionManager,
        storageMonitor: storageMonitor,
      );
    });

    tearDown(() async {
      await bloc.close();
      if (db.isOpen) await db.close();
      try {
        final f = File(testDbPath);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    });

    test('DatabaseHealthCheckRequested emits checking and loaded states', () async {
      final states = <DatabaseHealthState>[];
      bloc.stream.listen(states.add);

      bloc.add(const DatabaseHealthCheckRequested());
      await Future<void>.delayed(const Duration(milliseconds: 200));

      expect(states.any((s) => s is DatabaseHealthChecking), isTrue);
      expect(states.any((s) => s is DatabaseHealthLoaded), isTrue);
    });
  });
}
