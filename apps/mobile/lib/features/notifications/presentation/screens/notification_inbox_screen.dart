import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../../../shared/widgets/empty_state_view.dart';
import '../../../../shared/widgets/error_banner.dart';
import '../../../../shared/widgets/loading_indicator.dart';
import '../bloc/notification_bloc.dart';
import '../bloc/notification_event.dart';
import '../bloc/notification_state.dart';
import '../widgets/notification_api_gap_banner.dart';
import '../widgets/notification_detail_dialog.dart';
import '../widgets/notification_tile.dart';

/// Primary in-app notification center screen.
class NotificationInboxScreen extends StatefulWidget {
  const NotificationInboxScreen({super.key});

  @override
  State<NotificationInboxScreen> createState() =>
      _NotificationInboxScreenState();
}

class _NotificationInboxScreenState extends State<NotificationInboxScreen> {
  bool _filterOnlyUnread = false;

  @override
  void initState() {
    super.initState();
    context
        .read<NotificationBloc>()
        .add(const FetchNotificationInboxRequested());
  }

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<NotificationBloc, NotificationState>(
      listener: (context, state) {
        if (state is NotificationLoaded) {
          if (state.navigationRoute != null) {
            final route = state.navigationRoute!;
            context.read<NotificationBloc>().add(const ClearNavigationRoute());
            context.push(route);
          }
        }
      },
      builder: (context, state) {
        final unreadCount = state is NotificationLoaded ? state.unreadCount : 0;

        return Scaffold(
          backgroundColor: AppColors.background,
          appBar: AppBar(
            title: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Notifications'),
                if (unreadCount > 0) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      unreadCount > 99 ? '99+' : unreadCount.toString(),
                      style: AppTypography.caption.copyWith(
                        color: AppColors.textInverse,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ],
            ),
            centerTitle: false,
            actions: [
              IconButton(
                key: const Key('refresh_notifications_icon_button'),
                icon: const Icon(Icons.refresh_rounded),
                tooltip: 'Refresh Notifications',
                onPressed: () {
                  context.read<NotificationBloc>().add(
                        const FetchNotificationInboxRequested(isRefresh: true),
                      );
                },
              ),
            ],
          ),
          body: _buildBody(context, state),
        );
      },
    );
  }

  Widget _buildBody(BuildContext context, NotificationState state) {
    if (state is NotificationLoading) {
      return const Center(
        child: LoadingIndicator(message: 'Loading notifications...'),
      );
    }

    if (state is NotificationError) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ErrorBanner(
                message: state.message,
                onDismiss: () {
                  context.read<NotificationBloc>().add(
                        const FetchNotificationInboxRequested(),
                      );
                },
              ),
              const SizedBox(height: AppSpacing.md),
              ElevatedButton.icon(
                onPressed: () {
                  context.read<NotificationBloc>().add(
                        const FetchNotificationInboxRequested(),
                      );
                },
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Try Again'),
              ),
            ],
          ),
        ),
      );
    }

    if (state is NotificationLoaded) {
      final allNotifications = state.notifications;
      final displayNotifications = _filterOnlyUnread
          ? allNotifications.where((n) => !n.isRead).toList()
          : allNotifications;

      return RefreshIndicator(
        onRefresh: () async {
          context.read<NotificationBloc>().add(
                const FetchNotificationInboxRequested(isRefresh: true),
              );
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
          children: [
            if (state.hasApiGap)
              NotificationApiGapBanner(message: state.apiGapMessage),
            if (state.noticeMessage != null && !state.hasApiGap)
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: 4),
                child: ErrorBanner(message: state.noticeMessage!),
              ),
            _buildFilterTabs(allNotifications.length, state.unreadCount),
            const SizedBox(height: AppSpacing.xs),
            if (displayNotifications.isEmpty)
              _buildEmptyState()
            else
              ...displayNotifications.map(
                (notif) => NotificationTile(
                  key: Key('notification_tile_${notif.id}'),
                  notification: notif,
                  onTap: () {
                    context
                        .read<NotificationBloc>()
                        .add(NotificationTappedEvent(notif));
                    NotificationDetailDialog.show(context, notif);
                  },
                ),
              ),
          ],
        ),
      );
    }

    return const SizedBox.shrink();
  }

  Widget _buildFilterTabs(int totalCount, int unreadCount) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      child: Row(
        children: [
          ChoiceChip(
            key: const Key('filter_chip_all'),
            label: Text('All ($totalCount)'),
            selected: !_filterOnlyUnread,
            onSelected: (val) {
              if (val) setState(() => _filterOnlyUnread = false);
            },
          ),
          const SizedBox(width: 8),
          ChoiceChip(
            key: const Key('filter_chip_unread'),
            label: Text('Unread ($unreadCount)'),
            selected: _filterOnlyUnread,
            onSelected: (val) {
              if (val) setState(() => _filterOnlyUnread = true);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 60, horizontal: 24),
      child: EmptyStateView(
        title: _filterOnlyUnread ? 'No Unread Alerts' : 'No Notifications',
        description: _filterOnlyUnread
            ? 'You have caught up with all your unread messages.'
            : 'You have no outbound notifications or alerts at this time.',
        icon: Icons.notifications_none_rounded,
      ),
    );
  }
}
