import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/in_app_notification.dart';
import 'notification_category_badge.dart';

/// Card tile for rendering a single notification in the inbox list.
class NotificationTile extends StatelessWidget {
  final InAppNotification notification;
  final VoidCallback onTap;

  const NotificationTile({
    super.key,
    required this.notification,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isUnread = !notification.isRead;
    final timeStr = _formatRelativeTime(notification.createdAt);

    return Card(
      elevation: 0,
      margin:
          const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isUnread
              ? AppColors.primary.withAlpha(100)
              : AppColors.borderLight,
          width: isUnread ? 1.5 : 1.0,
        ),
      ),
      color:
          isUnread ? AppColors.primaryLight.withAlpha(90) : AppColors.surface,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (isUnread) ...[
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: AppColors.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                  ],
                  NotificationCategoryBadge(
                    category: notification.categoryLabel,
                    priority: notification.priority,
                  ),
                  const Spacer(),
                  Text(
                    timeStr,
                    style: AppTypography.caption.copyWith(
                      color: AppColors.textMuted,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                notification.title,
                style: AppTypography.bodyMedium.copyWith(
                  fontWeight: isUnread ? FontWeight.w700 : FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                notification.body,
                style: AppTypography.bodySmall.copyWith(
                  color: isUnread
                      ? AppColors.textPrimary
                      : AppColors.textSecondary,
                  height: 1.3,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatRelativeTime(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inSeconds < 60) {
      return 'Just now';
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes}m ago';
    } else if (difference.inHours < 24) {
      return '${difference.inHours}h ago';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}d ago';
    } else {
      return DateFormat('MMM d').format(dateTime);
    }
  }
}
