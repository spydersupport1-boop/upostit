import '../../../../core/errors/result.dart';
import '../entities/leave_balance.dart';
import '../entities/leave_request.dart';
import '../entities/leave_type.dart';
import '../entities/upcoming_holiday.dart';

abstract class LeaveRepository {
  Future<Result<List<LeaveBalance>>> getMyBalances();
  Future<Result<List<LeaveType>>> getLeaveTypes();
  Future<Result<LeaveRequest>> applyLeave({
    required String leaveTypeId,
    required String startDate,
    required String endDate,
    bool isHalfDay = false,
    String? halfDayPeriod,
    required String reason,
  });
  Future<Result<List<LeaveRequest>>> getMyLeaveRequests({
    String? status,
    int limit = 50,
  });
  Future<Result<LeaveRequest>> getLeaveRequestDetail(String id);
  Future<Result<LeaveRequest>> cancelLeaveRequest(String id, {String? reason});
  Future<Result<List<LeaveRequest>>> getSupervisorQueue({
    String? status,
    int limit = 100,
  });
  Future<Result<LeaveRequest>> adjudicateLeaveRequest(
    String id, {
    required String action,
    String? reason,
  });
  Future<Result<List<UpcomingHoliday>>> getUpcomingHolidays({int limit = 15});
}

