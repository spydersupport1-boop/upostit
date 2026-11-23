import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'core/theme/app_theme.dart';
import 'features/attendance/presentation/screens/attendance_home_screen.dart';
import 'features/auth/presentation/screens/login_screen.dart';
import 'features/auth/presentation/screens/splash_screen.dart';
import 'features/history/domain/entities/daily_attendance_detail.dart';
import 'features/history/presentation/screens/daily_attendance_detail_screen.dart';
import 'features/history/presentation/screens/history_screen.dart';
import 'features/history/presentation/screens/schedule_screen.dart';
import 'features/leave/presentation/screens/apply_leave_screen.dart';
import 'features/leave/presentation/screens/holiday_hub_screen.dart';
import 'features/leave/presentation/screens/leave_approvals_screen.dart';
import 'features/leave/presentation/screens/leave_dashboard_screen.dart';
import 'features/leave/presentation/screens/leave_history_screen.dart';
import 'features/notifications/presentation/screens/notification_inbox_screen.dart';
import 'features/profile/presentation/screens/profile_screen.dart';
import 'features/sync/presentation/screens/sync_status_screen.dart';

/// Central declarative router configuration using [GoRouter].
final GoRouter appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      name: 'splash',
      builder: (context, state) => const SplashScreen(),
    ),
    GoRoute(
      path: '/login',
      name: 'login',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/home',
      name: 'home',
      builder: (context, state) => const AttendanceHomeScreen(),
    ),
    GoRoute(
      path: '/schedule',
      name: 'schedule',
      builder: (context, state) => const ScheduleScreen(),
    ),
    GoRoute(
      path: '/history',
      name: 'history',
      builder: (context, state) => const HistoryScreen(),
    ),
    GoRoute(
      path: '/history/day',
      name: 'history_day',
      builder: (context, state) {
        final detail = state.extra as DailyAttendanceDetail?;
        if (detail == null) {
          return const HistoryScreen();
        }
        return DailyAttendanceDetailScreen(detail: detail);
      },
    ),
    GoRoute(
      path: '/profile',
      name: 'profile',
      builder: (context, state) => const ProfileScreen(),
    ),
    GoRoute(
      path: '/sync',
      name: 'sync',
      builder: (context, state) => const SyncStatusScreen(),
    ),
    GoRoute(
      path: '/leave',
      name: 'leave',
      builder: (context, state) => const LeaveDashboardScreen(),
    ),
    GoRoute(
      path: '/leave/apply',
      name: 'leave_apply',
      builder: (context, state) => const ApplyLeaveScreen(),
    ),
    GoRoute(
      path: '/leave/history',
      name: 'leave_history',
      builder: (context, state) => const LeaveHistoryScreen(),
    ),
    GoRoute(
      path: '/leave/holidays',
      name: 'leave_holidays',
      builder: (context, state) => const HolidayHubScreen(),
    ),
    GoRoute(
      path: '/leave/approvals',
      name: 'leave_approvals',
      builder: (context, state) => const LeaveApprovalsScreen(),
    ),
    GoRoute(
      path: '/notifications',
      name: 'notifications',
      builder: (context, state) => const NotificationInboxScreen(),
    ),
  ],
);

/// Root MaterialApp configured with Material 3 theme and declarative routing.
class AttendanceApp extends StatelessWidget {
  final GoRouter? customRouter;

  const AttendanceApp({super.key, this.customRouter});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'UPOSTIT Workforce',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      routerConfig: customRouter ?? appRouter,
    );
  }
}
