import 'package:dio/dio.dart';
import 'package:intl/intl.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../domain/entities/attendance_dashboard.dart';
import '../../domain/entities/attendance_event.dart';
import '../../domain/entities/attendance_policy.dart';
import '../../domain/entities/attendance_status.dart';
import '../../domain/entities/punch_result.dart';
import '../../domain/entities/today_shift.dart';
import '../../domain/entities/wifi_verification_result.dart';
import '../../domain/repositories/attendance_repository.dart';
import '../datasources/attendance_remote_data_source.dart';
import '../models/employee_wifi_verify_model.dart';
import '../models/punch_request_model.dart';

/// Implementation of [AttendanceRepository] backed by [AttendanceRemoteDataSource].
class AttendanceRepositoryImpl implements AttendanceRepository {
  final AttendanceRemoteDataSource remoteDataSource;

  AttendanceRepositoryImpl(this.remoteDataSource);

  @override
  Future<Result<PunchResult>> recordPunch({
    required AttendanceEventType eventType,
    required String idempotencyKey,
    DateTime? deviceReportedAt,
    String? locationId,
    double? latitude,
    double? longitude,
    double? accuracyMeters,
    String? wifiBssid,
    String? wifiSsid,
    String? wifiSignalStatus,
    String? deviceId,
    bool? isMockLocation,
    DateTime? locationCapturedAt,
    Map<String, dynamic> metadata = const {},
  }) async {
    try {
      final request = PunchRequestModel(
        eventType: eventType,
        idempotencyKey: idempotencyKey,
        deviceReportedAt: deviceReportedAt ?? DateTime.now().toUtc(),
        locationId: locationId,
        latitude: latitude,
        longitude: longitude,
        accuracyMeters: accuracyMeters,
        wifiBssid: wifiBssid,
        wifiSsid: wifiSsid,
        wifiSignalStatus: wifiSignalStatus,
        deviceId: deviceId ?? 'mobile-app-client',
        isMockLocation: isMockLocation,
        locationCapturedAt: locationCapturedAt,
        metadata: metadata,
      );

      final response = await remoteDataSource.recordPunch(request);
      return Result.success(response);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<WifiVerificationResult>> verifyWorkplaceWifi({
    required String locationId,
    String? bssid,
    String? ssid,
    DateTime? deviceReportedAt,
    String signalStatus = 'AVAILABLE',
    String? platform,
  }) async {
    try {
      final request = EmployeeWifiVerifyRequestModel(
        locationId: locationId,
        bssid: bssid,
        ssid: ssid,
        deviceReportedAt: deviceReportedAt ?? DateTime.now().toUtc(),
        signalStatus: signalStatus,
        platform: platform,
      );

      final response = await remoteDataSource.verifyWorkplaceWifi(request);
      return Result.success(response);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<AttendancePolicy>> getActivePolicy() async {
    try {
      final policy = await remoteDataSource.getMyAttendancePolicy();
      return Result.success(policy);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<AttendanceDashboard>> getTodayAttendanceDashboard() async {
    try {
      final now = DateTime.now();
      final dateStr = DateFormat('yyyy-MM-dd').format(now);

      // Query window encompassing local day in UTC
      final startOfDay = DateTime(now.year, now.month, now.day, 0, 0, 0);
      final endOfDay = DateTime(now.year, now.month, now.day, 23, 59, 59);

      // 1. Fetch daily projection and raw event ledger
      final day = await remoteDataSource.getAttendanceDay(dateStr);
      final events = await remoteDataSource.getAttendanceEvents(
        startDate: startOfDay,
        endDate: endOfDay,
      );

      // Sort events chronologically by effectiveAt
      events.sort((a, b) => a.effectiveAt.compareTo(b.effectiveAt));

      // 2. Fetch shift assignment, workplaces, and attendance policy with graceful degradation
      final shifts = await _safeFetchShifts(dateStr);
      final workplaces = await _safeFetchWorkplaces();
      final policy = await _safeFetchPolicy();

      final assignedShift = shifts.isNotEmpty ? shifts.first : null;
      final assignedWorkplace = workplaces.isNotEmpty
          ? workplaces.firstWhere((w) => w.isPrimary,
              orElse: () => workplaces.first)
          : null;

      // 3. Derive Attendance Status strictly from server-confirmed events
      final lastEvent = events.isNotEmpty ? events.last : null;
      final AttendanceStatus status;

      if (lastEvent == null) {
        status = AttendanceStatus.notCheckedIn;
      } else {
        switch (lastEvent.eventType) {
          case AttendanceEventType.checkIn:
          case AttendanceEventType.breakEnd:
            status = AttendanceStatus.working;
            break;
          case AttendanceEventType.breakStart:
            status = AttendanceStatus.onBreak;
            break;
          case AttendanceEventType.checkOut:
            status = AttendanceStatus.completed;
            break;
        }
      }

      // 4. Calculate live working and break durations anchored to server timestamps
      var workingSeconds = (day?.netWorkingMinutes ?? 0) * 60;
      var breakSeconds = (day?.totalBreakMinutes ?? 0) * 60;

      final nowUtc = DateTime.now().toUtc();
      if (lastEvent != null) {
        final secondsSinceLastEvent =
            nowUtc.difference(lastEvent.effectiveAt.toUtc()).inSeconds;
        final nonNegativeDiff =
            secondsSinceLastEvent > 0 ? secondsSinceLastEvent : 0;

        if (status == AttendanceStatus.working) {
          workingSeconds += nonNegativeDiff;
        } else if (status == AttendanceStatus.onBreak) {
          breakSeconds += nonNegativeDiff;
        }
      }

      final dashboard = AttendanceDashboard(
        status: status,
        todayDay: day,
        todayEvents: events,
        lastEvent: lastEvent,
        shift: assignedShift,
        workplace: assignedWorkplace,
        policy: policy,
        workingDuration: Duration(seconds: workingSeconds),
        breakDuration: Duration(seconds: breakSeconds),
      );

      return Result.success(dashboard);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  @override
  Future<Result<List<TodayShift>>> getShiftSchedule() async {
    try {
      final shifts = await remoteDataSource.getShiftAssignments();
      return Result.success(shifts);
    } on DioException catch (dioError) {
      return Result.failure(_mapDioError(dioError));
    } catch (e) {
      return Result.failure(ServerFailure(e.toString()));
    }
  }

  Future<AttendancePolicy?> _safeFetchPolicy() async {
    try {
      return await remoteDataSource.getMyAttendancePolicy();
    } catch (_) {
      return AttendancePolicy.defaultManual();
    }
  }

  Future<List<dynamic>> _safeFetchShifts(String dateStr) async {
    try {
      return await remoteDataSource.getShiftAssignments(dateStr);
    } catch (_) {
      return const [];
    }
  }

  Future<List<dynamic>> _safeFetchWorkplaces() async {
    try {
      return await remoteDataSource.getMyWorkplaces();
    } catch (_) {
      return const [];
    }
  }

  Failure _mapDioError(DioException dioError) {
    if (dioError.type == DioExceptionType.connectionTimeout ||
        dioError.type == DioExceptionType.sendTimeout ||
        dioError.type == DioExceptionType.receiveTimeout ||
        dioError.type == DioExceptionType.connectionError) {
      return const NetworkFailure(
          'Unable to connect to server. Please check your network connection.');
    }

    final statusCode = dioError.response?.statusCode;
    final responseData = dioError.response?.data;
    String errorMessage = 'A server error occurred. Please try again.';

    if (responseData is Map<String, dynamic>) {
      if (responseData['detail'] != null) {
        final detail = responseData['detail'];
        if (detail is String) {
          errorMessage = detail;
        } else if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] != null) {
            errorMessage = first['msg'].toString();
          }
        }
      } else if (responseData['message'] != null) {
        errorMessage = responseData['message'].toString();
      }
    }

    return ServerFailure(errorMessage, statusCode: statusCode);
  }
}
