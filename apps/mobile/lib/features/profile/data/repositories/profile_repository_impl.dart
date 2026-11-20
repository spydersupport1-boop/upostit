import '../../../../core/errors/app_exception.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../domain/entities/employee.dart';
import '../../domain/repositories/profile_repository.dart';
import '../datasources/profile_remote_data_source.dart';

class ProfileRepositoryImpl implements ProfileRepository {
  final ProfileRemoteDataSource _remoteDataSource;

  ProfileRepositoryImpl(this._remoteDataSource);

  @override
  Future<Result<Employee>> getMyEmployeeProfile() async {
    try {
      final employee = await _remoteDataSource.getMyEmployee();
      return Result.success(employee);
    } on NetworkException catch (e) {
      return Result.failure(NetworkFailure(e.message));
    } on AuthException catch (e) {
      return Result.failure(
        AuthFailure(
          e.message,
          statusCode: e.statusCode,
          isSessionExpired: e.isSessionExpired,
          isReuseDetected: e.isReuseDetected,
        ),
      );
    } on ServerException catch (e) {
      return Result.failure(ServerFailure(e.message, statusCode: e.statusCode));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }
}
