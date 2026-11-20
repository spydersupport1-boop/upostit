import 'package:flutter/material.dart';
import '../../core/constants/app_colors.dart';
import '../../core/constants/app_spacing.dart';
import '../../core/constants/app_typography.dart';

enum ButtonVariant { primary, secondary, outlined, destructive }

/// Production-ready accessible button component supporting variants,
/// loading spinner, leading icon, and disabled states.
class AppButton extends StatelessWidget {
  final String text;
  final VoidCallback? onPressed;
  final bool isLoading;
  final ButtonVariant variant;
  final IconData? icon;
  final double? width;
  final double height;

  const AppButton({
    super.key,
    required this.text,
    this.onPressed,
    this.isLoading = false,
    this.variant = ButtonVariant.primary,
    this.icon,
    this.width,
    this.height = 50.0,
  });

  @override
  Widget build(BuildContext context) {
    final isEnabled = onPressed != null && !isLoading;

    Color backgroundColor;
    Color foregroundColor;
    BorderSide? borderSide;

    switch (variant) {
      case ButtonVariant.primary:
        backgroundColor = AppColors.primary;
        foregroundColor = Colors.white;
        break;
      case ButtonVariant.secondary:
        backgroundColor = AppColors.secondary;
        foregroundColor = Colors.white;
        break;
      case ButtonVariant.outlined:
        backgroundColor = Colors.transparent;
        foregroundColor = AppColors.primary;
        borderSide = const BorderSide(color: AppColors.border, width: 1.5);
        break;
      case ButtonVariant.destructive:
        backgroundColor = AppColors.error;
        foregroundColor = Colors.white;
        break;
    }

    Widget content = Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (isLoading) ...[
          SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2.2,
              valueColor: AlwaysStoppedAnimation<Color>(
                variant == ButtonVariant.outlined
                    ? AppColors.primary
                    : Colors.white,
              ),
            ),
          ),
          const SizedBox(width: 12),
        ] else if (icon != null) ...[
          Icon(icon,
              size: 18,
              color: isEnabled ? foregroundColor : AppColors.textMuted),
          const SizedBox(width: 8),
        ],
        Text(
          text,
          style: AppTypography.buttonText.copyWith(
            color: isEnabled ? foregroundColor : AppColors.textMuted,
          ),
        ),
      ],
    );

    return Semantics(
      button: true,
      enabled: isEnabled,
      label: text,
      child: SizedBox(
        width: width ?? double.infinity,
        height: height,
        child: ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: backgroundColor,
            foregroundColor: foregroundColor,
            disabledBackgroundColor: AppColors.divider,
            disabledForegroundColor: AppColors.textMuted,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: AppRadius.mdBorderRadius,
              side: borderSide ?? BorderSide.none,
            ),
          ),
          onPressed: isEnabled ? onPressed : null,
          child: content,
        ),
      ),
    );
  }
}
