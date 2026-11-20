import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/services/sync_worker_impl.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mocktail/mocktail.dart';

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockAttendanceRemoteDataSource extends Mock
    implements AttendanceRemoteDataSource {}

void main() {
  late MockLocalQueueDao mockDao;
  late MockAttendanceRemoteDataSource mockRemoteDataSource;

  const tTenantId = 'tenant-crash-1';
  const tUserId = 'user-crash-1';
  const tEmployeeId = 'emp-crash-1';

  final Map<String, LocalQueueItem> inMemoryQueue = {};

  LocalQueueItem createQueueItem({
    required String localId,
    required String idempotencyKey,
    required AttendanceEventType eventType,
    required int sequenceNumber,
    SyncStatus syncStatus = SyncStatus.pendingSync,
    DateTime? lastAttemptedAt,
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: 'session-crash',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: DateTime.utc(2026, 11, 4, 11, sequenceNumber),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 3000000,
      bootSessionId: 'boot-crash-1',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'MANUAL',
      sequenceNumber: sequenceNumber,
      syncStatus: syncStatus,
      lastAttemptedAt: lastAttemptedAt,
      createdAt: DateTime.utc(2026, 11, 4, 11, sequenceNumber),
      updatedAt: DateTime.utc(2026, 11, 4, 11, sequenceNumber),
    );
  }

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-crash-key',
      ),
    );
    registerFallbackValue(SyncStatus.pendingSync);
    registerFallbackValue(const Duration(seconds: 120));
  });

  setUp(() {
    mockDao = MockLocalQueueDao();
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    inMemoryQueue.clear();

    when(() => mockDao.resetZombieSyncingItems(
          timeout: any(named: 'timeout'),
        )).thenAnswer((inv) async {
      final timeout = inv.namedArguments[#timeout] as Duration? ??
          const Duration(seconds: 120);
      final cutoff = DateTime.now().toUtc().subtract(timeout);
      int resetCount = 0;

      for (final id in inMemoryQueue.keys.toList()) {
        final item = inMemoryQueue[id]!;
        if (item.syncStatus == SyncStatus.syncing) {
          final attemptedAt = item.lastAttemptedAt ?? item.updatedAt;
          if (attemptedAt.isBefore(cutoff)) {
            inMemoryQueue[id] =
                item.copyWith(syncStatus: SyncStatus.pendingSync);
            resetCount++;
          }
        }
      }
      return resetCount;
    });

    when(() => mockDao.getPendingEventsFifo(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          limit: any(named: 'limit'),
        )).thenAnswer((inv) async {
      final list = inMemoryQueue.values
          .where((item) =>
              item.syncStatus == SyncStatus.pendingSync &&
              item.tenantId == tTenantId &&
              item.userId == tUserId)
          .toList();
      list.sort((a, b) => a.sequenceNumber.compareTo(b.sequenceNumber));
      return list;
    });

    when(() => mockDao.getEventById(any())).thenAnswer((inv) async {
      final id = inv.positionalArguments[0] as String;
      return inMemoryQueue[id];
    });

    when(() => mockDao.updateSyncStatus(
          localId: any(named: 'localId'),
          status: any(named: 'status'),
          serverEventId: any(named: 'serverEventId'),
          errorMessage: any(named: 'errorMessage'),
          statusCode: any(named: 'statusCode'),
        )).thenAnswer((inv) async {
      final id = inv.namedArguments[#localId] as String;
      final status = inv.namedArguments[#status] as SyncStatus;
      final srvId = inv.namedArguments[#serverEventId] as String?;
      final existing = inMemoryQueue[id];
      if (existing != null) {
        inMemoryQueue[id] = existing.copyWith(
          syncStatus: status,
          serverEventId: srvId,
        );
      }
    });

    when(() => mockRemoteDataSource.recordPunch(any())).thenAnswer((inv) async {
      final req = inv.positionalArguments[0] as PunchRequestModel;
      return PunchResponseModel(
        event: AttendanceEventModel(
          id: 'srv-${req.idempotencyKey}',
          tenantId: tTenantId,
          employeeId: tEmployeeId,
          eventType: req.eventType,
          eventCategory: 'STANDARD',
          serverReceivedAt: DateTime.now().toUtc(),
          effectiveAt: DateTime.now().toUtc(),
          source: 'MOBILE_OFFLINE_SYNC',
          timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
          reviewStatus: 'NOT_REQUIRED',
          idempotencyKey: req.idempotencyKey,
          createdAt: DateTime.now().toUtc(),
        ),
        isIdempotentReplay: false,
      );
    });
  });

  group('Phase 6.5.D — Crash & Restart Recovery Simulation', () {
    test(
        'Zombie recovery resets items stranded in SYNCING state (>120s) upon application boot',
        () async {
      // Simulate app kill while item 1 was in-flight (last attempted 150s ago)
      final strandedZombieItem = createQueueItem(
        localId: 'zombie-item-1',
        idempotencyKey: 'idemp-zombie',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
        syncStatus: SyncStatus.syncing,
        lastAttemptedAt:
            DateTime.now().toUtc().subtract(const Duration(seconds: 150)),
      );

      // Normal pending item
      final pendingItem = createQueueItem(
        localId: 'pending-item-2',
        idempotencyKey: 'idemp-pending',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 2,
        syncStatus: SyncStatus.pendingSync,
      );

      inMemoryQueue[strandedZombieItem.localId] = strandedZombieItem;
      inMemoryQueue[pendingItem.localId] = pendingItem;

      // Boot application and trigger sync worker
      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
      );

      final result = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // Verify zombie item was reset to pending and both items synced successfully
      expect(result.isCompleted, isTrue);
      expect(result.syncedCount, equals(2));

      expect(inMemoryQueue['zombie-item-1']!.syncStatus,
          equals(SyncStatus.synced));
      expect(inMemoryQueue['pending-item-2']!.syncStatus,
          equals(SyncStatus.synced));

      worker.dispose();
    });

    test(
        'Phone reboot simulation — boot telemetry changes but queue sequence and persistence remain intact',
        () async {
      // 1. Initial items created under Boot Session Alpha
      final p1 = createQueueItem(
        localId: 'boot-p1',
        idempotencyKey: 'idemp-boot-1',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
      );
      inMemoryQueue[p1.localId] = p1;

      // 2. Phone reboots: monotonic clock resets, boot session ID changes
      const newBootSessionId = 'boot-session-beta-after-reboot';
      final p2 = LocalQueueItem(
        localId: 'boot-p2',
        idempotencyKey: 'idemp-boot-2',
        sessionId: 'session-crash',
        tenantId: tTenantId,
        employeeId: tEmployeeId,
        userId: tUserId,
        eventType: AttendanceEventType.checkOut,
        deviceReportedAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
        timezoneOffsetMinutes: 0,
        monotonicBootTimeMs: 15000, // Just 15s after reboot
        bootSessionId: newBootSessionId,
        isRebootDetected: true,
        appliedPolicyVersion: 1,
        appliedPolicyMode: 'MANUAL',
        sequenceNumber: 2,
        syncStatus: SyncStatus.pendingSync,
        createdAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
        updatedAt: DateTime.utc(2026, 11, 4, 12, 0, 0),
      );
      inMemoryQueue[p2.localId] = p2;

      // Verify queue retains both punches across reboot boundary
      final items = await mockDao.getPendingEventsFifo(
        tenantId: tTenantId,
        userId: tUserId,
      );
      expect(items.length, equals(2));
      expect(items[0].bootSessionId, equals('boot-crash-1'));
      expect(items[0].isRebootDetected, isFalse);
      expect(items[1].bootSessionId, equals(newBootSessionId));
      expect(items[1].isRebootDetected, isTrue);

      // Verify FIFO sync successfully syncs both in sequence
      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
      );
      final result = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      expect(result.isCompleted, isTrue);
      expect(result.syncedCount, equals(2));
      expect(inMemoryQueue['boot-p1']!.syncStatus, equals(SyncStatus.synced));
      expect(inMemoryQueue['boot-p2']!.syncStatus, equals(SyncStatus.synced));

      worker.dispose();
    });
  });
}
