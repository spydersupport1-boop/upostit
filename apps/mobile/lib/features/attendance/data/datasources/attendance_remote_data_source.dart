import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_endpoints.dart';
import '../../../sync/data/models/batch_sync_models.dart';
import '../../../sync/data/models/employee_conflict_incident_list_model.dart';
import '../../../sync/data/models/offline_conflict_bundle_submit_request_model.dart';
import '../../../sync/data/models/offline_conflict_incident_model.dart';
import '../models/attendance_day_model.dart';
import '../models/attendance_event_model.dart';
import '../models/attendance_policy_model.dart';
import '../models/employee_wifi_verify_model.dart';
import '../models/employee_workplace_model.dart';
import '../models/punch_request_model.dart';
import '../models/punch_response_model.dart';
import '../models/shift_assignment_model.dart';

/// Contract for attendance remote HTTP data operations.
abstract class AttendanceRemoteDataSource {
  /// Submits an attendance presence punch to the append-only ledger.
  Future<PunchResponseModel> recordPunch(PunchRequestModel request);

  /// Retrieves the active attendance policy configuration for the current employee's company.
  Future<AttendancePolicyModel> getMyAttendancePolicy();

  /// Retrieves the derived daily attendance summary record for a specific date (YYYY-MM-DD).
  Future<AttendanceDayModel?> getAttendanceDay(String dateStr);

  /// Retrieves the raw attendance presence events for the authenticated employee within a time window.
  Future<List<AttendanceEventModel>> getAttendanceEvents({
    required DateTime startDate,
    required DateTime endDate,
  });

  /// Retrieves the active or upcoming shift assignments for the authenticated employee.
  Future<List<ShiftAssignmentModel>> getShiftAssignments([String? dateStr]);

  /// Retrieves the workplace assignments for the authenticated employee.
  Future<List<EmployeeWorkplaceModel>> getMyWorkplaces();

  /// Verifies connected Wi-Fi presence against an assigned workplace.
  Future<EmployeeWifiVerifyResponseModel> verifyWorkplaceWifi(
      EmployeeWifiVerifyRequestModel request);

  /// Submits an offline sequence conflict bundle for supervisor review.
  Future<OfflineConflictIncidentModel> submitConflictBundle(
      OfflineConflictBundleSubmitRequestModel request);

  /// Retrieves the list of submitted conflict incidents for the current employee.
  Future<EmployeeConflictIncidentListModel> getMyConflictIncidents({
    String? status,
    int limit = 50,
  });

  /// Submits a batch of offline attendance events to the batch sync protocol.
  Future<AttendanceBatchSyncResponseModel> syncBatch(
      AttendanceBatchSyncRequestModel request);
}

/// Implementation of [AttendanceRemoteDataSource] using [ApiClient].
class AttendanceRemoteDataSourceImpl implements AttendanceRemoteDataSource {
  final ApiClient _apiClient;

  AttendanceRemoteDataSourceImpl(this._apiClient);

  @override
  Future<EmployeeWifiVerifyResponseModel> verifyWorkplaceWifi(
      EmployeeWifiVerifyRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.verifyWifi,
      data: request.toJson(),
    );
    return EmployeeWifiVerifyResponseModel.fromJson(
        response.data as Map<String, dynamic>);
  }

  @override
  Future<PunchResponseModel> recordPunch(PunchRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.attendancePunch,
      data: request.toJson(),
    );
    return PunchResponseModel.fromJson(response.data as Map<String, dynamic>);
  }

  @override
  Future<AttendancePolicyModel> getMyAttendancePolicy() async {
    final response = await _apiClient.get(ApiEndpoints.attendancePolicyMe);
    return AttendancePolicyModel.fromJson(
        response.data as Map<String, dynamic>);
  }

  @override
  Future<AttendanceDayModel?> getAttendanceDay(String dateStr) async {
    final response = await _apiClient.get(
      ApiEndpoints.attendanceDays,
      queryParameters: {
        'start_date': dateStr,
        'end_date': dateStr,
        'limit': 1,
      },
    );

    final data = response.data as Map<String, dynamic>;
    final items = (data['items'] as List<dynamic>?) ?? [];
    if (items.isEmpty) {
      return null;
    }
    return AttendanceDayModel.fromJson(items.first as Map<String, dynamic>);
  }

  @override
  Future<List<AttendanceEventModel>> getAttendanceEvents({
    required DateTime startDate,
    required DateTime endDate,
  }) async {
    final response = await _apiClient.get(
      ApiEndpoints.attendanceEvents,
      queryParameters: {
        'start_date': startDate.toUtc().toIso8601String(),
        'end_date': endDate.toUtc().toIso8601String(),
        'limit': 50,
      },
    );

    final data = response.data as Map<String, dynamic>;
    final items = (data['items'] as List<dynamic>?) ?? [];
    return items
        .map((e) => AttendanceEventModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<List<ShiftAssignmentModel>> getShiftAssignments(
      [String? dateStr]) async {
    final response = await _apiClient.get(
      ApiEndpoints.shiftAssignments,
      queryParameters: {
        if (dateStr != null) 'effective_date': dateStr,
      },
    );

    if (response.data is List) {
      final list = response.data as List<dynamic>;
      return list
          .map((e) => ShiftAssignmentModel.fromJson(e as Map<String, dynamic>))
          .toList();
    } else if (response.data is Map<String, dynamic>) {
      final data = response.data as Map<String, dynamic>;
      final items = (data['items'] as List<dynamic>?) ?? [];
      return items
          .map((e) => ShiftAssignmentModel.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<List<EmployeeWorkplaceModel>> getMyWorkplaces() async {
    final response = await _apiClient.get(
      ApiEndpoints.employeeWorkplaces,
      queryParameters: {
        'is_current': true,
      },
    );

    final data = response.data as Map<String, dynamic>;
    final items = (data['items'] as List<dynamic>?) ?? [];
    return items
        .map((e) => EmployeeWorkplaceModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<OfflineConflictIncidentModel> submitConflictBundle(
      OfflineConflictBundleSubmitRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.offlineConflictsSubmit,
      data: request.toJson(),
    );
    return OfflineConflictIncidentModel.fromJson(
      response.data as Map<String, dynamic>,
    );
  }

  @override
  Future<EmployeeConflictIncidentListModel> getMyConflictIncidents({
    String? status,
    int limit = 50,
  }) async {
    final response = await _apiClient.get(
      ApiEndpoints.offlineConflictsMy,
      queryParameters: {
        if (status != null) 'status': status,
        'limit': limit,
      },
    );
    return EmployeeConflictIncidentListModel.fromJson(
      response.data as Map<String, dynamic>,
    );
  }

  @override
  Future<AttendanceBatchSyncResponseModel> syncBatch(
      AttendanceBatchSyncRequestModel request) async {
    final response = await _apiClient.post(
      ApiEndpoints.syncBatch,
      data: request.toJson(),
    );
    return AttendanceBatchSyncResponseModel.fromJson(
      response.data as Map<String, dynamic>,
    );
  }
}
