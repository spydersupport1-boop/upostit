import 'package:equatable/equatable.dart';

/// Domain entity representing a tenant-configured leave category.
class LeaveType extends Equatable {
  final String id;
  final String code;
  final String name;
  final String? description;
  final bool isPaid;
  final bool requiresApproval;
  final bool allowHalfDay;
  final int? maxConsecutiveDays;
  final double carryForwardLimit;
  final bool isActive;

  const LeaveType({
    required this.id,
    required this.code,
    required this.name,
    this.description,
    required this.isPaid,
    required this.requiresApproval,
    required this.allowHalfDay,
    this.maxConsecutiveDays,
    required this.carryForwardLimit,
    required this.isActive,
  });

  @override
  List<Object?> get props => [
        id,
        code,
        name,
        description,
        isPaid,
        requiresApproval,
        allowHalfDay,
        maxConsecutiveDays,
        carryForwardLimit,
        isActive,
      ];
}

