import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/upcoming_holiday.dart';

class HolidayTile extends StatelessWidget {
  final UpcomingHoliday holiday;

  const HolidayTile({super.key, required this.holiday});

  @override
  Widget build(BuildContext context) {
    final date = holiday.date;
    final dayNum = DateFormat('dd').format(date);
    final monthStr = DateFormat('MMM').format(date).toUpperCase();
    final weekdayStr = DateFormat('EEEE').format(date);

    final isPublic = holiday.holidayType == 'PUBLIC' || holiday.isPublic;
    final typeBadgeColor = isPublic ? AppColors.primary : AppColors.accent;

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          // Date Block
          Container(
            width: 50,
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
            decoration: BoxDecoration(
              color: AppColors.primaryLight,
              borderRadius: AppRadius.mdBorderRadius,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  monthStr,
                  style: const TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: AppColors.primary,
                  ),
                ),
                Text(
                  dayNum,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: AppColors.primaryDark,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          // Details
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  holiday.name,
                  style: AppTypography.headingMedium.copyWith(fontSize: 15),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  weekdayStr,
                  style: AppTypography.caption.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
                if (holiday.calendarName.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    holiday.calendarName,
                    style: AppTypography.caption.copyWith(
                      color: AppColors.textMuted,
                      fontSize: 11,
                    ),
                  ),
                ],
              ],
            ),
          ),
          // Badges
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.xs + 2,
                  vertical: 2,
                ),
                decoration: BoxDecoration(
                  color: typeBadgeColor.withValues(alpha: 0.1),
                  borderRadius: AppRadius.smBorderRadius,
                ),
                child: Text(
                  holiday.holidayType,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: typeBadgeColor,
                  ),
                ),
              ),
              if (holiday.isOptional) ...[
                const SizedBox(height: 4),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.xs + 2,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.warningLight,
                    borderRadius: AppRadius.smBorderRadius,
                  ),
                  child: const Text(
                    'Optional',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: AppColors.warning,
                    ),
                  ),
                ),
              ],
              if (holiday.resolutionSource != null) ...[
                const SizedBox(height: 4),
                Text(
                  holiday.resolutionSource!.replaceAll('_', ' ').toLowerCase(),
                  style: const TextStyle(
                    fontSize: 9,
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
