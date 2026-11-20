import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../models/leave_balance_model.dart';
import '../models/leave_request_model.dart';
import '../models/leave_type_model.dart';
import '../models/upcoming_holiday_model.dart';

abstract class LeaveRemoteDataSource {
  Future<List<LeaveBalanceModel>> getMyBalances();
  Future<List<LeaveTypeModel>> getLeaveTypes();
  Future<LeaveRequestModel> applyLeave({
    required String leaveTypeId,
    required String startDate,
    required String endDate,
    bool isHalfDay = false,
    String? halfDayPeriod,
    required String reason,
  });
  Future<List<LeaveRequestModel>> getMyLeaveRequests({
    String? status,
    int limit = 50,
  });
  Future<LeaveRequestModel> getLeaveRequestDetail(String id);
  Future<LeaveRequestModel> cancelLeaveRequest(String id, {String? reason});
  Future<List<LeaveRequestModel>> getSupervisorQueue({
    String? status,
    int limit = 100,
  });
  Future<LeaveRequestModel> adjudicateLeaveRequest(
    String id, {
    required String action,
    String? reason,
  });
  Future<List<UpcomingHolidayModel>> getUpcomingHolidays({int limit = 15});
}

class LeaveRemoteDataSourceImpl implements LeaveRemoteDataSource {
  final ApiClient apiClient;

  const LeaveRemoteDataSourceImpl(this.apiClient);

  @override
  Future<List<LeaveBalanceModel>> getMyBalances() async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.leaveBalancesMy,
    );
    final data = response.data;
    final list = data?['items'] ?? data?['data'];
    if (list is List) {
      return list
          .map((item) =>
              LeaveBalanceModel.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<List<LeaveTypeModel>> getLeaveTypes() async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.leaveTypes,
      queryParameters: {'is_active': true, 'limit': 100},
    );
    final data = response.data;
    final list = data?['items'] ?? data?['data'];
    if (list is List) {
      return list
          .map((item) => LeaveTypeModel.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<LeaveRequestModel> applyLeave({
    required String leaveTypeId,
    required String startDate,
    required String endDate,
    bool isHalfDay = false,
    String? halfDayPeriod,
    required String reason,
  }) async {
    final response = await apiClient.post<Map<String, dynamic>>(
      ApiEndpoints.leaveRequests,
      data: {
        'leave_type_id': leaveTypeId,
        'start_date': startDate,
        'end_date': endDate,
        'is_half_day': isHalfDay,
        if (isHalfDay && halfDayPeriod != null)
          'half_day_period': halfDayPeriod,
        'reason': reason,
      },
    );
    return LeaveRequestModel.fromJson(response.data!);
  }

  @override
  Future<List<LeaveRequestModel>> getMyLeaveRequests({
    String? status,
    int limit = 50,
  }) async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.leaveRequestsMy,
      queryParameters: {
        if (status != null && status != 'ALL') 'status': status,
        'limit': limit,
      },
    );
    final data = response.data;
    final list = data?['items'] ?? data?['data'];
    if (list is List) {
      return list
          .map((item) => LeaveRequestModel.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<LeaveRequestModel> getLeaveRequestDetail(String id) async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.leaveRequestDetail(id),
    );
    return LeaveRequestModel.fromJson(response.data!);
  }

  @override
  Future<LeaveRequestModel> cancelLeaveRequest(String id, {String? reason}) async {
    final response = await apiClient.post<Map<String, dynamic>>(
      ApiEndpoints.leaveRequestCancel(id),
      data: {
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      },
    );
    return LeaveRequestModel.fromJson(response.data!);
  }

  @override
  Future<List<LeaveRequestModel>> getSupervisorQueue({
    String? status,
    int limit = 100,
  }) async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.leaveRequests,
      queryParameters: {
        if (status != null && status != 'ALL') 'status': status,
        'limit': limit,
      },
    );
    final data = response.data;
    final list = data?['items'] ?? data?['data'];
    if (list is List) {
      return list
          .map((item) => LeaveRequestModel.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<LeaveRequestModel> adjudicateLeaveRequest(
    String id, {
    required String action,
    String? reason,
  }) async {
    final response = await apiClient.post<Map<String, dynamic>>(
      ApiEndpoints.leaveRequestDecision(id),
      data: {
        'action': action,
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      },
    );
    return LeaveRequestModel.fromJson(response.data!);
  }

  @override
  Future<List<UpcomingHolidayModel>> getUpcomingHolidays({int limit = 15}) async {
    final response = await apiClient.get<Map<String, dynamic>>(
      ApiEndpoints.holidaysUpcoming,
      queryParameters: {'limit': limit},
    );
    final data = response.data;
    final list = data?['items'] ?? data?['data'];
    if (list is List) {
      return list
          .map((item) =>
              UpcomingHolidayModel.fromJson(item as Map<String, dynamic>))
          .toList();
    }
    return [];
  }
}
