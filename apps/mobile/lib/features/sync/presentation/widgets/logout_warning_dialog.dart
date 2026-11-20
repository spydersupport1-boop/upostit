import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';

/// Modal dialog shown before logout when unresolved offline attendance records exist.
///
/// Warns the employee that pending punches will remain stored locally on the device
/// and will NOT synchronize with the server until this exact account logs back in.
class LogoutWarningDialog extends StatelessWidget {
  final int unresolvedCount;
  final VoidCallback onConfirmLogout;

  const LogoutWarningDialog({
    super.key,
    required this.unresolvedCount,
    required this.onConfirmLogout,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: AppRadius.lgBorderRadius),
      titlePadding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
      contentPadding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
      actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: const BoxDecoration(
              color: AppColors.warningLight,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.warning_amber_rounded,
              color: AppColors.warning,
              size: 26,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Unsynced Records Warning',
              style: AppTypography.headingMedium,
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.warningLight.withValues(alpha: 0.6),
                borderRadius: AppRadius.mdBorderRadius,
                border: Border.all(
                  color: AppColors.warning.withValues(alpha: 0.3),
                ),
              ),
              child: Text(
                'You have $unresolvedCount unsynchronized attendance punch${unresolvedCount > 1 ? 'es' : ''} stored locally on this device.',
                style: AppTypography.bodyMedium.copyWith(
                  fontWeight: FontWeight.w700,
                  color: const Color(0xFF92400E), // Amber 800
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'If you sign out now:',
              style: AppTypography.bodySmall.copyWith(
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            _buildBulletPoint(
              'Your punches will remain safely stored on this phone and will NOT be deleted.',
            ),
            const SizedBox(height: 6),
            _buildBulletPoint(
              'They will NOT synchronize with the server until you sign back in with this exact account.',
            ),
            const SizedBox(height: 6),
            _buildBulletPoint(
              'Another user signing in will NOT be able to see or synchronize your punches.',
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          key: const Key('cancel_logout_button'),
          onPressed: () => Navigator.pop(context),
          child: Text(
            'Cancel & Stay Signed In',
            style: AppTypography.buttonText.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
        ),
        ElevatedButton(
          key: const Key('confirm_logout_anyway_button'),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.error,
            foregroundColor: Colors.white,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: AppRadius.smBorderRadius,
            ),
          ),
          onPressed: () {
            Navigator.pop(context);
            onConfirmLogout();
          },
          child: const Text('Sign Out Anyway'),
        ),
      ],
    );
  }

  Widget _buildBulletPoint(String text) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('• ', style: TextStyle(fontWeight: FontWeight.w900)),
        Expanded(
          child: Text(
            text,
            style: AppTypography.bodySmall.copyWith(
              color: AppColors.textSecondary,
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }
}
