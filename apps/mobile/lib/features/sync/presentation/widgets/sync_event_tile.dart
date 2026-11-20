import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../attendance/domain/entities/attendance_event.dart';
import '../../domain/entities/local_queue_item.dart';
import '../../domain/entities/sync_status.dart';

/// Card tile presenting the immutable details and synchronization state of an offline attendance punch.
class SyncEventTile extends StatelessWidget {
  final LocalQueueItem item;

  const SyncEventTile({super.key, required this.item});

  @override
  Widget build(BuildContext context) {
    final timeStr = DateFormat('EEE, d MMM yyyy • h:mm:ss a')
        .format(item.deviceReportedAt.toLocal());

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Row 1: Event Type Icon, Name & Status Badge
          Row(
            children: [
              _buildEventIcon(item.eventType),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.eventType.displayName,
                      style: AppTypography.headingMedium.copyWith(fontSize: 16),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      timeStr,
                      style: AppTypography.bodySmall
                          .copyWith(color: AppColors.textMuted),
                    ),
                  ],
                ),
              ),
              _buildStatusBadge(item.syncStatus),
            ],
          ),

          // Row 2: Server confirmation or details if synced
          if (item.serverEventId != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.successLight,
                borderRadius: AppRadius.smBorderRadius,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_done_rounded,
                      color: AppColors.success, size: 14),
                  const SizedBox(width: 4),
                  Text(
                    'Server ID: ${item.serverEventId}',
                    style: const TextStyle(
                      color: AppColors.success,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ),
            ),
          ],

          // Row 3: Flagged for supervisor review
          if (item.syncStatus == SyncStatus.flaggedPendingReview) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: 6,
              ),
              decoration: BoxDecoration(
                color: AppColors.warningLight,
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(
                  color: AppColors.warning.withValues(alpha: 0.3),
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.flag_rounded,
                      color: AppColors.warning, size: 16),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      'Recorded on server, flagged for supervisor review (clock drift check).',
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.warning,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // Row 4: Quarantined explanation
          if (item.syncStatus == SyncStatus.quarantinedDependentFailure) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: 6,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFFF3E8FF), // Purple 100
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(
                  color: const Color(0xFFC084FC).withValues(alpha: 0.4),
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.shield_outlined,
                      color: Color(0xFF9333EA), size: 16),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      'Quarantined because an earlier punch in this session failed. Requires administrative review.',
                      style: AppTypography.bodySmall.copyWith(
                        color: const Color(0xFF7E22CE),
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // Row 5: Rejection error message
          if (item.syncStatus == SyncStatus.rejectedPermanent &&
              item.lastErrorMessage != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: 6,
              ),
              decoration: BoxDecoration(
                color: AppColors.errorLight,
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(
                  color: AppColors.error.withValues(alpha: 0.3),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.error_outline_rounded,
                      color: AppColors.error, size: 16),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      'Rejection Reason: ${item.lastErrorMessage}',
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.error,
                        fontSize: 12,
                      ),
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

  Widget _buildEventIcon(AttendanceEventType type) {
    Color color;
    IconData icon;

    switch (type) {
      case AttendanceEventType.checkIn:
        color = AppColors.success;
        icon = Icons.login_rounded;
        break;
      case AttendanceEventType.checkOut:
        color = AppColors.error;
        icon = Icons.logout_rounded;
        break;
      case AttendanceEventType.breakStart:
        color = AppColors.warning;
        icon = Icons.coffee_rounded;
        break;
      case AttendanceEventType.breakEnd:
        color = AppColors.primary;
        icon = Icons.play_arrow_rounded;
        break;
    }

    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        shape: BoxShape.circle,
      ),
      child: Icon(icon, color: color, size: 20),
    );
  }

  Widget _buildStatusBadge(SyncStatus status) {
    Color bg;
    Color fg;
    String label;
    IconData icon;

    switch (status) {
      case SyncStatus.pendingSync:
        bg = AppColors.warningLight;
        fg = AppColors.warning;
        label = 'Pending';
        icon = Icons.schedule_rounded;
        break;
      case SyncStatus.syncing:
        bg = AppColors.primaryLight;
        fg = AppColors.primary;
        label = 'Syncing';
        icon = Icons.sync_rounded;
        break;
      case SyncStatus.synced:
        bg = AppColors.successLight;
        fg = AppColors.success;
        label = 'Synced';
        icon = Icons.check_circle_rounded;
        break;
      case SyncStatus.rejectedPermanent:
        bg = AppColors.errorLight;
        fg = AppColors.error;
        label = 'Rejected';
        icon = Icons.cancel_rounded;
        break;
      case SyncStatus.quarantinedDependentFailure:
        bg = const Color(0xFFF3E8FF);
        fg = const Color(0xFF7E22CE);
        label = 'Quarantined';
        icon = Icons.shield_rounded;
        break;
      case SyncStatus.flaggedPendingReview:
        bg = AppColors.warningLight;
        fg = AppColors.warning;
        label = 'Flagged';
        icon = Icons.flag_rounded;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: fg, size: 12),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: fg,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}
