import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';

/// Warning banner displayed when offline queue usage approaches maximum capacity (>= 400 of 500).
class StorageThresholdBanner extends StatelessWidget {
  final int unacknowledgedCount;
  final int maxCapacity;
  final VoidCallback? onSyncNow;

  const StorageThresholdBanner({
    super.key,
    required this.unacknowledgedCount,
    this.maxCapacity = 500,
    this.onSyncNow,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.warningLight.withValues(alpha: 0.2),
        border: Border.all(color: AppColors.warning),
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Row(
        children: [
          const Icon(Icons.storage, color: AppColors.warning, size: 24),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Offline Queue Capacity Warning',
                  style: AppTypography.bodySmall.copyWith(
                    fontWeight: FontWeight.bold,
                    color: AppColors.warning,
                  ),
                ),
                Text(
                  '$unacknowledgedCount of $maxCapacity events pending sync. '
                  'Connect to network soon to avoid queue overflow.',
                  style: AppTypography.caption,
                ),
              ],
            ),
          ),
          if (onSyncNow != null)
            TextButton(
              onPressed: onSyncNow,
              child: const Text('Sync Now'),
            ),
        ],
      ),
    );
  }
}
