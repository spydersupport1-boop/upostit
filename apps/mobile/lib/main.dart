import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'app.dart';
import 'core/network/api_client.dart';
import 'core/storage/secure_storage_service.dart';
import 'core/storage/token_manager.dart';
import 'features/attendance/data/datasources/attendance_remote_data_source.dart';
import 'features/attendance/data/repositories/attendance_repository_impl.dart';
import 'features/attendance/presentation/bloc/attendance_bloc.dart';
import 'features/auth/data/datasources/auth_remote_data_source.dart';
import 'features/auth/data/repositories/auth_repository_impl.dart';
import 'features/auth/domain/usecases/login_usecase.dart';
import 'features/auth/domain/usecases/logout_usecase.dart';
import 'features/auth/domain/usecases/restore_session_usecase.dart';
import 'features/auth/presentation/bloc/auth_bloc.dart';
import 'features/auth/presentation/bloc/auth_event.dart';
import 'features/auth/presentation/bloc/auth_state.dart';
import 'features/devices/data/datasources/device_remote_data_source.dart';
import 'features/devices/data/repositories/device_repository_impl.dart';
import 'features/devices/data/services/device_identity_service.dart';
import 'features/devices/domain/repositories/device_repository.dart';
import 'features/devices/presentation/bloc/device_bloc.dart';
import 'features/history/data/datasources/history_remote_data_source.dart';
import 'features/history/data/repositories/history_repository_impl.dart';
import 'features/history/domain/repositories/history_repository.dart';
import 'features/history/presentation/bloc/history_bloc.dart';
import 'features/history/presentation/bloc/schedule_bloc.dart';
import 'features/leave/data/datasources/leave_remote_data_source.dart';
import 'features/leave/data/repositories/leave_repository_impl.dart';
import 'features/leave/domain/repositories/leave_repository.dart';
import 'features/leave/presentation/bloc/leave_bloc.dart';
import 'features/notifications/data/datasources/notification_remote_data_source.dart';
import 'features/notifications/data/repositories/notification_repository_impl.dart';
import 'features/notifications/data/services/firebase_push_notification_service.dart';
import 'features/notifications/domain/repositories/notification_repository.dart';
import 'features/notifications/presentation/bloc/notification_bloc.dart';
import 'features/notifications/presentation/bloc/notification_event.dart';
import 'features/profile/data/datasources/profile_remote_data_source.dart';
import 'features/profile/data/repositories/profile_repository_impl.dart';
import 'features/profile/domain/usecases/get_profile_usecase.dart';
import 'features/profile/presentation/bloc/profile_bloc.dart';
import 'features/sync/data/datasources/database_key_provider.dart';
import 'features/sync/data/datasources/downward_sync_dao.dart';
import 'features/sync/data/datasources/downward_sync_remote_data_source.dart';
import 'features/sync/data/datasources/local_queue_database.dart';
import 'features/sync/data/datasources/network_connectivity_service_impl.dart';
import 'features/sync/data/datasources/sqflite_local_queue_dao.dart';
import 'features/sync/data/services/background_sync_scheduler.dart';
import 'features/sync/data/services/downward_sync_coordinator.dart';
import 'features/sync/data/services/sync_worker_impl.dart';
import 'features/sync/data/services/unified_sync_coordinator.dart';
import 'features/sync/domain/repositories/local_queue_dao.dart';
import 'features/sync/domain/repositories/network_connectivity_service.dart';
import 'features/sync/domain/repositories/sync_worker.dart';
import 'features/sync/presentation/bloc/sync_bloc.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // 1. Foundational Storage & Token Infrastructure
  final tokenManager = InMemoryTokenManager();
  final secureStorage = FlutterSecureStorageService();

  late final AuthBloc authBloc;

  // 2. HTTP Network Client with Session Expiration Hook
  final apiClient = ApiClient(
    tokenManager: tokenManager,
    secureStorage: secureStorage,
    onSessionExpired: () {
      authBloc.add(const SessionExpiredDetected());
    },
  );

  // 3. Auth Feature Dependencies
  final authRemoteDataSource = AuthRemoteDataSourceImpl(apiClient);
  final authRepository = AuthRepositoryImpl(
    remoteDataSource: authRemoteDataSource,
    tokenManager: tokenManager,
    secureStorage: secureStorage,
  );
  final loginUseCase = LoginUseCase(authRepository);
  final restoreSessionUseCase = RestoreSessionUseCase(
    authRepository: authRepository,
    secureStorage: secureStorage,
    tokenManager: tokenManager,
  );
  final logoutUseCase = LogoutUseCase(
    authRepository: authRepository,
    secureStorage: secureStorage,
    tokenManager: tokenManager,
  );

  authBloc = AuthBloc(
    loginUseCase: loginUseCase,
    restoreSessionUseCase: restoreSessionUseCase,
    logoutUseCase: logoutUseCase,
    authRepository: authRepository,
    secureStorage: secureStorage,
  );

  // 4. Profile Feature Dependencies
  final profileRemoteDataSource = ProfileRemoteDataSourceImpl(apiClient);
  final profileRepository = ProfileRepositoryImpl(profileRemoteDataSource);
  final getProfileUseCase = GetProfileUseCase(profileRepository);

  final profileBloc = ProfileBloc(
    getProfileUseCase: getProfileUseCase,
  );

  // 5. Offline Queue & Sync Dependencies
  final keyProvider = FlutterSecureStorageDatabaseKeyProvider();
  final queueDatabase = LocalQueueDatabase(keyProvider: keyProvider);
  final localQueueDao = SqfliteLocalQueueDao(database: queueDatabase);
  final downwardSyncDao = SqfliteDownwardSyncDao(queueDatabase);
  final connectivityService = NetworkConnectivityServiceImpl();
  final attendanceRemoteDataSource = AttendanceRemoteDataSourceImpl(apiClient);
  final downwardRemoteDataSource = DownwardSyncRemoteDataSourceImpl(apiClient);
  final downwardCoordinator = DownwardSyncCoordinator(
    remoteDataSource: downwardRemoteDataSource,
    dao: downwardSyncDao,
    connectivityService: connectivityService,
  );
  final syncWorker = SyncWorkerImpl(
    localQueueDao: localQueueDao,
    remoteDataSource: attendanceRemoteDataSource,
    connectivityService: connectivityService,
  );
  final unifiedSyncCoordinator = UnifiedSyncCoordinator(
    syncWorker: syncWorker,
    downwardCoordinator: downwardCoordinator,
    localQueueDao: localQueueDao,
    downwardDao: downwardSyncDao,
    connectivityService: connectivityService,
  );
  final backgroundScheduler = DefaultBackgroundSyncScheduler(
    unifiedCoordinator: unifiedSyncCoordinator,
    connectivityService: connectivityService,
  );
  backgroundScheduler.initialize();
  final syncBloc = SyncBloc(
    localQueueDao: localQueueDao,
    syncWorker: syncWorker,
    connectivityService: connectivityService,
    remoteDataSource: attendanceRemoteDataSource,
    unifiedCoordinator: unifiedSyncCoordinator,
  );

  // 6. Device Identity & Binding Dependencies
  final deviceIdentityService = FlutterDeviceIdentityService();
  final deviceRemoteDataSource = DeviceRemoteDataSourceImpl(apiClient);
  final deviceRepository = DeviceRepositoryImpl(
    remoteDataSource: deviceRemoteDataSource,
    deviceIdentityService: deviceIdentityService,
  );
  final deviceBloc = DeviceBloc(repository: deviceRepository);

  // 7. Attendance Feature Dependencies
  final attendanceRepository =
      AttendanceRepositoryImpl(attendanceRemoteDataSource);
  final attendanceBloc = AttendanceBloc(
    repository: attendanceRepository,
    localQueueDao: localQueueDao,
    connectivityService: connectivityService,
    deviceIdentityService: deviceIdentityService,
  );

  // 8. History & Schedule Feature Dependencies
  final historyRemoteDataSource = HistoryRemoteDataSourceImpl(apiClient);
  final historyRepository = HistoryRepositoryImpl(
    remoteDataSource: historyRemoteDataSource,
    queueDao: localQueueDao,
    getTenantId: () {
      final state = authBloc.state;
      return state is Authenticated ? state.tenant.id : null;
    },
    getUserId: () {
      final state = authBloc.state;
      return state is Authenticated ? state.user.id : null;
    },
  );
  final historyBloc = HistoryBloc(historyRepository: historyRepository);
  final scheduleBloc = ScheduleBloc(historyRepository: historyRepository);

  // 9. Leave & Holiday Feature Dependencies
  final leaveRemoteDataSource = LeaveRemoteDataSourceImpl(apiClient);
  final leaveRepository = LeaveRepositoryImpl(leaveRemoteDataSource);
  final leaveBloc = LeaveBloc(repository: leaveRepository);

  // 10. Notification Feature Dependencies
  final pushService = FirebasePushNotificationService();
  final notificationRemoteDataSource =
      NotificationRemoteDataSourceImpl(apiClient);
  final notificationRepository = NotificationRepositoryImpl(
    remoteDataSource: notificationRemoteDataSource,
    secureStorage: secureStorage,
  );
  final notificationBloc = NotificationBloc(
    repository: notificationRepository,
    pushService: pushService,
    deviceIdentityService: deviceIdentityService,
    isUserAuthenticated: () => authBloc.state is Authenticated,
  );

  // Auto-register push tokens and schedule background sync when authenticated, or revoke on logout
  authBloc.stream.listen((authState) {
    if (authState is Authenticated) {
      notificationBloc.add(const InitializePushNotifications());
      backgroundScheduler.schedulePeriodicSync(
        tenantId: authState.tenant.id,
        userId: authState.user.id,
      );
    } else if (authState is Unauthenticated) {
      notificationBloc.add(const RevokeDeviceTokenRequested());
      notificationBloc.add(const ClearNotificationSession());
      backgroundScheduler.cancelPeriodicSync();
    }
  });

  // If already authenticated on cold boot (e.g. session restored)
  if (authBloc.state is Authenticated) {
    final authState = authBloc.state as Authenticated;
    notificationBloc.add(const InitializePushNotifications());
    backgroundScheduler.schedulePeriodicSync(
      tenantId: authState.tenant.id,
      userId: authState.user.id,
    );
  }

  // 11. Run Application Shell with Root Providers
  runApp(
    MultiRepositoryProvider(
      providers: [
        RepositoryProvider<LocalQueueDao>.value(value: localQueueDao),
        RepositoryProvider<DownwardSyncDao>.value(value: downwardSyncDao),
        RepositoryProvider<SyncWorker>.value(value: syncWorker),
        RepositoryProvider<DownwardSyncCoordinator>.value(
            value: downwardCoordinator),
        RepositoryProvider<UnifiedSyncCoordinator>.value(
            value: unifiedSyncCoordinator),
        RepositoryProvider<BackgroundSyncScheduler>.value(
            value: backgroundScheduler),
        RepositoryProvider<NetworkConnectivityService>.value(
            value: connectivityService),
        RepositoryProvider<HistoryRepository>.value(value: historyRepository),
        RepositoryProvider<LeaveRepository>.value(value: leaveRepository),
        RepositoryProvider<DeviceIdentityService>.value(
            value: deviceIdentityService),
        RepositoryProvider<DeviceRepository>.value(value: deviceRepository),
        RepositoryProvider<NotificationRepository>.value(
            value: notificationRepository),
      ],
      child: MultiBlocProvider(
        providers: [
          BlocProvider<AuthBloc>.value(value: authBloc),
          BlocProvider<ProfileBloc>.value(value: profileBloc),
          BlocProvider<AttendanceBloc>.value(value: attendanceBloc),
          BlocProvider<SyncBloc>.value(value: syncBloc),
          BlocProvider<HistoryBloc>.value(value: historyBloc),
          BlocProvider<ScheduleBloc>.value(value: scheduleBloc),
          BlocProvider<LeaveBloc>.value(value: leaveBloc),
          BlocProvider<DeviceBloc>.value(value: deviceBloc),
          BlocProvider<NotificationBloc>.value(value: notificationBloc),
        ],
        child: const AttendanceApp(),
      ),
    ),
  );
}
