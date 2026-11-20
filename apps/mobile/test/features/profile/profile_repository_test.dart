import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/features/profile/data/datasources/profile_remote_data_source.dart';
import 'package:mobile/features/profile/data/models/employee_model.dart';
import 'package:mobile/features/profile/data/repositories/profile_repository_impl.dart';
import 'package:mocktail/mocktail.dart';

class MockProfileRemoteDataSource extends Mock
    implements ProfileRemoteDataSource {}

void main() {
  late MockProfileRemoteDataSource mockRemoteDataSource;
  late ProfileRepositoryImpl repository;

  final testEmployeeModel = EmployeeModel(
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
    mockRemoteDataSource = MockProfileRemoteDataSource();
    repository = ProfileRepositoryImpl(mockRemoteDataSource);
  });

  group('ProfileRepositoryImpl.getMyEmployeeProfile', () {
    test('returns Employee entity on success', () async {
      when(() => mockRemoteDataSource.getMyEmployee())
          .thenAnswer((_) async => testEmployeeModel);

      final result = await repository.getMyEmployeeProfile();

      expect(result.isSuccess, isTrue);
      expect(result.data, testEmployeeModel);
      expect(result.data?.fullName, 'Alex Johnson');
    });

    test('returns ServerFailure with 404 when employee profile is not found',
        () async {
      when(() => mockRemoteDataSource.getMyEmployee()).thenThrow(
        const ServerException('Employee profile not found', statusCode: 404),
      );

      final result = await repository.getMyEmployeeProfile();

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<ServerFailure>());
      expect(result.failure?.statusCode, 404);
    });

    test('returns NetworkFailure on connectivity issue', () async {
      when(() => mockRemoteDataSource.getMyEmployee())
          .thenThrow(const NetworkException());

      final result = await repository.getMyEmployeeProfile();

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<NetworkFailure>());
    });
  });
}
