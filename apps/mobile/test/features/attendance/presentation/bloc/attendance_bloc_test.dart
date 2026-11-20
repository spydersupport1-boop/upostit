import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_dashboard.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/domain/entities/punch_result.dart';
import 'package:mobile/features/attendance/domain/repositories/attendance_repository.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_event.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';

class MockAttendanceRepository extends Mock implements AttendanceRepository {}

void main() {
  late MockAttendanceRepository mockRepository;

  setUpAll(() {
    registerFallbackValue(AttendanceEventType.checkIn);
  });

  setUp(() {
    mockRepository = MockAttendanceRepository();
  });

  const dummyDashboard = AttendanceDashboard(
    status: AttendanceStatus.notCheckedIn,
    todayEvents: [],
  );

  final workingDashboard = AttendanceDashboard(
    status: AttendanceStatus.working,
    todayEvents: [
      AttendanceEvent(
        id: 'evt-checkin-1',
        tenantId: 'tenant-1',
        employeeId: 'emp-1',
        eventType: AttendanceEventType.checkIn,
        eventCategory: 'STANDARD',
        serverReceivedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
        effectiveAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
        source: 'MOBILE',
        timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
        reviewStatus: 'NOT_REQUIRED',
        idempotencyKey: 'key-123',
        createdAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      ),
    ],
    workingDuration: const Duration(hours: 1),
  );

  final dummyPunchResult = PunchResult(
    event: AttendanceEvent(
      id: 'evt-checkin-1',
      tenantId: 'tenant-1',
      employeeId: 'emp-1',
      eventType: AttendanceEventType.checkIn,
      eventCategory: 'STANDARD',
      serverReceivedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      effectiveAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      source: 'MOBILE',
      timestampVerificationStatus: 'SERVER_AUTHORITATIVE',
      reviewStatus: 'NOT_REQUIRED',
      idempotencyKey: 'idem-fixed-uuid-1',
      createdAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
    ),
  );

  final pendingPunchResult = PunchResult(
    event: AttendanceEvent(
      id: 'evt-pending-1',
      tenantId: 'tenant-1',
      employeeId: 'emp-1',
      eventType: AttendanceEventType.checkIn,
      eventCategory: 'STANDARD',
      serverReceivedAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      effectiveAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
      source: 'MOBILE',
      timestampVerificationStatus: 'SUSPICIOUS_CLOCK_DRIFT',
      reviewStatus: 'PENDING_REVIEW',
      idempotencyKey: 'idem-pending-1',
      createdAt: DateTime.utc(2026, 11, 4, 9, 0, 0),
    ),
  );

  group('AttendanceBloc - Dashboard Fetching', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'emits [AttendanceLoading, AttendanceLoaded] when dashboard fetch succeeds',
      build: () {
        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.success(dummyDashboard));
        return AttendanceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const AttendanceDashboardRequested()),
      expect: () => [
        const AttendanceLoading(),
        const AttendanceLoaded(dashboard: dummyDashboard),
      ],
      verify: (_) {
        verify(() => mockRepository.getTodayAttendanceDashboard()).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'emits [AttendanceLoading, AttendanceLoadFailure] when initial dashboard fetch fails',
      build: () {
        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => const Result.failure(NetworkFailure()));
        return AttendanceBloc(repository: mockRepository);
      },
      act: (bloc) => bloc.add(const AttendanceDashboardRequested()),
      expect: () => [
        const AttendanceLoading(),
        const AttendanceLoadFailure(
          message:
              'Unable to connect to server. Please check your network connection.',
          isNetworkError: true,
        ),
      ],
    );
  });

  group('AttendanceBloc - Punch Lifecycle & Refresh', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'submits punch, receives server confirmation, and refreshes attendance dashboard',
      build: () {
        when(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => Result.success(workingDashboard));

        return AttendanceBloc(repository: mockRepository);
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'custom-idem-key-1',
      )),
      expect: () => [
        // 1. Submitting state (disables UI button)
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'custom-idem-key-1',
        ),
        // 2. Success state with refreshed dashboard from server
        AttendanceLoaded(
          dashboard: workingDashboard,
          isSubmittingPunch: false,
          lastPunchResult: dummyPunchResult,
          successNotice:
              'Check In recorded at ${DateFormat.jm().format(dummyPunchResult.event.effectiveAt.toLocal())}',
        ),
      ],
      verify: (_) {
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'custom-idem-key-1',
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).called(1);
        verify(() => mockRepository.getTodayAttendanceDashboard()).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'ignores punch submission while another punch request is already in-flight',
      build: () => AttendanceBloc(repository: mockRepository),
      seed: () => const AttendanceLoaded(
        dashboard: dummyDashboard,
        isSubmittingPunch: true,
        inFlightEventType: AttendanceEventType.checkIn,
        inFlightIdempotencyKey: 'in-flight-key',
      ),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
      )),
      expect: () => [],
      verify: (_) {
        verifyNever(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
            ));
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'displays rejected punch error when server returns HTTP 400',
      build: () {
        when(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).thenAnswer(
          (_) async => const Result.failure(
            ServerFailure('Employee is already checked in.', statusCode: 400),
          ),
        );
        return AttendanceBloc(repository: mockRepository);
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-rejected-1',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'idem-rejected-1',
        ),
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'idem-rejected-1',
          errorMessage: 'Employee is already checked in.',
          isRetriable: false,
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'displays pending-review notice when punch has PENDING_REVIEW status',
      build: () {
        when(() => mockRepository.recordPunch(
              eventType: any(named: 'eventType'),
              idempotencyKey: any(named: 'idempotencyKey'),
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).thenAnswer((_) async => Result.success(pendingPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => Result.success(workingDashboard));

        return AttendanceBloc(repository: mockRepository);
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) => bloc.add(const PunchActionSubmitted(
        eventType: AttendanceEventType.checkIn,
        customIdempotencyKey: 'idem-pending-1',
      )),
      expect: () => [
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'idem-pending-1',
        ),
        AttendanceLoaded(
          dashboard: workingDashboard,
          isSubmittingPunch: false,
          lastPunchResult: pendingPunchResult,
          successNotice:
              'Check In recorded at ${DateFormat.jm().format(pendingPunchResult.event.effectiveAt.toLocal())}',
          pendingReviewNotice:
              'Recorded but flagged for manager review (SUSPICIOUS_CLOCK_DRIFT)',
        ),
      ],
    );
  });

  group('AttendanceBloc - Idempotency Key Reuse on Retry', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'preserves idempotency key on network failure and reuses EXACT SAME key on PunchRetryRequested',
      build: () {
        // First attempt fails with network error
        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'key-to-retry-1234',
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).thenAnswer(
          (_) async =>
              const Result.failure(NetworkFailure('Network unreachable')),
        );

        return AttendanceBloc(repository: mockRepository);
      },
      seed: () => const AttendanceLoaded(dashboard: dummyDashboard),
      act: (bloc) async {
        // 1. Initial attempt fails
        bloc.add(const PunchActionSubmitted(
          eventType: AttendanceEventType.checkIn,
          customIdempotencyKey: 'key-to-retry-1234',
        ));
      },
      expect: () => [
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'key-to-retry-1234',
        ),
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: false,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'key-to-retry-1234',
          errorMessage: 'Network unreachable',
          isRetriable: true,
        ),
      ],
      verify: (_) {
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'key-to-retry-1234',
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).called(1);
      },
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'PunchRetryRequested executes punch with the preserved idempotency key and succeeds',
      build: () {
        when(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'key-to-retry-1234',
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).thenAnswer((_) async => Result.success(dummyPunchResult));

        when(() => mockRepository.getTodayAttendanceDashboard())
            .thenAnswer((_) async => Result.success(workingDashboard));

        return AttendanceBloc(repository: mockRepository);
      },
      seed: () => const AttendanceLoaded(
        dashboard: dummyDashboard,
        isSubmittingPunch: false,
        inFlightEventType: AttendanceEventType.checkIn,
        inFlightIdempotencyKey: 'key-to-retry-1234',
        errorMessage: 'Network unreachable',
        isRetriable: true,
      ),
      act: (bloc) => bloc.add(const PunchRetryRequested()),
      expect: () => [
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          isSubmittingPunch: true,
          inFlightEventType: AttendanceEventType.checkIn,
          inFlightIdempotencyKey: 'key-to-retry-1234',
          errorMessage: null,
          isRetriable: false,
        ),
        AttendanceLoaded(
          dashboard: workingDashboard,
          isSubmittingPunch: false,
          lastPunchResult: dummyPunchResult,
          successNotice:
              'Check In recorded at ${DateFormat.jm().format(dummyPunchResult.event.effectiveAt.toLocal())}',
        ),
      ],
      verify: (_) {
        // Confirms the retry passed the exact same idempotency key 'key-to-retry-1234'
        verify(() => mockRepository.recordPunch(
              eventType: AttendanceEventType.checkIn,
              idempotencyKey: 'key-to-retry-1234',
              deviceReportedAt: any(named: 'deviceReportedAt'),
            )).called(1);
      },
    );
  });

  group('AttendanceBloc - Live Timer Ticker', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'LiveTimerTicked advances working duration when status is working',
      build: () => AttendanceBloc(repository: mockRepository),
      seed: () => AttendanceLoaded(
        dashboard: workingDashboard.copyWith(
          workingDuration: const Duration(seconds: 10),
        ),
      ),
      act: (bloc) => bloc.add(const LiveTimerTicked()),
      expect: () => [
        AttendanceLoaded(
          dashboard: workingDashboard.copyWith(
            workingDuration: const Duration(seconds: 11),
          ),
        ),
      ],
    );

    blocTest<AttendanceBloc, AttendanceState>(
      'LiveTimerTicked advances break duration when status is onBreak',
      build: () => AttendanceBloc(repository: mockRepository),
      seed: () => AttendanceLoaded(
        dashboard: workingDashboard.copyWith(
          status: AttendanceStatus.onBreak,
          breakDuration: const Duration(seconds: 5),
        ),
      ),
      act: (bloc) => bloc.add(const LiveTimerTicked()),
      expect: () => [
        AttendanceLoaded(
          dashboard: workingDashboard.copyWith(
            status: AttendanceStatus.onBreak,
            breakDuration: const Duration(seconds: 6),
          ),
        ),
      ],
    );
  });

  group('AttendanceBloc - Notice Dismissal', () {
    blocTest<AttendanceBloc, AttendanceState>(
      'DismissFeedbackNotice clears error and notices',
      build: () => AttendanceBloc(repository: mockRepository),
      seed: () => const AttendanceLoaded(
        dashboard: dummyDashboard,
        errorMessage: 'Some error',
        successNotice: 'Some success',
        pendingReviewNotice: 'Some review',
      ),
      act: (bloc) => bloc.add(const DismissFeedbackNotice()),
      expect: () => [
        const AttendanceLoaded(
          dashboard: dummyDashboard,
          errorMessage: null,
          successNotice: null,
          pendingReviewNotice: null,
        ),
      ],
    );
  });
}
