import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';
import 'package:mobile/features/attendance/data/services/wifi_service.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/repositories/attendance_repository.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_event.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mocktail/mocktail.dart';

class MockAttendanceRepository extends Mock implements AttendanceRepository {}

class MockLocationService extends Mock implements LocationService {}

class MockWifiService extends Mock implements WifiService {}

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

class FakeLocalQueueItem extends Fake implements LocalQueueItem {}

void main() {
  late MockAttendanceRepository mockRepository;
  late MockLocationService mockLocationService;
  late MockWifiService mockWifiService;
  late MockLocalQueueDao mockDao;
  late MockNetworkConnectivityService mockConnectivity;

  setUpAll(() {
    registerFallbackValue(FakeLocalQueueItem());
    registerFallbackValue(AttendanceEventType.checkIn);
  });

  const tTenantId = 'tenant-test-1';
  const tUserId = 'user-test-1';
  const tEmployeeId = 'emp-test-1';

  final tDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayDay: AttendanceDay(
      id: 'day-1',
      tenantId: tTenantId,
      employeeId: tEmployeeId,
      attendanceDate: DateTime.utc(2026, 11, 4),
      totalWorkingMinutes: 0,
      totalBreakMinutes: 0,
      netWorkingMinutes: 0,
      status: 'ABSENT',
      calculationStatus: 'PENDING',
      lastCalculatedAt: DateTime.utc(2026, 11, 4),
    ),
    todayEvents: const [],
    policy: AttendancePolicy.defaultManual(tenantId: tTenantId),
  );

  setUp(() {
    mockRepository = MockAttendanceRepository();
    mockLocationService = MockLocationService();
    mockWifiService = MockWifiService();
    mockDao = MockLocalQueueDao();
    mockConnectivity = MockNetworkConnectivityService();

    when(() => mockRepository.getTodayAttendanceDashboard())
        .thenAnswer((_) async => Result.success(tDashboard));
    when(() => mockLocationService.checkPermissionStatus())
        .thenAnswer((_) async => LocationPermissionStatus.granted);
    when(() => mockDao.insertPendingEvent(any())).thenAnswer(
        (invocation) async =>
            invocation.positionalArguments.first as LocalQueueItem);
  });

  group('AttendanceBloc Offline Punch Capture', () {
    test(
        'when device is offline, punch is persisted to local queue and offlineNotice is emitted',
        () async {
      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => false);

      final bloc = AttendanceBloc(
        repository: mockRepository,
        locationService: mockLocationService,
        wifiService: mockWifiService,
        localQueueDao: mockDao,
        connectivityService: mockConnectivity,
        tenantId: tTenantId,
        userId: tUserId,
        employeeId: tEmployeeId,
      );

      // 1. Load dashboard
      bloc.add(const AttendanceDashboardRequested());
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(bloc.state, isA<AttendanceLoaded>());

      // 2. Submit punch while offline
      bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idemp-offline-1',
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate<AttendanceState>((s) =>
              s is AttendanceLoaded &&
              s.isSubmittingPunch == true &&
              s.inFlightEventType == AttendanceEventType.checkIn),
          predicate<AttendanceState>((s) =>
              s is AttendanceLoaded &&
              s.isSubmittingPunch == false &&
              s.offlineNotice != null &&
              s.offlineNotice!.contains('saved locally')),
        ]),
      );

      // Verify repository.recordPunch was never called over network
      verifyNever(() => mockRepository.recordPunch(
            eventType: any(named: 'eventType'),
            idempotencyKey: any(named: 'idempotencyKey'),
            deviceReportedAt: any(named: 'deviceReportedAt'),
            locationId: any(named: 'locationId'),
            latitude: any(named: 'latitude'),
            longitude: any(named: 'longitude'),
            accuracyMeters: any(named: 'accuracyMeters'),
            wifiBssid: any(named: 'wifiBssid'),
            wifiSsid: any(named: 'wifiSsid'),
            wifiSignalStatus: any(named: 'wifiSignalStatus'),
            metadata: any(named: 'metadata'),
          ));

      // Verify persisted in DAO with correct attributes
      final captured = verify(() => mockDao.insertPendingEvent(captureAny()))
          .captured
          .first as LocalQueueItem;

      expect(captured.idempotencyKey, equals('idemp-offline-1'));
      expect(captured.eventType, equals(AttendanceEventType.checkIn));
      expect(captured.tenantId, equals(tTenantId));
      expect(captured.userId, equals(tUserId));
      expect(captured.employeeId, equals(tEmployeeId));
      expect(captured.syncStatus, equals(SyncStatus.pendingSync));

      await bloc.close();
    });

    test(
        'when server returns NetworkFailure, punch is persisted to local queue and offlineNotice is emitted',
        () async {
      when(() => mockConnectivity.isConnected()).thenAnswer((_) async => true);

      when(() => mockRepository.recordPunch(
            eventType: any(named: 'eventType'),
            idempotencyKey: any(named: 'idempotencyKey'),
            deviceReportedAt: any(named: 'deviceReportedAt'),
            locationId: any(named: 'locationId'),
            latitude: any(named: 'latitude'),
            longitude: any(named: 'longitude'),
            accuracyMeters: any(named: 'accuracyMeters'),
            wifiBssid: any(named: 'wifiBssid'),
            wifiSsid: any(named: 'wifiSsid'),
            wifiSignalStatus: any(named: 'wifiSignalStatus'),
            metadata: any(named: 'metadata'),
          )).thenAnswer((_) async => const Result.failure(
            NetworkFailure('SocketException: Connection refused'),
          ));

      final bloc = AttendanceBloc(
        repository: mockRepository,
        locationService: mockLocationService,
        wifiService: mockWifiService,
        localQueueDao: mockDao,
        connectivityService: mockConnectivity,
        tenantId: tTenantId,
        userId: tUserId,
        employeeId: tEmployeeId,
      );

      // 1. Load dashboard
      bloc.add(const AttendanceDashboardRequested());
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(bloc.state, isA<AttendanceLoaded>());

      // 2. Submit punch
      bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkOut,
        customIdempotencyKey: 'idemp-net-fail-2',
      ));

      await expectLater(
        bloc.stream,
        emitsInOrder([
          predicate<AttendanceState>(
              (s) => s is AttendanceLoaded && s.isSubmittingPunch == true),
          predicate<AttendanceState>((s) =>
              s is AttendanceLoaded &&
              s.isSubmittingPunch == false &&
              s.offlineNotice != null &&
              s.offlineNotice!.contains('saved locally')),
        ]),
      );

      // Verify DAO stored the punch
      final captured = verify(() => mockDao.insertPendingEvent(captureAny()))
          .captured
          .first as LocalQueueItem;

      expect(captured.idempotencyKey, equals('idemp-net-fail-2'));
      expect(captured.eventType, equals(AttendanceEventType.checkOut));
      expect(captured.syncStatus, equals(SyncStatus.pendingSync));

      await bloc.close();
    });
  });
}
