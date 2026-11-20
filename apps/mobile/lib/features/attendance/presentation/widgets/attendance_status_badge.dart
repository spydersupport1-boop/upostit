import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../domain/entities/attendance_status.dart';

/// Visual pill badge indicating the employee's current attendance state.
class AttendanceStatusBadge extends StatelessWidget {
  final AttendanceStatus status;

  const AttendanceStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color dot;
    Color text;

    switch (status) {
      case AttendanceStatus.working:
        bg = AppColors.successLight;
        dot = AppColors.success;
        text = AppColors.success;
        break;
      case AttendanceStatus.onBreak:
        bg = AppColors.warningLight;
        dot = AppColors.warning;
        text = AppColors.warning;
        break;
      case AttendanceStatus.completed:
        bg = AppColors.borderLight;
        dot = AppColors.textSecondary;
        text = AppColors.textSecondary;
        break;
      case AttendanceStatus.notCheckedIn:
        bg = AppColors.primaryLight;
        dot = AppColors.primary;
        text = AppColors.primary;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm * 1.5, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppRadius.fullBorderRadius,
        border: Border.all(color: dot.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: dot,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: AppSpacing.xs + 2),
          Text(
            status.displayName.toUpperCase(),
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: text,
            ),
          ),
        ],
      ),
    );
  }
}
