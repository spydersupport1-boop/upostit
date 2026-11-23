import 'package:equatable/equatable.dart';
import '../../domain/entities/leave_balance.dart';
import '../../domain/entities/leave_request.dart';
import '../../domain/entities/leave_type.dart';
import '../../domain/entities/upcoming_holiday.dart';

class LeaveState extends Equatable {
  final bool isLoading;
  final bool isSubmitting;
  final List<LeaveBalance> balances;
  final List<LeaveType> leaveTypes;
  final List<LeaveRequest> myRequests;
  final List<UpcomingHoliday> upcomingHolidays;
  final List<LeaveRequest> supervisorQueue;
  final String? statusFilter;
  final String? successNotice;
  final String? errorMessage;
  final LeaveRequest? lastSubmittedRequest;

  const LeaveState({
    this.isLoading = false,
    this.isSubmitting = false,
    this.balances = const [],
    this.leaveTypes = const [],
    this.myRequests = const [],
    this.upcomingHolidays = const [],
    this.supervisorQueue = const [],
    this.statusFilter,
    this.successNotice,
    this.errorMessage,
    this.lastSubmittedRequest,
  });

  factory LeaveState.initial() => const LeaveState();

  LeaveState copyWith({
    bool? isLoading,
    bool? isSubmitting,
    List<LeaveBalance>? balances,
    List<LeaveType>? leaveTypes,
    List<LeaveRequest>? myRequests,
    List<UpcomingHoliday>? upcomingHolidays,
    List<LeaveRequest>? supervisorQueue,
    String? statusFilter,
    String? successNotice,
    String? errorMessage,
    LeaveRequest? lastSubmittedRequest,
    bool clearStatusFilter = false,
    bool clearNotices = false,
  }) {
    return LeaveState(
      isLoading: isLoading ?? this.isLoading,
      isSubmitting: isSubmitting ?? this.isSubmitting,
      balances: balances ?? this.balances,
      leaveTypes: leaveTypes ?? this.leaveTypes,
      myRequests: myRequests ?? this.myRequests,
      upcomingHolidays: upcomingHolidays ?? this.upcomingHolidays,
      supervisorQueue: supervisorQueue ?? this.supervisorQueue,
      statusFilter:
          clearStatusFilter ? null : (statusFilter ?? this.statusFilter),
      successNotice:
          clearNotices ? null : (successNotice ?? this.successNotice),
      errorMessage: clearNotices ? null : (errorMessage ?? this.errorMessage),
      lastSubmittedRequest: lastSubmittedRequest ?? this.lastSubmittedRequest,
    );
  }

  @override
  List<Object?> get props => [
        isLoading,
        isSubmitting,
        balances,
        leaveTypes,
        myRequests,
        upcomingHolidays,
        supervisorQueue,
        statusFilter,
        successNotice,
        errorMessage,
        lastSubmittedRequest,
      ];
}
