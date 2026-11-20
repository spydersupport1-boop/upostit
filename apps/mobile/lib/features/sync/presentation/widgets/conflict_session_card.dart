import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/app_button.dart';
import '../../../attendance/domain/entities/attendance_event.dart';
import '../../domain/entities/offline_sequence_conflict_bundle.dart';

/// Card presenting an offline attendance session conflict with primary rejected punch,
/// dependent quarantined punches, supervisor notes, and submission controls.
class ConflictSessionCard extends StatefulWidget {
  final OfflineSequenceConflictBundle bundle;
  final bool isSubmitting;
  final bool isConnected;
  final void Function(String notes) onSubmit;
  final VoidCallback onRefreshStatus;

  const ConflictSessionCard({
    super.key,
    required this.bundle,
    this.isSubmitting = false,
    this.isConnected = true,
    required this.onSubmit,
    required this.onRefreshStatus,
  });

  @override
  State<ConflictSessionCard> createState() => _ConflictSessionCardState();
}

class _ConflictSessionCardState extends State<ConflictSessionCard> {
  late final TextEditingController _notesController;

  @override
  void initState() {
    super.initState();
    _notesController = TextEditingController(
      text: widget.bundle.employeeNotes ?? '',
    );
  }

  @override
  void didUpdateWidget(covariant ConflictSessionCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.bundle.employeeNotes != oldWidget.bundle.employeeNotes &&
        widget.bundle.employeeNotes != null) {
      _notesController.text = widget.bundle.employeeNotes!;
    }
  }

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bundle = widget.bundle;
    final primary = bundle.primaryRejectedEvent;
    final hasSession = bundle.sessionId != null && bundle.sessionId!.isNotEmpty;
    final sessionDisplay = hasSession
        ? 'Session #${bundle.sessionId!.length > 8 ? bundle.sessionId!.substring(0, 8) : bundle.sessionId}'
        : 'Offline Session';

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(
          color: _getBorderColor(bundle.submissionStatus),
          width: 1.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. Header Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.shield_outlined,
                    color: Color(0xFF9333EA),
                    size: 20,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        sessionDisplay,
                        style:
                            AppTypography.headingMedium.copyWith(fontSize: 15),
                      ),
                      Text(
                        '${bundle.totalEventsCount} event${bundle.totalEventsCount > 1 ? 's' : ''} in conflict bundle',
                        style: AppTypography.bodySmall
                            .copyWith(color: AppColors.textMuted, fontSize: 11),
                      ),
                    ],
                  ),
                ],
              ),
              _buildStatusBadge(bundle.submissionStatus),
            ],
          ),

          const SizedBox(height: AppSpacing.md),
          const Divider(height: 1, color: AppColors.borderLight),
          const SizedBox(height: AppSpacing.md),

          // 2. Primary Rejected Event Details
          Text(
            'Primary Rejected Event',
            style: AppTypography.bodySmall.copyWith(
              fontWeight: FontWeight.w700,
              color: AppColors.error,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Container(
            padding: const EdgeInsets.all(AppSpacing.sm),
            decoration: BoxDecoration(
              color: AppColors.errorLight,
              borderRadius: AppRadius.smBorderRadius,
              border: Border.all(color: AppColors.error.withValues(alpha: 0.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Icon(
                          primary.eventType == AttendanceEventType.checkIn
                              ? Icons.login_rounded
                              : Icons.logout_rounded,
                          size: 16,
                          color: AppColors.error,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          primary.eventType == AttendanceEventType.checkIn
                              ? 'Check-In'
                              : 'Check-Out',
                          style: AppTypography.bodySmall.copyWith(
                            fontWeight: FontWeight.w700,
                            color: AppColors.error,
                          ),
                        ),
                      ],
                    ),
                    Text(
                      DateFormat('d MMM yyyy, h:mm:ss a')
                          .format(primary.deviceReportedAt.toLocal()),
                      style: AppTypography.bodySmall.copyWith(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
                if (primary.lastErrorMessage != null &&
                    primary.lastErrorMessage!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Rejection: ${primary.lastErrorMessage!}',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.error,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ],
            ),
          ),

          // 3. Dependent Quarantined Events
          if (bundle.dependentEvents.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              'Dependent Quarantined Events (${bundle.dependentEvents.length})',
              style: AppTypography.bodySmall.copyWith(
                fontWeight: FontWeight.w700,
                color: const Color(0xFF9333EA),
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Column(
              children: bundle.dependentEvents.map((dep) {
                return Container(
                  margin: const EdgeInsets.only(bottom: 4),
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFAF5FF),
                    borderRadius: AppRadius.smBorderRadius,
                    border: Border.all(
                      color: const Color(0xFF9333EA).withValues(alpha: 0.15),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Icon(
                            dep.eventType == AttendanceEventType.checkIn
                                ? Icons.login_rounded
                                : Icons.logout_rounded,
                            size: 14,
                            color: const Color(0xFF9333EA),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            dep.eventType == AttendanceEventType.checkIn
                                ? 'Check-In'
                                : 'Check-Out',
                            style: AppTypography.bodySmall.copyWith(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: const Color(0xFF6B21A8),
                            ),
                          ),
                        ],
                      ),
                      Text(
                        DateFormat('d MMM, h:mm:ss a')
                            .format(dep.deviceReportedAt.toLocal()),
                        style: AppTypography.bodySmall.copyWith(
                          fontSize: 11,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ],

          // 4. Supervisor Decision Callout (if decided)
          if (bundle.supervisorDecision != null ||
              bundle.supervisorDecisionReason != null) ...[
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: bundle.isApproved
                    ? AppColors.successLight
                    : AppColors.errorLight,
                borderRadius: AppRadius.smBorderRadius,
                border: Border.all(
                  color: bundle.isApproved
                      ? AppColors.success.withValues(alpha: 0.3)
                      : AppColors.error.withValues(alpha: 0.3),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        bundle.isApproved
                            ? Icons.check_circle_outline_rounded
                            : Icons.cancel_outlined,
                        size: 16,
                        color: bundle.isApproved
                            ? AppColors.success
                            : AppColors.error,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Supervisor Decision: ${bundle.supervisorDecision ?? (bundle.isApproved ? "APPROVED" : "REJECTED")}',
                        style: AppTypography.bodySmall.copyWith(
                          fontWeight: FontWeight.w700,
                          color: bundle.isApproved
                              ? AppColors.success
                              : AppColors.error,
                        ),
                      ),
                    ],
                  ),
                  if (bundle.supervisorDecisionReason != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      'Reason: ${bundle.supervisorDecisionReason!}',
                      style: AppTypography.bodySmall.copyWith(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],

          const SizedBox(height: AppSpacing.md),

          // 5. Actions / Controls
          if (bundle.submissionStatus ==
              ConflictSubmissionStatus.notSubmitted) ...[
            TextField(
              key: Key('conflict_notes_input_${bundle.bundleId}'),
              controller: _notesController,
              decoration: InputDecoration(
                hintText:
                    'Add an explanation for supervisor review (optional)...',
                hintStyle: AppTypography.bodySmall
                    .copyWith(color: AppColors.textMuted),
                contentPadding: const EdgeInsets.all(AppSpacing.sm),
                border: OutlineInputBorder(
                  borderRadius: AppRadius.smBorderRadius,
                  borderSide: const BorderSide(color: AppColors.border),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: AppRadius.smBorderRadius,
                  borderSide: const BorderSide(color: AppColors.primary),
                ),
              ),
              maxLines: 2,
              style: AppTypography.bodySmall,
            ),
            const SizedBox(height: AppSpacing.sm),
            AppButton(
              key: Key('submit_conflict_${bundle.bundleId}'),
              text: widget.isSubmitting
                  ? 'Submitting...'
                  : 'Submit for Supervisor Review',
              icon: Icons.send_rounded,
              isLoading: widget.isSubmitting,
              onPressed: (!widget.isConnected || widget.isSubmitting)
                  ? null
                  : () => widget.onSubmit(_notesController.text.trim()),
            ),
            if (!widget.isConnected) ...[
              const SizedBox(height: 4),
              Text(
                'Internet connection required to submit conflict.',
                style: AppTypography.bodySmall.copyWith(
                  color: AppColors.textMuted,
                  fontSize: 11,
                ),
              ),
            ],
          ] else if (bundle.submissionStatus ==
              ConflictSubmissionStatus.pendingReview) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    'Submitted for review. Awaiting supervisor decision.',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.textSecondary,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
                TextButton.icon(
                  key: Key('refresh_conflict_status_${bundle.bundleId}'),
                  onPressed: widget.onRefreshStatus,
                  icon: const Icon(Icons.refresh_rounded, size: 16),
                  label: const Text('Check Status'),
                ),
              ],
            ),
          ] else if (bundle.submissionStatus ==
              ConflictSubmissionStatus.approved) ...[
            Row(
              children: [
                const Icon(Icons.check_circle_rounded,
                    color: AppColors.success, size: 18),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Conflict resolved and approved. Attendance recalculated.',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.success,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Color _getBorderColor(ConflictSubmissionStatus status) {
    switch (status) {
      case ConflictSubmissionStatus.notSubmitted:
        return const Color(0xFF9333EA).withValues(alpha: 0.4);
      case ConflictSubmissionStatus.pendingReview:
        return AppColors.primary.withValues(alpha: 0.4);
      case ConflictSubmissionStatus.approved:
        return AppColors.success.withValues(alpha: 0.4);
      case ConflictSubmissionStatus.rejected:
        return AppColors.error.withValues(alpha: 0.4);
    }
  }

  Widget _buildStatusBadge(ConflictSubmissionStatus status) {
    Color bg;
    Color fg;
    String label;

    switch (status) {
      case ConflictSubmissionStatus.notSubmitted:
        bg = AppColors.warningLight;
        fg = AppColors.warning;
        label = 'Needs Review';
        break;
      case ConflictSubmissionStatus.pendingReview:
        bg = AppColors.primaryLight;
        fg = AppColors.primary;
        label = 'Pending Review';
        break;
      case ConflictSubmissionStatus.approved:
        bg = AppColors.successLight;
        fg = AppColors.success;
        label = 'Approved';
        break;
      case ConflictSubmissionStatus.rejected:
        bg = AppColors.errorLight;
        fg = AppColors.error;
        label = 'Rejected';
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: fg.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: AppTypography.bodySmall.copyWith(
          color: fg,
          fontWeight: FontWeight.w700,
          fontSize: 11,
        ),
      ),
    );
  }
}
