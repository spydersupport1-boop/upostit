import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/features/profile/domain/entities/employee.dart';
import 'package:mobile/features/profile/domain/usecases/get_profile_usecase.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_bloc.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_event.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_state.dart';
import 'package:mocktail/mocktail.dart';

class MockGetProfileUseCase extends Mock implements GetProfileUseCase {}

void main() {
  late MockGetProfileUseCase mockGetProfileUseCase;
  late ProfileBloc profileBloc;

  final testEmployee = Employee(
    id: 'emp-uuid-1',
    tenantId: 'tenant-uuid-1',
    employeeId: 'EMP-001',
    firstName: 'Alex',
    lastName: 'Johnson',
    workEmail: 'alex@acme.com',
    phoneNumber: '+15551234567',
    departmentName: 'Engineering',
    designationTitle: 'Senior Software Engineer',
    employmentType: 'full_time',
    status: 'active',
    joiningDate: DateTime(2023, 1, 15),
  );

  setUp(() {
    mockGetProfileUseCase = MockGetProfileUseCase();
    profileBloc = ProfileBloc(getProfileUseCase: mockGetProfileUseCase);
  });

  tearDown(() {
    profileBloc.close();
  });

  test('initial state is ProfileInitial', () {
    expect(profileBloc.state, const ProfileInitial());
  });

  group('FetchProfileRequested', () {
    blocTest<ProfileBloc, ProfileState>(
      'emits [ProfileLoading, ProfileLoaded] when employee profile exists',
      build: () {
        when(() => mockGetProfileUseCase())
            .thenAnswer((_) async => Result.success(testEmployee));
        return profileBloc;
      },
      act: (bloc) => bloc.add(const FetchProfileRequested()),
      expect: () => [
        const ProfileLoading(),
        ProfileLoaded(employee: testEmployee, hasLinkedEmployee: true),
      ],
    );

    blocTest<ProfileBloc, ProfileState>(
      'emits [ProfileLoading, ProfileLoaded(employee: null)] when account has no linked employee profile (404)',
      build: () {
        when(() => mockGetProfileUseCase()).thenAnswer(
          (_) async => const Result.failure(
            ServerFailure('Employee profile not found', statusCode: 404),
          ),
        );
        return profileBloc;
      },
      act: (bloc) => bloc.add(const FetchProfileRequested()),
      expect: () => [
        const ProfileLoading(),
        const ProfileLoaded(employee: null, hasLinkedEmployee: false),
      ],
    );

    blocTest<ProfileBloc, ProfileState>(
      'emits [ProfileLoading, ProfileError] when API request fails with 500 error',
      build: () {
        when(() => mockGetProfileUseCase()).thenAnswer(
          (_) async => const Result.failure(
            ServerFailure('Internal server error', statusCode: 500),
          ),
        );
        return profileBloc;
      },
      act: (bloc) => bloc.add(const FetchProfileRequested()),
      expect: () => [
        const ProfileLoading(),
        const ProfileError('Internal server error'),
      ],
    );
  });

  group('ProfileRefreshed', () {
    blocTest<ProfileBloc, ProfileState>(
      'reloads profile data on refresh trigger',
      build: () {
        when(() => mockGetProfileUseCase())
            .thenAnswer((_) async => Result.success(testEmployee));
        return profileBloc;
      },
      act: (bloc) => bloc.add(const ProfileRefreshed()),
      expect: () => [
        ProfileLoaded(employee: testEmployee, hasLinkedEmployee: true),
      ],
    );
  });
}
