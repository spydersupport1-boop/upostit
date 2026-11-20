import '../../domain/entities/upcoming_holiday.dart';

class UpcomingHolidayModel extends UpcomingHoliday {
  const UpcomingHolidayModel({
    required super.id,
    required super.holidayDate,
    required super.name,
    required super.holidayType,
    required super.isOptional,
    super.description,
    required super.calendarId,
    required super.calendarName,
    super.resolutionSource,
  });

  factory UpcomingHolidayModel.fromJson(Map<String, dynamic> json) {
    return UpcomingHolidayModel(
      id: json['id'] as String,
      holidayDate: json['holiday_date'] as String,
      name: json['name'] as String,
      holidayType: json['holiday_type'] as String? ?? 'PUBLIC',
      isOptional: json['is_optional'] as bool? ?? false,
      description: json['description'] as String?,
      calendarId: json['calendar_id'] as String? ?? '',
      calendarName: json['calendar_name'] as String? ?? 'Holiday Calendar',
      resolutionSource: json['resolution_source'] as String?,
    );
  }
}
