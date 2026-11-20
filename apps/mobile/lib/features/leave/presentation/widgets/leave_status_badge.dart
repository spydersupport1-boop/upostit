import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';

class LeaveStatusBadge extends StatelessWidget {
  final String status;

  const LeaveStatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final (label, textColor, bgColor) = _resolveStatus();

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xxs + 1,
      ),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: AppRadius.fullBorderRadius,
        border: Border.all(color: textColor.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: textColor,
          letterSpacing: 0.2,
        ),
      ),
    );
  }

  (String, Color, Color) _resolveStatus() {
    switch (status.toUpperCase()) {
      case 'APPROVED':
        return ('Approved', AppColors.success, AppColors.successLight);
      case 'PENDING_APPROVAL':
        return ('Pending', AppColors.warning, AppColors.warningLight);
      case 'REJECTED':
        return ('Rejected', AppColors.error, AppColors.errorLight);
      case 'CANCELLED':
        return ('Cancelled', AppColors.textSecondary, AppColors.divider);
      default:
        return (status, AppColors.textSecondary, AppColors.divider);
    }
  }
}
