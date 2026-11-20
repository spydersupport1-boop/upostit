import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_day.dart';

class DailyAttendanceTile extends StatelessWidget {
  final AttendanceDay day;
  final VoidCallback onTap;

  const DailyAttendanceTile({
    super.key,
    required this.day,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final dateStr = DateFormat('EEE, MMM d').format(day.attendanceDate);
    final workingHours = day.netWorkingMinutes ~/ 60;
    final workingMins = day.netWorkingMinutes % 60;
    final workingDurationFormatted = '${workingHours}h ${workingMins}m';

    final (statusLabel, statusColor, statusBg) = _resolveStatus(day.status);

    final checkInStr = day.firstCheckIn != null
        ? DateFormat('h:mm a').format(day.firstCheckIn!.toLocal())
        : '--:--';
    final checkOutStr = day.lastCheckOut != null
        ? DateFormat('h:mm a').format(day.lastCheckOut!.toLocal())
        : (day.firstCheckIn != null ? 'In Progress' : '--:--');

    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.mdBorderRadius,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    dateStr,
                    style: AppTypography.headingMedium.copyWith(fontSize: 15),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: statusBg,
                      borderRadius: AppRadius.fullBorderRadius,
                      border: Border.all(
                        color: statusColor.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Text(
                      statusLabel,
                      style: AppTypography.caption.copyWith(
                        color: statusColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: [
                  const Icon(Icons.login_rounded,
                      size: 14, color: AppColors.textSecondary),
                  const SizedBox(width: 4),
                  Text(
                    checkInStr,
                    style: AppTypography.bodySmall.copyWith(
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Text('–',
                      style: TextStyle(color: AppColors.textSecondary)),
                  const SizedBox(width: 8),
                  const Icon(Icons.logout_rounded,
                      size: 14, color: AppColors.textSecondary),
                  const SizedBox(width: 4),
                  Text(
                    checkOutStr,
                    style: AppTypography.bodySmall.copyWith(
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    workingDurationFormatted,
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
              if (day.lateArrivalMinutes > 0 || day.isIncomplete) ...[
                const SizedBox(height: AppSpacing.xs + 2),
                Wrap(
                  spacing: 6,
                  children: [
                    if (day.lateArrivalMinutes > 0)
                      Text(
                        'Late by ${day.lateArrivalMinutes}m',
                        style: AppTypography.caption.copyWith(
                          color: AppColors.warning,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    if (day.isIncomplete)
                      Text(
                        'Incomplete Session',
                        style: AppTypography.caption.copyWith(
                          color: Colors.purple,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  (String, Color, Color) _resolveStatus(String status) {
    switch (status.toUpperCase()) {
      case 'PRESENT':
        return ('Present', AppColors.success, AppColors.successLight);
      case 'LATE':
        return ('Late', AppColors.warning, AppColors.warningLight);
      case 'HALF_DAY':
        return ('Half Day', Colors.orange, const Color(0xFFFFF7ED));
      case 'ABSENT':
        return ('Absent', AppColors.error, AppColors.errorLight);
      case 'INCOMPLETE':
        return ('Incomplete', Colors.purple, const Color(0xFFF3E8FF));
      case 'PENDING_REVIEW':
        return ('Under Review', Colors.deepOrange, const Color(0xFFFFEDD5));
      default:
        return (status, AppColors.textSecondary, AppColors.surface);
    }
  }
}
