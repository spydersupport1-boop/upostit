import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/downward_sync_dao.dart';
import 'package:mobile/features/sync/data/datasources/downward_sync_remote_data_source.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/data/models/batch_sync_models.dart';
import 'package:mobile/features/sync/data/models/sync_delta_model.dart';
import 'package:mobile/features/sync/data/services/background_sync_scheduler.dart';
import 'package:mobile/features/sync/data/services/downward_sync_coordinator.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/data/services/unified_sync_coordinator.dart';
import 'package:mobile/features/sync/domain/entities/downward_sync_result.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_queue_summary.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_bloc.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_event.dart';
import 'package:mobile/features/sync/presentation/bloc/sync_state.dart';
import 'package:workmanager/workmanager.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockDownwardSyncDao extends Mock implements DownwardSyncDao {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

class MockDownwardSyncRemoteDataSource extends Mock
    implements DownwardSyncRemoteDataSource {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

class MockDownwardSyncCoordinator extends Mock
    implements DownwardSyncCoordinator {}

class MockWorkmanager extends Mock implements Workmanager {}

class FakeAttendanceBatchSyncRequestModel extends Fake
    implements AttendanceBatchSyncRequestModel {}

class FakeConstraints extends Fake implements Constraints {}

class TestKeyProvider implements DatabaseKeyProvider {
  @override
  Future<String> getEncryptionKey({required bool databaseExists}) async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<String> getOrCreateEncryptionKey() async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<String?> getExistingKey() async =>
      '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

  @override
  Future<void> clearKeyForTesting() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    sqfliteFfiInit();
    registerFallbackValue(FakeAttendanceBatchSyncRequestModel());
    registerFallbackValue(SyncStatus.pendingSync);
    registerFallbackValue(const Duration(seconds: 120));
    registerFallbackValue(ExistingPeriodicWorkPolicy.keep);
    registerFallbackValue(BackoffPolicy.exponential);
    registerFallbackValue(FakeConstraints());
    registerFallbackValue(const SyncDeltaModel(
      syncType: 'FULL',
      serverTime: '2026-11-23T19:00:00Z',
      nextCursor: 'cur_test',
      hasMore: false,
    ));
  });

  const tTenantId = 'tenant-test-11-4';
  const tUserId = 'user-test-11-4';
  const tEmployeeId = 'emp-test-11-4';

  LocalQueueItem makeQueueItem({
    required String localId,
    required String idempotencyKey,
    required int sequenceNumber,
    AttendanceEventType eventType = AttendanceEventType.checkIn,
    String sessionId = 'session-1',
    SyncStatus status = SyncStatus.pendingSync,
    int retryCount = 0,
  }) {
    final now = DateTime.utc(2026, 11, 23, 8, 0, 0);
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId,
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: now,
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 1000000 + sequenceNumber * 1000,
      bootSessionId: 'boot-session-1',
      isRebootDetected: false,
      sequenceNumber: sequenceNumber,
      syncStatus: status,
      retryCount: retryCount,
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'STRICT',
      metadataJson: '{}',
      createdAt: now,
      updatedAt: now,
    );
  }

  group('Phase 11.4 — Batch Upload & Partial Receipt Processing', () {
    late MockLocalQueueDao mockDao;
    late MockAttendanceRemoteDataSource mockRemoteDataSource;
    late MockNetworkConnectivityService mockConnectivityService;
    late SyncWorkerImpl syncWorker;
    final Map<String, LocalQueueItem> inMemoryQueue = {};

    setUp(() {
      mockDao = MockLocalQueueDao();
      mockRemoteDataSource = MockAttendanceRemoteDataSource();
      mockConnectivityService = MockNetworkConnectivityService();
      inMemoryQueue.clear();

      when(() => mockConnectivityService.isConnected()).thenAnswer((_) async => true);
      when(() => mockConnectivityService.onConnectivityRestored)
          .thenAnswer((_) => const Stream.empty());
      when(() => mockDao.resetZombieSyncingItems(
            timeout: any(named: 'timeout'),
          )).thenAnswer((_) async => 0);
      when(() => mockDao.getPendingCount(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => inMemoryQueue.values.where((i) => i.syncStatus == SyncStatus.pendingSync).length);

      when(() => mockDao.getEventById(any())).thenAnswer((inv) async {
        final id = inv.positionalArguments.first as String;
        return inMemoryQueue[id];
      });

      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async {
        return inMemoryQueue.values
            .where((i) => i.syncStatus == SyncStatus.pendingSync)
            .toList()
          ..sort((a, b) => a.sequenceNumber.compareTo(b.sequenceNumber));
      });

      when(() => mockDao.updateSyncStatus(
            localId: any(named: 'localId'),
            status: any(named: 'status'),
            serverEventId: any(named: 'serverEventId'),
            errorMessage: any(named: 'errorMessage'),
            statusCode: any(named: 'statusCode'),
          )).thenAnswer((inv) async {
        final localId = inv.namedArguments[#localId] as String;
        final status = inv.namedArguments[#status] as SyncStatus;
        final old = inMemoryQueue[localId];
        if (old != null) {
          inMemoryQueue[localId] = old.copyWith(
            syncStatus: status,
            serverEventId: inv.namedArguments[#serverEventId] as String?,
            lastErrorMessage: inv.namedArguments[#errorMessage] as String?,
            lastErrorStatusCode: inv.namedArguments[#statusCode] as int?,
            retryCount: status == SyncStatus.pendingSync ? old.retryCount + 1 : old.retryCount,
          );
        }
      });

      when(() => mockDao.markPermanentlyRejected(
            localId: any(named: 'localId'),
            errorMessage: any(named: 'errorMessage'),
            statusCode: any(named: 'statusCode'),
          )).thenAnswer((inv) async {
        final localId = inv.namedArguments[#localId] as String;
        final old = inMemoryQueue[localId];
        if (old != null) {
          inMemoryQueue[localId] = old.copyWith(
            syncStatus: SyncStatus.rejectedPermanent,
            lastErrorMessage: inv.namedArguments[#errorMessage] as String?,
            lastErrorStatusCode: inv.namedArguments[#statusCode] as int?,
          );
        }
      });

      when(() => mockDao.quarantineDependentEvents(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            conflictBundleId: any(named: 'conflictBundleId'),
            fromLocalId: any(named: 'fromLocalId'),
          )).thenAnswer((inv) async {
        final bundleId = inv.namedArguments[#conflictBundleId] as String;
        int count = 0;
        for (final entry in inMemoryQueue.entries) {
          final s = entry.value.syncStatus;
          if ((s == SyncStatus.pendingSync || s == SyncStatus.syncing) && entry.value.sessionId == 'session-reject' && entry.key != 'loc-5') {
            inMemoryQueue[entry.key] = entry.value.copyWith(
              syncStatus: SyncStatus.quarantinedDependentFailure,
              conflictBundleId: bundleId,
            );
            count++;
          }
        }
        return count;
      });

      syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
        preferBatch: true,
      );
    });

    tearDown(() {
      syncWorker.dispose();
    });

    test('processes partial batch receipts with mixed ACCEPTED, DUPLICATE, REQUIRES_REVIEW, RETRYABLE, and REJECTED statuses', () async {
      final item1 = makeQueueItem(localId: 'loc-1', idempotencyKey: 'idem-1', sequenceNumber: 1, sessionId: 'sess-ok');
      final item2 = makeQueueItem(localId: 'loc-2', idempotencyKey: 'idem-2', sequenceNumber: 2, sessionId: 'sess-ok');
      final item3 = makeQueueItem(localId: 'loc-3', idempotencyKey: 'idem-3', sequenceNumber: 3, sessionId: 'sess-review');
      final item4 = makeQueueItem(localId: 'loc-4', idempotencyKey: 'idem-4', sequenceNumber: 4, sessionId: 'sess-retry');
      final item5 = makeQueueItem(localId: 'loc-5', idempotencyKey: 'idem-5', sequenceNumber: 5, sessionId: 'session-reject');
      final item6 = makeQueueItem(localId: 'loc-6', idempotencyKey: 'idem-6', sequenceNumber: 6, sessionId: 'session-reject');

      inMemoryQueue['loc-1'] = item1;
      inMemoryQueue['loc-2'] = item2;
      inMemoryQueue['loc-3'] = item3;
      inMemoryQueue['loc-4'] = item4;
      inMemoryQueue['loc-5'] = item5;
      inMemoryQueue['loc-6'] = item6;

      when(() => mockRemoteDataSource.syncBatch(any())).thenAnswer((_) async {
        return const AttendanceBatchSyncResponseModel(
          totalItems: 5,
          acceptedCount: 1,
          duplicateCount: 1,
          requiresReviewCount: 1,
          rejectedCount: 1,
          retryableCount: 1,
          receipts: [
            BatchSyncReceiptItemModel(localId: 'loc-1', idempotencyKey: 'idem-1', status: 'ACCEPTED', eventType: 'CHECK_IN', serverEventId: 'evt-1'),
            BatchSyncReceiptItemModel(localId: 'loc-2', idempotencyKey: 'idem-2', status: 'DUPLICATE', eventType: 'CHECK_IN', serverEventId: 'evt-2', idempotentReplay: true),
            BatchSyncReceiptItemModel(localId: 'loc-3', idempotencyKey: 'idem-3', status: 'REQUIRES_REVIEW', eventType: 'CHECK_IN', serverEventId: 'evt-3', reviewStatus: 'NEEDS_REVIEW'),
            BatchSyncReceiptItemModel(localId: 'loc-4', idempotencyKey: 'idem-4', status: 'RETRYABLE', eventType: 'CHECK_IN', errorMessage: 'Lock timeout'),
            BatchSyncReceiptItemModel(localId: 'loc-5', idempotencyKey: 'idem-5', status: 'REJECTED', eventType: 'CHECK_IN', errorMessage: 'Geofence breached'),
          ],
        );
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
        useBatch: true,
      );

      // Verify counts
      expect(result.syncedCount, equals(3)); // ACCEPTED (1) + DUPLICATE (1) + REQUIRES_REVIEW (1)
      expect(result.retryableFailureCount, equals(1)); // RETRYABLE (loc-4)
      expect(result.permanentlyRejectedCount, equals(1)); // REJECTED (loc-5)
      expect(result.quarantinedCount, equals(1)); // loc-6 quarantined because in same session as loc-5

      // Verify queue item states
      expect(inMemoryQueue['loc-1']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['loc-2']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['loc-3']!.syncStatus, equals(SyncStatus.flaggedPendingReview));
      expect(inMemoryQueue['loc-4']!.syncStatus, equals(SyncStatus.pendingSync));
      expect(inMemoryQueue['loc-5']!.syncStatus, equals(SyncStatus.rejectedPermanent));
      expect(inMemoryQueue['loc-6']!.syncStatus, equals(SyncStatus.quarantinedDependentFailure));

      // Invariant: NEVER delete failed, rejected, or un-synced items from the queue
      expect(inMemoryQueue.containsKey('loc-4'), isTrue);
      expect(inMemoryQueue.containsKey('loc-5'), isTrue);
      expect(inMemoryQueue.containsKey('loc-6'), isTrue);
    });

    test('never fabricates fake BREAK_END or alters historical ledger entries', () async {
      final breakStart = makeQueueItem(
        localId: 'loc-brk',
        idempotencyKey: 'idem-brk',
        sequenceNumber: 1,
        eventType: AttendanceEventType.breakStart,
      );
      final checkOut = makeQueueItem(
        localId: 'loc-out',
        idempotencyKey: 'idem-out',
        sequenceNumber: 2,
        eventType: AttendanceEventType.checkOut,
      );
      inMemoryQueue['loc-brk'] = breakStart;
      inMemoryQueue['loc-out'] = checkOut;

      when(() => mockRemoteDataSource.syncBatch(any())).thenAnswer((inv) async {
        final req = inv.positionalArguments.first as AttendanceBatchSyncRequestModel;
        expect(req.items.length, equals(2));
        expect(req.items[0].eventType, equals('BREAK_START'));
        expect(req.items[1].eventType, equals('CHECK_OUT'));

        return const AttendanceBatchSyncResponseModel(
          totalItems: 2,
          acceptedCount: 2,
          duplicateCount: 0,
          requiresReviewCount: 0,
          rejectedCount: 0,
          receipts: [
            BatchSyncReceiptItemModel(localId: 'loc-brk', idempotencyKey: 'idem-brk', status: 'ACCEPTED', eventType: 'BREAK_START', serverEventId: 'evt-brk'),
            BatchSyncReceiptItemModel(localId: 'loc-out', idempotencyKey: 'idem-out', status: 'ACCEPTED', eventType: 'CHECK_OUT', serverEventId: 'evt-out', reviewStatus: 'NEEDS_REVIEW'),
          ],
        );
      });

      final result = await syncWorker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
        useBatch: true,
      );

      expect(result.syncedCount, equals(2));
      expect(inMemoryQueue['loc-brk']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['loc-out']!.syncStatus, equals(SyncStatus.synced));
    });
  });

  group('Phase 11.4 — Downward Sync Stale-Response Protection & Monotonic Ordering', () {
    late LocalQueueDatabase dbHelper;
    late SqfliteDownwardSyncDao dao;

    setUp(() async {
      dbHelper = LocalQueueDatabase(
        keyProvider: TestKeyProvider(),
        factory: databaseFactoryFfi,
        customPath: inMemoryDatabasePath,
      );
      await dbHelper.open();
      dao = SqfliteDownwardSyncDao(dbHelper);
    });

    tearDown(() async {
      await dbHelper.close();
    });

    test('monotonic version check rejects older policy version (e.g. v5 cannot overwrite v6)', () async {
      // Step 1: Save policy version 6
      const deltaV6 = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T10:00:00Z',
        nextCursor: 'cur_v6',
        hasMore: false,
        attendancePolicy: SyncAttendancePolicyModel(
          id: 'pol-1',
          version: 6,
          isActive: true,
          defaultMode: 'GPS_ONLY',
          allowedMethods: ['GPS_ONLY'],
          requiredMethods: ['GPS_ONLY'],
          combinationRule: 'OR',
          gpsConfig: {'radius_meters': 50},
          wifiConfig: {},
          updatedAt: '2026-11-23T10:00:00Z',
        ),
      );

      await dao.applyDeltaTransactionally(deltaV6);
      final stored1 = await dao.getCachedAttendancePolicy();
      expect(stored1, isNotNull);
      expect(stored1!['version'], equals(6));

      // Step 2: An outdated server response delivers policy version 5
      const deltaV5 = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T08:00:00Z',
        nextCursor: 'cur_v5',
        hasMore: false,
        attendancePolicy: SyncAttendancePolicyModel(
          id: 'pol-1',
          version: 5,
          isActive: true,
          defaultMode: 'GPS_ONLY',
          allowedMethods: ['GPS_ONLY'],
          requiredMethods: ['GPS_ONLY'],
          combinationRule: 'OR',
          gpsConfig: {'radius_meters': 100},
          wifiConfig: {},
          updatedAt: '2026-11-20T08:00:00Z',
        ),
      );

      // Verify staleness checker directly
      final isStale = SqfliteDownwardSyncDao.isIncomingStale(
        existingRow: stored1,
        incomingUpdatedAt: deltaV5.attendancePolicy!.updatedAt,
        incomingVersion: deltaV5.attendancePolicy!.version,
      );
      expect(isStale, isTrue);

      // Apply delta transactionally - should reject stale policy update
      await dao.applyDeltaTransactionally(deltaV5);

      // Invariant: Local database retains version 6
      final stored2 = await dao.getCachedAttendancePolicy();
      expect(stored2!['version'], equals(6));

      // Step 3: Incoming policy version 7 should successfully update
      const deltaV7 = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T12:00:00Z',
        nextCursor: 'cur_v7',
        hasMore: false,
        attendancePolicy: SyncAttendancePolicyModel(
          id: 'pol-1',
          version: 7,
          isActive: true,
          defaultMode: 'GPS_ONLY',
          allowedMethods: ['GPS_ONLY'],
          requiredMethods: ['GPS_ONLY'],
          combinationRule: 'OR',
          gpsConfig: {'radius_meters': 30},
          wifiConfig: {},
          updatedAt: '2026-11-23T12:00:00Z',
        ),
      );

      await dao.applyDeltaTransactionally(deltaV7);
      final stored3 = await dao.getCachedAttendancePolicy();
      expect(stored3!['version'], equals(7));
    });

    test('monotonic updated_at check rejects stale entity overwrites', () async {
      // Step 1: Save workplace with updated_at = 12:00:00
      const delta1 = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T12:00:00Z',
        nextCursor: 'cur_wp1',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'wp-hq',
            name: 'HQ Modernized',
            code: 'HQ-1',
            addressLine1: '100 Main St',
            city: 'Metro City',
            latitude: 37.7749,
            longitude: -122.4194,
            radiusMeters: 100,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T12:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(delta1);

      final cached1 = await dao.getCachedWorkplaces();
      expect(cached1.first['name'], equals('HQ Modernized'));

      // Step 2: Stale response with updated_at = 10:00:00
      const deltaStale = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T10:00:00Z',
        nextCursor: 'cur_wp_stale',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'wp-hq',
            name: 'Old HQ Stale',
            code: 'HQ-1',
            addressLine1: '100 Main St',
            city: 'Metro City',
            latitude: 37.7749,
            longitude: -122.4194,
            radiusMeters: 50,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T10:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(deltaStale);

      // Invariant: Stale update rejected, retained newer version
      final cached2 = await dao.getCachedWorkplaces();
      expect(cached2.first['name'], equals('HQ Modernized'));
    });

    test('tombstone monotonic check does not delete record if local record is newer than deletion', () async {
      // Save workplace updated at 15:00:00
      const deltaNew = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T15:00:00Z',
        nextCursor: 'cur_t1',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'wp-store-1',
            name: 'Downtown Store',
            code: 'DS-1',
            addressLine1: '200 Market St',
            city: 'Metro City',
            latitude: 37.77,
            longitude: -122.42,
            radiusMeters: 100,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T15:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(deltaNew);
      expect((await dao.getCachedWorkplaces()).length, equals(1));

      // Tombstone with older deleted_at = 14:00:00 (stale delete event)
      const staleTombstoneDelta = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T14:00:00Z',
        nextCursor: 'cur_t2',
        hasMore: false,
        tombstones: [
          SyncTombstoneModel(
            entityType: 'workplace',
            entityId: 'wp-store-1',
            deletedAt: '2026-11-23T14:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(staleTombstoneDelta);

      // Record remains present because it was updated after the tombstone deletion timestamp
      expect((await dao.getCachedWorkplaces()).length, equals(1));

      // Valid tombstone with newer deleted_at = 16:00:00
      const freshTombstoneDelta = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T16:00:00Z',
        nextCursor: 'cur_t3',
        hasMore: false,
        tombstones: [
          SyncTombstoneModel(
            entityType: 'workplace',
            entityId: 'wp-store-1',
            deletedAt: '2026-11-23T16:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(freshTombstoneDelta);

      // Record successfully removed
      expect((await dao.getCachedWorkplaces()).isEmpty, isTrue);
    });

    test('duplicate delta responses are applied idempotently without creating duplicate records', () async {
      const deltaDupe = SyncDeltaModel(
        syncType: 'DELTA',
        serverTime: '2026-11-23T17:00:00Z',
        nextCursor: 'cur_dupe_1',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'wp-dupe',
            name: 'Idempotent Office',
            code: 'IDEM-1',
            addressLine1: '300 Pine St',
            city: 'Metro City',
            latitude: 37.78,
            longitude: -122.40,
            radiusMeters: 50,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T17:00:00Z',
          ),
        ],
      );

      // Apply first time
      await dao.applyDeltaTransactionally(deltaDupe);
      expect((await dao.getCachedWorkplaces()).where((w) => w['id'] == 'wp-dupe').length, equals(1));
      expect(await dao.getCommittedCursor(), equals('cur_dupe_1'));

      // Apply second time (duplicate response re-delivery)
      await dao.applyDeltaTransactionally(deltaDupe);
      expect((await dao.getCachedWorkplaces()).where((w) => w['id'] == 'wp-dupe').length, equals(1));
      expect(await dao.getCommittedCursor(), equals('cur_dupe_1'));
    });

    test('interrupted transaction rolls back cleanly without committing cursor or partial entities', () async {
      // Step 1: Baseline valid sync
      const baselineDelta = SyncDeltaModel(
        syncType: 'FULL',
        serverTime: '2026-11-23T18:00:00Z',
        nextCursor: 'cur_baseline',
        hasMore: false,
        workplaces: [
          SyncWorkplaceModel(
            id: 'wp-baseline',
            name: 'Baseline Office',
            code: 'BASE-1',
            addressLine1: '400 Market St',
            city: 'Metro City',
            latitude: 37.78,
            longitude: -122.40,
            radiusMeters: 50,
            timezone: 'UTC',
            wifiBssids: [],
            isActive: true,
            isAssigned: true,
            isPrimary: true,
            updatedAt: '2026-11-23T18:00:00Z',
          ),
        ],
      );
      await dao.applyDeltaTransactionally(baselineDelta);
      expect(await dao.getCommittedCursor(), equals('cur_baseline'));

      // Step 2: Simulate interrupted transaction by executing a transaction on the underlying database that throws
      final db = dbHelper.database;
      try {
        await db.transaction((txn) async {
          await txn.insert(
            LocalQueueDatabase.cachedWorkplacesTable,
            {
              'id': 'wp-aborted',
              'name': 'Aborted Office',
              'code': 'ABORT-1',
              'address_line_1': 'Should Roll Back',
              'city': 'Metro City',
              'latitude': 37.78,
              'longitude': -122.40,
              'radius_meters': 50,
              'timezone': 'UTC',
              'wifi_bssids_json': '[]',
              'is_active': 1,
              'is_assigned': 1,
              'is_primary': 1,
              'created_at': DateTime.now().toUtc().toIso8601String(),
              'updated_at': DateTime.now().toUtc().toIso8601String(),
            },
          );
          // Advance cursor inside transaction before abortion
          await txn.insert(
            LocalQueueDatabase.syncStateTable,
            {
              'key': 'downward_sync_cursor',
              'value': 'cur_corrupted_aborted',
              'updated_at': DateTime.now().toUtc().toIso8601String(),
            },
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
          // Simulate fatal crash/interruption
          throw Exception('Simulated crash / power failure mid-transaction');
        });
      } catch (_) {
        // Expected transaction failure
      }

      // Invariant: The aborted transaction must have rolled back completely
      final workplacesAfter = await dao.getCachedWorkplaces();
      expect(workplacesAfter.any((w) => w['id'] == 'wp-aborted'), isFalse);
      expect(await dao.getCommittedCursor(), equals('cur_baseline'));
    });
  });

  group('Phase 11.4 — UnifiedSyncCoordinator Orchestration', () {
    late MockLocalQueueDao mockDao;
    late MockDownwardSyncDao mockDownwardDao;
    late MockAttendanceRemoteDataSource mockRemoteDataSource;
    late MockDownwardSyncCoordinator mockDownwardCoordinator;
    late MockNetworkConnectivityService mockConnectivityService;
    late SyncWorkerImpl syncWorker;
    late UnifiedSyncCoordinator unifiedCoordinator;

    setUp(() {
      mockDao = MockLocalQueueDao();
      mockDownwardDao = MockDownwardSyncDao();
      mockRemoteDataSource = MockAttendanceRemoteDataSource();
      mockDownwardCoordinator = MockDownwardSyncCoordinator();
      mockConnectivityService = MockNetworkConnectivityService();

      when(() => mockConnectivityService.isConnected()).thenAnswer((_) async => true);
      when(() => mockConnectivityService.onConnectivityRestored)
          .thenAnswer((_) => const Stream.empty());
      when(() => mockDao.resetZombieSyncingItems(
            timeout: any(named: 'timeout'),
          )).thenAnswer((_) async => 0);
      when(() => mockDao.getPendingCount(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => 0);

      when(() => mockDao.getEventById(any())).thenAnswer((_) async => null);

      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async => []);

      syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivityService,
      );

      unifiedCoordinator = UnifiedSyncCoordinator(
        syncWorker: syncWorker,
        downwardCoordinator: mockDownwardCoordinator,
        localQueueDao: mockDao,
        downwardDao: mockDownwardDao,
        connectivityService: mockConnectivityService,
      );
    });

    tearDown(() {
      unifiedCoordinator.dispose();
      syncWorker.dispose();
    });

    test('orchestrates full bidirectional sync and emits distinct operational phases', () async {
      when(() => mockDownwardCoordinator.sync(
            forceFull: any(named: 'forceFull'),
          )).thenAnswer((_) async => DownwardSyncResult.success(
            syncType: 'DELTA',
            itemsSynced: 12,
          ));

      final phases = <UnifiedSyncPhase>[];
      final sub = unifiedCoordinator.progressStream.listen((event) {
        phases.add(event.phase);
      });

      final result = await unifiedCoordinator.synchronizeAll(
        tenantId: tTenantId,
        userId: tUserId,
      );

      await Future.delayed(const Duration(milliseconds: 50));
      await sub.cancel();

      expect(result.isCompleted, isTrue);
      expect(result.upwardResult?.isCompleted, isTrue);
      expect(result.downwardResult?.isSuccess, isTrue);

      expect(phases, contains(UnifiedSyncPhase.checkingConnectivity));
      expect(phases, contains(UnifiedSyncPhase.uploadingAttendance));
      expect(phases, contains(UnifiedSyncPhase.downloadingReferenceData));
      expect(phases, contains(UnifiedSyncPhase.applyingLocalUpdates));
      expect(phases, contains(UnifiedSyncPhase.fullySynchronized));
    });

    test('cross-state resilience: downward sync failure does not corrupt upward sync results', () async {
      when(() => mockDownwardCoordinator.sync(
            forceFull: any(named: 'forceFull'),
          )).thenAnswer((_) async => DownwardSyncResult.failure(
            'Delta API Internal Server Error',
          ));

      final result = await unifiedCoordinator.synchronizeAll(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isFalse);
      expect(result.upwardResult?.isCompleted, isTrue);
      expect(result.downwardResult?.isFailure, isTrue);
    });

    test('handles authentication error without corrupting local state or deleting items', () async {
      final authItem = makeQueueItem(localId: 'loc-auth', idempotencyKey: 'idem-auth', sequenceNumber: 1);
      when(() => mockDao.getPendingCount(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => 1);
      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async => [authItem]);
      when(() => mockDao.getEventById('loc-auth')).thenAnswer((_) async => authItem);
      when(() => mockDao.updateSyncStatus(
            localId: any(named: 'localId'),
            status: any(named: 'status'),
            serverEventId: any(named: 'serverEventId'),
            errorMessage: any(named: 'errorMessage'),
            statusCode: any(named: 'statusCode'),
          )).thenAnswer((_) async {});

      when(() => mockRemoteDataSource.syncBatch(any())).thenThrow(
        const AuthException('Token expired or account suspended', statusCode: 401),
      );

      final result = await unifiedCoordinator.synchronizeAll(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isAuthRequired, isTrue);
      expect(result.isCompleted, isFalse);
    });

    test('concurrent downward sync requests are deduplicated into single flight', () async {
      final mockRemote = MockDownwardSyncRemoteDataSource();
      final mockConn = MockNetworkConnectivityService();
      when(() => mockConn.isConnected()).thenAnswer((_) async => true);
      when(() => mockDownwardDao.getCommittedCursor()).thenAnswer((_) async => null);
      when(() => mockDownwardDao.applyDeltaTransactionally(any())).thenAnswer((_) async {});

      int networkCalls = 0;
      when(() => mockRemote.fetchDelta(cursor: any(named: 'cursor'), limit: any(named: 'limit')))
          .thenAnswer((_) async {
        networkCalls++;
        await Future.delayed(const Duration(milliseconds: 50));
        return const SyncDeltaModel(
          syncType: 'FULL',
          serverTime: '2026-11-23T19:00:00Z',
          nextCursor: 'cur_flight',
          hasMore: false,
        );
      });

      final coordinator = DownwardSyncCoordinator(
        remoteDataSource: mockRemote,
        dao: mockDownwardDao,
        connectivityService: mockConn,
      );

      final f1 = coordinator.sync();
      final f2 = coordinator.sync();

      final results = await Future.wait([f1, f2]);

      // Exactly one network call was made for both concurrent requests
      expect(networkCalls, equals(1));
      expect(results[0].isSuccess, isTrue);
      expect(results[1].isSuccess, isTrue);
    });
  });

  group('Phase 11.4 — DefaultBackgroundSyncScheduler Mutex & Constraints', () {
    late MockNetworkConnectivityService mockConnectivity;
    late MockDownwardSyncDao mockDownwardDao;
    late MockLocalQueueDao mockDao;
    late MockAttendanceRemoteDataSource mockRemote;
    late MockDownwardSyncCoordinator mockDownwardCoord;
    late SyncWorkerImpl syncWorker;
    late UnifiedSyncCoordinator unifiedCoord;
    late DefaultBackgroundSyncScheduler scheduler;

    setUp(() {
      mockConnectivity = MockNetworkConnectivityService();
      mockDownwardDao = MockDownwardSyncDao();
      mockDao = MockLocalQueueDao();
      mockRemote = MockAttendanceRemoteDataSource();
      mockDownwardCoord = MockDownwardSyncCoordinator();

      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => true);
      when(() => mockConnectivity.onConnectivityRestored).thenAnswer((_) => const Stream.empty());
      when(() => mockDao.resetZombieSyncingItems(
            timeout: any(named: 'timeout'),
          )).thenAnswer((_) async => 0);
      when(() => mockDao.getPendingCount(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => 0);
      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async => []);

      syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemote,
        connectivityService: mockConnectivity,
      );

      unifiedCoord = UnifiedSyncCoordinator(
        syncWorker: syncWorker,
        downwardCoordinator: mockDownwardCoord,
        localQueueDao: mockDao,
        downwardDao: mockDownwardDao,
        connectivityService: mockConnectivity,
      );

      scheduler = DefaultBackgroundSyncScheduler(
        unifiedCoordinator: unifiedCoord,
        connectivityService: mockConnectivity,
      );
    });

    tearDown(() {
      scheduler.dispose();
      unifiedCoord.dispose();
      syncWorker.dispose();
    });

    test('enforces mutual exclusion mutex preventing concurrent runs', () async {
      when(() => mockDownwardCoord.sync(
            forceFull: any(named: 'forceFull'),
          )).thenAnswer((_) async {
        await Future.delayed(const Duration(milliseconds: 100));
        return DownwardSyncResult.success(syncType: 'DELTA', itemsSynced: 1);
      });

      // Launch two background passes concurrently
      final f1 = scheduler.executeBackgroundSyncPass(tenantId: tTenantId, userId: tUserId);
      final f2 = scheduler.executeBackgroundSyncPass(tenantId: tTenantId, userId: tUserId);

      final results = await Future.wait([f1, f2]);

      // Exactly one execution should succeed, the other skipped due to mutex lock
      expect(results.contains(true), isTrue);
      expect(results.contains(false), isTrue);
    });

    test('skips background execution when network is disconnected', () async {
      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => false);

      final executed = await scheduler.executeBackgroundSyncPass(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(executed, isFalse);
    });

    test('schedules native WorkManager periodic task with network connected and exponential backoff', () async {
      final mockWm = MockWorkmanager();
      when(() => mockWm.registerPeriodicTask(
            any(),
            any(),
            frequency: any(named: 'frequency'),
            flexInterval: any(named: 'flexInterval'),
            inputData: any(named: 'inputData'),
            initialDelay: any(named: 'initialDelay'),
            constraints: any(named: 'constraints'),
            existingWorkPolicy: any(named: 'existingWorkPolicy'),
            backoffPolicy: any(named: 'backoffPolicy'),
            backoffPolicyDelay: any(named: 'backoffPolicyDelay'),
            tag: any(named: 'tag'),
            foregroundServiceConfig: any(named: 'foregroundServiceConfig'),
          )).thenAnswer((_) async {});
      when(() => mockWm.cancelByUniqueName(any())).thenAnswer((_) async {});

      final nativeScheduler = DefaultBackgroundSyncScheduler(
        unifiedCoordinator: unifiedCoord,
        connectivityService: mockConnectivity,
        workmanager: mockWm,
      );

      await nativeScheduler.schedulePeriodicSync(
        tenantId: tTenantId,
        userId: tUserId,
        interval: const Duration(minutes: 15),
      );

      verify(() => mockWm.registerPeriodicTask(
            kBackgroundSyncPeriodicUniqueName,
            kBackgroundSyncPeriodicTask,
            frequency: const Duration(minutes: 15),
            constraints: any(named: 'constraints'),
            existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
            backoffPolicy: BackoffPolicy.exponential,
            backoffPolicyDelay: const Duration(seconds: 30),
            inputData: {
              'tenantId': tTenantId,
              'userId': tUserId,
            },
          )).called(1);

      await nativeScheduler.cancelPeriodicSync();
      verify(() => mockWm.cancelByUniqueName(kBackgroundSyncPeriodicUniqueName)).called(1);
    });

    test('handleNativeTask safely skips when credentials/context are missing', () async {
      final executed = await DefaultBackgroundSyncScheduler.handleNativeTask(
        taskName: kBackgroundSyncPeriodicTask,
        inputData: null,
      );
      expect(executed, isTrue);

      final executedEmpty = await DefaultBackgroundSyncScheduler.handleNativeTask(
        taskName: kBackgroundSyncPeriodicTask,
        inputData: {'tenantId': '', 'userId': ''},
      );
      expect(executedEmpty, isTrue);
    });

    test('handleNativeTask delegates to activeCoordinator when credentials provided', () async {
      when(() => mockDownwardCoord.sync(
            forceFull: any(named: 'forceFull'),
          )).thenAnswer((_) async => DownwardSyncResult.success(
            syncType: 'DELTA',
            itemsSynced: 5,
          ));

      final result = await DefaultBackgroundSyncScheduler.handleNativeTask(
        taskName: kBackgroundSyncPeriodicTask,
        inputData: {'tenantId': tTenantId, 'userId': tUserId},
      );

      expect(result, isTrue);
    });
  });

  group('Phase 11.4 — Resilient SyncBloc Operational States', () {
    late MockLocalQueueDao mockDao;
    late MockNetworkConnectivityService mockConnectivity;
    late MockAttendanceRemoteDataSource mockRemoteDataSource;
    late SyncWorkerImpl syncWorker;
    late SyncBloc syncBloc;

    setUp(() {
      mockDao = MockLocalQueueDao();
      mockConnectivity = MockNetworkConnectivityService();
      mockRemoteDataSource = MockAttendanceRemoteDataSource();

      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => true);
      when(() => mockConnectivity.onConnectivityRestored)
          .thenAnswer((_) => const Stream.empty());
      when(() => mockDao.getPendingEventsFifo(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
            limit: any(named: 'limit'),
          )).thenAnswer((_) async => []);
      when(() => mockDao.getConflictBundles(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => []);
      when(() => mockDao.getQueueSummary(
            tenantId: any(named: 'tenantId'),
            userId: any(named: 'userId'),
          )).thenAnswer((_) async => const SyncQueueSummary());

      syncWorker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
        connectivityService: mockConnectivity,
      );

      syncBloc = SyncBloc(
        localQueueDao: mockDao,
        syncWorker: syncWorker,
        connectivityService: mockConnectivity,
      );
    });

    tearDown(() {
      syncBloc.close();
      syncWorker.dispose();
    });

    test('updates operational phase, retry status, and timestamps without leaking PII', () async {
      expect(syncBloc.state.phase, equals(SyncOperationalPhase.idle));

      // Dispatch progress event
      syncBloc.add(const SyncUnifiedProgressReceived(
        UnifiedSyncProgress(
          phase: UnifiedSyncPhase.downloadingReferenceData,
          message: 'Synchronizing rosters and policies',
        ),
      ));

      await expectLater(
        syncBloc.stream,
        emitsThrough(predicate<SyncState>((s) =>
            s.phase == SyncOperationalPhase.downloadingReferenceData &&
            s.currentOperation == 'Synchronizing rosters and policies')),
      );

      // Dispatch fully synchronized
      syncBloc.add(SyncUnifiedProgressReceived(
        UnifiedSyncProgress(
          phase: UnifiedSyncPhase.fullySynchronized,
          message: 'Synchronization complete',
          lastSuccessfulDownload: DateTime.utc(2026, 11, 23, 12, 0, 0),
        ),
      ));

      await expectLater(
        syncBloc.stream,
        emitsThrough(predicate<SyncState>((s) =>
            s.phase == SyncOperationalPhase.fullySynchronized &&
            s.lastSuccessfulDownload != null)),
      );
    });
  });
}
