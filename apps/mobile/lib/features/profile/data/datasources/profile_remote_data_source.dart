import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/employee_model.dart';

abstract class ProfileRemoteDataSource {
  Future<EmployeeModel> getMyEmployee();
}

class ProfileRemoteDataSourceImpl implements ProfileRemoteDataSource {
  final ApiClient _apiClient;

  ProfileRemoteDataSourceImpl(this._apiClient);

  @override
  Future<EmployeeModel> getMyEmployee() async {
    final response = await _apiClient.get(ApiEndpoints.employeeMe);
    return EmployeeModel.fromJson(response.data as Map<String, dynamic>);
  }
}
