import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';

class AuditTimelineTile extends StatelessWidget {
  final AttendanceEvent event;
  final bool isFirst;
  final bool isLast;

  const AuditTimelineTile({
    super.key,
    required this.event,
    this.isFirst = false,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final (icon, color, label) = _resolveEventInfo(event.eventType);
    final timeStr = DateFormat('h:mm:ss a').format(event.effectiveAt.toLocal());

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Timeline indicator line + circle
          SizedBox(
            width: 36,
            child: Column(
              children: [
                if (!isFirst)
                  Container(width: 2, height: 12, color: AppColors.border)
                else
                  const SizedBox(height: 12),
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                    border: Border.all(color: color, width: 1.5),
                  ),
                  child: Center(
                    child: Icon(icon, size: 13, color: color),
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(width: 2, color: AppColors.border),
                  )
                else
                  const SizedBox(height: 12),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),

          // Event Details Card
          Expanded(
            child: Container(
              margin: const EdgeInsets.only(bottom: AppSpacing.sm),
              padding: const EdgeInsets.all(AppSpacing.sm + 4),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        label,
                        style: AppTypography.bodySmall.copyWith(
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      Text(
                        timeStr,
                        style: AppTypography.caption.copyWith(
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      // Verification source chip
                      _buildChip(
                        label: event.source,
                        icon: _resolveSourceIcon(event.source),
                        color: AppColors.textSecondary,
                        bgColor: AppColors.background,
                      ),
                      // Timestamp verification status
                      _buildChip(
                        label: event.timestampVerificationStatus,
                        color: event.timestampVerificationStatus == 'VERIFIED'
                            ? AppColors.success
                            : AppColors.info,
                        bgColor: event.timestampVerificationStatus == 'VERIFIED'
                            ? AppColors.successLight
                            : AppColors.primaryLight,
                      ),
                      if (event.reviewStatus == 'PENDING_REVIEW')
                        _buildChip(
                          label: 'Flagged Review',
                          icon: Icons.flag_rounded,
                          color: AppColors.warning,
                          bgColor: AppColors.warningLight,
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChip({
    required String label,
    IconData? icon,
    required Color color,
    required Color bgColor,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 10, color: color),
            const SizedBox(width: 3),
          ],
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  (IconData, Color, String) _resolveEventInfo(AttendanceEventType type) {
    switch (type) {
      case AttendanceEventType.checkIn:
        return (Icons.login_rounded, AppColors.success, 'Check-In');
      case AttendanceEventType.breakStart:
        return (Icons.coffee_rounded, AppColors.warning, 'Break Start');
      case AttendanceEventType.breakEnd:
        return (Icons.play_arrow_rounded, AppColors.primary, 'Break End');
      case AttendanceEventType.checkOut:
        return (Icons.logout_rounded, AppColors.error, 'Check-Out');
    }
  }

  IconData _resolveSourceIcon(String source) {
    final s = source.toUpperCase();
    if (s.contains('GPS')) return Icons.location_on_outlined;
    if (s.contains('WIFI')) return Icons.wifi_rounded;
    return Icons.touch_app_outlined;
  }
}
