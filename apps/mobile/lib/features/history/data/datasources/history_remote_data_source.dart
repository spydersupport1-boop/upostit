import 'package:intl/intl.dart';
import 'package:mobile/core/network/api_client.dart';
import 'package:mobile/core/network/api_endpoints.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/shift_assignment_model.dart';

/// Contract for remote attendance history, projection days, and shift scheduling.
abstract class HistoryRemoteDataSource {
  /// Fetches daily attendance projections for a specific calendar month.
  Future<List<AttendanceDayModel>> getMonthlyAttendanceDays({
    required int year,
    required int month,
  });

  /// Fetches the raw attendance presence event ledger for a specific calendar date.
  Future<List<AttendanceEventModel>> getDayAuditEvents({
    required DateTime date,
  });

  /// Fetches the derived attendance summary projection for a single day.
  Future<AttendanceDayModel?> getDayProjection({
    required DateTime date,
  });

  /// Fetches all active and upcoming shift assignments for the current employee.
  Future<List<ShiftAssignmentModel>> getShiftAssignments([String? dateStr]);
}

/// Implementation backed by the authenticated [ApiClient].
class HistoryRemoteDataSourceImpl implements HistoryRemoteDataSource {
  final ApiClient _apiClient;

  HistoryRemoteDataSourceImpl(this._apiClient);

  @override
  Future<List<AttendanceDayModel>> getMonthlyAttendanceDays({
    required int year,
    required int month,
  }) async {
    final start = DateTime(year, month, 1);
    final end = DateTime(year, month + 1, 0); // Last day of month
    final startStr = DateFormat('yyyy-MM-dd').format(start);
    final endStr = DateFormat('yyyy-MM-dd').format(end);

    final response = await _apiClient.get(
      ApiEndpoints.attendanceDays,
      queryParameters: {
        'start_date': startStr,
        'end_date': endStr,
        'limit': 100,
      },
    );

    final dynamic rawData = response.data;
    final List<dynamic> items;
    if (rawData is Map<String, dynamic>) {
      items = (rawData['items'] as List<dynamic>?) ?? [];
    } else if (rawData is List) {
      items = rawData;
    } else {
      items = [];
    }
    return items
        .map((e) => AttendanceDayModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<List<AttendanceEventModel>> getDayAuditEvents({
    required DateTime date,
  }) async {
    final startOfDay = DateTime(date.year, date.month, date.day, 0, 0, 0);
    final endOfDay = DateTime(date.year, date.month, date.day, 23, 59, 59);

    final response = await _apiClient.get(
      ApiEndpoints.attendanceEvents,
      queryParameters: {
        'start_date': startOfDay.toUtc().toIso8601String(),
        'end_date': endOfDay.toUtc().toIso8601String(),
        'limit': 100,
      },
    );

    final dynamic rawData = response.data;
    final List<dynamic> items;
    if (rawData is Map<String, dynamic>) {
      items = (rawData['items'] as List<dynamic>?) ?? [];
    } else if (rawData is List) {
      items = rawData;
    } else {
      items = [];
    }
    final events = items
        .map((e) => AttendanceEventModel.fromJson(e as Map<String, dynamic>))
        .toList();
    events.sort((a, b) => a.effectiveAt.compareTo(b.effectiveAt));
    return events;
  }

  @override
  Future<AttendanceDayModel?> getDayProjection({
    required DateTime date,
  }) async {
    final dateStr = DateFormat('yyyy-MM-dd').format(date);
    final response = await _apiClient.get(
      ApiEndpoints.attendanceDays,
      queryParameters: {
        'start_date': dateStr,
        'end_date': dateStr,
        'limit': 1,
      },
    );

    final dynamic rawData = response.data;
    final List<dynamic> items;
    if (rawData is Map<String, dynamic>) {
      items = (rawData['items'] as List<dynamic>?) ?? [];
    } else if (rawData is List) {
      items = rawData;
    } else {
      items = [];
    }
    if (items.isEmpty) return null;
    return AttendanceDayModel.fromJson(items.first as Map<String, dynamic>);
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
}
