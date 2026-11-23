import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_typography.dart';

/// Renders a color-coded chip indicating the notification domain category.
class NotificationCategoryBadge extends StatelessWidget {
  final String category;
  final String? priority;

  const NotificationCategoryBadge({
    super.key,
    required this.category,
    this.priority,
  });

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color fg;
    IconData icon;

    final cat = category.toLowerCase();
    if (cat.contains('leave')) {
      bg = AppColors.primaryLight;
      fg = AppColors.primary;
      icon = Icons.event_note_rounded;
    } else if (cat.contains('attendance') || cat.contains('conflict')) {
      bg = AppColors.warningLight;
      fg = AppColors.warning;
      icon = Icons.access_time_rounded;
    } else if (cat.contains('security') ||
        cat.contains('fraud') ||
        cat.contains('gps')) {
      bg = AppColors.errorLight;
      fg = AppColors.error;
      icon = Icons.shield_outlined;
    } else if (cat.contains('account') || cat.contains('password')) {
      bg = AppColors.infoLight;
      fg = AppColors.info;
      icon = Icons.lock_outline_rounded;
    } else {
      bg = AppColors.borderLight;
      fg = AppColors.textSecondary;
      icon = Icons.notifications_none_rounded;
    }

    final isUrgent = priority != null && priority!.toUpperCase() == 'URGENT';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border:
            isUrgent ? Border.all(color: AppColors.error, width: 1.2) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: fg),
          const SizedBox(width: 4),
          Text(
            isUrgent ? 'URGENT • $category' : category,
            style: AppTypography.caption.copyWith(
              color: fg,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
