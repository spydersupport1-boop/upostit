import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../bloc/leave_bloc.dart';
import '../bloc/leave_event.dart';
import '../bloc/leave_state.dart';
import '../widgets/holiday_tile.dart';

class HolidayHubScreen extends StatefulWidget {
  const HolidayHubScreen({super.key});

  @override
  State<HolidayHubScreen> createState() => _HolidayHubScreenState();
}

class _HolidayHubScreenState extends State<HolidayHubScreen> {
  @override
  void initState() {
    super.initState();
    context.read<LeaveBloc>().add(const UpcomingHolidaysRequested());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Holiday Calendar'),
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
          }
        },
        builder: (context, state) {
          return RefreshIndicator(
            onRefresh: () async {
              context.read<LeaveBloc>().add(const UpcomingHolidaysRequested());
            },
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppSpacing.pagePadding,
              children: [
                // Info banner explaining three-tier calendar resolution
                Container(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  decoration: BoxDecoration(
                    color: AppColors.infoLight,
                    borderRadius: AppRadius.mdBorderRadius,
                    border: Border.all(
                      color: AppColors.info.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.info_outline, color: AppColors.info, size: 20),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Text(
                          'Holidays are automatically resolved based on your location, department, or company calendar.',
                          style: AppTypography.caption.copyWith(
                            color: AppColors.info,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.lg),

                Text(
                  'Upcoming Holidays',
                  style: AppTypography.headingMedium,
                ),
                const SizedBox(height: AppSpacing.sm),

                if (state.isLoading && state.upcomingHolidays.isEmpty)
                  const Padding(
                    padding: EdgeInsets.only(top: 80.0),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else if (state.upcomingHolidays.isEmpty)
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.xl),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: AppRadius.mdBorderRadius,
                      border: Border.all(color: AppColors.borderLight),
                    ),
                    child: const Center(
                      child: Text(
                        'No upcoming holidays scheduled for your workplace.',
                        style: TextStyle(color: AppColors.textSecondary),
                      ),
                    ),
                  )
                else
                  ...state.upcomingHolidays.map(
                    (holiday) => HolidayTile(holiday: holiday),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}
