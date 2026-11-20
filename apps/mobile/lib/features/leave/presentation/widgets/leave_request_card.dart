import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/leave_request.dart';
import 'leave_status_badge.dart';

class LeaveRequestCard extends StatelessWidget {
  final LeaveRequest request;
  final VoidCallback? onCancel;
  final bool isSubmitting;

  const LeaveRequestCard({
    super.key,
    required this.request,
    this.onCancel,
    this.isSubmitting = false,
  });

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('MMM d, yyyy');
    final startStr = dateFormat.format(request.startDateTime);
    final endStr = dateFormat.format(request.endDateTime);
    final dateRangeStr =
        request.startDate == request.endDate ? startStr : '$startStr – $endStr';

    final daysStr =
        '${request.totalDays % 1 == 0 ? request.totalDays.toInt() : request.totalDays} ${request.totalDays == 1 ? 'day' : 'days'}';

    final canCancel = request.canCancel(DateTime.now());

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: Category, Days, Status
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.xs + 2,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.primaryLight,
                      borderRadius: AppRadius.smBorderRadius,
                    ),
                    child: Text(
                      request.leaveTypeCode ?? 'LEAVE',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    daysStr,
                    style: AppTypography.headingMedium.copyWith(fontSize: 14),
                  ),
                ],
              ),
              LeaveStatusBadge(status: request.status),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),

          // Date Range & Half-day
          Row(
            children: [
              const Icon(
                Icons.calendar_today_outlined,
                size: 14,
                color: AppColors.textSecondary,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                dateRangeStr,
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w500,
                  color: AppColors.textPrimary,
                ),
              ),
              if (request.isHalfDay) ...[
                const SizedBox(width: AppSpacing.sm),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.xs + 2,
                    vertical: 1,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.infoLight,
                    borderRadius: AppRadius.smBorderRadius,
                  ),
                  child: Text(
                    request.halfDayPeriod == 'FIRST_HALF'
                        ? 'First Half'
                        : 'Second Half',
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: AppColors.info,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xs),

          // Reason
          Text(
            request.reason,
            style: AppTypography.caption.copyWith(
              color: AppColors.textSecondary,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),

          // Reviewer note if rejected or notes present
          if (request.reviewNotes != null &&
              request.reviewNotes!.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.xs + 4),
              decoration: BoxDecoration(
                color: request.isRejected
                    ? AppColors.errorLight
                    : AppColors.background,
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(
                  color: request.isRejected
                      ? AppColors.error.withValues(alpha: 0.2)
                      : AppColors.borderLight,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    request.isRejected
                        ? Icons.info_outline
                        : Icons.check_circle_outline,
                    size: 14,
                    color: request.isRejected
                        ? AppColors.error
                        : AppColors.success,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      'Supervisor: ${request.reviewNotes}',
                      style: TextStyle(
                        fontSize: 11,
                        color: request.isRejected
                            ? AppColors.error
                            : AppColors.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // Cancel button if eligible
          if (canCancel && onCancel != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: SizedBox(
                height: 32,
                child: OutlinedButton(
                  onPressed: isSubmitting ? null : onCancel,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.error,
                    side: const BorderSide(color: AppColors.error),
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm + 4,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: AppRadius.smBorderRadius,
                    ),
                  ),
                  child: isSubmitting
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor:
                                AlwaysStoppedAnimation<Color>(AppColors.error),
                          ),
                        )
                      : const Text(
                          'Cancel Request',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
