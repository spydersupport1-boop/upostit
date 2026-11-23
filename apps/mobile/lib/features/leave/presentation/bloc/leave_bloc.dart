import 'package:flutter_bloc/flutter_bloc.dart';
import '../../domain/repositories/leave_repository.dart';
import 'leave_event.dart';
import 'leave_state.dart';

class LeaveBloc extends Bloc<LeaveEvent, LeaveState> {
  final LeaveRepository _repository;

  LeaveBloc({required LeaveRepository repository})
      : _repository = repository,
        super(LeaveState.initial()) {
    on<LeaveDashboardRequested>(_onDashboardRequested);
    on<LeaveApplicationSubmitted>(_onApplicationSubmitted);
    on<LeaveCancellationRequested>(_onCancellationRequested);
    on<LeaveHistoryRequested>(_onHistoryRequested);
    on<UpcomingHolidaysRequested>(_onUpcomingHolidaysRequested);
    on<SupervisorQueueRequested>(_onSupervisorQueueRequested);
    on<SupervisorDecisionSubmitted>(_onSupervisorDecisionSubmitted);
    on<LeaveNoticesCleared>(_onNoticesCleared);
  }

  Future<void> _onDashboardRequested(
    LeaveDashboardRequested event,
    Emitter<LeaveState> emit,
  ) async {
    emit(state.copyWith(isLoading: true, clearNotices: true));

    final balancesResult = await _repository.getMyBalances();
    final leaveTypesResult = await _repository.getLeaveTypes();
    final myRequestsResult = await _repository.getMyLeaveRequests(limit: 5);
    final holidaysResult = await _repository.getUpcomingHolidays(limit: 5);

    String? error;
    if (balancesResult.isFailure) {
      error = balancesResult.error.message;
    } else if (leaveTypesResult.isFailure) {
      error = leaveTypesResult.error.message;
    } else if (myRequestsResult.isFailure) {
      error = myRequestsResult.error.message;
    } else if (holidaysResult.isFailure) {
      error = holidaysResult.error.message;
    }

    emit(state.copyWith(
      isLoading: false,
      balances:
          balancesResult.isSuccess ? balancesResult.value : state.balances,
      leaveTypes: leaveTypesResult.isSuccess
          ? leaveTypesResult.value
          : state.leaveTypes,
      myRequests: myRequestsResult.isSuccess
          ? myRequestsResult.value
          : state.myRequests,
      upcomingHolidays: holidaysResult.isSuccess
          ? holidaysResult.value
          : state.upcomingHolidays,
      errorMessage: error,
    ));
  }

  Future<void> _onApplicationSubmitted(
    LeaveApplicationSubmitted event,
    Emitter<LeaveState> emit,
  ) async {
    if (state.isSubmitting) return;

    emit(state.copyWith(isSubmitting: true, clearNotices: true));

    final result = await _repository.applyLeave(
      leaveTypeId: event.leaveTypeId,
      startDate: event.startDate,
      endDate: event.endDate,
      isHalfDay: event.isHalfDay,
      halfDayPeriod: event.halfDayPeriod,
      reason: event.reason,
    );

    if (result.isSuccess) {
      final newRequest = result.value;
      final updatedRequests = [newRequest, ...state.myRequests];
      emit(state.copyWith(
        isSubmitting: false,
        myRequests: updatedRequests,
        lastSubmittedRequest: newRequest,
        successNotice: 'Leave request submitted successfully',
      ));
      // Refresh balances in background
      final balancesResult = await _repository.getMyBalances();
      if (balancesResult.isSuccess) {
        emit(state.copyWith(balances: balancesResult.value));
      }
    } else {
      emit(state.copyWith(
        isSubmitting: false,
        errorMessage: result.error.message,
      ));
    }
  }

  Future<void> _onCancellationRequested(
    LeaveCancellationRequested event,
    Emitter<LeaveState> emit,
  ) async {
    if (state.isSubmitting) return;

    emit(state.copyWith(isSubmitting: true, clearNotices: true));

    final result = await _repository.cancelLeaveRequest(
      event.requestId,
      reason: event.reason,
    );

    if (result.isSuccess) {
      final updated = state.myRequests
          .map((r) => r.id == event.requestId ? result.value : r)
          .toList();
      emit(state.copyWith(
        isSubmitting: false,
        myRequests: updated,
        successNotice: 'Leave request cancelled successfully',
      ));
      // Refresh balances
      final balancesResult = await _repository.getMyBalances();
      if (balancesResult.isSuccess) {
        emit(state.copyWith(balances: balancesResult.value));
      }
    } else {
      emit(state.copyWith(
        isSubmitting: false,
        errorMessage: result.error.message,
      ));
    }
  }

  Future<void> _onHistoryRequested(
    LeaveHistoryRequested event,
    Emitter<LeaveState> emit,
  ) async {
    emit(state.copyWith(
      isLoading: true,
      statusFilter: event.statusFilter,
      clearStatusFilter: event.statusFilter == null,
      clearNotices: true,
    ));

    final result = await _repository.getMyLeaveRequests(
      status: event.statusFilter,
      limit: 100,
    );

    if (result.isSuccess) {
      emit(state.copyWith(
        isLoading: false,
        myRequests: result.value,
      ));
    } else {
      emit(state.copyWith(
        isLoading: false,
        errorMessage: result.error.message,
      ));
    }
  }

  Future<void> _onUpcomingHolidaysRequested(
    UpcomingHolidaysRequested event,
    Emitter<LeaveState> emit,
  ) async {
    emit(state.copyWith(isLoading: true, clearNotices: true));

    final result = await _repository.getUpcomingHolidays(limit: 50);

    if (result.isSuccess) {
      emit(state.copyWith(
        isLoading: false,
        upcomingHolidays: result.value,
      ));
    } else {
      emit(state.copyWith(
        isLoading: false,
        errorMessage: result.error.message,
      ));
    }
  }

  Future<void> _onSupervisorQueueRequested(
    SupervisorQueueRequested event,
    Emitter<LeaveState> emit,
  ) async {
    emit(state.copyWith(
      isLoading: true,
      statusFilter: event.statusFilter,
      clearStatusFilter: event.statusFilter == null,
      clearNotices: true,
    ));

    final result = await _repository.getSupervisorQueue(
      status: event.statusFilter,
      limit: 100,
    );

    if (result.isSuccess) {
      emit(state.copyWith(
        isLoading: false,
        supervisorQueue: result.value,
      ));
    } else {
      emit(state.copyWith(
        isLoading: false,
        errorMessage: result.error.message,
      ));
    }
  }

  Future<void> _onSupervisorDecisionSubmitted(
    SupervisorDecisionSubmitted event,
    Emitter<LeaveState> emit,
  ) async {
    if (state.isSubmitting) return;

    emit(state.copyWith(isSubmitting: true, clearNotices: true));

    final result = await _repository.adjudicateLeaveRequest(
      event.requestId,
      action: event.action,
      reason: event.reason,
    );

    if (result.isSuccess) {
      final updatedQueue = state.supervisorQueue
          .map((r) => r.id == event.requestId ? result.value : r)
          .toList();
      emit(state.copyWith(
        isSubmitting: false,
        supervisorQueue: updatedQueue,
        successNotice:
            'Leave request ${event.action == 'APPROVE' ? 'approved' : 'rejected'} successfully',
      ));
    } else {
      emit(state.copyWith(
        isSubmitting: false,
        errorMessage: result.error.message,
      ));
    }
  }

  void _onNoticesCleared(
    LeaveNoticesCleared event,
    Emitter<LeaveState> emit,
  ) {
    emit(state.copyWith(clearNotices: true));
  }
}
