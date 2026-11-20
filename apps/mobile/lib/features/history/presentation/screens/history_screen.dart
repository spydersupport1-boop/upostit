import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile/core/constants/app_colors.dart';
import 'package:mobile/core/constants/app_spacing.dart';
import 'package:mobile/core/constants/app_typography.dart';
import 'package:mobile/shared/widgets/loading_indicator.dart';
import '../bloc/history_bloc.dart';
import '../bloc/history_event.dart';
import '../bloc/history_state.dart';
import '../widgets/attendance_summary_cards.dart';
import '../widgets/daily_attendance_tile.dart';
import '../widgets/monthly_calendar_grid.dart';
import 'daily_attendance_detail_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  @override
  void initState() {
    super.initState();
    final bloc = context.read<HistoryBloc>();
    if (bloc.state is HistoryInitial) {
      bloc.add(HistoryMonthRequested(month: DateTime.now()));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Attendance History'),
        centerTitle: false,
        actions: [
          IconButton(
            key: const Key('refresh_history_button'),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh History',
            onPressed: () {
              context.read<HistoryBloc>().add(const HistoryRefreshed());
            },
          ),
        ],
      ),
      body: BlocConsumer<HistoryBloc, HistoryState>(
        listener: (context, state) {
          if (state is HistoryLoaded &&
              state.selectedDayDetail != null &&
              !state.isLoadingDayDetail) {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => DailyAttendanceDetailScreen(
                  detail: state.selectedDayDetail!,
                ),
              ),
            );
          }
        },
        builder: (context, state) {
          if (state is HistoryLoading || state is HistoryInitial) {
            return const Center(
              child: LoadingIndicator(message: 'Loading attendance history...'),
            );
          }

          if (state is HistoryFailure) {
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
                      'Failed to Load History',
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
                      key: const Key('history_retry_button'),
                      onPressed: () {
                        context.read<HistoryBloc>().add(
                              HistoryMonthRequested(month: DateTime.now()),
                            );
                      },
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            );
          }

          final loaded = state as HistoryLoaded;

          return RefreshIndicator(
            onRefresh: () async {
              context.read<HistoryBloc>().add(const HistoryRefreshed());
            },
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 1. Monthly Summary Cards
                  AttendanceSummaryCards(summary: loaded.summary),

                  const SizedBox(height: AppSpacing.md),

                  // 2. Interactive Monthly Calendar Grid
                  MonthlyCalendarGrid(
                    currentMonth: loaded.currentMonth,
                    days: loaded.days,
                    selectedDate: loaded.selectedDate,
                    onMonthChanged: (newMonth) {
                      context.read<HistoryBloc>().add(
                            HistoryMonthRequested(month: newMonth),
                          );
                    },
                    onDaySelected: (date) {
                      final dayRecord = loaded.days.where((d) {
                        return d.attendanceDate.year == date.year &&
                            d.attendanceDate.month == date.month &&
                            d.attendanceDate.day == date.day;
                      }).firstOrNull;

                      context.read<HistoryBloc>().add(
                            HistoryDaySelected(
                              selectedDate: date,
                              preloadedDay: dayRecord,
                            ),
                          );
                    },
                  ),

                  const SizedBox(height: AppSpacing.lg),

                  // 3. Daily List for Selected Month
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Monthly Records',
                        style:
                            AppTypography.headingMedium.copyWith(fontSize: 16),
                      ),
                      Text(
                        '${loaded.days.length} recorded',
                        style: AppTypography.caption.copyWith(
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),

                  if (loaded.days.isEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(AppSpacing.xl),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        children: [
                          const Icon(Icons.calendar_today_outlined,
                              size: 40, color: AppColors.textSecondary),
                          const SizedBox(height: AppSpacing.sm),
                          Text(
                            'No Attendance Records',
                            style: AppTypography.headingMedium
                                .copyWith(fontSize: 15),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'No attendance activity recorded for this calendar month.',
                            style: AppTypography.caption.copyWith(
                              color: AppColors.textSecondary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    )
                  else
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: loaded.days.length,
                      itemBuilder: (context, index) {
                        // Display in descending order (latest first)
                        final day = loaded.days[loaded.days.length - 1 - index];
                        return DailyAttendanceTile(
                          day: day,
                          onTap: () {
                            context.read<HistoryBloc>().add(
                                  HistoryDaySelected(
                                    selectedDate: day.attendanceDate,
                                    preloadedDay: day,
                                  ),
                                );
                          },
                        );
                      },
                    ),

                  const SizedBox(height: AppSpacing.xl),
                ],
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: _buildBottomNav(context),
    );
  }

  Widget _buildBottomNav(BuildContext context) {
    return NavigationBar(
      selectedIndex: 2,
      onDestinationSelected: (index) {
        if (index == 0) {
          context.go('/home');
        } else if (index == 1) {
          context.go('/schedule');
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
