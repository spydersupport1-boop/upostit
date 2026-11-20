import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/sync/data/datasources/network_connectivity_service_impl.dart';

class FakeConnectivity extends Fake implements Connectivity {
  final StreamController<List<ConnectivityResult>> _controller =
      StreamController<List<ConnectivityResult>>.broadcast();

  List<ConnectivityResult> currentResults = [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged =>
      _controller.stream;

  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => currentResults;

  void emit(List<ConnectivityResult> results) {
    currentResults = results;
    _controller.add(results);
  }

  void close() {
    _controller.close();
  }
}

void main() {
  group('NetworkConnectivityServiceImpl', () {
    late FakeConnectivity fakeConnectivity;
    bool backendReachable = true;

    setUp(() {
      fakeConnectivity = FakeConnectivity();
      backendReachable = true;
    });

    tearDown(() {
      fakeConnectivity.close();
    });

    test('isConnected returns false when connectivity is none', () async {
      fakeConnectivity.currentResults = [ConnectivityResult.none];
      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
      );

      final connected = await service.isConnected();
      expect(connected, isFalse);

      service.dispose();
    });

    test(
        'isConnected returns false when interface is connected but backend is unreachable',
        () async {
      fakeConnectivity.currentResults = [ConnectivityResult.wifi];
      backendReachable = false;

      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
      );

      final connected = await service.isConnected();
      expect(connected, isFalse);

      service.dispose();
    });

    test(
        'isConnected returns true when interface is wifi and backend reachable',
        () async {
      fakeConnectivity.currentResults = [ConnectivityResult.wifi];
      backendReachable = true;

      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
      );

      final connected = await service.isConnected();
      expect(connected, isTrue);

      service.dispose();
    });

    test('isConnected returns true on mobile data and ethernet when reachable',
        () async {
      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
      );

      fakeConnectivity.currentResults = [ConnectivityResult.mobile];
      expect(await service.isConnected(), isTrue);

      fakeConnectivity.currentResults = [ConnectivityResult.ethernet];
      expect(await service.isConnected(), isTrue);

      service.dispose();
    });

    test(
        'emits onConnectivityRestored when connectivity returns and reachability is verified',
        () async {
      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
        debounceDuration: const Duration(milliseconds: 50),
      );

      final emitted = <bool>[];
      final sub = service.onConnectivityRestored.listen(emitted.add);

      // Start disconnected
      fakeConnectivity.emit([ConnectivityResult.none]);
      await Future<void>.delayed(const Duration(milliseconds: 70));
      expect(emitted, isEmpty);

      // Connect to Wi-Fi with verified backend
      backendReachable = true;
      fakeConnectivity.emit([ConnectivityResult.wifi]);
      await Future<void>.delayed(const Duration(milliseconds: 100));

      expect(emitted.length, equals(1));
      expect(emitted.first, isTrue);

      await sub.cancel();
      service.dispose();
    });

    test(
        'does not emit onConnectivityRestored when network connected but backend unreachable',
        () async {
      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
        debounceDuration: const Duration(milliseconds: 50),
      );

      final emitted = <bool>[];
      final sub = service.onConnectivityRestored.listen(emitted.add);

      // Connect to Wi-Fi with unreachable backend (e.g. captive portal)
      backendReachable = false;
      fakeConnectivity.emit([ConnectivityResult.wifi]);
      await Future<void>.delayed(const Duration(milliseconds: 100));

      expect(emitted, isEmpty);

      await sub.cancel();
      service.dispose();
    });

    test('debounces rapid network interface switches without duplicate events',
        () async {
      final service = NetworkConnectivityServiceImpl(
        connectivity: fakeConnectivity,
        reachabilityChecker: () async => backendReachable,
        debounceDuration: const Duration(milliseconds: 80),
      );

      final emitted = <bool>[];
      final sub = service.onConnectivityRestored.listen(emitted.add);

      backendReachable = true;
      // Rapid switching between cellular and wifi
      fakeConnectivity.emit([ConnectivityResult.mobile]);
      await Future<void>.delayed(const Duration(milliseconds: 30));
      fakeConnectivity.emit([ConnectivityResult.wifi]);
      await Future<void>.delayed(const Duration(milliseconds: 30));
      fakeConnectivity.emit([ConnectivityResult.wifi, ConnectivityResult.vpn]);
      await Future<void>.delayed(const Duration(milliseconds: 120));

      // Exactly ONE debounced emission
      expect(emitted.length, equals(1));

      await sub.cancel();
      service.dispose();
    });
  });
}
