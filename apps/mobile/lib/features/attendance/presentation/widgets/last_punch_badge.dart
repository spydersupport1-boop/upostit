import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/attendance_event.dart';

/// Clean banner showing the most recent attendance event logged today.
class LastPunchBadge extends StatelessWidget {
  final AttendanceEvent? lastEvent;

  const LastPunchBadge({super.key, this.lastEvent});

  @override
  Widget build(BuildContext context) {
    if (lastEvent == null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.background,
          borderRadius: AppRadius.mdBorderRadius,
          border: Border.all(color: AppColors.borderLight),
        ),
        child: Row(
          children: [
            const Icon(Icons.info_outline_rounded,
                size: 16, color: AppColors.textMuted),
            const SizedBox(width: AppSpacing.sm),
            Text(
              'No punches recorded yet today.',
              style: AppTypography.bodySmall,
            ),
          ],
        ),
      );
    }

    final timeStr = DateFormat.jm().format(lastEvent!.effectiveAt.toLocal());
    final isPendingReview = lastEvent!.isPendingReview;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm + 2,
      ),
      decoration: BoxDecoration(
        color: isPendingReview ? AppColors.warningLight : AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(
          color: isPendingReview
              ? AppColors.warning.withValues(alpha: 0.3)
              : AppColors.borderLight,
        ),
      ),
      child: Row(
        children: [
          Icon(
            Icons.history_rounded,
            size: 18,
            color: isPendingReview ? AppColors.warning : AppColors.primary,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text.rich(
              TextSpan(
                style: AppTypography.bodySmall
                    .copyWith(color: AppColors.textPrimary),
                children: [
                  const TextSpan(text: 'Last punch: '),
                  TextSpan(
                    text: '${lastEvent!.eventType.displayName} at $timeStr',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color:
                  isPendingReview ? AppColors.warning : AppColors.successLight,
              borderRadius: AppRadius.smBorderRadius,
            ),
            child: Text(
              isPendingReview ? 'UNDER REVIEW' : 'CONFIRMED',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: isPendingReview ? Colors.white : AppColors.success,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
