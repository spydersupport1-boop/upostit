import 'package:flutter/material.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/features/history/domain/entities/monthly_attendance_summary.dart';

class AttendanceSummaryCards extends StatelessWidget {
  final MonthlyAttendanceSummary summary;

  const AttendanceSummaryCards({super.key, required this.summary});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return Row(
          children: [
            Expanded(
              child: _buildMetricCard(
                label: 'Present',
                value: summary.presentCount.toString(),
                color: AppColors.success,
                bgColor: AppColors.successLight,
                icon: Icons.check_circle_outline_rounded,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: _buildMetricCard(
                label: 'Late',
                value: summary.lateCount.toString(),
                color: AppColors.warning,
                bgColor: AppColors.warningLight,
                icon: Icons.access_time_rounded,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: _buildMetricCard(
                label: 'Absent',
                value: summary.absentCount.toString(),
                color: AppColors.error,
                bgColor: AppColors.errorLight,
                icon: Icons.cancel_outlined,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: _buildMetricCard(
                label: 'Worked',
                value: summary.formattedTotalHours,
                color: AppColors.primary,
                bgColor: AppColors.primaryLight,
                icon: Icons.timer_outlined,
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildMetricCard({
    required String label,
    required String value,
    required Color color,
    required Color bgColor,
    required IconData icon,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.sm + 2,
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: AppTypography.bodySmall.copyWith(
                  color: AppColors.textSecondary,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
              Icon(icon, color: color, size: 14),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            value,
            style: AppTypography.headingMedium.copyWith(
              color: color,
              fontSize: 15,
              fontWeight: FontWeight.w700,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
