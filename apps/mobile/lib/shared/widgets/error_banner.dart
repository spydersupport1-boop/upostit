import 'package:flutter/material.dart';
import '../../core/constants/app_colors.dart';
import '../../core/constants/app_spacing.dart';
import '../../core/constants/app_typography.dart';

/// Reusable contextual banner for error, warning, or info notifications.
class ErrorBanner extends StatelessWidget {
  final String message;
  final VoidCallback? onDismiss;
  final bool isWarning;

  const ErrorBanner({
    super.key,
    required this.message,
    this.onDismiss,
    this.isWarning = false,
  });

  @override
  Widget build(BuildContext context) {
    final bgColor = isWarning ? AppColors.warningLight : AppColors.errorLight;
    final borderColor = isWarning ? AppColors.warning : AppColors.error;
    final icon =
        isWarning ? Icons.warning_amber_rounded : Icons.error_outline_rounded;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: borderColor.withValues(alpha: 0.3), width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: borderColor),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: AppTypography.bodyMedium.copyWith(
                color: borderColor,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          if (onDismiss != null)
            GestureDetector(
              onTap: onDismiss,
              child: Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child: Icon(Icons.close, size: 18, color: borderColor),
              ),
            ),
        ],
      ),
    );
  }
}
