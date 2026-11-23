import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/app_button.dart';
import '../../../../shared/widgets/error_banner.dart';
import '../../../../shared/widgets/loading_indicator.dart';
import '../../../auth/domain/entities/user_profile.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../auth/presentation/bloc/auth_event.dart';
import '../../../auth/presentation/bloc/auth_state.dart';
import '../../../devices/presentation/widgets/device_status_card.dart';
import '../../../notifications/presentation/bloc/notification_bloc.dart';
import '../../../notifications/presentation/bloc/notification_event.dart';
import '../../../sync/domain/repositories/local_queue_dao.dart';
import '../../../sync/presentation/widgets/logout_warning_dialog.dart';
import '../bloc/profile_bloc.dart';
import '../bloc/profile_event.dart';
import '../bloc/profile_state.dart';

/// Authenticated user and employee profile screen.
class ProfileScreen extends StatefulWidget {
  final LocalQueueDao? localQueueDao;

  const ProfileScreen({super.key, this.localQueueDao});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  @override
  void initState() {
    super.initState();
    context.read<ProfileBloc>().add(const FetchProfileRequested());
  }

  Future<void> _onLogoutPressed(
      BuildContext context, Authenticated authState) async {
    LocalQueueDao? dao = widget.localQueueDao;
    if (dao == null) {
      try {
        dao = RepositoryProvider.of<LocalQueueDao>(context);
      } catch (_) {
        dao = null;
      }
    }

    int unresolvedCount = 0;
    if (dao != null) {
      try {
        unresolvedCount = await dao.getUnresolvedCount(
          tenantId: authState.userProfile.tenant.id,
          userId: authState.userProfile.user.id,
        );
      } catch (_) {
        unresolvedCount = 0;
      }
    }

    if (!context.mounted) return;

    if (unresolvedCount > 0) {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (dialogCtx) => LogoutWarningDialog(
          unresolvedCount: unresolvedCount,
          onConfirmLogout: () {
            try {
              context
                  .read<NotificationBloc>()
                  .add(const RevokeDeviceTokenRequested());
              context
                  .read<NotificationBloc>()
                  .add(const ClearNotificationSession());
            } catch (_) {}
            context.read<AuthBloc>().add(const LogoutRequested());
          },
        ),
      );
    } else {
      showDialog(
        context: context,
        builder: (dialogCtx) => AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: AppRadius.lgBorderRadius),
          title: Text('Sign Out', style: AppTypography.headingMedium),
          content: Text(
            'Are you sure you want to sign out of your workspace session?',
            style: AppTypography.bodyMedium,
          ),
          actionsPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogCtx),
              child: Text('Cancel',
                  style: AppTypography.buttonText
                      .copyWith(color: AppColors.textSecondary)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.error,
                foregroundColor: Colors.white,
                elevation: 0,
                shape: RoundedRectangleBorder(
                    borderRadius: AppRadius.smBorderRadius),
              ),
              onPressed: () {
                Navigator.pop(dialogCtx);
                try {
                  context
                      .read<NotificationBloc>()
                      .add(const RevokeDeviceTokenRequested());
                  context
                      .read<NotificationBloc>()
                      .add(const ClearNotificationSession());
                } catch (_) {}
                context.read<AuthBloc>().add(const LogoutRequested());
              },
              child: const Text('Sign Out'),
            ),
          ],
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return BlocListener<AuthBloc, AuthState>(
      listener: (context, state) {
        if (state is Unauthenticated) {
          context.go('/login');
        }
      },
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          title: const Text('Profile & Identity'),
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh_rounded),
              tooltip: 'Refresh Profile',
              onPressed: () {
                context.read<ProfileBloc>().add(const ProfileRefreshed());
              },
            ),
          ],
        ),
        body: BlocBuilder<AuthBloc, AuthState>(
          builder: (context, authState) {
            if (authState is! Authenticated) {
              return const LoadingIndicator(
                  message: 'Loading authentication session...');
            }

            final userProfile = authState.userProfile;

            return BlocBuilder<ProfileBloc, ProfileState>(
              builder: (context, profileState) {
                if (profileState is ProfileLoading) {
                  return const LoadingIndicator(
                      message: 'Loading employee profile...');
                }

                return SingleChildScrollView(
                  padding: AppSpacing.pagePadding,
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (profileState is ProfileError) ...[
                            ErrorBanner(
                                message: profileState.message, isWarning: true),
                            const SizedBox(height: 16),
                          ],
                          _buildTenantCard(userProfile.tenant),
                          const SizedBox(height: 16),
                          _buildUserCard(userProfile, profileState),
                          const SizedBox(height: 16),
                          const DeviceStatusCard(),
                          const SizedBox(height: 16),
                          _buildNotificationCenterTile(context),
                          const SizedBox(height: 16),
                          _buildSyncQueueTile(context),
                          const SizedBox(height: 32),
                          AppButton(
                            text: 'Sign Out of Account',
                            icon: Icons.logout_rounded,
                            variant: ButtonVariant.destructive,
                            onPressed: () =>
                                _onLogoutPressed(context, authState),
                          ),
                          const SizedBox(height: 24),
                          _buildVersionFooter(),
                        ],
                      ),
                    ),
                  ),
                );
              },
            );
          },
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: 3,
          onDestinationSelected: (index) {
            if (index == 0) {
              context.go('/home');
            } else if (index == 1) {
              context.go('/schedule');
            } else if (index == 2) {
              context.go('/history');
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
        ),
      ),
    );
  }

  Widget _buildTenantCard(TenantEntity tenant) {
    return Card(
      child: Padding(
        padding: AppSpacing.cardPadding,
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: AppRadius.mdBorderRadius,
              ),
              child: const Icon(Icons.business_rounded,
                  color: AppColors.primary, size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(tenant.name, style: AppTypography.headingMedium),
                  const SizedBox(height: 2),
                  Text(
                    'Workspace: ${tenant.slug} • ${tenant.timezone}',
                    style: AppTypography.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUserCard(UserProfile userProfile, ProfileState profileState) {
    final employee =
        profileState is ProfileLoaded ? profileState.employee : null;
    final displayName = employee?.fullName.isNotEmpty == true
        ? employee!.fullName
        : userProfile.user.fullName;
    final displayEmail = employee?.workEmail.isNotEmpty == true
        ? employee!.workEmail
        : userProfile.user.email;
    final role = userProfile.user.role;
    final initials = displayName.isNotEmpty
        ? displayName
            .split(' ')
            .map((s) => s.isNotEmpty ? s[0] : '')
            .take(2)
            .join('')
            .toUpperCase()
        : 'U';

    return Card(
      child: Padding(
        padding: AppSpacing.cardPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: AppColors.primary,
                  child: Text(
                    initials,
                    style: AppTypography.headingMedium
                        .copyWith(color: Colors.white),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(displayName, style: AppTypography.headingMedium),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          _buildBadge(role.toUpperCase(),
                              AppColors.primaryLight, AppColors.primary),
                          const SizedBox(width: 8),
                          _buildBadge('ACTIVE', AppColors.successLight,
                              AppColors.success),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const Divider(),
            _buildDataRow(Icons.email_outlined, 'Work Email', displayEmail),
            const SizedBox(height: 12),
            _buildDataRow(
              Icons.badge_outlined,
              'Employee ID',
              employee?.employeeId ?? 'Administrative User',
            ),
            if (employee?.departmentName != null) ...[
              const SizedBox(height: 12),
              _buildDataRow(Icons.domain_rounded, 'Department',
                  employee!.departmentName!),
            ],
            if (employee?.designationTitle != null) ...[
              const SizedBox(height: 12),
              _buildDataRow(Icons.work_outline_rounded, 'Designation',
                  employee!.designationTitle!),
            ],
            if (employee?.employmentType != null) ...[
              const SizedBox(height: 12),
              _buildDataRow(Icons.schedule_rounded, 'Type',
                  employee!.employmentType.replaceAll('_', ' ').toUpperCase()),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBadge(String text, Color bgColor, Color textColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        text,
        style:
            AppTypography.labelMedium.copyWith(color: textColor, fontSize: 11),
      ),
    );
  }

  Widget _buildDataRow(IconData icon, String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: AppColors.textSecondary),
        const SizedBox(width: 10),
        SizedBox(
          width: 110,
          child: Text(
            label,
            style: AppTypography.bodyMedium
                .copyWith(color: AppColors.textSecondary),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: AppTypography.bodyMedium.copyWith(
                fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          ),
        ),
      ],
    );
  }

  Widget _buildNotificationCenterTile(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.border),
      ),
      child: ListTile(
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: AppColors.primaryLight,
            borderRadius: AppRadius.smBorderRadius,
          ),
          child: const Icon(Icons.notifications_outlined,
              color: AppColors.primary),
        ),
        title: Text(
          'Notification Center',
          style: AppTypography.bodyMedium.copyWith(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          'View push alerts and workforce communications',
          style: AppTypography.bodySmall,
        ),
        trailing: const Icon(Icons.chevron_right_rounded,
            color: AppColors.textSecondary),
        onTap: () => context.push('/notifications'),
      ),
    );
  }

  Widget _buildSyncQueueTile(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.border),
      ),
      child: ListTile(
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: AppColors.primaryLight,
            borderRadius: AppRadius.smBorderRadius,
          ),
          child:
              const Icon(Icons.cloud_sync_outlined, color: AppColors.primary),
        ),
        title: Text(
          'Offline Attendance Queue',
          style: AppTypography.bodyMedium.copyWith(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          'View queued punches, sync status and timeline',
          style: AppTypography.bodySmall,
        ),
        trailing: const Icon(Icons.chevron_right_rounded,
            color: AppColors.textSecondary),
        onTap: () => context.push('/sync'),
      ),
    );
  }

  Widget _buildVersionFooter() {
    return Center(
      child: Text(
        'UPOSTIT v0.1.0 • Stage B Core Mobile',
        style: AppTypography.bodySmall,
      ),
    );
  }
}
