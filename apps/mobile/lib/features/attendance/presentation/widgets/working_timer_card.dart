import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/attendance_status.dart';

/// Clean timer widget displaying live working elapsed duration, break time, and remaining shift time.
class WorkingTimerCard extends StatelessWidget {
  final Duration workingDuration;
  final Duration breakDuration;
  final AttendanceStatus status;
  final Duration? remainingDuration;

  const WorkingTimerCard({
    super.key,
    required this.workingDuration,
    required this.breakDuration,
    required this.status,
    this.remainingDuration,
  });

  String _formatDuration(Duration d) {
    final hours = d.inHours.toString().padLeft(2, '0');
    final minutes = (d.inMinutes % 60).toString().padLeft(2, '0');
    final seconds = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$hours:$minutes:$seconds';
  }

  String _formatRemaining(Duration d) {
    final hours = d.inHours;
    final minutes = d.inMinutes % 60;
    if (hours == 0 && minutes == 0) return 'Shift Ended';
    if (hours == 0) return '$minutes mins';
    return '$hours hrs $minutes mins';
  }

  @override
  Widget build(BuildContext context) {
    final isWorking = status == AttendanceStatus.working;
    final isOnBreak = status == AttendanceStatus.onBreak;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.lg,
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.lgBorderRadius,
        border: Border.all(color: AppColors.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.schedule_rounded,
                size: 16,
                color: isWorking
                    ? AppColors.success
                    : (isOnBreak ? AppColors.warning : AppColors.textMuted),
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                isOnBreak
                    ? 'BREAK TIME ELAPSED'
                    : (isWorking
                        ? 'WORKING TIME ELAPSED'
                        : 'TODAY TOTAL WORKING TIME'),
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                  color: isWorking
                      ? AppColors.success
                      : (isOnBreak ? AppColors.warning : AppColors.textMuted),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            _formatDuration(isOnBreak ? breakDuration : workingDuration),
            key: const Key('working_timer_text'),
            style: AppTypography.displayLarge.copyWith(
              fontSize: 40,
              fontWeight: FontWeight.w800,
              fontFeatures: const [FontFeature.tabularFigures()],
              color: isOnBreak ? AppColors.warning : AppColors.textPrimary,
              letterSpacing: 1.0,
            ),
          ),
          if (breakDuration > Duration.zero && !isOnBreak) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm * 1.5,
                vertical: AppSpacing.xxs + 2,
              ),
              decoration: BoxDecoration(
                color: AppColors.warningLight,
                borderRadius: AppRadius.fullBorderRadius,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.free_breakfast_outlined,
                    size: 13,
                    color: AppColors.warning,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    'Break Taken: ${_formatDuration(breakDuration)}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.warning,
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (isWorking && remainingDuration != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm * 1.5,
                vertical: AppSpacing.xxs + 2,
              ),
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: AppRadius.fullBorderRadius,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.timelapse_rounded,
                    size: 13,
                    color: AppColors.primary,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    'Remaining Shift: ${_formatRemaining(remainingDuration!)}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
