import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/attendance_event.dart';
import '../../domain/entities/attendance_status.dart';

/// Primary action widget providing context-aware punch controls with optimistic visual feedback.
class HeroPunchCard extends StatelessWidget {
  final AttendanceStatus status;
  final bool isSubmitting;
  final bool isUnsupported;
  final AttendanceEventType? inFlightEventType;
  final void Function(AttendanceEventType eventType) onPunchPressed;

  const HeroPunchCard({
    super.key,
    required this.status,
    required this.isSubmitting,
    this.isUnsupported = false,
    this.inFlightEventType,
    required this.onPunchPressed,
  });

  void _handleTap(AttendanceEventType type) {
    if (isSubmitting || isUnsupported) return;
    HapticFeedback.mediumImpact();
    onPunchPressed(type);
  }

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case AttendanceStatus.notCheckedIn:
        return _buildSinglePunchButton(
          label: 'CHECK IN',
          subtitle: 'Tap to record presence',
          icon: Icons.fingerprint_rounded,
          color: AppColors.success,
          lightColor: AppColors.successLight,
          targetType: AttendanceEventType.checkIn,
          key: const Key('hero_check_in_button'),
        );

      case AttendanceStatus.working:
        return Column(
          children: [
            _buildSinglePunchButton(
              label: 'CHECK OUT',
              subtitle: 'End shift for today',
              icon: Icons.logout_rounded,
              color: AppColors.error,
              lightColor: AppColors.errorLight,
              targetType: AttendanceEventType.checkOut,
              key: const Key('hero_check_out_button'),
            ),
            const SizedBox(height: AppSpacing.md),
            _buildSecondaryBreakButton(
              label: 'START BREAK',
              icon: Icons.free_breakfast_outlined,
              color: AppColors.warning,
              lightColor: AppColors.warningLight,
              targetType: AttendanceEventType.breakStart,
              key: const Key('break_start_button'),
            ),
          ],
        );

      case AttendanceStatus.onBreak:
        return Column(
          children: [
            _buildSinglePunchButton(
              label: 'RESUME WORK',
              subtitle: 'End break and continue working',
              icon: Icons.play_arrow_rounded,
              color: AppColors.info,
              lightColor: AppColors.infoLight,
              targetType: AttendanceEventType.breakEnd,
              key: const Key('hero_break_end_button'),
            ),
            const SizedBox(height: AppSpacing.md),
            _buildSecondaryBreakButton(
              label: 'CHECK OUT',
              icon: Icons.logout_rounded,
              color: AppColors.error,
              lightColor: AppColors.errorLight,
              targetType: AttendanceEventType.checkOut,
              key: const Key('break_checkout_button'),
            ),
          ],
        );

      case AttendanceStatus.completed:
        return Column(
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.xl,
              ),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.lgBorderRadius,
                border: Border.all(color: AppColors.borderLight),
              ),
              child: Column(
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: const BoxDecoration(
                      color: AppColors.successLight,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.check_circle_rounded,
                      color: AppColors.success,
                      size: 36,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    'Shift Completed',
                    style: AppTypography.headingMedium,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'You have checked out for today. Great job!',
                    style: AppTypography.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            // Allow checking in again if shift allows multi-session punches
            OutlinedButton.icon(
              key: const Key('re_check_in_button'),
              onPressed: isSubmitting
                  ? null
                  : () => _handleTap(AttendanceEventType.checkIn),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
                shape: RoundedRectangleBorder(
                  borderRadius: AppRadius.mdBorderRadius,
                ),
              ),
              icon: isSubmitting &&
                      inFlightEventType == AttendanceEventType.checkIn
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.login_rounded, size: 18),
              label: const Text('Check In Again'),
            ),
          ],
        );
    }
  }

  Widget _buildSinglePunchButton({
    required String label,
    required String subtitle,
    required IconData icon,
    required Color color,
    required Color lightColor,
    required AttendanceEventType targetType,
    required Key key,
  }) {
    final isThisSubmitting = isSubmitting && inFlightEventType == targetType;
    final effectiveLabel = isUnsupported ? 'PUNCH DISABLED' : label;
    final effectiveSubtitle = isUnsupported
        ? 'Verification method not supported on this release'
        : (isThisSubmitting ? 'Recording attendance...' : subtitle);
    final effectiveColor = isUnsupported ? AppColors.textMuted : color;
    final effectiveLightColor = isUnsupported ? AppColors.surface : lightColor;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: key,
        onTap: (isSubmitting || isUnsupported)
            ? null
            : () => _handleTap(targetType),
        borderRadius: AppRadius.xlBorderRadius,
        splashColor: effectiveColor.withValues(alpha: 0.1),
        highlightColor: effectiveColor.withValues(alpha: 0.05),
        child: Ink(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: AppRadius.xlBorderRadius,
            border: Border.all(
              color: isSubmitting || isUnsupported
                  ? AppColors.borderLight
                  : effectiveColor.withValues(alpha: 0.3),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: effectiveColor.withValues(
                    alpha: isUnsupported ? 0.04 : 0.12),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.lg + 4,
            ),
            child: Row(
              children: [
                // Prominent circular badge
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    color: isSubmitting || isUnsupported
                        ? AppColors.borderLight
                        : effectiveLightColor,
                    shape: BoxShape.circle,
                  ),
                  child: isThisSubmitting
                      ? Center(
                          child: SizedBox(
                            width: 26,
                            height: 26,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.8,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(effectiveColor),
                            ),
                          ),
                        )
                      : Icon(
                          icon,
                          color: isSubmitting || isUnsupported
                              ? AppColors.textMuted
                              : effectiveColor,
                          size: 32,
                        ),
                ),
                const SizedBox(width: AppSpacing.md + 2),
                // Text details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        effectiveLabel,
                        style: AppTypography.headingMedium.copyWith(
                          fontSize: 19,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.3,
                          color: isSubmitting || isUnsupported
                              ? AppColors.textMuted
                              : effectiveColor,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        effectiveSubtitle,
                        style: AppTypography.bodySmall.copyWith(
                          color: AppColors.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.arrow_forward_ios_rounded,
                  size: 18,
                  color: isSubmitting
                      ? AppColors.border
                      : color.withValues(alpha: 0.6),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSecondaryBreakButton({
    required String label,
    required IconData icon,
    required Color color,
    required Color lightColor,
    required AttendanceEventType targetType,
    required Key key,
  }) {
    final isThisSubmitting = isSubmitting && inFlightEventType == targetType;

    return SizedBox(
      width: double.infinity,
      height: 50,
      child: OutlinedButton(
        key: key,
        onPressed: isSubmitting ? null : () => _handleTap(targetType),
        style: OutlinedButton.styleFrom(
          foregroundColor: color,
          side: BorderSide(color: color.withValues(alpha: 0.4)),
          backgroundColor: lightColor.withValues(alpha: 0.4),
          shape: RoundedRectangleBorder(
            borderRadius: AppRadius.lgBorderRadius,
          ),
        ),
        child: isThisSubmitting
            ? Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text('Recording...', style: TextStyle(color: color)),
                ],
              )
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(icon, size: 20, color: color),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.2,
                      color: color,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
