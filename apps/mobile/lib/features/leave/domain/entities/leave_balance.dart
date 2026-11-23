import 'package:equatable/equatable.dart';

/// Domain entity representing an employee's annual leave balance for a category.
class LeaveBalance extends Equatable {
  final String id;
  final String employeeId;
  final String leaveTypeId;
  final String leaveTypeCode;
  final String leaveTypeName;
  final int year;
  final double annualAllocation;
  final double carriedForward;
  final double accrued;
  final double used;
  final double pendingApproval;
  final double availableBalance;

  const LeaveBalance({
    required this.id,
    required this.employeeId,
    required this.leaveTypeId,
    required this.leaveTypeCode,
    required this.leaveTypeName,
    required this.year,
    required this.annualAllocation,
    required this.carriedForward,
    required this.accrued,
    required this.used,
    required this.pendingApproval,
    required this.availableBalance,
  });

  @override
  List<Object?> get props => [
        id,
        employeeId,
        leaveTypeId,
        leaveTypeCode,
        leaveTypeName,
        year,
        annualAllocation,
        carriedForward,
        accrued,
        used,
        pendingApproval,
        availableBalance,
      ];
}
