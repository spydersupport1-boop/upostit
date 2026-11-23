import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../bloc/leave_bloc.dart';
import '../bloc/leave_event.dart';
import '../bloc/leave_state.dart';
import '../widgets/leave_request_card.dart';

class LeaveHistoryScreen extends StatefulWidget {
  const LeaveHistoryScreen({super.key});

  @override
  State<LeaveHistoryScreen> createState() => _LeaveHistoryScreenState();
}

class _LeaveHistoryScreenState extends State<LeaveHistoryScreen> {
  String? _selectedFilter;

  @override
  void initState() {
    super.initState();
    context.read<LeaveBloc>().add(const LeaveHistoryRequested());
  }

  void _onFilterChanged(String? filter) {
    setState(() => _selectedFilter = filter);
    context.read<LeaveBloc>().add(LeaveHistoryRequested(statusFilter: filter));
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
                hintText: 'e.g. Schedule changed',
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
    final filters = [
      (null, 'All'),
      ('PENDING_APPROVAL', 'Pending'),
      ('APPROVED', 'Approved'),
      ('REJECTED', 'Rejected'),
      ('CANCELLED', 'Cancelled'),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Leave History'),
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

              // Request List
              Expanded(
                child: state.isLoading && state.myRequests.isEmpty
                    ? const Center(child: CircularProgressIndicator())
                    : RefreshIndicator(
                        onRefresh: () async {
                          context.read<LeaveBloc>().add(
                                LeaveHistoryRequested(
                                  statusFilter: _selectedFilter,
                                ),
                              );
                        },
                        child: state.myRequests.isEmpty
                            ? ListView(
                                physics: const AlwaysScrollableScrollPhysics(),
                                children: const [
                                  SizedBox(height: 100),
                                  Center(
                                    child: Text(
                                      'No leave requests found for this filter.',
                                      style: TextStyle(
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                  ),
                                ],
                              )
                            : ListView.builder(
                                padding: AppSpacing.pagePadding,
                                itemCount: state.myRequests.length,
                                itemBuilder: (context, index) {
                                  final req = state.myRequests[index];
                                  return LeaveRequestCard(
                                    request: req,
                                    isSubmitting: state.isSubmitting,
                                    onCancel: () =>
                                        _showCancelDialog(context, req.id),
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
