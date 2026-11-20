import '../../../../core/errors/result.dart';
import '../entities/employee.dart';
import '../repositories/profile_repository.dart';

class GetProfileUseCase {
  final ProfileRepository _repository;

  GetProfileUseCase(this._repository);

  Future<Result<Employee>> call() {
    return _repository.getMyEmployeeProfile();
  }
}
