import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/assigned_workplace.dart';
import '../../domain/entities/today_shift.dart';

/// Card presenting today's assigned shift timings and primary workplace.
class ShiftWorkplaceCard extends StatelessWidget {
  final TodayShift? shift;
  final AssignedWorkplace? workplace;

  const ShiftWorkplaceCard({
    super.key,
    this.shift,
    this.workplace,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.lgBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          // Shift Section
          Expanded(
            child: Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    borderRadius: AppRadius.mdBorderRadius,
                  ),
                  child: const Icon(
                    Icons.access_time_filled_rounded,
                    color: AppColors.primary,
                    size: 20,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'TODAY SHIFT',
                        style: AppTypography.bodySmall.copyWith(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        shift?.name ?? 'No Shift Assigned',
                        style: AppTypography.labelLarge.copyWith(fontSize: 13),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        shift?.formattedHours ?? 'Rest Day / Flexible',
                        style: AppTypography.bodySmall.copyWith(fontSize: 11),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Container(
            height: 40,
            width: 1,
            color: AppColors.divider,
            margin: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          ),
          // Workplace Section
          Expanded(
            child: Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: AppColors.infoLight,
                    borderRadius: AppRadius.mdBorderRadius,
                  ),
                  child: const Icon(
                    Icons.business_rounded,
                    color: AppColors.info,
                    size: 20,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'WORKPLACE',
                        style: AppTypography.bodySmall.copyWith(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        workplace?.locationName ?? 'Main Workplace',
                        style: AppTypography.labelLarge.copyWith(fontSize: 13),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        workplace?.city.isNotEmpty == true
                            ? workplace!.city
                            : 'On-site / Office',
                        style: AppTypography.bodySmall.copyWith(fontSize: 11),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
