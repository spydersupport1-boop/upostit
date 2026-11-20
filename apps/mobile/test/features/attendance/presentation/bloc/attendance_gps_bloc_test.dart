import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
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

class MockAttendanceRepository extends Mock implements AttendanceRepository {}

class MockLocationService extends Mock implements LocationService {}

void main() {
  late MockAttendanceRepository mockRepository;
  late MockLocationService mockLocationService;

  setUpAll(() {
    registerFallbackValue(AttendanceEventType.checkIn);
    registerFallbackValue(Duration.zero);
  });

  setUp(() {
    mockRepository = MockAttendanceRepository();
    mockLocationService = MockLocationService();
  });

  const manualPolicy = AttendancePolicy(
    tenantId: 'tenant-manual',
    version: 1,
    defaultMode: 'MANUAL',
    allowedMethods: ['MANUAL'],
    requiredMethods: ['MANUAL'],
    combinationRule: 'OR',
    requiresGps: false,
  );

  const gpsPolicy = AttendancePolicy(
    tenantId: 'tenant-gps',
    version: 2,
    defaultMode: 'GPS_ONLY',
    allowedMethods: ['GPS_ONLY'],
    requiredMethods: ['GPS_ONLY'],
    combinationRule: 'OR',
    requiresGps: true,
    maxAccuracyMeters: 50,
    maxLocationAgeSeconds: 20,
  );

  const bioPolicy = AttendancePolicy(
    tenantId: 'tenant-bio',
    version: 1,
    defaultMode: 'BIOMETRIC_ONLY',
    allowedMethods: ['BIOMETRIC_ONLY'],
    requiredMethods: ['BIOMETRIC_ONLY'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresBiometric: true,
  );

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

  const manualDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
    policy: manualPolicy,
  );

  const gpsDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
    policy: gpsPolicy,
    workplace: assignedWorkplace,
  );

  const gpsDashboardNoWorkplace = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
    policy: gpsPolicy,
    workplace: null,
  );

  final validLocationReading = LocationReading(
    latitude: 40.7532,
    longitude: -73.9746,
    accuracyMeters: 12.0,
    timestamp: DateTime.utc(2026, 11, 5, 8, 30, 0),
    isMocked: false,
  );

  final dummyPunchResult = PunchResult(
    event: AttendanceEvent(
      id: 'evt-gps-1',
      tenantId: 'tenant-gps',
      employeeId: 'emp-1',
      eventType: AttendanceEventType.checkIn,
      eventCategory: 'STANDARD',
      serverReceivedAt: DateTime.utc(2026, 11, 5, 8, 30, 1),
      effectiveAt: DateTime.utc(2026, 11, 5, 8, 30, 1),
      source: 'MOBILE',
      timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
      reviewStatus: 'NOT_REQUIRED',
      idempotencyKey: 'idem-fixed-1',
      locationId: 'loc-hq-uuid',
      createdAt: DateTime.utc(2026, 11, 5, 8, 30, 1),
    ),
  );

  final workingGpsDashboard = AttendanceDashboard(
    status: AttendanceStatus.working,
    todayEvents: [dummyPunchResult.event],
    policy: gpsPolicy,
    workplace: assignedWorkplace,
    workingDuration: const Duration(seconds: 0),
  );

  group('MANUAL Policy vs GPS Policy Punch Behavior', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'MANUAL policy punches without invoking location service or requesting permissions',
      build: () {
        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'manual-idem-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: null,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              metadata: any(named: 'metadata'),
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard()).thenAnswer(
          (_) async => const Result.success(AttendanceDashboard(
            status: AttendanceStatus.working,
            todayEvents: [],
            policy: manualPolicy,
          )),
        );

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: manualDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'manual-idem-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: manualDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'manual-idem-key',
        ),
        isA<AttendanceLoaded>()
            .having((s) => s.isSubmittingPunch, 'isSubmittingPunch', false)
            .having(
                (s) => s.dashboard.status, 'status', AttendanceStatus.working)
            .having(
                (s) => s.lastLocationReading, 'lastLocationReading', isNull),
      ],
      verify: (_) {
        // LocationService is NEVER touched for MANUAL policy
        verifyNever(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            ));
        verifyNever(() => mockLocationService.checkPermissionStatus());
        verifyNever(() => mockLocationService.requestPermission());

        // Punch is recorded with null GPS fields
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'manual-idem-key',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: null,
              latitude: null,
              longitude: null,
              accuracyMeters: null,
              metadata: any(named: 'metadata'),
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'GPS_ONLY policy acquires fresh location fix and includes coordinates in punch request',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: 50,
              maxLocationAgeSeconds: 20,
            )).thenAnswer((_) async => validLocationReading);

        when(() => mockLocationService.calculateDistanceMeters(
              startLatitude: validLocationReading.latitude,
              startLongitude: validLocationReading.longitude,
              endLatitude: assignedWorkplace.latitude!,
              endLongitude: assignedWorkplace.longitude!,
            )).thenReturn(15.0);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'gps-idem-key',
              deviceReportedAt: validLocationReading.timestamp.toUtc(),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationReading.latitude,
              longitude: validLocationReading.longitude,
              accuracyMeters: validLocationReading.accuracyMeters,
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => Result.success(workingGpsDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'gps-idem-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-idem-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-idem-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-idem-key',
          locationStatusMessage: 'Verifying workplace perimeter...',
          lastLocationReading: validLocationReading,
          advisoryDistanceMeters: 15.0,
          isInsideGeofence: true,
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
        ),
        AttendanceLoaded(
          dashboard: workingGpsDashboard,
          isSubmittingPunch: false,
          lastPunchResult: dummyPunchResult,
          successNotice:
              'Check In recorded at ${DateFormat.jm().format(dummyPunchResult.event.effectiveAt.toLocal())}',
          inFlightEventType: null,
          inFlightIdempotencyKey: null,
        ),
      ],
      verify: (_) {
        verify(() => mockLocationService.getCurrentLocation(
              maxAccuracyMeters: 50,
              maxLocationAgeSeconds: 20,
            )).called(1);

        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'gps-idem-key',
              deviceReportedAt: validLocationReading.timestamp.toUtc(),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationReading.latitude,
              longitude: validLocationReading.longitude,
              accuracyMeters: validLocationReading.accuracyMeters,
              metadata: {},
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'blocks punch when policy mandates GPS but employee has no assigned workplace',
      build: () => AttendanceBloc(
        repository: mockRepository,
        locationService: mockLocationService,
      ),
      seed: () => const AttendanceLoaded(dashboard: gpsDashboardNoWorkplace),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'gps-no-wp-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboardNoWorkplace,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-no-wp-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboardNoWorkplace,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-no-wp-key',
          errorMessage:
              'No assigned workplace location found for your profile. An active workplace assignment is required to verify GPS attendance.',
          isRetriable: false,
        ),
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
      'unsupported attendance method (BIOMETRIC_ONLY) displays informative message and blocks submission',
      build: () => AttendanceBloc(
        repository: mockRepository,
        locationService: mockLocationService,
      ),
      seed: () => const AttendanceLoaded(
        dashboard: AttendanceDashboard(
          status: AttendanceStatus.notCheckedIn,
          todayEvents: [],
          policy: bioPolicy,
        ),
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'bio-punch-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: AttendanceDashboard(
            status: AttendanceStatus.notCheckedIn,
            todayEvents: [],
            policy: bioPolicy,
          ),
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'bio-punch-key',
        ),
        const AttendanceLoaded(
          dashboard: AttendanceDashboard(
            status: AttendanceStatus.notCheckedIn,
            todayEvents: [],
            policy: bioPolicy,
          ),
          isSubmittingPunch: false,
          errorMessage:
              'Dedicated biometric terminal attendance is not supported on mobile devices.',
          isRetriable: false,
          inFlightEventType: null,
          inFlightIdempotencyKey: null,
        ),
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
  });

  group('GPS Hardware and Permission Edge Cases', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'handles LocationPermissionDeniedException cleanly with prompt',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(const LocationPermissionDeniedException());

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'perm-denied-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-denied-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-denied-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-denied-key',
          errorMessage:
              'Location permission is required for attendance verification. Please grant location access.',
          isRetriable: true,
          isLocationPermissionDenied: true,
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
      'handles LocationPermissionPermanentlyDeniedException cleanly with settings guidance',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(const LocationPermissionPermanentlyDeniedException());

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'perm-perm-denied-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-perm-denied-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-perm-denied-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'perm-perm-denied-key',
          errorMessage:
              'Location permission is permanently denied. Please enable location access in system settings.',
          isRetriable: true,
          isLocationPermissionDenied: true,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles LocationServiceDisabledException when GPS hardware toggle is off',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(const LocationServiceDisabledException());

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'gps-off-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-off-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-off-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'gps-off-key',
          errorMessage:
              'Location services (GPS) are turned off. Please enable location services in your device settings.',
          isRetriable: true,
          isLocationServiceDisabled: true,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles LocationTimeoutException when GPS satellite fix times out',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(const LocationTimeoutException());

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'timeout-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'timeout-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'timeout-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'timeout-key',
          errorMessage:
              'GPS location acquisition timed out. Please ensure you have a clear view of the sky and try again.',
          isRetriable: true,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles LocationAccuracyException when accuracy exceeds policy threshold',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(
          LocationAccuracyException(actualAccuracy: 120.0, maxAllowable: 50),
        );

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'poor-acc-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'poor-acc-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'poor-acc-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'poor-acc-key',
          errorMessage:
              'GPS accuracy (120.0m) is insufficient. Maximum allowable threshold is 50m. Please step outside or near a window.',
          isRetriable: true,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles LocationStaleException when reading timestamp is too old',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(
          LocationStaleException(actualAgeSeconds: 45, maxAllowableSeconds: 20),
        );

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'stale-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'stale-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'stale-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'stale-key',
          errorMessage:
              'GPS reading is stale (45s old). A fresh location fix (< 20s) is required.',
          isRetriable: true,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'handles MockLocationDetectedException as non-retriable security violation',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
            )).thenThrow(const MockLocationDetectedException());

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'mocked-loc-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'mocked-loc-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'mocked-loc-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'mocked-loc-key',
          errorMessage:
              'Simulated or mock location detected. Please disable mock location apps to record attendance.',
          isRetriable: false,
        ),
      ],
    );
  });

  group('Server Geofence Rejection & Idempotency Key Preservation', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'captures and displays authoritative server geofence rejection message',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
              checkMockLocation: any(named: 'checkMockLocation'),
            )).thenAnswer((_) async => validLocationReading);

        when(() => mockLocationService.calculateDistanceMeters(
              startLatitude: any(named: 'startLatitude'),
              startLongitude: any(named: 'startLongitude'),
              endLatitude: any(named: 'endLatitude'),
              endLongitude: any(named: 'endLongitude'),
            )).thenReturn(250.0);

        when(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: any(named: 'locationId'),
              latitude: any(named: 'latitude'),
              longitude: any(named: 'longitude'),
              accuracyMeters: any(named: 'accuracyMeters'),
              metadata: any(named: 'metadata'),
            )).thenAnswer(
          (_) async => const Result.failure(
            ServerFailure(
              'Your location (250m away) is outside the authorized workplace geofence radius (100m).',
              statusCode: 400,
            ),
          ),
        );

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'geofence-rejected-key',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'geofence-rejected-key',
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'geofence-rejected-key',
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'geofence-rejected-key',
          locationStatusMessage: 'Verifying workplace perimeter...',
          lastLocationReading: validLocationReading,
          advisoryDistanceMeters: 250.0,
          isInsideGeofence: false,
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
        ),
        AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'geofence-rejected-key',
          lastLocationReading: validLocationReading,
          advisoryDistanceMeters: 250.0,
          isInsideGeofence: false,
          errorMessage:
              'Your location (250m away) is outside the authorized workplace geofence radius (100m).',
          isRetriable: false,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'PunchRetryRequested reuses identical idempotency key after GPS failure recovery',
      build: () {
        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
              checkMockLocation: any(named: 'checkMockLocation'),
            )).thenAnswer((_) async => validLocationReading);

        when(() => mockLocationService.calculateDistanceMeters(
              startLatitude: any(named: 'startLatitude'),
              startLongitude: any(named: 'startLongitude'),
              endLatitude: any(named: 'endLatitude'),
              endLongitude: any(named: 'endLongitude'),
            )).thenReturn(10.0);

        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'preserved-idempotency-key-777',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationReading.latitude,
              longitude: validLocationReading.longitude,
              accuracyMeters: validLocationReading.accuracyMeters,
              metadata: {},
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => Result.success(workingGpsDashboard));

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: gpsDashboard,
        isSubmittingPunch: false,
        inFlightEventType: AttendanceEventType.checkIn,
        inFlightIdempotencyKey: 'preserved-idempotency-key-777',
        errorMessage: 'GPS location acquisition timed out.',
        isRetriable: true,
      ),
      act: (bloc) => bloc.add(const PunchRetryRequested()),
      expect: () => [
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'preserved-idempotency-key-777',
          errorMessage: null,
          isRetriable: false,
        ),
        const AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'preserved-idempotency-key-777',
          errorMessage: null,
          isRetriable: false,
          locationStatusMessage: 'Acquiring GPS location...',
        ),
        AttendanceLoaded(
          dashboard: gpsDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'preserved-idempotency-key-777',
          errorMessage: null,
          isRetriable: false,
          locationStatusMessage: 'Verifying workplace perimeter...',
          lastLocationReading: validLocationReading,
          advisoryDistanceMeters: 10.0,
          isInsideGeofence: true,
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
        ),
        AttendanceLoaded(
          dashboard: workingGpsDashboard,
          isSubmittingPunch: false,
          lastPunchResult: dummyPunchResult,
          successNotice:
              'Check In recorded at ${DateFormat.jm().format(dummyPunchResult.event.effectiveAt.toLocal())}',
          inFlightEventType: null,
          inFlightIdempotencyKey: null,
          errorMessage: null,
          isRetriable: false,
        ),
      ],
      verify: (_) {
        // Confirms that the exact same idempotency key 'preserved-idempotency-key-777' was passed
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'preserved-idempotency-key-777',
              deviceReportedAt: any(named: 'deviceReportedAt'),
              locationId: assignedWorkplace.locationId,
              latitude: validLocationReading.latitude,
              longitude: validLocationReading.longitude,
              accuracyMeters: validLocationReading.accuracyMeters,
              metadata: {},
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'Double-tap protection: ignores second punch submission while first is still in-flight',
      build: () => AttendanceBloc(
        repository: mockRepository,
        locationService: mockLocationService,
      ),
      seed: () => const AttendanceLoaded(
        dashboard: gpsDashboard,
        isSubmittingPunch: true,
        inFlightEventType: AttendanceEventType.checkIn,
        inFlightIdempotencyKey: 'already-in-flight-key',
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'duplicate-double-tap-key',
      )),
      expect: () => [],
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
  });

  group('Location Probing and Permission Resolution Events', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'LocationProbeRequested acquires fresh fix and calculates advisory distance',
      build: () {
        when(() => mockLocationService.checkPermissionStatus())
            .thenAnswer((_) async => LocationPermissionStatus.granted);

        when(() => mockLocationService.getCurrentLocation(
              timeout: any(named: 'timeout'),
              maxAccuracyMeters: any(named: 'maxAccuracyMeters'),
              maxLocationAgeSeconds: any(named: 'maxLocationAgeSeconds'),
              checkMockLocation: any(named: 'checkMockLocation'),
            )).thenAnswer((_) async => validLocationReading);

        when(() => mockLocationService.calculateDistanceMeters(
              startLatitude: validLocationReading.latitude,
              startLongitude: validLocationReading.longitude,
              endLatitude: assignedWorkplace.latitude!,
              endLongitude: assignedWorkplace.longitude!,
            )).thenReturn(25.0);

        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(dashboard: gpsDashboard),
      act: (bloc) => bloc.add(const LocationProbeRequested()),
      expect: () => [
        AttendanceLoaded(
          dashboard: gpsDashboard,
          lastLocationReading: validLocationReading,
          advisoryDistanceMeters: 25.0,
          isInsideGeofence: true,
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'LocationPermissionResolutionRequested opens location settings when service disabled',
      build: () {
        when(() => mockLocationService.openLocationSettings())
            .thenAnswer((_) async => true);
        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: gpsDashboard,
        isLocationServiceDisabled: true,
      ),
      act: (bloc) => bloc.add(const LocationPermissionResolutionRequested()),
      expect: () => [],
      verify: (_) {
        verify(() => mockLocationService.openLocationSettings()).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'LocationPermissionResolutionRequested opens app settings when permission permanently denied',
      build: () {
        when(() => mockLocationService.checkPermissionStatus()).thenAnswer(
            (_) async => LocationPermissionStatus.permanentlyDenied);
        when(() => mockLocationService.openAppSettings())
            .thenAnswer((_) async => true);
        return AttendanceBloc(
          repository: mockRepository,
          locationService: mockLocationService,
        );
      },
      seed: () => const AttendanceLoaded(
        dashboard: gpsDashboard,
        isLocationPermissionDenied: true,
      ),
      act: (bloc) => bloc.add(const LocationPermissionResolutionRequested()),
      expect: () => [],
      verify: (_) {
        verify(() => mockLocationService.openAppSettings()).called(1);
      },
    );
  });
}
