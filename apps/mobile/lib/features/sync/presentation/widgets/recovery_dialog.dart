import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../data/services/database_recovery_coordinator.dart';

/// Modal dialog shown when offline database is corrupted, unreadable, or missing its encryption key.
///
/// Communicates fail-closed status clearly: the encrypted file is preserved as backup
/// rather than silently destroyed.
class RecoveryDialog extends StatelessWidget {
  final DatabaseRecoveryReport report;
  final VoidCallback? onQuarantineConfirmed;
  final VoidCallback? onDismiss;

  const RecoveryDialog({
    super.key,
    required this.report,
    this.onQuarantineConfirmed,
    this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    final isCritical = report.status == DatabaseHealthStatus.corruptedDatabase ||
        report.status == DatabaseHealthStatus.missingKey;

    return AlertDialog(
      title: Row(
        children: [
          Icon(
            isCritical ? Icons.security_update_warning : Icons.warning_amber,
            color: isCritical ? AppColors.error : AppColors.warning,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Database Security Recovery',
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
            Text(
              'Status: ${report.status.name.toUpperCase()}',
              style: AppTypography.bodySmall.copyWith(
                fontWeight: FontWeight.bold,
                color: isCritical ? AppColors.error : AppColors.warning,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              report.message,
              style: AppTypography.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(AppRadius.sm),
                border: Border.all(color: AppColors.borderLight),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Fail-Closed Invariant Guarantee:',
                    style: AppTypography.bodySmall.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'Your offline attendance evidence is never silently deleted. '
                    'If the encrypted database cannot be opened, it will be securely '
                    'quarantined as a timestamped backup file for forensic recovery.',
                    style: AppTypography.caption,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        if (onDismiss != null)
          TextButton(
            onPressed: onDismiss,
            child: const Text('Dismiss'),
          ),
        if (onQuarantineConfirmed != null)
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
            ),
            onPressed: onQuarantineConfirmed,
            child: const Text('Quarantine & Reset'),
          ),
      ],
    );
  }
}
