import 'package:equatable/equatable.dart';

/// Domain entity representing an upcoming statutory or company holiday.
class UpcomingHoliday extends Equatable {
  final String id;
  final String holidayDate;
  final String name;
  final String holidayType;
  final bool isOptional;
  final String? description;
  final String calendarId;
  final String calendarName;
  final String? resolutionSource;

  const UpcomingHoliday({
    required this.id,
    required this.holidayDate,
    required this.name,
    required this.holidayType,
    required this.isOptional,
    this.description,
    required this.calendarId,
    required this.calendarName,
    this.resolutionSource,
  });

  DateTime get date => DateTime.tryParse(holidayDate) ?? DateTime.now();

  bool get isPublic => holidayType == 'PUBLIC';
  bool get isCompany => holidayType == 'COMPANY';
  bool get isFloating => isOptional || holidayType == 'OPTIONAL';

  @override
  List<Object?> get props => [
        id,
        holidayDate,
        name,
        holidayType,
        isOptional,
        description,
        calendarId,
        calendarName,
        resolutionSource,
      ];
}
