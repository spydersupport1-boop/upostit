import '../../../../core/errors/result.dart';
import '../entities/attendance_dashboard.dart';
import '../entities/attendance_event.dart';
import '../entities/attendance_policy.dart';
import '../entities/punch_result.dart';
import '../entities/today_shift.dart';
import '../entities/wifi_verification_result.dart';

/// Contract for attendance data operations and business rules.
abstract class AttendanceRepository {
  /// Submits an attendance presence punch with a client-generated idempotency key.
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
  });

  /// Verifies connected Wi-Fi presence against an assigned workplace.
  Future<Result<WifiVerificationResult>> verifyWorkplaceWifi({
    required String locationId,
    String? bssid,
    String? ssid,
    DateTime? deviceReportedAt,
    String signalStatus = 'AVAILABLE',
    String? platform,
  });

  /// Fetches the active attendance policy configuration for the current employee's company.
  Future<Result<AttendancePolicy>> getActivePolicy();

  /// Fetches the complete attendance dashboard for today based on server ledger and projections.
  Future<Result<AttendanceDashboard>> getTodayAttendanceDashboard();

  /// Fetches the active and upcoming shift assignments for the authenticated employee.
  Future<Result<List<TodayShift>>> getShiftSchedule();
}
