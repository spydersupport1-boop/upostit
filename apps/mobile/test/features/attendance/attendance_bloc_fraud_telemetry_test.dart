import 'dart:convert';
import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';
import 'package:mobile/features/attendance/domain/entities/assigned_workplace.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/entities/punch_result.dart';
import 'package:mobile/features/attendance/domain/repositories/attendance_repository.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_event.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';
import 'package:mobile/features/devices/data/services/device_identity_service.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/repositories/local_queue_dao.dart';
import 'package:mobile/features/sync/domain/repositories/network_connectivity_service.dart';
import 'package:mocktail/mocktail.dart';

class MockAttendanceRepository extends Mock implements AttendanceRepository {}

class MockLocationService extends Mock implements LocationService {}

class MockDeviceIdentityService extends Mock implements DeviceIdentityService {}

class MockLocalQueueDao extends Mock implements LocalQueueDao {}

class MockNetworkConnectivityService extends Mock
    implements NetworkConnectivityService {}

class FakeLocalQueueItem extends Fake implements LocalQueueItem {}

void main() {
  late MockAttendanceRepository mockRepository;
  late MockLocationService mockLocationService;
  late MockDeviceIdentityService mockDeviceIdentityService;
  late MockLocalQueueDao mockLocalQueueDao;
  late MockNetworkConnectivityService mockConnectivityService;

  const testInstallationId = 'installation-id-mock-999';
  final fixedCaptureTime = DateTime.utc(2026, 11, 19, 14, 30, 0);

  final dummyEvent = AttendanceEvent(
    id: 'event-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    eventType: AttendanceEventType.checkIn,
    eventCategory: 'STANDARD',
    serverReceivedAt: fixedCaptureTime,
    effectiveAt: fixedCaptureTime,
    source: 'MOBILE',
    timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
    reviewStatus: 'NOT_REQUIRED',
    idempotencyKey: 'idem-fixed-1',
    createdAt: fixedCaptureTime,
  );

  final dummyPunchResult = PunchResult(event: dummyEvent);

  const assignedWorkplace = AssignedWorkplace(
    id: 'wp-assign-1',
    locationId: 'loc-hq-uuid',
    locationName: 'Corporate HQ',
    locationCode: 'HQ-1',
    address: '100 Main St',
    city: 'San Francisco',
    countryCode: 'US',
    isPrimary: true,
    isCurrent: true,
    latitude: 37.7749,
    longitude: -122.4194,
    radiusMeters: 100,
  );

  const gpsPolicy = AttendancePolicy(
    tenantId: 'tenant-1',
    version: 1,
    defaultMode: 'GPS_ONLY',
    allowedMethods: ['GPS_ONLY'],
    requiredMethods: ['GPS_ONLY'],
    combinationRule: 'OR',
    requiresGps: true,
    maxAccuracyMeters: 50,
    maxLocationAgeSeconds: 30,
  );

  const dummyDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
    policy: gpsPolicy,
    workplace: assignedWorkplace,
  );

  final mockedLocationReading = LocationReading(
    latitude: 37.7749,
    longitude: -122.4194,
    accuracyMeters: 15.0,
    timestamp: fixedCaptureTime,
    isMocked: true,
  );

  final authenticLocationReading = LocationReading(
    latitude: 37.7749,
    longitude: -122.4194,
    accuracyMeters: 10.0,
    timestamp: fixedCaptureTime,
    isMocked: false,
  );

  setUpAll(() {
    registerFallbackValue(FakeLocalQueueItem());
    registerFallbackValue(AttendanceEventType.checkIn);
  });

  setUp(() {
    mockRepository = MockAttendanceRepository();
    mockLocationService = MockLocationService();
    mockDeviceIdentityService = MockDeviceIdentityService();
    mockLocalQueueDao = MockLocalQueueDao();
    mockConnectivityService = MockNetworkConnectivityService();

    when(() => mockDeviceIdentityService.getOrCreateInstallationId())
        .thenAnswer((_) async => testInstallationId);
    when(() => mockConnectivityService.isConnected())
        .thenAnswer((_) async => true);
    when(() => mockLocationService.checkPermissionStatus())
        .thenAnswer((_) async => LocationPermissionStatus.granted);
    when(() => mockLocationService.calculateDistanceMeters(
          startLatitude: any(named: 'startLatitude'),
          startLongitude: any(named: 'startLongitude'),
          endLatitude: any(named: 'endLatitude'),
          endLongitude: any(named: 'endLongitude'),
        )).thenReturn(10.0);
    when(() => mockRepository.getTodayAttendanceDashboard())
        .thenAnswer((_) async => const Result.success(dummyDashboard));
  });

  group('AttendanceBloc - Fraud Telemetry & Device Binding', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'forwards installation device_id, is_mock_location: false, and location_captured_at to repository.recordPunch',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenAnswer((_) async => authenticLocationReading);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'idem-key-auth-1',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: authenticLocationReading.latitude,
              longitude: authenticLocationReading.longitude,
              accuracyMeters: authenticLocationReading.accuracyMeters,
              wifiBssid: any(named: 'wifiBssid'),
              wifiSsid: any(named: 'wifiSsid'),
              wifiSignalStatus: any(named: 'wifiSignalStatus'),
              deviceId: testInstallationId,
              isMockLocation: false,
              locationCapturedAt: fixedCaptureTime,
              metadata: any(named: 'metadata'),
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          deviceIdentityService: mockDeviceIdentityService,
          connectivityService: mockConnectivityService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-key-auth-1',
      )),
      verify: (bloc) {
        expect(
          bloc.state,
          isA<AttendanceLoaded>()
              .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
              .having((s) => s.lastPunchResult, 'lastPunchResult',
                  dummyPunchResult),
        );
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'idem-key-auth-1',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: authenticLocationReading.latitude,
              longitude: authenticLocationReading.longitude,
              accuracyMeters: authenticLocationReading.accuracyMeters,
              wifiBssid: any(named: 'wifiBssid'),
              wifiSsid: any(named: 'wifiSsid'),
              wifiSignalStatus: any(named: 'wifiSignalStatus'),
              deviceId: testInstallationId,
              isMockLocation: false,
              locationCapturedAt: fixedCaptureTime,
              metadata: any(named: 'metadata'),
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'forwards is_mock_location: true when location service reports mocked GPS reading',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenAnswer((_) async => mockedLocationReading);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'idem-key-mock-1',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: mockedLocationReading.latitude,
              longitude: mockedLocationReading.longitude,
              accuracyMeters: mockedLocationReading.accuracyMeters,
              wifiBssid: any(named: 'wifiBssid'),
              wifiSsid: any(named: 'wifiSsid'),
              wifiSignalStatus: any(named: 'wifiSignalStatus'),
              deviceId: testInstallationId,
              isMockLocation: true,
              locationCapturedAt: fixedCaptureTime,
              metadata: any(named: 'metadata'),
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          deviceIdentityService: mockDeviceIdentityService,
          connectivityService: mockConnectivityService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-key-mock-1',
      )),
      verify: (_) {
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'idem-key-mock-1',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: mockedLocationReading.latitude,
              longitude: mockedLocationReading.longitude,
              accuracyMeters: mockedLocationReading.accuracyMeters,
              wifiBssid: any(named: 'wifiBssid'),
              wifiSsid: any(named: 'wifiSsid'),
              wifiSignalStatus: any(named: 'wifiSignalStatus'),
              deviceId: testInstallationId,
              isMockLocation: true,
              locationCapturedAt: fixedCaptureTime,
              metadata: any(named: 'metadata'),
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles HTTP 403 device revoked response with clear message and non-retriable state',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenAnswer((_) async => authenticLocationReading);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'idem-key-revoked',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: any(named: 'latitude'),
              longitude: any(named: 'longitude'),
              accuracyMeters: any(named: 'accuracyMeters'),
              wifiBssid: any(named: 'wifiBssid'),
              wifiSsid: any(named: 'wifiSsid'),
              wifiSignalStatus: any(named: 'wifiSignalStatus'),
              deviceId: any(named: 'deviceId'),
              isMockLocation: any(named: 'isMockLocation'),
              locationCapturedAt: any(named: 'locationCapturedAt'),
              metadata: any(named: 'metadata'),
            )).thenAnswer((_) async => const Result.failure(
              ServerFailure(
                'Device authorization revoked: Device stolen report',
                statusCode: 403,
              ),
            ));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          deviceIdentityService: mockDeviceIdentityService,
          connectivityService: mockConnectivityService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-key-revoked',
      )),
      verify: (bloc) {
        expect(
          bloc.state,
          isA<AttendanceLoaded>()
              .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
              .having(
                (s) => s.errorMessage,
                'errorMessage',
                'Device access revoked. Please contact HR to authorize this device.',
              )
              .having((s) => s.isRetriable, 'isRetriable', false),
        );
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'offline punch preserves deviceId, is_mock_location, and location_captured_at in LocalQueueItem',
      build: () {
        when(() => mockConnectivityService.isConnected())
            .thenAnswer((_) async => false);
        when(() => mockLocationService.getCurrentLocation(
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenAnswer((_) async => mockedLocationReading);
        when(() => mockLocalQueueDao.insertPendingEvent(any())).thenAnswer(
            (invocation) async =>
                invocation.positionalArguments.first as LocalQueueItem);

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          deviceIdentityService: mockDeviceIdentityService,
          connectivityService: mockConnectivityService,
          localQueueDao: mockLocalQueueDao,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-key-offline-telemetry',
      )),
      verify: (bloc) {
        expect(
          bloc.state,
          isA<AttendanceLoaded>()
              .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
              .having(
                (s) => s.offlineNotice,
                'offlineNotice',
                contains('Punch saved locally'),
              ),
        );

        final captured = verify(() => mockLocalQueueDao.insertPendingEvent(
              captureAny(that: isA<LocalQueueItem>()),
            )).captured.first as LocalQueueItem;

        expect(captured.deviceId, equals(testInstallationId));
        final meta = jsonDecode(captured.metadataJson) as Map<String, dynamic>;
        expect(meta['is_mock_location'], isTrue);
        expect(meta['location_captured_at'], isNotNull);
      },
    );
  });

  group('PunchRequestModel - JSON serialization with fraud telemetry', () {
    test(
        'serializes device_id, is_mock_location, and location_captured_at accurately',
        () {
      final request = PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-12345',
        deviceReportedAt: fixedCaptureTime,
        deviceId: 'device-xyz-888',
        isMockLocation: true,
        locationCapturedAt: fixedCaptureTime,
        latitude: 37.7749,
        longitude: -122.4194,
        accuracyMeters: 12.5,
      );

      final json = request.toJson();

      expect(json['event_type'], equals('CHECK_IN'));
      expect(json['idempotency_key'], equals('idem-12345'));
      expect(json['device_id'], equals('device-xyz-888'));
      expect(json['is_mock_location'], isTrue);
      expect(json['location_captured_at'], equals('2026-11-19T14:30:00.000Z'));
      expect(json['latitude'], equals(37.7749));
      expect(json['longitude'], equals(-122.4194));
      expect(json['accuracy_meters'], equals(12.5));
    });
  });
}
