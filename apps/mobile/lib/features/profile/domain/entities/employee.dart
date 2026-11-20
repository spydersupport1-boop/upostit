import 'package:equatable/equatable.dart';

/// Domain entity representing an employee profile in UPOSTIT.
class Employee extends Equatable {
  final String id;
  final String tenantId;
  final String? userId;
  final String employeeId;
  final String firstName;
  final String lastName;
  final String workEmail;
  final String? phoneNumber;
  final String? departmentId;
  final String? departmentName;
  final String? designationId;
  final String? designationTitle;
  final String? reportingManagerId;
  final String? reportingManagerName;
  final String employmentType;
  final DateTime? joiningDate;
  final String status;
  final String? workLocation;

  const Employee({
    required this.id,
    required this.tenantId,
    this.userId,
    required this.employeeId,
    required this.firstName,
    required this.lastName,
    required this.workEmail,
    this.phoneNumber,
    this.departmentId,
    this.departmentName,
    this.designationId,
    this.designationTitle,
    this.reportingManagerId,
    this.reportingManagerName,
    required this.employmentType,
    this.joiningDate,
    required this.status,
    this.workLocation,
  });

  String get fullName => '$firstName $lastName'.trim();

  @override
  List<Object?> get props => [
        id,
        tenantId,
        userId,
        employeeId,
        firstName,
        lastName,
        workEmail,
        phoneNumber,
        departmentId,
        departmentName,
        designationId,
        designationTitle,
        reportingManagerId,
        reportingManagerName,
        employmentType,
        joiningDate,
        status,
        workLocation,
      ];
}
