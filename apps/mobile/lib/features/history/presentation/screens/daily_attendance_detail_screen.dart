import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/features/history/domain/entities/daily_attendance_detail.dart';
import '../widgets/audit_timeline_tile.dart';

class DailyAttendanceDetailScreen extends StatelessWidget {
  final DailyAttendanceDetail detail;

  const DailyAttendanceDetailScreen({super.key, required this.detail});

  @override
  Widget build(BuildContext context) {
    final dateFormatted = DateFormat('EEEE, MMMM d, yyyy').format(detail.date);
    final (statusLabel, statusColor, statusBg) =
        _resolveStatus(detail.effectiveStatus);

    final workHours = detail.workingDuration.inHours;
    final workMins = detail.workingDuration.inMinutes % 60;
    final breakHours = detail.breakDuration.inHours;
    final breakMins = detail.breakDuration.inMinutes % 60;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Attendance Details'),
        centerTitle: false,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. Date & Status Header Card
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.mdBorderRadius,
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(
                          dateFormatted,
                          style: AppTypography.headingMedium
                              .copyWith(fontSize: 16),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm + 2,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: statusBg,
                          borderRadius: AppRadius.fullBorderRadius,
                          border: Border.all(
                            color: statusColor.withValues(alpha: 0.3),
                          ),
                        ),
                        child: Text(
                          statusLabel,
                          style: AppTypography.caption.copyWith(
                            color: statusColor,
                            fontWeight: FontWeight.w700,
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (detail.hasPendingPunches) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Container(
                      padding: const EdgeInsets.all(AppSpacing.sm),
                      decoration: BoxDecoration(
                        color: AppColors.primaryLight,
                        borderRadius: AppRadius.smBorderRadius,
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.cloud_upload_outlined,
                              size: 16, color: AppColors.primary),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: Text(
                              '${detail.pendingQueueItems.length} punch(es) stored locally pending synchronization.',
                              style: AppTypography.caption.copyWith(
                                color: AppColors.primary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.md),

            // 2. Assigned Shift Details
            _buildShiftCard(),

            const SizedBox(height: AppSpacing.md),

            // 3. Working Duration Summary
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.mdBorderRadius,
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Time Summary',
                    style: AppTypography.headingMedium.copyWith(fontSize: 15),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Row(
                    children: [
                      Expanded(
                        child: _buildMetric(
                          label: 'Worked Duration',
                          value: '${workHours}h ${workMins}m',
                          color: AppColors.primary,
                          icon: Icons.timer_outlined,
                        ),
                      ),
                      Expanded(
                        child: _buildMetric(
                          label: 'Break Duration',
                          value: breakHours > 0
                              ? '${breakHours}h ${breakMins}m'
                              : '${breakMins}m',
                          color: AppColors.warning,
                          icon: Icons.coffee_rounded,
                        ),
                      ),
                    ],
                  ),
                  if (detail.lateMinutes > 0 || detail.earlyMinutes > 0) ...[
                    const Divider(height: AppSpacing.lg),
                    Row(
                      children: [
                        if (detail.lateMinutes > 0)
                          Expanded(
                            child: _buildMetric(
                              label: 'Late Arrival',
                              value: '${detail.lateMinutes} mins',
                              color: AppColors.error,
                              icon: Icons.alarm_off_rounded,
                            ),
                          ),
                        if (detail.earlyMinutes > 0)
                          Expanded(
                            child: _buildMetric(
                              label: 'Early Departure',
                              value: '${detail.earlyMinutes} mins',
                              color: Colors.orange,
                              icon: Icons.exit_to_app_rounded,
                            ),
                          ),
                      ],
                    ),
                  ],
                ],
              ),
            ),

            const SizedBox(height: AppSpacing.md),

            // 4. Chronological Event Audit Trail
            Text(
              'Event Ledger Timeline',
              style: AppTypography.headingMedium.copyWith(fontSize: 15),
            ),
            const SizedBox(height: AppSpacing.sm),
            if (detail.events.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppSpacing.lg),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: AppRadius.mdBorderRadius,
                  border: Border.all(color: AppColors.border),
                ),
                child: Center(
                  child: Text(
                    'No server presence events recorded for this date.',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
              )
            else
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: detail.events.length,
                itemBuilder: (context, index) {
                  return AuditTimelineTile(
                    event: detail.events[index],
                    isFirst: index == 0,
                    isLast: index == detail.events.length - 1,
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildShiftCard() {
    final shift = detail.shift;
    if (shift == null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: AppRadius.mdBorderRadius,
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            const Icon(Icons.event_busy_rounded,
                color: AppColors.textSecondary),
            const SizedBox(width: AppSpacing.sm),
            Text(
              'No Shift Assigned (Rest Day / Flexible)',
              style: AppTypography.bodySmall
                  .copyWith(color: AppColors.textSecondary),
            ),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '${shift.name} (${shift.code})',
                style: AppTypography.headingMedium.copyWith(fontSize: 15),
              ),
              if (shift.isOvernight)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.indigo.shade50,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    'Overnight',
                    style: AppTypography.caption.copyWith(
                      color: Colors.indigo,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              const Icon(Icons.schedule_rounded,
                  size: 16, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text(
                shift.formattedHours,
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(width: 12),
              if (shift.breakDurationMinutes > 0) ...[
                const Icon(Icons.coffee_outlined,
                    size: 16, color: AppColors.textSecondary),
                const SizedBox(width: 4),
                Text(
                  '${shift.breakDurationMinutes}m break',
                  style: AppTypography.caption
                      .copyWith(color: AppColors.textSecondary),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetric({
    required String label,
    required String value,
    required Color color,
    required IconData icon,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 14, color: AppColors.textSecondary),
            const SizedBox(width: 4),
            Text(
              label,
              style: AppTypography.caption
                  .copyWith(color: AppColors.textSecondary),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: AppTypography.headingMedium.copyWith(
            fontSize: 16,
            color: color,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }

  (String, Color, Color) _resolveStatus(String status) {
    switch (status.toUpperCase()) {
      case 'PRESENT':
      case 'COMPLETED':
        return ('Present', AppColors.success, AppColors.successLight);
      case 'LATE':
        return ('Late', AppColors.warning, AppColors.warningLight);
      case 'HALF_DAY':
        return ('Half Day', Colors.orange, const Color(0xFFFFF7ED));
      case 'ABSENT':
        return ('Absent', AppColors.error, AppColors.errorLight);
      case 'INCOMPLETE':
        return ('Incomplete', Colors.purple, const Color(0xFFF3E8FF));
      case 'PENDING_REVIEW':
        return ('Under Review', Colors.deepOrange, const Color(0xFFFFEDD5));
      case 'PENDING_SYNC':
        return ('Pending Sync', AppColors.info, AppColors.primaryLight);
      default:
        return (status, AppColors.textSecondary, AppColors.background);
    }
  }
}
