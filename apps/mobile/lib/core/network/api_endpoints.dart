/// Central API endpoint definitions matching FastAPI router paths.
class ApiEndpoints {
  // Authentication routes (/api/v1/auth)
  static const String login = '/api/v1/auth/login';
  static const String refresh = '/api/v1/auth/refresh';
  static const String logout = '/api/v1/auth/logout';
  static const String authMe = '/api/v1/auth/me';

  // Employee routes (/api/v1/employees)
  static const String employeeMe = '/api/v1/employees/me';
  static const String employeeWorkplaces = '/api/v1/employees/me/workplaces';

  // Attendance routes (/api/v1/attendance)
  static const String attendancePunch = '/api/v1/attendance/punch';
  static const String attendanceDays = '/api/v1/attendance/days';
  static const String attendanceEvents = '/api/v1/attendance/events';
  static const String attendancePolicyMe = '/api/v1/attendance/policy/me';
  static const String verifyCoordinates =
      '/api/v1/employees/me/workplaces/verify-coordinates';
  static const String verifyWifi =
      '/api/v1/employees/me/workplaces/verify-wifi';

  // Shift routes (/api/v1/shifts)
  static const String shiftAssignments = '/api/v1/shifts/assignments';

  // Offline Attendance Conflict routes (/api/v1/attendance)
  static const String offlineConflictsSubmit =
      '/api/v1/attendance/offline-conflicts/submit';
  static const String offlineConflictsMy =
      '/api/v1/attendance/offline-conflicts/my';

  // Device routes (/api/v1/devices)
  static const String devicesRegister = '/api/v1/devices/register';
  static const String devicesMe = '/api/v1/devices/me';

  // Leave routes (/api/v1/leave)
  static const String leaveBalancesMy = '/api/v1/leave/balances/my';
  static const String leaveRequests = '/api/v1/leave/requests';
  static const String leaveRequestsMy = '/api/v1/leave/requests/my';
  static String leaveRequestDetail(String id) => '/api/v1/leave/requests/$id';
  static String leaveRequestCancel(String id) =>
      '/api/v1/leave/requests/$id/cancel';
  static String leaveRequestDecision(String id) =>
      '/api/v1/leave/requests/$id/decision';
  static const String leaveTypes = '/api/v1/leave/types';

  // Holiday routes (/api/v1/holidays)
  static const String holidaysUpcoming = '/api/v1/holidays/upcoming';
}
