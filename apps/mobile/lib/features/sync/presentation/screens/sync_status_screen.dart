import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/app_button.dart';
import '../../../../shared/widgets/empty_state_view.dart';
import '../../../../shared/widgets/loading_indicator.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../auth/presentation/bloc/auth_state.dart';
import '../bloc/sync_bloc.dart';
import '../bloc/sync_event.dart';
import '../bloc/sync_state.dart';
import '../widgets/conflict_session_card.dart';
import '../widgets/offline_status_banner.dart';
import '../widgets/sync_event_tile.dart';

/// Full screen dashboard presenting offline queue metrics, synchronization controls, and event ledger history.
class SyncStatusScreen extends StatefulWidget {
  const SyncStatusScreen({super.key});

  @override
  State<SyncStatusScreen> createState() => _SyncStatusScreenState();
}

class _SyncStatusScreenState extends State<SyncStatusScreen> {
  @override
  void initState() {
    super.initState();
    _refreshSummary();
  }

  void _refreshSummary() {
    final authState = context.read<AuthBloc>().state;
    if (authState is Authenticated) {
      context.read<SyncBloc>().add(
            SyncSummaryRequested(
              tenantId: authState.userProfile.user.tenantId,
              userId: authState.userProfile.user.id,
            ),
          );
    }
  }

  void _onSyncNowPressed() {
    final authState = context.read<AuthBloc>().state;
    if (authState is Authenticated) {
      context.read<SyncBloc>().add(
            SyncNowRequested(
              tenantId: authState.userProfile.user.tenantId,
              userId: authState.userProfile.user.id,
            ),
          );
    }
  }

  void _onSubmitConflict(String bundleId, String notes) {
    context.read<SyncBloc>().add(
          SyncSubmitConflictBundleRequested(
            bundleId: bundleId,
            employeeNotes: notes.isEmpty ? null : notes,
          ),
        );
  }

  void _onRefreshConflictStatus() {
    final authState = context.read<AuthBloc>().state;
    if (authState is Authenticated) {
      context.read<SyncBloc>().add(
            SyncRefreshConflictStatusRequested(
              tenantId: authState.userProfile.user.tenantId,
              userId: authState.userProfile.user.id,
            ),
          );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Offline Sync Status'),
        actions: [
          IconButton(
            key: const Key('refresh_sync_summary_button'),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh Status',
            onPressed: _refreshSummary,
          ),
        ],
      ),
      body: BlocConsumer<SyncBloc, SyncState>(
        listener: (context, state) {
          if (state.successMessage != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(
                  children: [
                    const Icon(Icons.check_circle_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(state.successMessage!)),
                  ],
                ),
                backgroundColor: AppColors.success,
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
          if (state.conflictActionSuccess != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(
                  children: [
                    const Icon(Icons.check_circle_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(state.conflictActionSuccess!)),
                  ],
                ),
                backgroundColor: AppColors.success,
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
          if (state.conflictActionError != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(
                  children: [
                    const Icon(Icons.error_outline_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(state.conflictActionError!)),
                  ],
                ),
                backgroundColor: AppColors.error,
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
        },
        builder: (context, state) {
          if (state.isLoading && state.events.isEmpty) {
            return const Center(
              child: LoadingIndicator(message: 'Loading sync ledger...'),
            );
          }

          final lastSyncedFormatted = state.lastSyncedAt != null
              ? DateFormat('d MMM yyyy, h:mm a')
                  .format(state.lastSyncedAt!.toLocal())
              : 'Never in this session';

          return RefreshIndicator(
            onRefresh: () async => _refreshSummary(),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 1. Offline Mode Banner
                  const OfflineStatusBanner(),
                  const SizedBox(height: AppSpacing.md),

                  // 2. Error Message Notice (if any)
                  if (state.errorMessage != null) ...[
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: AppSpacing.md),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        color: AppColors.errorLight,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(
                          color: AppColors.error.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline_rounded,
                              color: AppColors.error, size: 20),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              state.errorMessage!,
                              style: AppTypography.bodySmall.copyWith(
                                color: AppColors.error,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],

                  // 3. Metrics Grid Overview
                  _buildMetricsGrid(state),

                  const SizedBox(height: AppSpacing.md),

                  // 4. Synchronization Action Card
                  _buildSyncActionCard(state, lastSyncedFormatted),

                  const SizedBox(height: AppSpacing.lg),

                  // 4b. Quarantined Session Conflicts Section (Milestone 8.4)
                  if (state.conflictBundles.isNotEmpty) ...[
                    _buildConflictBundlesSection(state),
                    const SizedBox(height: AppSpacing.lg),
                  ],

                  // 5. Section Header for Stored Records
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Stored Queue Records',
                        style:
                            AppTypography.headingMedium.copyWith(fontSize: 16),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.divider,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '${state.events.length}',
                          style: AppTypography.bodySmall.copyWith(
                            fontWeight: FontWeight.w700,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: AppSpacing.sm),

                  // 6. Event List or Empty State
                  if (state.events.isEmpty) ...[
                    const SizedBox(height: AppSpacing.md),
                    const EmptyStateView(
                      title: 'Queue is Empty',
                      description:
                          'All attendance punches have been synchronized with the server or no records have been created offline.',
                      icon: Icons.done_all_rounded,
                    ),
                  ] else ...[
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: state.events.length,
                      separatorBuilder: (_, __) =>
                          const SizedBox(height: AppSpacing.sm),
                      itemBuilder: (context, index) {
                        return SyncEventTile(item: state.events[index]);
                      },
                    ),
                  ],

                  const SizedBox(height: AppSpacing.xl),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildMetricsGrid(SyncState state) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cardWidth = (constraints.maxWidth - AppSpacing.sm * 2) / 3;

        return Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            _buildMetricCard(
              title: 'Pending',
              count: state.pendingCount,
              color: AppColors.warning,
              icon: Icons.schedule_rounded,
              width: cardWidth,
            ),
            _buildMetricCard(
              title: 'Syncing',
              count: state.syncingCount,
              color: AppColors.primary,
              icon: Icons.sync_rounded,
              width: cardWidth,
            ),
            _buildMetricCard(
              title: 'Synced',
              count: state.syncedCount,
              color: AppColors.success,
              icon: Icons.check_circle_outline_rounded,
              width: cardWidth,
            ),
            _buildMetricCard(
              title: 'Flagged',
              count: state.flaggedCount,
              color: AppColors.warning,
              icon: Icons.flag_outlined,
              width: cardWidth,
            ),
            _buildMetricCard(
              title: 'Quarantined',
              count: state.quarantinedCount,
              color: const Color(0xFF9333EA),
              icon: Icons.shield_outlined,
              width: cardWidth,
            ),
            _buildMetricCard(
              title: 'Rejected',
              count: state.permanentlyRejectedCount,
              color: AppColors.error,
              icon: Icons.cancel_outlined,
              width: cardWidth,
            ),
          ],
        );
      },
    );
  }

  Widget _buildMetricCard({
    required String title,
    required int count,
    required Color color,
    required IconData icon,
    required double width,
  }) {
    return Container(
      width: width,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 16),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  title,
                  style: AppTypography.bodySmall.copyWith(
                    color: AppColors.textMuted,
                    fontSize: 11,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '$count',
            style: AppTypography.headingMedium.copyWith(
              color: count > 0 ? color : AppColors.textPrimary,
              fontSize: 20,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSyncActionCard(SyncState state, String lastSyncedFormatted) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Manual Synchronization',
                      style:
                          AppTypography.headingMedium.copyWith(fontSize: 15)),
                  const SizedBox(height: 2),
                  Text(
                    'Last synced: $lastSyncedFormatted',
                    style: AppTypography.bodySmall
                        .copyWith(color: AppColors.textMuted),
                  ),
                ],
              ),
              if (state.isSyncing)
                const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          AppButton(
            key: const Key('manual_sync_now_button'),
            text: state.isSyncing ? 'Synchronizing...' : 'Sync Now',
            icon: Icons.sync_rounded,
            isLoading: state.isSyncing,
            onPressed: (state.isSyncing || !state.isConnected)
                ? null
                : _onSyncNowPressed,
          ),
          if (!state.isConnected) ...[
            const SizedBox(height: AppSpacing.xs),
            Center(
              child: Text(
                'Internet connection required to synchronize',
                style: AppTypography.bodySmall
                    .copyWith(color: AppColors.textMuted),
              ),
            ),
          ] else if (state.isSyncing && state.currentOperation != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Center(
              child: Text(
                state.currentOperation!,
                style: AppTypography.bodySmall.copyWith(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ] else if (state.retryStatus != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Center(
              child: Text(
                state.retryStatus!,
                style: AppTypography.bodySmall.copyWith(
                  color: AppColors.warning,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConflictBundlesSection(SyncState state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
                Text(
                  'Quarantined Conflicts',
                  style: AppTypography.headingMedium.copyWith(fontSize: 16),
                ),
              ],
            ),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 8,
                vertical: 2,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFF9333EA).withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '${state.conflictBundles.length}',
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w700,
                  color: const Color(0xFF9333EA),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Attendance sessions quarantined due to backend policy rejections. Submit for supervisor review to resolve.',
          style: AppTypography.bodySmall.copyWith(
            color: AppColors.textMuted,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        ...state.conflictBundles.map((bundle) {
          final isThisSubmitting = state.isSubmittingConflict &&
              state.submittingBundleId == bundle.bundleId;
          return ConflictSessionCard(
            key: Key('conflict_bundle_${bundle.bundleId}'),
            bundle: bundle,
            isSubmitting: isThisSubmitting,
            isConnected: state.isConnected,
            onSubmit: (notes) => _onSubmitConflict(bundle.bundleId, notes),
            onRefreshStatus: _onRefreshConflictStatus,
          );
        }),
      ],
    );
  }
}
