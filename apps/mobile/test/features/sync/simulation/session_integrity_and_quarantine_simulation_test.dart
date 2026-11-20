import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
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

  const tTenantId = 'tenant-session-1';
  const tUserId = 'user-session-1';
  const tEmployeeId = 'emp-session-1';

  final Map<String, LocalQueueItem> inMemoryQueue = {};
  final List<String> dispatchedEventTypes = [];

  LocalQueueItem createSessionItem({
    required String localId,
    required String idempotencyKey,
    required String sessionId,
    required AttendanceEventType eventType,
    required int sequenceNumber,
  }) {
    return LocalQueueItem(
      localId: localId,
      idempotencyKey: idempotencyKey,
      sessionId: sessionId,
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      userId: tUserId,
      eventType: eventType,
      deviceReportedAt: DateTime.utc(2026, 11, 4, 8, sequenceNumber),
      timezoneOffsetMinutes: 0,
      monotonicBootTimeMs: 4000000 + sequenceNumber * 1000,
      bootSessionId: 'boot-session-1',
      appliedPolicyVersion: 1,
      appliedPolicyMode: 'MANUAL',
      sequenceNumber: sequenceNumber,
      syncStatus: SyncStatus.pendingSync,
      createdAt: DateTime.utc(2026, 11, 4, 8, sequenceNumber),
      updatedAt: DateTime.utc(2026, 11, 4, 8, sequenceNumber),
    );
  }

  setUpAll(() {
    registerFallbackValue(
      const PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'fallback-session-key',
      ),
    );
    registerFallbackValue(SyncStatus.pendingSync);
    registerFallbackValue(const Duration(seconds: 120));
  });

  setUp(() {
    mockDao = MockLocalQueueDao();
    mockRemoteDataSource = MockAttendanceRemoteDataSource();
    inMemoryQueue.clear();
    dispatchedEventTypes.clear();

    when(() => mockDao.resetZombieSyncingItems(
          timeout: any(named: 'timeout'),
        )).thenAnswer((_) async => 0);

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

    when(() => mockDao.markPermanentlyRejected(
          localId: any(named: 'localId'),
          errorMessage: any(named: 'errorMessage'),
          statusCode: any(named: 'statusCode'),
        )).thenAnswer((inv) async {
      final id = inv.namedArguments[#localId] as String;
      final existing = inMemoryQueue[id];
      if (existing != null) {
        inMemoryQueue[id] = existing.copyWith(
          syncStatus: SyncStatus.rejectedPermanent,
          lastErrorMessage: inv.namedArguments[#errorMessage] as String?,
          lastErrorStatusCode: inv.namedArguments[#statusCode] as int?,
        );
      }
    });

    // Session-aware quarantine implementation
    when(() => mockDao.quarantineDependentEvents(
          tenantId: any(named: 'tenantId'),
          userId: any(named: 'userId'),
          conflictBundleId: any(named: 'conflictBundleId'),
          fromLocalId: any(named: 'fromLocalId'),
        )).thenAnswer((inv) async {
      final fromId = inv.namedArguments[#fromLocalId] as String;
      final bundleId = inv.namedArguments[#conflictBundleId] as String;
      final failedItem = inMemoryQueue[fromId];
      if (failedItem == null) return 0;

      int quarantined = 0;
      for (final id in inMemoryQueue.keys.toList()) {
        final item = inMemoryQueue[id]!;
        // Quarantine only events in the SAME session with higher sequence number
        if (item.sessionId == failedItem.sessionId &&
            item.sequenceNumber > failedItem.sequenceNumber &&
            (item.syncStatus == SyncStatus.pendingSync ||
                item.syncStatus == SyncStatus.syncing)) {
          inMemoryQueue[id] = item.copyWith(
            syncStatus: SyncStatus.quarantinedDependentFailure,
            conflictBundleId: bundleId,
          );
          quarantined++;
        }
      }
      return quarantined;
    });
  });

  group('Phase 6.5.D — Session Integrity & Quarantine Simulation', () {
    test(
        'Permanent failure in Shift 1 quarantines Shift 1 dependent punches, while Shift 2 independent shift remains eligible and syncs',
        () async {
      // Shift 1: Session A (Morning shift)
      final sA1 = createSessionItem(
        localId: 'sa-checkin',
        idempotencyKey: 'idemp-sa-1',
        sessionId: 'session-shift-morning',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 1,
      );
      final sA2 = createSessionItem(
        localId: 'sa-breakstart',
        idempotencyKey: 'idemp-sa-2',
        sessionId: 'session-shift-morning',
        eventType: AttendanceEventType.breakStart,
        sequenceNumber: 2,
      );
      final sA3 = createSessionItem(
        localId: 'sa-breakend',
        idempotencyKey: 'idemp-sa-3',
        sessionId: 'session-shift-morning',
        eventType: AttendanceEventType.breakEnd,
        sequenceNumber: 3,
      );
      final sA4 = createSessionItem(
        localId: 'sa-checkout',
        idempotencyKey: 'idemp-sa-4',
        sessionId: 'session-shift-morning',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 4,
      );

      // Shift 2: Session B (Evening shift - completely independent session)
      final sB1 = createSessionItem(
        localId: 'sb-checkin',
        idempotencyKey: 'idemp-sb-1',
        sessionId: 'session-shift-evening',
        eventType: AttendanceEventType.checkIn,
        sequenceNumber: 5,
      );
      final sB2 = createSessionItem(
        localId: 'sb-checkout',
        idempotencyKey: 'idemp-sb-2',
        sessionId: 'session-shift-evening',
        eventType: AttendanceEventType.checkOut,
        sequenceNumber: 6,
      );

      inMemoryQueue['sa-checkin'] = sA1;
      inMemoryQueue['sa-breakstart'] = sA2;
      inMemoryQueue['sa-breakend'] = sA3;
      inMemoryQueue['sa-checkout'] = sA4;
      inMemoryQueue['sb-checkin'] = sB1;
      inMemoryQueue['sb-checkout'] = sB2;

      // Mock remote data source: sa-checkin fails permanently with HTTP 400
      when(() => mockRemoteDataSource.recordPunch(any()))
          .thenAnswer((inv) async {
        final req = inv.positionalArguments[0] as PunchRequestModel;
        dispatchedEventTypes.add(req.eventType.toBackendString());

        if (req.idempotencyKey == 'idemp-sa-1') {
          throw const ServerException(
            'Punch rejected: Inactive shift template or missing schedule window.',
            statusCode: 400,
          );
        }

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

      final worker = SyncWorkerImpl(
        localQueueDao: mockDao,
        remoteDataSource: mockRemoteDataSource,
      );

      final result = await worker.synchronizeQueue(
        tenantId: tTenantId,
        userId: tUserId,
      );

      // Verify sync result
      expect(result.permanentlyRejectedCount, equals(1)); // sa-checkin
      expect(result.quarantinedCount,
          equals(3)); // sa-breakstart, sa-breakend, sa-checkout
      expect(result.syncedCount, equals(2)); // sb-checkin, sb-checkout
      expect(result.retryableFailureCount, equals(0));

      // Verify exact states in queue:
      expect(inMemoryQueue['sa-checkin']!.syncStatus,
          equals(SyncStatus.rejectedPermanent));
      expect(inMemoryQueue['sa-breakstart']!.syncStatus,
          equals(SyncStatus.quarantinedDependentFailure));
      expect(inMemoryQueue['sa-breakend']!.syncStatus,
          equals(SyncStatus.quarantinedDependentFailure));
      expect(inMemoryQueue['sa-checkout']!.syncStatus,
          equals(SyncStatus.quarantinedDependentFailure));

      // CRITICAL ASSERTION: Shift 2 events were NOT quarantined and synced cleanly!
      expect(
          inMemoryQueue['sb-checkin']!.syncStatus, equals(SyncStatus.synced));
      expect(
          inMemoryQueue['sb-checkout']!.syncStatus, equals(SyncStatus.synced));

      worker.dispose();
    });
  });
}
