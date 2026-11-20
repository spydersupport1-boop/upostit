import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';

class MonthlyCalendarGrid extends StatelessWidget {
  final DateTime currentMonth;
  final List<AttendanceDay> days;
  final DateTime? selectedDate;
  final ValueChanged<DateTime> onMonthChanged;
  final ValueChanged<DateTime> onDaySelected;

  const MonthlyCalendarGrid({
    super.key,
    required this.currentMonth,
    required this.days,
    this.selectedDate,
    required this.onMonthChanged,
    required this.onDaySelected,
  });

  @override
  Widget build(BuildContext context) {
    final year = currentMonth.year;
    final month = currentMonth.month;
    final firstDay = DateTime(year, month, 1);
    final daysInMonth = DateTime(year, month + 1, 0).day;
    final leadingBlanks = (firstDay.weekday - 1); // 0 for Mon, 6 for Sun

    final Map<int, AttendanceDay> dayMap = {
      for (final d in days) d.attendanceDate.day: d,
    };

    final now = DateTime.now();
    final isCurrentMonth = now.year == year && now.month == month;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.lgBorderRadius,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          // Month Navigator Bar
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                key: const Key('calendar_prev_month_button'),
                icon: const Icon(Icons.chevron_left_rounded),
                onPressed: () {
                  onMonthChanged(DateTime(year, month - 1, 1));
                },
              ),
              Text(
                DateFormat('MMMM yyyy').format(currentMonth),
                style: AppTypography.headingMedium.copyWith(fontSize: 16),
              ),
              IconButton(
                key: const Key('calendar_next_month_button'),
                icon: const Icon(Icons.chevron_right_rounded),
                onPressed: () {
                  onMonthChanged(DateTime(year, month + 1, 1));
                },
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),

          // Day of Week Headers
          const Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _WeekdayHeader('M'),
              _WeekdayHeader('T'),
              _WeekdayHeader('W'),
              _WeekdayHeader('T'),
              _WeekdayHeader('F'),
              _WeekdayHeader('S'),
              _WeekdayHeader('S'),
            ],
          ),
          const Divider(height: AppSpacing.md, thickness: 0.5),

          // Calendar Grid
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: leadingBlanks + daysInMonth,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 7,
              mainAxisSpacing: 6,
              crossAxisSpacing: 6,
              childAspectRatio: 1.0,
            ),
            itemBuilder: (context, index) {
              if (index < leadingBlanks) {
                return const SizedBox.shrink();
              }
              final dayNum = index - leadingBlanks + 1;
              final dayDate = DateTime(year, month, dayNum);
              final isToday = isCurrentMonth && now.day == dayNum;
              final isSelected = selectedDate != null &&
                  selectedDate!.year == year &&
                  selectedDate!.month == month &&
                  selectedDate!.day == dayNum;

              final attendanceDay = dayMap[dayNum];

              return _DayCell(
                dayNumber: dayNum,
                isToday: isToday,
                isSelected: isSelected,
                attendanceDay: attendanceDay,
                onTap: () => onDaySelected(dayDate),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  final String label;

  const _WeekdayHeader(this.label);

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 32,
      child: Center(
        child: Text(
          label,
          style: AppTypography.bodySmall.copyWith(
            fontWeight: FontWeight.w700,
            color: AppColors.textSecondary,
            fontSize: 12,
          ),
        ),
      ),
    );
  }
}

class _DayCell extends StatelessWidget {
  final int dayNumber;
  final bool isToday;
  final bool isSelected;
  final AttendanceDay? attendanceDay;
  final VoidCallback onTap;

  const _DayCell({
    required this.dayNumber,
    required this.isToday,
    required this.isSelected,
    this.attendanceDay,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final statusColor = _resolveStatusColor(attendanceDay);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.primary
              : (isToday
                  ? AppColors.primaryLight.withValues(alpha: 0.5)
                  : null),
          borderRadius: BorderRadius.circular(8),
          border: isToday && !isSelected
              ? Border.all(color: AppColors.primary, width: 1.5)
              : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              dayNumber.toString(),
              style: TextStyle(
                fontSize: 13,
                fontWeight:
                    isSelected || isToday ? FontWeight.w700 : FontWeight.w500,
                color: isSelected
                    ? Colors.white
                    : (isToday ? AppColors.primary : AppColors.textPrimary),
              ),
            ),
            const SizedBox(height: 2),
            if (statusColor != null)
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: isSelected ? Colors.white : statusColor,
                  shape: BoxShape.circle,
                ),
              )
            else
              const SizedBox(height: 6),
          ],
        ),
      ),
    );
  }

  Color? _resolveStatusColor(AttendanceDay? day) {
    if (day == null) return null;
    final status = day.status.toUpperCase();
    switch (status) {
      case 'PRESENT':
        return AppColors.success;
      case 'LATE':
        return AppColors.warning;
      case 'HALF_DAY':
        return Colors.orange;
      case 'ABSENT':
        return AppColors.error;
      case 'INCOMPLETE':
        return Colors.purple;
      case 'PENDING_REVIEW':
        return Colors.deepOrange;
      default:
        if (day.firstCheckIn != null) return AppColors.success;
        return null;
    }
  }
}
