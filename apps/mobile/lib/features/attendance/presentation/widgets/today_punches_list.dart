import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/attendance_event.dart';

/// Timeline component listing today's sequence of recorded attendance events.
class TodayPunchesList extends StatelessWidget {
  final List<AttendanceEvent> events;

  const TodayPunchesList({super.key, required this.events});

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.lgBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.timeline_rounded,
                  size: 18, color: AppColors.primary),
              const SizedBox(width: AppSpacing.xs + 2),
              Text(
                'TODAY PUNCH TIMELINE',
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5,
                  color: AppColors.textPrimary,
                ),
              ),
              const Spacer(),
              Text(
                '${events.length} event${events.length == 1 ? '' : 's'}',
                style: AppTypography.bodySmall,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          const Divider(height: 1, color: AppColors.divider),
          const SizedBox(height: AppSpacing.sm),
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: events.length,
            separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
            itemBuilder: (context, index) {
              final event = events[index];
              return _buildEventItem(event);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildEventItem(AttendanceEvent event) {
    Color iconColor;
    Color iconBg;
    IconData icon;

    switch (event.eventType) {
      case AttendanceEventType.checkIn:
        iconColor = AppColors.success;
        iconBg = AppColors.successLight;
        icon = Icons.login_rounded;
        break;
      case AttendanceEventType.checkOut:
        iconColor = AppColors.error;
        iconBg = AppColors.errorLight;
        icon = Icons.logout_rounded;
        break;
      case AttendanceEventType.breakStart:
        iconColor = AppColors.warning;
        iconBg = AppColors.warningLight;
        icon = Icons.pause_rounded;
        break;
      case AttendanceEventType.breakEnd:
        iconColor = AppColors.info;
        iconBg = AppColors.infoLight;
        icon = Icons.play_arrow_rounded;
        break;
    }

    final timeStr = DateFormat.jm().format(event.effectiveAt.toLocal());

    return Row(
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: iconBg,
            shape: BoxShape.circle,
          ),
          child: Icon(icon, size: 16, color: iconColor),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                event.eventType.displayName,
                style: AppTypography.labelLarge.copyWith(fontSize: 13),
              ),
              Text(
                event.isPendingReview
                    ? 'Pending manager review'
                    : 'Server confirmed',
                style: AppTypography.bodySmall.copyWith(
                  fontSize: 11,
                  color: event.isPendingReview
                      ? AppColors.warning
                      : AppColors.textMuted,
                ),
              ),
            ],
          ),
        ),
        Text(
          timeStr,
          style: AppTypography.bodyMedium.copyWith(
            fontWeight: FontWeight.w600,
            fontSize: 13,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}
