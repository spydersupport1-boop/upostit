import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/shared/widgets/loading_indicator.dart';
import 'package:mobile/features/attendance/domain/entities/today_shift.dart';
import '../bloc/schedule_bloc.dart';
import '../bloc/schedule_event.dart';
import '../bloc/schedule_state.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  @override
  void initState() {
    super.initState();
    final bloc = context.read<ScheduleBloc>();
    if (bloc.state is ScheduleInitial) {
      bloc.add(const ScheduleRequested());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Shift Schedule'),
        centerTitle: false,
        actions: [
          IconButton(
            key: const Key('refresh_schedule_button'),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh Schedule',
            onPressed: () {
              context.read<ScheduleBloc>().add(const ScheduleRequested());
            },
          ),
        ],
      ),
      body: BlocBuilder<ScheduleBloc, ScheduleState>(
        builder: (context, state) {
          if (state is ScheduleLoading || state is ScheduleInitial) {
            return const Center(
              child: LoadingIndicator(message: 'Loading shift schedule...'),
            );
          }

          if (state is ScheduleFailure) {
            return Center(
              child: Padding(
                padding: AppSpacing.pagePadding,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline_rounded,
                        color: AppColors.error, size: 48),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'Failed to Load Schedule',
                      style: AppTypography.headingMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      state.message,
                      style: AppTypography.bodySmall,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    ElevatedButton.icon(
                      key: const Key('schedule_retry_button'),
                      onPressed: () {
                        context
                            .read<ScheduleBloc>()
                            .add(const ScheduleRequested());
                      },
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            );
          }

          final loaded = state as ScheduleLoaded;

          if (!loaded.hasAssignedShift) {
            return _buildEmptyState();
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (loaded.currentShift != null) ...[
                  Text(
                    'Active Shift',
                    style: AppTypography.headingMedium.copyWith(fontSize: 16),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  _buildShiftCard(loaded.currentShift!, isActive: true),
                  const SizedBox(height: AppSpacing.lg),
                ],
                if (loaded.upcomingShifts.isNotEmpty) ...[
                  Text(
                    'Upcoming Shifts (${loaded.upcomingShifts.length})',
                    style: AppTypography.headingMedium.copyWith(fontSize: 16),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  ListView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: loaded.upcomingShifts.length,
                    itemBuilder: (context, index) {
                      return _buildShiftCard(loaded.upcomingShifts[index],
                          isActive: false);
                    },
                  ),
                ],
              ],
            ),
          );
        },
      ),
      bottomNavigationBar: _buildBottomNav(context),
    );
  }

  Widget _buildShiftCard(TodayShift shift, {required bool isActive}) {
    final effectiveFromStr = shift.effectiveFrom != null
        ? DateFormat('MMM d, yyyy').format(shift.effectiveFrom!)
        : null;
    final effectiveToStr = shift.effectiveTo != null
        ? DateFormat('MMM d, yyyy').format(shift.effectiveTo!)
        : 'Ongoing';

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(
          color: isActive
              ? AppColors.primary.withValues(alpha: 0.3)
              : AppColors.border,
          width: isActive ? 1.5 : 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  '${shift.name} (${shift.code})',
                  style: AppTypography.headingMedium.copyWith(
                    fontSize: 16,
                    color: isActive ? AppColors.primary : AppColors.textPrimary,
                  ),
                ),
              ),
              if (isActive)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    borderRadius: AppRadius.fullBorderRadius,
                  ),
                  child: Text(
                    'Active Now',
                    style: AppTypography.caption.copyWith(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w700,
                      fontSize: 11,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              const Icon(Icons.schedule_rounded,
                  size: 16, color: AppColors.textSecondary),
              const SizedBox(width: 6),
              Text(
                shift.formattedHours,
                style: AppTypography.bodySmall.copyWith(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '(${shift.formattedScheduledDuration})',
                style: AppTypography.caption.copyWith(
                  color: AppColors.textSecondary,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              if (shift.isOvernight)
                _buildTag(
                    'Overnight Shift', Colors.indigo, Colors.indigo.shade50),
              if (shift.isFlexible)
                _buildTag('Flexible Hours', Colors.teal, Colors.teal.shade50),
              _buildTag(
                '${shift.gracePeriodMinutes}m grace period',
                AppColors.textSecondary,
                AppColors.background,
              ),
              if (shift.breakDurationMinutes > 0)
                _buildTag(
                  '${shift.breakDurationMinutes}m break',
                  AppColors.warning,
                  AppColors.warningLight,
                ),
            ],
          ),
          if (effectiveFromStr != null) ...[
            const Divider(height: AppSpacing.lg),
            Row(
              children: [
                const Icon(Icons.date_range_outlined,
                    size: 14, color: AppColors.textSecondary),
                const SizedBox(width: 4),
                Text(
                  'Effective: $effectiveFromStr – $effectiveToStr',
                  style: AppTypography.caption.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTag(String text, Color textColor, Color bgColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: textColor,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: AppSpacing.pagePadding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: const BoxDecoration(
                color: AppColors.background,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.event_available_rounded,
                  size: 40, color: AppColors.textSecondary),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'No Assigned Shift',
              style: AppTypography.headingMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'You currently have no scheduled shift assignments. You may be on flexible hours or an off day.',
              style: AppTypography.bodySmall.copyWith(
                color: AppColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomNav(BuildContext context) {
    return NavigationBar(
      selectedIndex: 1,
      onDestinationSelected: (index) {
        if (index == 0) {
          context.go('/home');
        } else if (index == 2) {
          context.go('/history');
        } else if (index == 3) {
          context.go('/profile');
        }
      },
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.timer_outlined),
          selectedIcon: Icon(Icons.timer_rounded),
          label: 'Attendance',
        ),
        NavigationDestination(
          icon: Icon(Icons.calendar_month_outlined),
          selectedIcon: Icon(Icons.calendar_month_rounded),
          label: 'Schedule',
        ),
        NavigationDestination(
          icon: Icon(Icons.history_rounded),
          selectedIcon: Icon(Icons.history_toggle_off_rounded),
          label: 'History',
        ),
        NavigationDestination(
          icon: Icon(Icons.person_outline_rounded),
          selectedIcon: Icon(Icons.person_rounded),
          label: 'Profile',
        ),
      ],
    );
  }
}
