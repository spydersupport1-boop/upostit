import '../../../../core/errors/result.dart';
import '../entities/employee.dart';

/// Contract for employee profile data operations.
abstract class ProfileRepository {
  /// Fetches the authenticated user's employee profile from /api/v1/employees/me.
  Future<Result<Employee>> getMyEmployeeProfile();
}
