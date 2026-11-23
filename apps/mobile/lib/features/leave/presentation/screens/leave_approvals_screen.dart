import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../auth/presentation/bloc/auth_state.dart';
import '../../../profile/presentation/bloc/profile_bloc.dart';
import '../../../profile/presentation/bloc/profile_state.dart';
import '../../domain/entities/leave_request.dart';
import '../bloc/leave_bloc.dart';
import '../bloc/leave_event.dart';
import '../bloc/leave_state.dart';
import '../widgets/leave_status_badge.dart';

class LeaveApprovalsScreen extends StatefulWidget {
  const LeaveApprovalsScreen({super.key});

  @override
  State<LeaveApprovalsScreen> createState() => _LeaveApprovalsScreenState();
}

class _LeaveApprovalsScreenState extends State<LeaveApprovalsScreen> {
  String? _selectedFilter = 'PENDING_APPROVAL';

  @override
  void initState() {
    super.initState();
    context.read<LeaveBloc>().add(
          SupervisorQueueRequested(statusFilter: _selectedFilter),
        );
  }

  void _onFilterChanged(String? filter) {
    setState(() => _selectedFilter = filter);
    context.read<LeaveBloc>().add(
          SupervisorQueueRequested(statusFilter: filter),
        );
  }

  void _showApproveDialog(BuildContext context, LeaveRequest request) {
    final notesController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Approve Leave Request'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Approve ${request.totalDays % 1 == 0 ? request.totalDays.toInt() : request.totalDays} day(s) of ${request.leaveTypeCode ?? 'leave'}?',
              style: const TextStyle(fontSize: 14),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: notesController,
              decoration: const InputDecoration(
                labelText: 'Approval notes (optional)',
                hintText: 'e.g. Approved, coverage confirmed',
                border: OutlineInputBorder(),
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.success,
              foregroundColor: Colors.white,
            ),
            onPressed: () {
              Navigator.of(ctx).pop();
              context.read<LeaveBloc>().add(
                    SupervisorDecisionSubmitted(
                      requestId: request.id,
                      action: 'APPROVE',
                      reason: notesController.text.trim().isEmpty
                          ? null
                          : notesController.text.trim(),
                    ),
                  );
            },
            child: const Text('Approve'),
          ),
        ],
      ),
    );
  }

  void _showRejectDialog(BuildContext context, LeaveRequest request) {
    final formKey = GlobalKey<FormState>();
    final reasonController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reject Leave Request'),
        content: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Reject leave request for ${request.totalDays % 1 == 0 ? request.totalDays.toInt() : request.totalDays} day(s)?',
                style: const TextStyle(fontSize: 14),
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: reasonController,
                decoration: const InputDecoration(
                  labelText: 'Rejection Reason *',
                  hintText: 'Please provide reason for rejection...',
                  border: OutlineInputBorder(),
                ),
                maxLines: 3,
                validator: (val) {
                  if (val == null || val.trim().isEmpty) {
                    return 'Rejection reason is required';
                  }
                  if (val.trim().length < 3) {
                    return 'Must be at least 3 characters';
                  }
                  return null;
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
            ),
            onPressed: () {
              if (formKey.currentState!.validate()) {
                Navigator.of(ctx).pop();
                context.read<LeaveBloc>().add(
                      SupervisorDecisionSubmitted(
                        requestId: request.id,
                        action: 'REJECT',
                        reason: reasonController.text.trim(),
                      ),
                    );
              }
            },
            child: const Text('Reject Request'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthBloc>().state;
    final currentUserId =
        authState is Authenticated ? authState.userProfile.user.id : null;

    String? currentEmployeeId;
    try {
      final profileBloc = context.read<ProfileBloc?>();
      if (profileBloc != null &&
          profileBloc.state is ProfileLoaded &&
          (profileBloc.state as ProfileLoaded).employee != null) {
        currentEmployeeId = (profileBloc.state as ProfileLoaded).employee!.id;
      }
    } catch (_) {
      // ProfileBloc not available in scope or test mock
    }

    final filters = [
      ('PENDING_APPROVAL', 'Pending'),
      ('APPROVED', 'Approved'),
      ('REJECTED', 'Rejected'),
      (null, 'All'),
    ];

    final dateFormat = DateFormat('MMM d, yyyy');

    return Scaffold(
      appBar: AppBar(
        title: const Text('Leave Approvals'),
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
          return Column(
            children: [
              // Filter Chips
              Container(
                height: 52,
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.xs,
                ),
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: filters.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(width: AppSpacing.xs),
                  itemBuilder: (context, index) {
                    final (val, label) = filters[index];
                    final isSelected = _selectedFilter == val;
                    return FilterChip(
                      selected: isSelected,
                      label: Text(label),
                      selectedColor: AppColors.primaryLight,
                      labelStyle: TextStyle(
                        fontSize: 12,
                        fontWeight:
                            isSelected ? FontWeight.w600 : FontWeight.w400,
                        color: isSelected
                            ? AppColors.primary
                            : AppColors.textSecondary,
                      ),
                      onSelected: (_) => _onFilterChanged(val),
                    );
                  },
                ),
              ),
              const Divider(height: 1),

              // Queue List
              Expanded(
                child: state.isLoading && state.supervisorQueue.isEmpty
                    ? const Center(child: CircularProgressIndicator())
                    : RefreshIndicator(
                        onRefresh: () async {
                          context.read<LeaveBloc>().add(
                                SupervisorQueueRequested(
                                  statusFilter: _selectedFilter,
                                ),
                              );
                        },
                        child: state.supervisorQueue.isEmpty
                            ? ListView(
                                physics: const AlwaysScrollableScrollPhysics(),
                                children: const [
                                  SizedBox(height: 100),
                                  Center(
                                    child: Text(
                                      'No leave requests awaiting adjudication.',
                                      style: TextStyle(
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                  ),
                                ],
                              )
                            : ListView.builder(
                                padding: AppSpacing.pagePadding,
                                itemCount: state.supervisorQueue.length,
                                itemBuilder: (context, index) {
                                  final req = state.supervisorQueue[index];
                                  final isSelf = (currentEmployeeId != null &&
                                          req.employeeId ==
                                              currentEmployeeId) ||
                                      (currentUserId != null &&
                                          req.employeeId == currentUserId);
                                  final isPending = req.isPending;

                                  final startStr =
                                      dateFormat.format(req.startDateTime);
                                  final endStr =
                                      dateFormat.format(req.endDateTime);
                                  final dateRangeStr =
                                      req.startDate == req.endDate
                                          ? startStr
                                          : '$startStr – $endStr';
                                  final daysStr =
                                      '${req.totalDays % 1 == 0 ? req.totalDays.toInt() : req.totalDays} ${req.totalDays == 1 ? 'day' : 'days'}';

                                  return Container(
                                    margin: const EdgeInsets.only(
                                      bottom: AppSpacing.md,
                                    ),
                                    padding:
                                        const EdgeInsets.all(AppSpacing.md),
                                    decoration: BoxDecoration(
                                      color: AppColors.surface,
                                      borderRadius: AppRadius.mdBorderRadius,
                                      border: Border.all(
                                        color: AppColors.borderLight,
                                      ),
                                    ),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        // Top Row: Type, Days, Status
                                        Row(
                                          mainAxisAlignment:
                                              MainAxisAlignment.spaceBetween,
                                          children: [
                                            Row(
                                              children: [
                                                Container(
                                                  padding: const EdgeInsets
                                                      .symmetric(
                                                    horizontal:
                                                        AppSpacing.xs + 2,
                                                    vertical: 2,
                                                  ),
                                                  decoration: BoxDecoration(
                                                    color:
                                                        AppColors.primaryLight,
                                                    borderRadius: AppRadius
                                                        .smBorderRadius,
                                                  ),
                                                  child: Text(
                                                    req.leaveTypeCode ??
                                                        'LEAVE',
                                                    style: const TextStyle(
                                                      fontSize: 11,
                                                      fontWeight:
                                                          FontWeight.w700,
                                                      color: AppColors.primary,
                                                    ),
                                                  ),
                                                ),
                                                const SizedBox(
                                                  width: AppSpacing.sm,
                                                ),
                                                Text(
                                                  daysStr,
                                                  style: AppTypography
                                                      .headingMedium
                                                      .copyWith(fontSize: 14),
                                                ),
                                              ],
                                            ),
                                            LeaveStatusBadge(
                                                status: req.status),
                                          ],
                                        ),
                                        const SizedBox(height: AppSpacing.sm),

                                        // Dates & Half-Day
                                        Row(
                                          children: [
                                            const Icon(
                                              Icons.calendar_today_outlined,
                                              size: 14,
                                              color: AppColors.textSecondary,
                                            ),
                                            const SizedBox(
                                              width: AppSpacing.xs,
                                            ),
                                            Text(
                                              dateRangeStr,
                                              style: AppTypography.bodySmall
                                                  .copyWith(
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                            if (req.isHalfDay) ...[
                                              const SizedBox(
                                                width: AppSpacing.sm,
                                              ),
                                              Container(
                                                padding:
                                                    const EdgeInsets.symmetric(
                                                  horizontal: AppSpacing.xs + 2,
                                                  vertical: 1,
                                                ),
                                                decoration: BoxDecoration(
                                                  color: AppColors.infoLight,
                                                  borderRadius:
                                                      AppRadius.smBorderRadius,
                                                ),
                                                child: Text(
                                                  req.halfDayPeriod ==
                                                          'FIRST_HALF'
                                                      ? 'First Half'
                                                      : 'Second Half',
                                                  style: const TextStyle(
                                                    fontSize: 10,
                                                    fontWeight: FontWeight.w600,
                                                    color: AppColors.info,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ],
                                        ),
                                        const SizedBox(height: AppSpacing.xs),

                                        // Reason
                                        Text(
                                          'Reason: ${req.reason}',
                                          style: AppTypography.caption.copyWith(
                                            color: AppColors.textSecondary,
                                          ),
                                        ),

                                        if (req.reviewNotes != null &&
                                            req.reviewNotes!.isNotEmpty) ...[
                                          const SizedBox(height: AppSpacing.xs),
                                          Text(
                                            'Notes: ${req.reviewNotes}',
                                            style: const TextStyle(
                                              fontSize: 11,
                                              color: AppColors.textMuted,
                                              fontStyle: FontStyle.italic,
                                            ),
                                          ),
                                        ],

                                        // Anti-self-approval notice
                                        if (isSelf && isPending) ...[
                                          const SizedBox(height: AppSpacing.sm),
                                          Container(
                                            padding: const EdgeInsets.all(
                                              AppSpacing.xs + 2,
                                            ),
                                            decoration: BoxDecoration(
                                              color: AppColors.warningLight,
                                              borderRadius:
                                                  AppRadius.smBorderRadius,
                                            ),
                                            child: const Row(
                                              children: [
                                                Icon(
                                                  Icons.block,
                                                  size: 14,
                                                  color: AppColors.warning,
                                                ),
                                                SizedBox(width: AppSpacing.xs),
                                                Expanded(
                                                  child: Text(
                                                    'Anti-Self-Approval: You cannot approve or reject your own leave request.',
                                                    style: TextStyle(
                                                      fontSize: 11,
                                                      color: AppColors.warning,
                                                      fontWeight:
                                                          FontWeight.w500,
                                                    ),
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                        ],

                                        // Action buttons if pending and not self
                                        if (isPending && !isSelf) ...[
                                          const SizedBox(height: AppSpacing.md),
                                          Row(
                                            mainAxisAlignment:
                                                MainAxisAlignment.end,
                                            children: [
                                              OutlinedButton.icon(
                                                onPressed: state.isSubmitting
                                                    ? null
                                                    : () => _showRejectDialog(
                                                          context,
                                                          req,
                                                        ),
                                                icon: const Icon(Icons.close,
                                                    size: 16),
                                                label: const Text('Reject'),
                                                style: OutlinedButton.styleFrom(
                                                  foregroundColor:
                                                      AppColors.error,
                                                  side: const BorderSide(
                                                    color: AppColors.error,
                                                  ),
                                                  padding: const EdgeInsets
                                                      .symmetric(
                                                    horizontal: AppSpacing.md,
                                                    vertical: AppSpacing.xs,
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(
                                                width: AppSpacing.sm,
                                              ),
                                              ElevatedButton.icon(
                                                onPressed: state.isSubmitting
                                                    ? null
                                                    : () => _showApproveDialog(
                                                          context,
                                                          req,
                                                        ),
                                                icon: const Icon(Icons.check,
                                                    size: 16),
                                                label: const Text('Approve'),
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor:
                                                      AppColors.success,
                                                  foregroundColor: Colors.white,
                                                  padding: const EdgeInsets
                                                      .symmetric(
                                                    horizontal: AppSpacing.md,
                                                    vertical: AppSpacing.xs,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ],
                                    ),
                                  );
                                },
                              ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
