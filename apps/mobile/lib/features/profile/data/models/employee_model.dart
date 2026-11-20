import '../../domain/entities/employee.dart';

/// Data model for [Employee] entity matching FastAPI EmployeeResponse.
class EmployeeModel extends Employee {
  const EmployeeModel({
    required super.id,
    required super.tenantId,
    super.userId,
    required super.employeeId,
    required super.firstName,
    required super.lastName,
    required super.workEmail,
    super.phoneNumber,
    super.departmentId,
    super.departmentName,
    super.designationId,
    super.designationTitle,
    super.reportingManagerId,
    super.reportingManagerName,
    required super.employmentType,
    super.joiningDate,
    required super.status,
    super.workLocation,
  });

  factory EmployeeModel.fromJson(Map<String, dynamic> json) {
    DateTime? parsedJoiningDate;
    if (json['joining_date'] != null) {
      parsedJoiningDate = DateTime.tryParse(json['joining_date'] as String);
    }

    return EmployeeModel(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String,
      userId: json['user_id'] as String?,
      employeeId: json['employee_id'] as String? ?? 'N/A',
      firstName: json['first_name'] as String? ?? '',
      lastName: json['last_name'] as String? ?? '',
      workEmail: json['work_email'] as String? ?? '',
      phoneNumber: json['phone_number'] as String?,
      departmentId: json['department_id'] as String?,
      departmentName: json['department_name'] as String?,
      designationId: json['designation_id'] as String?,
      designationTitle: json['designation_title'] as String?,
      reportingManagerId: json['reporting_manager_id'] as String?,
      reportingManagerName: json['reporting_manager_name'] as String?,
      employmentType: json['employment_type'] as String? ?? 'full_time',
      joiningDate: parsedJoiningDate,
      status: json['status'] as String? ?? 'active',
      workLocation: json['work_location'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tenant_id': tenantId,
      'user_id': userId,
      'employee_id': employeeId,
      'first_name': firstName,
      'last_name': lastName,
      'work_email': workEmail,
      'phone_number': phoneNumber,
      'department_id': departmentId,
      'department_name': departmentName,
      'designation_id': designationId,
      'designation_title': designationTitle,
      'reporting_manager_id': reportingManagerId,
      'reporting_manager_name': reportingManagerName,
      'employment_type': employmentType,
      'joining_date': joiningDate?.toIso8601String().split('T').first,
      'status': status,
      'work_location': workLocation,
    };
  }
}
