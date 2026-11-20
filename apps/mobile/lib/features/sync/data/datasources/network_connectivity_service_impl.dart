import 'dart:async';
import 'dart:io';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../../../../core/config/env_config.dart';
import '../../domain/repositories/network_connectivity_service.dart';

/// Implementation of [NetworkConnectivityService] backed by [Connectivity]
/// and an active network reachability probe.
class NetworkConnectivityServiceImpl implements NetworkConnectivityService {
  final Connectivity _connectivity;
  final Future<bool> Function()? _customReachabilityChecker;
  final Duration _debounceDuration;

  final StreamController<bool> _restoredController =
      StreamController<bool>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _subscription;
  Timer? _debounceTimer;

  bool _wasConnected = false;
  bool _isDisposed = false;

  NetworkConnectivityServiceImpl({
    Connectivity? connectivity,
    Future<bool> Function()? reachabilityChecker,
    Duration debounceDuration = const Duration(milliseconds: 1000),
  })  : _connectivity = connectivity ?? Connectivity(),
        _customReachabilityChecker = reachabilityChecker,
        _debounceDuration = debounceDuration {
    _initListener();
  }

  void _initListener() {
    _subscription = _connectivity.onConnectivityChanged.listen(
      _handleConnectivityChanged,
      onError: (Object error) {
        // Suppress stream errors and treat as disconnected
        _wasConnected = false;
      },
    );
  }

  void _handleConnectivityChanged(List<ConnectivityResult> results) {
    if (_isDisposed) return;

    final hasHardwareInterface = results.any((r) =>
        r == ConnectivityResult.wifi ||
        r == ConnectivityResult.mobile ||
        r == ConnectivityResult.ethernet ||
        r == ConnectivityResult.vpn ||
        r == ConnectivityResult.other);

    if (!hasHardwareInterface) {
      _debounceTimer?.cancel();
      _wasConnected = false;
      return;
    }

    // Debounce rapid network interface switching (e.g. cellular to wifi handoff)
    _debounceTimer?.cancel();
    _debounceTimer = Timer(_debounceDuration, () async {
      if (_isDisposed) return;

      final isReachable = await checkBackendReachability();
      if (isReachable && !_wasConnected) {
        _wasConnected = true;
        if (!_restoredController.isClosed) {
          _restoredController.add(true);
        }
      } else if (!isReachable) {
        _wasConnected = false;
      }
    });
  }

  @override
  Stream<bool> get onConnectivityRestored => _restoredController.stream;

  @override
  Future<bool> isConnected() async {
    try {
      final results = await _connectivity.checkConnectivity();
      final hasHardwareInterface = results.any((r) =>
          r == ConnectivityResult.wifi ||
          r == ConnectivityResult.mobile ||
          r == ConnectivityResult.ethernet ||
          r == ConnectivityResult.vpn ||
          r == ConnectivityResult.other);

      if (!hasHardwareInterface) {
        _wasConnected = false;
        return false;
      }

      final reachable = await checkBackendReachability();
      _wasConnected = reachable;
      return reachable;
    } catch (_) {
      _wasConnected = false;
      return false;
    }
  }

  @override
  Future<bool> checkBackendReachability() async {
    final custom = _customReachabilityChecker;
    if (custom != null) {
      return await custom();
    }

    try {
      final uri = Uri.parse(EnvConfig.apiBaseUrl);
      final host = uri.host.isNotEmpty ? uri.host : 'localhost';

      // Perform low-level DNS / socket lookup
      final lookup = await InternetAddress.lookup(host).timeout(
        const Duration(seconds: 4),
      );

      if (lookup.isNotEmpty && lookup[0].rawAddress.isNotEmpty) {
        return true;
      }
      return false;
    } on SocketException {
      return false;
    } on TimeoutException {
      return false;
    } catch (_) {
      return false;
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    _debounceTimer?.cancel();
    _subscription?.cancel();
    _restoredController.close();
  }
}
