import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';
import 'package:mobile/features/attendance/data/services/wifi_service.dart';
import 'package:mobile/features/attendance/domain/entities/assigned_workplace.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/entities/punch_result.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_evidence.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_verification_result.dart';
import 'package:mobile/features/attendance/domain/repositories/attendance_repository.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_event.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';

class MockAttendanceRepository extends Mock implements AttendanceRepository {}

class MockLocationService extends Mock implements LocationService {}

class MockWifiService extends Mock implements WifiService {}

void main() {
  late MockAttendanceRepository mockRepository;
  late MockLocationService mockLocationService;
  late MockWifiService mockWifiService;

  setUpAll(() {
    registerFallbackValue(AttendanceEventType.checkIn);
    registerFallbackValue(Duration.zero);
    registerFallbackValue(DateTime.now());
  });

  setUp(() {
    mockRepository = MockAttendanceRepository();
    mockLocationService = MockLocationService();
    mockWifiService = MockWifiService();
  });

  const assignedWorkplace = AssignedWorkplace(
    id: 'wp-assign-1',
    locationId: 'loc-hq-uuid',
    locationName: 'Corporate HQ',
    locationCode: 'HQ-1',
    address: '100 Main St',
    city: 'New York',
    countryCode: 'US',
    isPrimary: true,
    isCurrent: true,
    latitude: 40.7531,
    longitude: -73.9745,
    radiusMeters: 100,
  );

  const wifiOnlyPolicyReject = AttendancePolicy(
    tenantId: 'tenant-wifi',
    version: 1,
    defaultMode: 'WIFI_ONLY',
    allowedMethods: ['WIFI'],
    requiredMethods: ['WIFI'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresWifi: true,
    wifiFallbackAction: 'REJECT',
  );

  const wifiOnlyPolicyGpsFallback = AttendancePolicy(
    tenantId: 'tenant-wifi',
    version: 2,
    defaultMode: 'WIFI_ONLY',
    allowedMethods: ['WIFI', 'GPS'],
    requiredMethods: ['WIFI'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresWifi: true,
    wifiFallbackAction: 'GPS_FALLBACK',
    maxAccuracyMeters: 50,
    maxLocationAgeSeconds: 20,
  );

  const wifiOnlyPolicySupervisorReview = AttendancePolicy(
    tenantId: 'tenant-wifi',
    version: 3,
    defaultMode: 'WIFI_ONLY',
    allowedMethods: ['WIFI'],
    requiredMethods: ['WIFI'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresWifi: true,
    wifiFallbackAction: 'SUPERVISOR_REVIEW',
  );

  const wifiOnlyPolicyManualFallback = AttendancePolicy(
    tenantId: 'tenant-wifi',
    version: 4,
    defaultMode: 'WIFI_ONLY',
    allowedMethods: ['WIFI', 'MANUAL'],
    requiredMethods: ['WIFI'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresWifi: true,
    wifiFallbackAction: 'MANUAL_FALLBACK',
    allowedFallbackMethods: ['MANUAL'],
  );

  const combinedAndPolicy = AttendancePolicy(
    tenantId: 'tenant-combined',
    version: 5,
    defaultMode: 'COMBINED',
    allowedMethods: ['GPS', 'WIFI'],
    requiredMethods: ['GPS', 'WIFI'],
    combinationRule: 'AND',
    requiresGps: true,
    requiresWifi: true,
    maxAccuracyMeters: 100,
    maxLocationAgeSeconds: 30,
  );

  const combinedOrPolicy = AttendancePolicy(
    tenantId: 'tenant-combined',
    version: 6,
    defaultMode: 'COMBINED',
    allowedMethods: ['GPS', 'WIFI'],
    requiredMethods: ['GPS', 'WIFI'],
    combinationRule: 'OR',
    requiresGps: true,
    requiresWifi: true,
    maxAccuracyMeters: 100,
    maxLocationAgeSeconds: 30,
  );

  const wifiDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
    policy: wifiOnlyPolicyReject,
    workplace: assignedWorkplace,
  );

  final authorizedWifiEvidence = WifiEvidence(
    bssid: 'AA:BB:CC:DD:EE:01',
    ssid: 'Corp-Office-5G',
    signalStatus: WifiSignalStatus.available,
    deviceReportedAt: DateTime.utc(2026, 11, 6, 8, 30, 0),
    platform: 'android',
  );

  final unavailableWifiEvidence = WifiEvidence(
    signalStatus: WifiSignalStatus.unavailable,
    deviceReportedAt: DateTime.utc(2026, 11, 6, 8, 30, 0),
    platform: 'android',
    errorMessage: 'Device is not connected to recognized Wi-Fi.',
  );

  final permissionDeniedWifiEvidence = WifiEvidence(
    signalStatus: WifiSignalStatus.permissionDenied,
    deviceReportedAt: DateTime.utc(2026, 11, 6, 8, 30, 0),
    platform: 'android',
    errorMessage: 'Location permission is required to detect Wi-Fi.',
  );

  final validLocationFix = LocationReading(
    latitude: 40.7531,
    longitude: -73.9745,
    accuracyMeters: 12.0,
    timestamp: DateTime.utc(2026, 11, 6, 8, 30, 0),
  );

  final dummyPunchResult = PunchResult(
    event: AttendanceEvent(
      id: 'evt-wifi-1',
      tenantId: 'tenant-wifi',
      employeeId: 'emp-1',
      eventType: AttendanceEventType.checkIn,
      eventCategory: 'STANDARD',
      serverReceivedAt: DateTime.utc(2026, 11, 6, 8, 30, 1),
      effectiveAt: DateTime.utc(2026, 11, 6, 8, 30, 1),
      source: 'MOBILE',
      timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
      reviewStatus: 'NOT_REQUIRED',
      idempotencyKey: 'wifi-idem-key',
      locationId: 'loc-hq-uuid',
      createdAt: DateTime.utc(2026, 11, 6, 8, 30, 1),
    ),
  );

  const workingDashboard = AttendanceDashboard(
    status: AttendanceStatus.working,
    todayEvents: [],
    policy: wifiOnlyPolicyReject,
    workplace: assignedWorkplace,
  );

  group('WIFI_ONLY Policy Punch Workflows', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'positive Wi-Fi punch captures authorized BSSID and records punch with mode WIFI',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => authorizedWifiEvidence);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-idem-key',
              deviceReportedAt: authorizedWifiEvidence.deviceReportedAt,
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: 'AA:BB:CC:DD:EE:01',
              wifiSsid: 'Corp-Office-5G',
              wifiSignalStatus: 'AVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: wifiDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-idem-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-idem-key',
        ),
        const AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-idem-key',
          wifiStatusMessage: 'Checking workplace Wi-Fi...',
        ),
        AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-idem-key',
          wifiStatusMessage: 'Checking workplace Wi-Fi...',
          lastWifiEvidence: authorizedWifiEvidence,
        ),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working)
            .having(
                (s) => s.lastPunchResult, 'lastPunchResult', dummyPunchResult),
      ],
      verify: (_) {
        verify(() => mockWifiService.getConnectedWifiEvidence()).called(1);
        verifyNever(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            ));
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'WIFI_ONLY with REJECT fallback strictly rejects punch when Wi-Fi is unavailable',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: wifiDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-reject-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-reject-key',
        ),
        const AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-reject-key',
          wifiStatusMessage: 'Checking workplace Wi-Fi...',
        ),
        AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-reject-key',
          wifiStatusMessage: 'Checking workplace Wi-Fi...',
          lastWifiEvidence: unavailableWifiEvidence,
        ),
        AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-reject-key',
          lastWifiEvidence: unavailableWifiEvidence,
          errorMessage: 'Device is not connected to recognized Wi-Fi.',
          isRetriable: true,
        ),
      ],
      verify: (_) {
        verifyNever(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
            ));
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'WIFI_ONLY with GPS_FALLBACK engages GPS fix when Wi-Fi is unavailable and punches with coordinates',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 50,
              maxLocationAgeSeconds: 20,
            )).thenAnswer((_) async => validLocationFix);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-gps-fb-key',
              deviceReportedAt: validLocationFix.timestamp.toUtc(),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationFix.latitude,
              longitude: validLocationFix.longitude,
              accuracyMeters: validLocationFix.accuracyMeters,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: wifiOnlyPolicyGpsFallback,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-gps-fb-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>().having(
            (s) => s.wifiStatusMessage, 'wifiStatusMessage', contains('Wi-Fi')),
        isA<AttendanceLoaded>()
            .having((s) => s.lastWifiEvidence, 'lastWifiEvidence', isNotNull),
        isA<AttendanceLoaded>().having((s) => s.wifiStatusMessage,
            'wifiStatusMessage', contains('GPS fallback')),
        isA<AttendanceLoaded>().having((s) => s.lastLocationReading,
            'lastLocationReading', validLocationFix),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working),
      ],
      verify: (_) {
        verify(() => mockWifiService.getConnectedWifiEvidence()).called(1);
        verify(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 50,
              maxLocationAgeSeconds: 20,
            )).called(1);
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-gps-fb-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationFix.latitude,
              longitude: validLocationFix.longitude,
              accuracyMeters: validLocationFix.accuracyMeters,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'WIFI_ONLY with SUPERVISOR_REVIEW submits punch with UNAVAILABLE signal status',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-supervisor-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: wifiOnlyPolicySupervisorReview,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-supervisor-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>().having((s) => s.wifiStatusMessage,
            'wifiStatusMessage', contains('supervisor review')),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false),
      ],
      verify: (_) {
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-supervisor-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'WIFI_ONLY with MANUAL_FALLBACK records punch without Wi-Fi when Wi-Fi is unavailable',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-manual-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: wifiOnlyPolicyManualFallback,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-manual-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>().having(
            (s) => s.wifiStatusMessage,
            'wifiStatusMessage',
            'Wi-Fi unavailable. Submitting manual fallback...'),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false),
      ],
      verify: (_) {
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'wifi-manual-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'WIFI_ONLY with PERMISSION_DENIED displays permission prompt and flags isWifiPermissionDenied',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => permissionDeniedWifiEvidence);

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: wifiDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'wifi-perm-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'wifi-perm-key',
          lastWifiEvidence: permissionDeniedWifiEvidence,
          errorMessage:
              'Wi-Fi permission is required to verify workplace attendance.',
          isRetriable: true,
          isWifiPermissionDenied: true,
        ),
      ],
    );
  });

  group('COMBINED Policy Modes (Dual-Factor AND / OR)', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'COMBINED + AND mandates both valid Wi-Fi and fresh GPS fix',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => authorizedWifiEvidence);

        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 100,
              maxLocationAgeSeconds: 30,
            )).thenAnswer((_) async => validLocationFix);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'combined-and-key',
              deviceReportedAt: validLocationFix.timestamp.toUtc(),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationFix.latitude,
              longitude: validLocationFix.longitude,
              accuracyMeters: validLocationFix.accuracyMeters,
              wifiBssid: 'AA:BB:CC:DD:EE:01',
              wifiSsid: 'Corp-Office-5G',
              wifiSignalStatus: 'AVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: combinedAndPolicy,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'combined-and-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>().having((s) => s.lastWifiEvidence,
            'lastWifiEvidence', authorizedWifiEvidence),
        isA<AttendanceLoaded>().having((s) => s.lastLocationReading,
            'lastLocationReading', validLocationFix),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working),
      ],
      verify: (_) {
        verify(() => mockWifiService.getConnectedWifiEvidence()).called(1);
        verify(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 100,
              maxLocationAgeSeconds: 30,
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'Guardrail: COMBINED + AND strictly rejects punch when Wi-Fi is unavailable, even with valid GPS',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: combinedAndPolicy,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'combined-guardrail-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>()
            .having((s) => s.lastWifiEvidence, 'lastWifiEvidence', isNotNull),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.errorMessage,
                'errorMessage',
                contains(
                    'Dual-factor attendance policy requires both GPS and Wi-Fi')),
      ],
      verify: (_) {
        verifyNever(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            ));
        verifyNever(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
            ));
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'COMBINED + OR punches with Wi-Fi alone when Wi-Fi is available',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => authorizedWifiEvidence);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'combined-or-wifi-key',
              deviceReportedAt: authorizedWifiEvidence.deviceReportedAt,
              locationId: assignedWorkplace.locationId,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              wifiBssid: 'AA:BB:CC:DD:EE:01',
              wifiSsid: 'Corp-Office-5G',
              wifiSignalStatus: 'AVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: combinedOrPolicy,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'combined-or-wifi-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working),
      ],
      verify: (_) {
        verify(() => mockWifiService.getConnectedWifiEvidence()).called(1);
        verifyNever(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            ));
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'COMBINED + OR automatically engages GPS when Wi-Fi is unavailable and succeeds',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => unavailableWifiEvidence);

        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 100,
              maxLocationAgeSeconds: 30,
            )).thenAnswer((_) async => validLocationFix);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'combined-or-gps-key',
              deviceReportedAt: validLocationFix.timestamp.toUtc(),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationFix.latitude,
              longitude: validLocationFix.longitude,
              accuracyMeters: validLocationFix.accuracyMeters,
              wifiBssid: null,
              wifiSsid: null,
              wifiSignalStatus: 'UNAVAILABLE',
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(workingDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: combinedOrPolicy,
          workplace: assignedWorkplace,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'combined-or-gps-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>().having((s) => s.lastLocationReading,
            'lastLocationReading', validLocationFix),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working),
      ],
      verify: (_) {
        verify(() => mockWifiService.getConnectedWifiEvidence()).called(1);
        verify(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 100,
              maxLocationAgeSeconds: 30,
            )).called(1);
      },
    );
  });

  group('Idempotency & HTTP 422 Handling', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'handles HTTP 422 payload mismatch as a non-retriable idempotency conflict',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => authorizedWifiEvidence);

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
              ServerFailure(
                'Idempotency key reused with mismatched request payload.',
                statusCode: 422,
              ),
            ));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: wifiDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'tampered-key',
      )),
      expect: () => [
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', true),
        isA<AttendanceLoaded>(),
        isA<AttendanceLoaded>(),
        AttendanceLoaded(
          dashboard: wifiDashboard,
          isSubmittingPunch: false,
          inFlightEventType: null,
          inFlightIdempotencyKey: null,
          lastWifiEvidence: authorizedWifiEvidence,
          errorMessage:
              'Idempotency key reused with mismatched request payload.',
          isRetriable: false,
        ),
      ],
    );
  });

  group('Wi-Fi Probe Workflow', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'WifiProbeRequested probes connected Wi-Fi against assigned workplace and updates verification state',
      build: () {
        when(() => mockWifiService.getConnectedWifiEvidence())
            .thenAnswer((_) async => authorizedWifiEvidence);

        when(() => mockRepository.verifyWorkplaceWifi(
              locationId: assignedWorkplace.locationId,
              bssid: 'AA:BB:CC:DD:EE:01',
              ssid: 'Corp-Office-5G',
              signalStatus: 'AVAILABLE',
              deviceReportedAt: authorizedWifiEvidence.deviceReportedAt,
              platform: 'android',
            )).thenAnswer((_) async => const Result.success(
              WifiVerificationResult(
                locationId: 'loc-hq-uuid',
                locationName: 'Corporate HQ',
                locationCode: 'HQ-1',
                reportedBssid: 'AA:BB:CC:DD:EE:01',
                matchStatus: WifiMatchStatus.matched,
                isVerified: true,
                matchedAccessPointName: 'HQ-Main-AP',
                message:
                    'Connected to authorized workplace access point "HQ-Main-AP".',
              ),
            ));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
          wifiService: mockWifiService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: wifiDashboard),
      act: (bloc) => bloc.add(const WifiProbeRequested()),
      expect: () => [
        const AttendanceLoaded(
          dashboard: wifiDashboard,
          isWifiProbing: true,
          wifiStatusMessage: 'Checking workplace Wi-Fi...',
        ),
        isA<AttendanceLoaded>()
            .having((s) => s.isWifiProbing, 'isWifiProbing', false)
            .having((s) => s.lastWifiVerificationResult?.isVerified,
                'isVerified', true)
            .having((s) => s.wifiStatusMessage, 'wifiStatusMessage',
                contains('Connected to authorized workplace access point')),
      ],
    );
  });
}
