import 'package:equatable/equatable.dart';

/// Domain entity representing an employee's assigned work shift.
class TodayShift extends Equatable {
  final String id;
  final String name;
  final String code;
  final String? startTime;
  final String? endTime;
  final int gracePeriodMinutes;
  final int breakDurationMinutes;
  final bool isOvernight;
  final bool isFlexible;
  final DateTime? effectiveFrom;
  final DateTime? effectiveTo;
  final List<int> weeklyOffDays;

  const TodayShift({
    required this.id,
    required this.name,
    required this.code,
    this.startTime,
    this.endTime,
    this.gracePeriodMinutes = 15,
    this.breakDurationMinutes = 0,
    this.isOvernight = false,
    this.isFlexible = false,
    this.effectiveFrom,
    this.effectiveTo,
    this.weeklyOffDays = const [],
  });

  String get formattedHours {
    if (isFlexible || startTime == null || endTime == null) {
      return 'Flexible Hours';
    }
    final start = _formatTime(startTime!);
    final end = _formatTime(endTime!);
    return '$start – $end';
  }

  /// Calculates total scheduled work duration excluding breaks.
  Duration? get scheduledDuration {
    if (startTime == null || endTime == null) return null;
    final startParts = startTime!.split(':');
    final endParts = endTime!.split(':');
    if (startParts.length < 2 || endParts.length < 2) return null;
    final startMins = (int.tryParse(startParts[0]) ?? 0) * 60 +
        (int.tryParse(startParts[1]) ?? 0);
    var endMins = (int.tryParse(endParts[0]) ?? 0) * 60 +
        (int.tryParse(endParts[1]) ?? 0);
    if (isOvernight || endMins <= startMins) {
      endMins += 24 * 60;
    }
    return Duration(minutes: endMins - startMins);
  }

  String get formattedScheduledDuration {
    final dur = scheduledDuration;
    if (dur == null) return 'Flexible';
    final hours = dur.inHours;
    final mins = dur.inMinutes % 60;
    if (mins == 0) return '$hours hrs';
    return '$hours hrs $mins mins';
  }

  /// Accurately calculates remaining shift time from scheduled end time.
  Duration? calculateRemainingTime(DateTime now, DateTime? checkInTime) {
    if (endTime == null || checkInTime == null) return null;
    final parts = endTime!.split(':');
    if (parts.length < 2) return null;
    final endHour = int.tryParse(parts[0]) ?? 0;
    final endMinute = int.tryParse(parts[1]) ?? 0;
    var scheduledEnd = DateTime(
      checkInTime.year,
      checkInTime.month,
      checkInTime.day,
      endHour,
      endMinute,
    );
    if (isOvernight) {
      scheduledEnd = scheduledEnd.add(const Duration(days: 1));
    }
    final diff = scheduledEnd.difference(now);
    if (diff.isNegative) return Duration.zero;
    return diff;
  }

  bool isActiveOn(DateTime date) {
    final dayOnly = DateTime.utc(date.year, date.month, date.day);
    if (effectiveFrom != null) {
      final fromOnly = DateTime.utc(
        effectiveFrom!.year,
        effectiveFrom!.month,
        effectiveFrom!.day,
      );
      if (dayOnly.isBefore(fromOnly)) return false;
    }
    if (effectiveTo != null) {
      final toOnly = DateTime.utc(
        effectiveTo!.year,
        effectiveTo!.month,
        effectiveTo!.day,
      );
      if (dayOnly.isAfter(toOnly)) return false;
    }
    return true;
  }

  bool isUpcoming(DateTime referenceDate) {
    if (effectiveFrom == null) return false;
    final refOnly = DateTime.utc(
      referenceDate.year,
      referenceDate.month,
      referenceDate.day,
    );
    final fromOnly = DateTime.utc(
      effectiveFrom!.year,
      effectiveFrom!.month,
      effectiveFrom!.day,
    );
    return fromOnly.isAfter(refOnly);
  }

  static String _formatTime(String timeStr) {
    final parts = timeStr.split(':');
    if (parts.length >= 2) {
      final hour = int.tryParse(parts[0]) ?? 0;
      final minute = parts[1];
      final period = hour >= 12 ? 'PM' : 'AM';
      final formattedHour = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
      return '$formattedHour:$minute $period';
    }
    return timeStr;
  }

  @override
  List<Object?> get props => [
        id,
        name,
        code,
        startTime,
        endTime,
        gracePeriodMinutes,
        breakDurationMinutes,
        isOvernight,
        isFlexible,
        effectiveFrom,
        effectiveTo,
        weeklyOffDays,
      ];
}
