import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/error_banner.dart';
import '../../../../shared/widgets/loading_indicator.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../auth/presentation/bloc/auth_state.dart';
import '../../../profile/presentation/bloc/profile_bloc.dart';
import '../../../profile/presentation/bloc/profile_state.dart';
import '../../../sync/presentation/widgets/offline_status_banner.dart';
import '../bloc/attendance_bloc.dart';
import '../bloc/attendance_event.dart';
import '../bloc/attendance_state.dart';
import '../../domain/entities/attendance_event.dart';
import '../widgets/attendance_status_badge.dart';
import '../widgets/geofence_status_card.dart';
import '../widgets/hero_punch_card.dart';
import '../widgets/last_punch_badge.dart';
import '../widgets/shift_workplace_card.dart';
import '../widgets/today_punches_list.dart';
import '../widgets/wifi_status_card.dart';
import '../widgets/working_timer_card.dart';

/// Production-quality primary employee attendance home screen.
class AttendanceHomeScreen extends StatefulWidget {
  const AttendanceHomeScreen({super.key});

  @override
  State<AttendanceHomeScreen> createState() => _AttendanceHomeScreenState();
}

class _AttendanceHomeScreenState extends State<AttendanceHomeScreen>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Dispatch dashboard request on screen mount
    context.read<AttendanceBloc>().add(const AttendanceDashboardRequested());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // User may have returned from system settings (e.g. enabling GPS or granting permission)
      final bloc = context.read<AttendanceBloc>();
      if (bloc.state is AttendanceLoaded) {
        final loaded = bloc.state as AttendanceLoaded;
        if (loaded.isLocationPermissionDenied ||
            loaded.isLocationServiceDisabled) {
          bloc.add(const AttendanceDashboardRequested());
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: _buildAppBar(context),
      body: BlocConsumer<AttendanceBloc, AttendanceState>(
        listener: (context, state) {
          if (state is AttendanceLoaded && state.successNotice != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(
                  children: [
                    const Icon(Icons.check_circle_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(state.successNotice!)),
                  ],
                ),
                backgroundColor: AppColors.success,
                behavior: SnackBarBehavior.floating,
                duration: const Duration(seconds: 3),
              ),
            );
          }
          if (state is AttendanceLoaded && state.offlineNotice != null) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(
                  children: [
                    const Icon(Icons.cloud_off_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(child: Text(state.offlineNotice!)),
                  ],
                ),
                backgroundColor: AppColors.info,
                behavior: SnackBarBehavior.floating,
                duration: const Duration(seconds: 4),
              ),
            );
          }
        },
        builder: (context, state) {
          if (state is AttendanceLoading || state is AttendanceInitial) {
            return const Center(
              child: LoadingIndicator(message: 'Loading attendance status...'),
            );
          }

          if (state is AttendanceLoadFailure) {
            return Center(
              child: Padding(
                padding: AppSpacing.pagePadding,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: const BoxDecoration(
                        color: AppColors.errorLight,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.cloud_off_rounded,
                          color: AppColors.error, size: 30),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'Failed to Load Attendance',
                      style: AppTypography.headingMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      state.message,
                      style: AppTypography.bodyMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    ElevatedButton.icon(
                      key: const Key('attendance_load_retry_button'),
                      onPressed: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const AttendanceDashboardRequested());
                      },
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('Retry Connection'),
                    ),
                  ],
                ),
              ),
            );
          }

          final loaded = state as AttendanceLoaded;
          final dashboard = loaded.dashboard;
          final todayFormatted =
              DateFormat('EEEE, d MMMM yyyy').format(DateTime.now());

          DateTime? firstCheckIn = dashboard.todayDay?.firstCheckIn;
          if (firstCheckIn == null) {
            for (final e in dashboard.todayEvents) {
              if (e.eventType == AttendanceEventType.checkIn) {
                firstCheckIn = e.effectiveAt;
                break;
              }
            }
          }
          final remainingShift =
              (dashboard.shift != null && firstCheckIn != null)
                  ? dashboard.shift!
                      .calculateRemainingTime(DateTime.now(), firstCheckIn)
                  : null;

          return RefreshIndicator(
            onRefresh: () async {
              context
                  .read<AttendanceBloc>()
                  .add(const AttendanceDashboardRequested());
            },
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 0. Offline Status Banner
                  const OfflineStatusBanner(),
                  const SizedBox(height: AppSpacing.sm),

                  // 1. Employee greeting & current date
                  _buildEmployeeGreeting(todayFormatted, loaded),

                  const SizedBox(height: AppSpacing.md),

                  // 2. Feedback Banners (Error / Retriable / Pending Review)
                  if (loaded.errorMessage != null) ...[
                    ErrorBanner(
                      message: loaded.errorMessage!,
                      onDismiss: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const DismissFeedbackNotice());
                      },
                    ),
                    if (loaded.isRetriable) ...[
                      const SizedBox(height: AppSpacing.xs),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton.icon(
                          key: const Key('punch_retry_button'),
                          onPressed: loaded.isSubmittingPunch
                              ? null
                              : () {
                                  context
                                      .read<AttendanceBloc>()
                                      .add(const PunchRetryRequested());
                                },
                          icon: const Icon(Icons.replay_rounded, size: 16),
                          label: const Text('Retry Punch Submission'),
                        ),
                      ),
                    ],
                    const SizedBox(height: AppSpacing.sm),
                  ],

                  if (loaded.pendingReviewNotice != null) ...[
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        color: AppColors.warningLight,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(
                            color: AppColors.warning.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.flag_rounded,
                              color: AppColors.warning, size: 20),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              loaded.pendingReviewNotice!,
                              style: AppTypography.bodySmall.copyWith(
                                color: AppColors.warning,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],

                  // 2.5 Unsupported Policy Warning Banner
                  if (dashboard.policy != null &&
                      !dashboard.policy!.isSupportedInThisRelease) ...[
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: AppSpacing.md),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        color: AppColors.errorLight,
                        borderRadius: AppRadius.mdBorderRadius,
                        border: Border.all(
                            color: AppColors.error.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.block_rounded,
                              color: AppColors.error, size: 22),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              dashboard.policy!.unsupportedMessage ??
                                  'This company attendance verification method is not supported on this device.',
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

                  // 3. Shift and Workplace Card
                  ShiftWorkplaceCard(
                    shift: dashboard.shift,
                    workplace: dashboard.workplace,
                  ),

                  // 3.5 GPS Geofence Status Card (Rendered only when policy requires GPS)
                  if (dashboard.policy?.requiresGps == true) ...[
                    const SizedBox(height: AppSpacing.sm),
                    GeofenceStatusCard(
                      policy: dashboard.policy,
                      workplace: dashboard.workplace,
                      lastReading: loaded.lastLocationReading,
                      advisoryDistanceMeters: loaded.advisoryDistanceMeters,
                      isInsideGeofence: loaded.isInsideGeofence,
                      isPermissionDenied: loaded.isLocationPermissionDenied,
                      isServiceDisabled: loaded.isLocationServiceDisabled,
                      inFlightStatusMessage: loaded.locationStatusMessage,
                      onResolvePermission: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const LocationPermissionResolutionRequested());
                      },
                      onProbeLocation: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const LocationProbeRequested());
                      },
                    ),
                  ],

                  // 3.6 Workplace Wi-Fi Status Card (Rendered when policy requires Wi-Fi)
                  if (dashboard.policy?.requiresWifi == true) ...[
                    const SizedBox(height: AppSpacing.sm),
                    WifiStatusCard(
                      policy: dashboard.policy,
                      workplace: dashboard.workplace,
                      lastEvidence: loaded.lastWifiEvidence,
                      lastVerificationResult: loaded.lastWifiVerificationResult,
                      isProbing: loaded.isWifiProbing,
                      isPermissionDenied: loaded.isWifiPermissionDenied,
                      inFlightStatusMessage: loaded.wifiStatusMessage,
                      onProbeWifi: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const WifiProbeRequested());
                      },
                      onResolvePermission: () {
                        context
                            .read<AttendanceBloc>()
                            .add(const LocationPermissionResolutionRequested());
                      },
                    ),
                  ],

                  // 3.8 Quick Navigation Action Row
                  Row(
                    children: [
                      Expanded(
                        child: _buildQuickNavCard(
                          icon: Icons.calendar_month_outlined,
                          label: 'Schedule',
                          onTap: () => context.go('/schedule'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(
                        child: _buildQuickNavCard(
                          icon: Icons.history_rounded,
                          label: 'History',
                          onTap: () => context.go('/history'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(
                        child: _buildQuickNavCard(
                          icon: Icons.beach_access_outlined,
                          label: 'Leave',
                          onTap: () => context.push('/leave'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(
                        child: _buildQuickNavCard(
                          icon: Icons.cloud_sync_outlined,
                          label: 'Sync Queue',
                          onTap: () => context.push('/sync'),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: AppSpacing.md),

                  // 4. Live Elapsed Working Timer Card
                  WorkingTimerCard(
                    workingDuration: loaded.workingDuration,
                    breakDuration: loaded.breakDuration,
                    status: loaded.status,
                    remainingDuration: remainingShift,
                  ),

                  const SizedBox(height: AppSpacing.lg),

                  // 5. Hero Punch Card (Primary Action)
                  HeroPunchCard(
                    status: loaded.status,
                    isSubmitting: loaded.isSubmittingPunch,
                    isUnsupported: dashboard.policy != null &&
                        !dashboard.policy!.isSupportedInThisRelease,
                    inFlightEventType: loaded.inFlightEventType,
                    onPunchPressed: (eventType) {
                      context.read<AttendanceBloc>().add(
                            PunchActionSubmitted(eventType: eventType),
                          );
                    },
                  ),

                  const SizedBox(height: AppSpacing.md),

                  // 6. Last Punch Badge
                  LastPunchBadge(lastEvent: dashboard.lastEvent),

                  const SizedBox(height: AppSpacing.md),

                  // 7. Today's Punch Timeline
                  TodayPunchesList(events: dashboard.todayEvents),

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

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      title: const Text('Attendance'),
      centerTitle: false,
      actions: [
        IconButton(
          key: const Key('sync_status_app_bar_button'),
          icon: const Icon(Icons.cloud_sync_outlined),
          tooltip: 'Sync Status & Queue',
          onPressed: () => context.push('/sync'),
        ),
        IconButton(
          key: const Key('refresh_attendance_button'),
          icon: const Icon(Icons.refresh_rounded),
          tooltip: 'Refresh Status',
          onPressed: () {
            context
                .read<AttendanceBloc>()
                .add(const AttendanceDashboardRequested());
          },
        ),
      ],
    );
  }

  Widget _buildEmployeeGreeting(
      String todayFormatted, AttendanceLoaded loaded) {
    return BlocBuilder<ProfileBloc, ProfileState>(
      builder: (context, profileState) {
        String name = 'Team Member';
        String designation = 'Employee';

        if (profileState is ProfileLoaded && profileState.employee != null) {
          name = profileState.employee!.fullName;
          designation = profileState.employee!.designationTitle ?? 'Staff';
        } else {
          final authState = context.read<AuthBloc>().state;
          if (authState is Authenticated) {
            name = authState.userProfile.user.fullName;
            designation = authState.userProfile.user.role.toUpperCase();
          }
        }

        return Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            CircleAvatar(
              radius: 24,
              backgroundColor: AppColors.primaryLight,
              child: Text(
                name.isNotEmpty ? name[0].toUpperCase() : 'U',
                style: const TextStyle(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w700,
                  fontSize: 18,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm + 4),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: AppTypography.headingMedium.copyWith(fontSize: 17),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    '$designation • $todayFormatted',
                    style: AppTypography.bodySmall.copyWith(fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            AttendanceStatusBadge(status: loaded.status),
          ],
        );
      },
    );
  }

  Widget _buildQuickNavCard({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.mdBorderRadius,
      child: Container(
        padding: const EdgeInsets.symmetric(
          vertical: AppSpacing.sm,
          horizontal: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: AppRadius.mdBorderRadius,
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          children: [
            Icon(icon, size: 20, color: AppColors.primary),
            const SizedBox(height: 4),
            Text(
              label,
              style: AppTypography.caption.copyWith(
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomNav(BuildContext context) {
    return NavigationBar(
      selectedIndex: 0,
      onDestinationSelected: (index) {
        if (index == 1) {
          context.go('/schedule');
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
