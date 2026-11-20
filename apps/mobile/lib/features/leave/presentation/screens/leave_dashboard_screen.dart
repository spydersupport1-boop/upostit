import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../auth/presentation/bloc/auth_state.dart';
import '../bloc/leave_bloc.dart';
import '../bloc/leave_event.dart';
import '../bloc/leave_state.dart';
import '../widgets/balance_card.dart';
import '../widgets/holiday_tile.dart';
import '../widgets/leave_request_card.dart';

class LeaveDashboardScreen extends StatefulWidget {
  const LeaveDashboardScreen({super.key});

  @override
  State<LeaveDashboardScreen> createState() => _LeaveDashboardScreenState();
}

class _LeaveDashboardScreenState extends State<LeaveDashboardScreen> {
  @override
  void initState() {
    super.initState();
    context.read<LeaveBloc>().add(const LeaveDashboardRequested());
  }

  void _showCancelDialog(BuildContext context, String requestId) {
    final reasonController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel Leave Request'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Are you sure you want to cancel this leave request? This action cannot be undone.',
              style: TextStyle(fontSize: 14),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: reasonController,
              decoration: const InputDecoration(
                labelText: 'Reason for cancellation (optional)',
                hintText: 'e.g. Plans changed',
                border: OutlineInputBorder(),
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Keep Leave'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
            ),
            onPressed: () {
              Navigator.of(ctx).pop();
              context.read<LeaveBloc>().add(
                    LeaveCancellationRequested(
                      requestId: requestId,
                      reason: reasonController.text.trim().isEmpty
                          ? null
                          : reasonController.text.trim(),
                    ),
                  );
            },
            child: const Text('Cancel Request'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthBloc>().state;
    final isSupervisor = authState is Authenticated &&
        authState.userProfile.user.role.toUpperCase() != 'EMPLOYEE';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Leave & Holidays'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              context.read<LeaveBloc>().add(const LeaveDashboardRequested());
            },
          ),
        ],
      ),
      body: BlocConsumer<LeaveBloc, LeaveState>(
        listener: (context, state) {
          if (state.errorMessage != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(state.errorMessage!),
                backgroundColor: AppColors.error,
              ),
            );
            context.read<LeaveBloc>().add(const LeaveNoticesCleared());
          } else if (state.successNotice != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(state.successNotice!),
                backgroundColor: AppColors.success,
              ),
            );
            context.read<LeaveBloc>().add(const LeaveNoticesCleared());
          }
        },
        builder: (context, state) {
          if (state.isLoading && state.balances.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          return RefreshIndicator(
            onRefresh: () async {
              context.read<LeaveBloc>().add(const LeaveDashboardRequested());
            },
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppSpacing.pagePadding,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Action button bar
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: () => context.push('/leave/apply'),
                          icon: const Icon(Icons.add, size: 18),
                          label: const Text('Apply for Leave'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppColors.primary,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(
                              vertical: AppSpacing.sm + 4,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: AppRadius.mdBorderRadius,
                            ),
                          ),
                        ),
                      ),
                      if (isSupervisor) ...[
                        const SizedBox(width: AppSpacing.sm),
                        OutlinedButton.icon(
                          onPressed: () => context.push('/leave/approvals'),
                          icon: const Icon(Icons.assignment_turned_in, size: 18),
                          label: const Text('Approvals'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.primary,
                            padding: const EdgeInsets.symmetric(
                              vertical: AppSpacing.sm + 4,
                              horizontal: AppSpacing.md,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: AppRadius.mdBorderRadius,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: AppSpacing.lg),

                  // Leave Balances Section
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Leave Balances',
                        style: AppTypography.headingMedium,
                      ),
                      Text(
                        '${DateTime.now().year} Allocation',
                        style: AppTypography.caption.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  if (state.balances.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.borderLight),
                      ),
                      child: const Center(
                        child: Text(
                          'No leave allocations configured for this year.',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                      ),
                    )
                  else
                    SizedBox(
                      height: 155,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: state.balances.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(width: AppSpacing.sm),
                        itemBuilder: (context, index) {
                          final balance = state.balances[index];
                          final leaveType = state.leaveTypes
                              .where((t) => t.id == balance.leaveTypeId)
                              .firstOrNull;
                          return BalanceCard(
                            balance: balance,
                            leaveType: leaveType,
                          );
                        },
                      ),
                    ),
                  const SizedBox(height: AppSpacing.lg),

                  // Recent Requests Section
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Recent Requests',
                        style: AppTypography.headingMedium,
                      ),
                      TextButton(
                        onPressed: () => context.push('/leave/history'),
                        child: const Text('View All'),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  if (state.myRequests.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.borderLight),
                      ),
                      child: const Center(
                        child: Text(
                          'No leave requests yet.',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                      ),
                    )
                  else
                    ...state.myRequests.take(3).map(
                          (request) => LeaveRequestCard(
                            request: request,
                            isSubmitting: state.isSubmitting,
                            onCancel: () =>
                                _showCancelDialog(context, request.id),
                          ),
                        ),
                  const SizedBox(height: AppSpacing.lg),

                  // Upcoming Holidays Section
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Upcoming Holidays',
                        style: AppTypography.headingMedium,
                      ),
                      TextButton(
                        onPressed: () => context.push('/leave/holidays'),
                        child: const Text('View Calendar'),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  if (state.upcomingHolidays.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.borderLight),
                      ),
                      child: const Center(
                        child: Text(
                          'No upcoming holidays scheduled.',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                      ),
                    )
                  else
                    ...state.upcomingHolidays.take(3).map(
                          (holiday) => HolidayTile(holiday: holiday),
                        ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
