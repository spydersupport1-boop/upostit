import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/in_app_notification.dart';
import 'notification_category_badge.dart';

/// Modal dialog displaying full details of an in-app notification.
class NotificationDetailDialog extends StatelessWidget {
  final InAppNotification notification;

  const NotificationDetailDialog({
    super.key,
    required this.notification,
  });

  static Future<void> show(
      BuildContext context, InAppNotification notification) {
    return showDialog(
      context: context,
      builder: (context) =>
          NotificationDetailDialog(notification: notification),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('MMM d, yyyy • h:mm a');
    final formattedTime = dateFormat.format(notification.createdAt);

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      backgroundColor: AppColors.surface,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                NotificationCategoryBadge(
                  category: notification.categoryLabel,
                  priority: notification.priority,
                ),
                Text(
                  formattedTime,
                  style: AppTypography.caption
                      .copyWith(color: AppColors.textMuted),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              notification.title,
              style: AppTypography.headingMedium.copyWith(
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.borderLight),
              ),
              child: Text(
                notification.body,
                style: AppTypography.bodyMedium.copyWith(
                  color: AppColors.textSecondary,
                  height: 1.4,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Close'),
                ),
                if (notification.deepLinkRoute != null) ...[
                  const SizedBox(width: AppSpacing.sm),
                  ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      minimumSize: const Size(0, 40),
                      backgroundColor: AppColors.primary,
                      foregroundColor: AppColors.textInverse,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                    onPressed: () {
                      Navigator.of(context).pop();
                      context.push(notification.deepLinkRoute!);
                    },
                    child: Text(_getActionLabel(notification.deepLinkRoute!)),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _getActionLabel(String route) {
    if (route.contains('approvals')) return 'View Approvals';
    if (route.contains('leave')) return 'View Leave';
    if (route.contains('sync')) return 'View Queue';
    if (route.contains('home')) return 'View Attendance';
    return 'Open Screen';
  }
}
