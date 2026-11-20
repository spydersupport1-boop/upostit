import '../../../../core/errors/app_exception.dart';
import '../../../../core/errors/failure.dart';
import '../../../../core/errors/result.dart';
import '../../domain/entities/leave_balance.dart';
import '../../domain/entities/leave_request.dart';
import '../../domain/entities/leave_type.dart';
import '../../domain/entities/upcoming_holiday.dart';
import '../../domain/repositories/leave_repository.dart';
import '../datasources/leave_remote_data_source.dart';

class LeaveRepositoryImpl implements LeaveRepository {
  final LeaveRemoteDataSource remoteDataSource;

  const LeaveRepositoryImpl(this.remoteDataSource);

  Failure _mapExceptionToFailure(Object e) {
    if (e is NetworkException) {
      return const NetworkFailure();
    }
    if (e is AuthException) {
      return AuthFailure(
        e.message,
        statusCode: e.statusCode ?? 401,
        isSessionExpired: e.isSessionExpired,
        isReuseDetected: e.isReuseDetected,
      );
    }
    if (e is ServerException) {
      return ServerFailure(e.message, statusCode: e.statusCode);
    }
    return ServerFailure(e.toString());
  }

  @override
  Future<Result<List<LeaveBalance>>> getMyBalances() async {
    try {
      final balances = await remoteDataSource.getMyBalances();
      return Result.success(balances);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<List<LeaveType>>> getLeaveTypes() async {
    try {
      final types = await remoteDataSource.getLeaveTypes();
      return Result.success(types);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<LeaveRequest>> applyLeave({
    required String leaveTypeId,
    required String startDate,
    required String endDate,
    bool isHalfDay = false,
    String? halfDayPeriod,
    required String reason,
  }) async {
    try {
      final request = await remoteDataSource.applyLeave(
        leaveTypeId: leaveTypeId,
        startDate: startDate,
        endDate: endDate,
        isHalfDay: isHalfDay,
        halfDayPeriod: halfDayPeriod,
        reason: reason,
      );
      return Result.success(request);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<List<LeaveRequest>>> getMyLeaveRequests({
    String? status,
    int limit = 50,
  }) async {
    try {
      final requests = await remoteDataSource.getMyLeaveRequests(
        status: status,
        limit: limit,
      );
      return Result.success(requests);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<LeaveRequest>> getLeaveRequestDetail(String id) async {
    try {
      final request = await remoteDataSource.getLeaveRequestDetail(id);
      return Result.success(request);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<LeaveRequest>> cancelLeaveRequest(String id, {String? reason}) async {
    try {
      final request = await remoteDataSource.cancelLeaveRequest(id, reason: reason);
      return Result.success(request);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<List<LeaveRequest>>> getSupervisorQueue({
    String? status,
    int limit = 100,
  }) async {
    try {
      final requests = await remoteDataSource.getSupervisorQueue(
        status: status,
        limit: limit,
      );
      return Result.success(requests);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<LeaveRequest>> adjudicateLeaveRequest(
    String id, {
    required String action,
    String? reason,
  }) async {
    try {
      final request = await remoteDataSource.adjudicateLeaveRequest(
        id,
        action: action,
        reason: reason,
      );
      return Result.success(request);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }

  @override
  Future<Result<List<UpcomingHoliday>>> getUpcomingHolidays({int limit = 15}) async {
    try {
      final holidays = await remoteDataSource.getUpcomingHolidays(limit: limit);
      return Result.success(holidays);
    } catch (e) {
      return Result.failure(_mapExceptionToFailure(e));
    }
  }
}

