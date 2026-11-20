import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../bloc/sync_bloc.dart';
import '../bloc/sync_state.dart';

/// Reusable non-intrusive status banner indicating offline mode or synchronization activity.
///
/// Discretely indicates when internet connectivity is down and alerts the employee
/// that attendance punches will be stored locally and securely until connection returns.
class OfflineStatusBanner extends StatelessWidget {
  final VoidCallback? onTap;

  const OfflineStatusBanner({super.key, this.onTap});

  @override
  Widget build(BuildContext context) {
    try {
      context.read<SyncBloc>();
    } catch (_) {
      return const SizedBox.shrink();
    }

    return BlocBuilder<SyncBloc, SyncState>(
      builder: (context, state) {
        // If connected and no pending records, keep UI clean
        if (state.isConnected &&
            state.unresolvedCount == 0 &&
            !state.isSyncing) {
          return const SizedBox.shrink();
        }

        // Case A: Disconnected / Offline Mode
        if (!state.isConnected) {
          return InkWell(
            onTap: onTap ?? () => context.push('/sync'),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: AppColors.infoLight,
                border: Border.all(
                  color: AppColors.info.withValues(alpha: 0.3),
                ),
                borderRadius: AppRadius.smBorderRadius,
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.cloud_off_rounded,
                    color: AppColors.info,
                    size: 20,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'Offline Mode — Punches are saved locally and will sync when connected.',
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.info,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  if (state.unresolvedCount > 0) ...[
                    const SizedBox(width: AppSpacing.xs),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.info,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${state.unresolvedCount} pending',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        }

        // Case B: Currently Synchronizing
        if (state.isSyncing) {
          return Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: AppColors.primaryLight,
              border: Border.all(
                color: AppColors.primary.withValues(alpha: 0.3),
              ),
              borderRadius: AppRadius.smBorderRadius,
            ),
            child: Row(
              children: [
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor:
                        AlwaysStoppedAnimation<Color>(AppColors.primary),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    'Synchronizing offline attendance records...',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          );
        }

        // Case C: Online with pending / unresolved punches waiting
        if (state.unresolvedCount > 0) {
          return InkWell(
            onTap: onTap ?? () => context.push('/sync'),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: AppColors.warningLight,
                border: Border.all(
                  color: AppColors.warning.withValues(alpha: 0.3),
                ),
                borderRadius: AppRadius.smBorderRadius,
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.sync_problem_rounded,
                    color: AppColors.warning,
                    size: 20,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      '${state.unresolvedCount} punch${state.unresolvedCount > 1 ? 'es' : ''} stored locally waiting to sync.',
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.warning,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Text(
                    'View',
                    style: AppTypography.buttonText.copyWith(
                      color: AppColors.warning,
                      fontSize: 12,
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right_rounded,
                    color: AppColors.warning,
                    size: 18,
                  ),
                ],
              ),
            ),
          );
        }

        return const SizedBox.shrink();
      },
    );
  }
}
