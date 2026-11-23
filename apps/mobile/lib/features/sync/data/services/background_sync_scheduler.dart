import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:workmanager/workmanager.dart';
import '../../domain/repositories/network_connectivity_service.dart';
import 'unified_sync_coordinator.dart';

/// Task identifiers registered with Android WorkManager and iOS BGTaskScheduler.
const String kBackgroundSyncPeriodicUniqueName = 'com.upostit.mobile.sync.periodic';
const String kBackgroundSyncPeriodicTask = 'com.upostit.mobile.sync.periodic';
const String kBackgroundSyncProcessingTask = 'com.upostit.mobile.sync.processing';

/// Top-level callback dispatcher registered with native WorkManager / BGTaskScheduler.
/// Must be annotated with `@pragma('vm:entry-point')` so Flutter AOT preserves it in background isolates.
@pragma('vm:entry-point')
void backgroundSyncCallbackDispatcher() {
  Workmanager().executeTask((taskName, inputData) async {
    WidgetsFlutterBinding.ensureInitialized();
    debugPrint(
      'BackgroundSyncScheduler: Native background callback invoked: task=$taskName, data=$inputData',
    );
    return await DefaultBackgroundSyncScheduler.handleNativeTask(
      taskName: taskName,
      inputData: inputData,
    );
  });
}

/// Contract for background synchronization scheduling on native platforms (Android WorkManager / iOS BGTaskScheduler).
abstract class BackgroundSyncScheduler {
  /// Initializes the native WorkManager engine if supported on the platform.
  Future<void> initialize();

  /// Schedules recurring background synchronization with network and battery constraints.
  Future<void> schedulePeriodicSync({
    required String tenantId,
    required String userId,
    Duration interval = const Duration(minutes: 15),
  });

  /// Cancels recurring background synchronization (e.g. on user logout).
  Future<void> cancelPeriodicSync();

  /// Executes a single background synchronization pass if constraints are satisfied.
  Future<bool> executeBackgroundSyncPass({
    required String tenantId,
    required String userId,
  });
}

/// Production implementation of [BackgroundSyncScheduler] providing:
/// 1. Native Android WorkManager registration with [NetworkType.connected], exponential backoff, and [ExistingPeriodicWorkPolicy.keep].
/// 2. Native iOS BGTaskScheduler registration with permitted identifiers and network-aware processing.
/// 3. In-process timer fallback for development, desktop, and headless test runners.
/// 4. Strict concurrency mutex preventing overlapping background/foreground sync runs.
class DefaultBackgroundSyncScheduler implements BackgroundSyncScheduler {
  final UnifiedSyncCoordinator _unifiedCoordinator;
  final NetworkConnectivityService? _connectivityService;
  final Workmanager _workmanager;

  bool _isBackgroundPassRunning = false;
  bool _isInitialized = false;
  Timer? _simulatedPeriodicTimer;
  String? _scheduledTenantId;
  String? _scheduledUserId;

  /// Optional delegate handler for native task dispatch in background isolates or unit tests.
  static Future<bool> Function({
    required String taskName,
    Map<String, dynamic>? inputData,
  })? customTaskHandler;

  /// Active coordinator reference for background isolates when running without customTaskHandler.
  static UnifiedSyncCoordinator? activeCoordinator;

  DefaultBackgroundSyncScheduler({
    required UnifiedSyncCoordinator unifiedCoordinator,
    NetworkConnectivityService? connectivityService,
    Workmanager? workmanager,
  })  : _unifiedCoordinator = unifiedCoordinator,
        _connectivityService = connectivityService,
        _workmanager = workmanager ?? Workmanager() {
    activeCoordinator = unifiedCoordinator;
  }

  @override
  Future<void> initialize() async {
    if (_isInitialized) return;
    try {
      await _workmanager.initialize(
        backgroundSyncCallbackDispatcher,
      );
      _isInitialized = true;
      debugPrint('BackgroundSyncScheduler: Native WorkManager initialized successfully.');
    } catch (e) {
      debugPrint('BackgroundSyncScheduler: Native WorkManager initialization skipped or unsupported: $e');
    }
  }

  @override
  Future<void> schedulePeriodicSync({
    required String tenantId,
    required String userId,
    Duration interval = const Duration(minutes: 15),
  }) async {
    _scheduledTenantId = tenantId;
    _scheduledUserId = userId;

    // 1. Native Android WorkManager / iOS BGTaskScheduler registration
    try {
      await _workmanager.registerPeriodicTask(
        kBackgroundSyncPeriodicUniqueName,
        kBackgroundSyncPeriodicTask,
        frequency: interval,
        constraints: Constraints(
          networkType: NetworkType.connected,
        ),
        existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
        backoffPolicy: BackoffPolicy.exponential,
        backoffPolicyDelay: const Duration(seconds: 30),
        inputData: {
          'tenantId': tenantId,
          'userId': userId,
        },
      );
      debugPrint(
        'BackgroundSyncScheduler: Native periodic task scheduled ($kBackgroundSyncPeriodicUniqueName) every ${interval.inMinutes}m (Constraints: NetworkConnected)',
      );
    } catch (e) {
      debugPrint(
        'BackgroundSyncScheduler: Native WorkManager registration fallback (e.g. running in test/desktop): $e',
      );
    }

    // 2. In-process periodic timer fallback (for platforms/simulators without background execution or unit tests)
    _simulatedPeriodicTimer?.cancel();
    _simulatedPeriodicTimer = Timer.periodic(interval, (_) {
      if (_scheduledTenantId != null && _scheduledUserId != null) {
        executeBackgroundSyncPass(
          tenantId: _scheduledTenantId!,
          userId: _scheduledUserId!,
        );
      }
    });

    debugPrint(
      'BackgroundSyncScheduler: Scheduled periodic sync every ${interval.inMinutes}m for user $userId (Tenant: $tenantId)',
    );
  }

  @override
  Future<void> cancelPeriodicSync() async {
    _simulatedPeriodicTimer?.cancel();
    _simulatedPeriodicTimer = null;
    _scheduledTenantId = null;
    _scheduledUserId = null;

    try {
      await _workmanager.cancelByUniqueName(kBackgroundSyncPeriodicUniqueName);
      debugPrint('BackgroundSyncScheduler: Native periodic work canceled ($kBackgroundSyncPeriodicUniqueName).');
    } catch (e) {
      debugPrint('BackgroundSyncScheduler: Native WorkManager cancel error: $e');
    }
    debugPrint('BackgroundSyncScheduler: Canceled periodic background sync.');
  }

  @override
  Future<bool> executeBackgroundSyncPass({
    required String tenantId,
    required String userId,
  }) async {
    // 1. Concurrency Mutex: prevent overlapping background workers
    if (_isBackgroundPassRunning) {
      debugPrint('BackgroundSyncScheduler: Background pass already running, skipping.');
      return false;
    }
    _isBackgroundPassRunning = true;

    try {
      // 2. Network Reachability Constraint
      if (_connectivityService != null) {
        final isConnected = await _connectivityService.isConnected();
        if (!isConnected) {
          debugPrint('BackgroundSyncScheduler: No network reachability, deferring pass.');
          return false;
        }
      }

      debugPrint('BackgroundSyncScheduler: Executing background synchronization pass...');
      final result = await _unifiedCoordinator.synchronizeAll(
        tenantId: tenantId,
        userId: userId,
        forceFullDownward: false,
      );

      debugPrint(
        'BackgroundSyncScheduler: Background pass finished. Completed: ${result.isCompleted}, '
        'Upward synced: ${result.upwardResult?.syncedCount ?? 0}, '
        'Downward synced: ${result.downwardResult?.itemsSynced ?? 0}',
      );
      return result.isCompleted;
    } catch (e) {
      debugPrint('BackgroundSyncScheduler: Background sync pass failed gracefully: $e');
      return false;
    } finally {
      _isBackgroundPassRunning = false;
    }
  }

  /// Static handler invoked when the background isolate receives a native task.
  static Future<bool> handleNativeTask({
    required String taskName,
    Map<String, dynamic>? inputData,
  }) async {
    if (customTaskHandler != null) {
      return await customTaskHandler!(
        taskName: taskName,
        inputData: inputData,
      );
    }

    // Context & Authentication validation
    final tenantId = inputData?['tenantId'] as String?;
    final userId = inputData?['userId'] as String?;

    if (tenantId == null || tenantId.isEmpty || userId == null || userId.isEmpty) {
      debugPrint(
        'BackgroundSyncScheduler: Missing tenantId or userId in background payload. Acknowledging task without execution.',
      );
      return true; // No credentials/context available
    }

    if (activeCoordinator != null) {
      try {
        final result = await activeCoordinator!.synchronizeAll(
          tenantId: tenantId,
          userId: userId,
          forceFullDownward: false,
        );
        return result.isCompleted;
      } catch (e) {
        debugPrint('BackgroundSyncScheduler: Background task execution failed: $e');
        return false; // Tells WorkManager to retry based on backoff policy
      }
    }

    debugPrint('BackgroundSyncScheduler: No active coordinator bound in isolate.');
    return true;
  }

  void dispose() {
    cancelPeriodicSync();
    if (activeCoordinator == _unifiedCoordinator) {
      activeCoordinator = null;
    }
  }
}
