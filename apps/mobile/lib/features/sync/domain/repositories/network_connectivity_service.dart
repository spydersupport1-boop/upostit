import 'dart:async';

/// Contract for observing platform network interface changes and verifying
/// end-to-end backend API reachability.
abstract class NetworkConnectivityService {
  /// Broadcast stream that emits `true` whenever internet connectivity is
  /// restored and confirmed via reachability probe.
  Stream<bool> get onConnectivityRestored;

  /// Returns whether the device currently has active network connectivity
  /// that can reach the backend.
  Future<bool> isConnected();

  /// Actively probes whether the backend server is reachable.
  Future<bool> checkBackendReachability();

  /// Disposes background listeners, stream controllers, and timers.
  void dispose();
}
