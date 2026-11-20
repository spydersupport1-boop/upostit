import 'dart:async';
import 'dart:math' as math;
import 'package:geolocator/geolocator.dart';

/// Status of location permissions for attendance verification.
enum LocationPermissionStatus {
  granted,
  denied,
  permanentlyDenied,
  serviceDisabled,
}

/// Structured hardware GPS reading with accuracy, timestamp, and mock indicator.
class LocationReading {
  final double latitude;
  final double longitude;
  final double accuracyMeters;
  final DateTime timestamp;
  final bool isMocked;

  const LocationReading({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
    required this.timestamp,
    this.isMocked = false,
  });

  /// Evaluates whether this location reading exceeds allowable staleness.
  bool isStale({int maxAgeSeconds = 30}) {
    final now = DateTime.now().toUtc();
    final age = now.difference(timestamp.toUtc()).inSeconds.abs();
    return age > maxAgeSeconds;
  }

  /// Evaluates whether horizontal accuracy is within allowable threshold.
  bool isAccurate({int maxAccuracyMeters = 100}) {
    return accuracyMeters <= maxAccuracyMeters;
  }
}

/// Domain exceptions for location failures.
class LocationException implements Exception {
  final String message;
  const LocationException(this.message);

  @override
  String toString() => message;
}

class LocationServiceDisabledException extends LocationException {
  const LocationServiceDisabledException([
    super.message =
        'Location services (GPS) are turned off. Please enable location services in your device settings.',
  ]);
}

class LocationPermissionDeniedException extends LocationException {
  const LocationPermissionDeniedException([
    super.message =
        'Location permission is required for attendance verification. Please grant location access.',
  ]);
}

class LocationPermissionPermanentlyDeniedException extends LocationException {
  const LocationPermissionPermanentlyDeniedException([
    super.message =
        'Location permission is permanently denied. Please enable location access in system settings.',
  ]);
}

class LocationTimeoutException extends LocationException {
  const LocationTimeoutException([
    super.message =
        'GPS location acquisition timed out. Please ensure you have a clear view of the sky and try again.',
  ]);
}

class LocationAccuracyException extends LocationException {
  final double actualAccuracy;
  final int maxAllowable;

  LocationAccuracyException({
    required this.actualAccuracy,
    required this.maxAllowable,
  }) : super(
          'GPS accuracy (${actualAccuracy.toStringAsFixed(1)}m) is insufficient. Maximum allowable threshold is ${maxAllowable}m. Please step outside or near a window.',
        );
}

class LocationStaleException extends LocationException {
  final int actualAgeSeconds;
  final int maxAllowableSeconds;

  LocationStaleException({
    required this.actualAgeSeconds,
    required this.maxAllowableSeconds,
  }) : super(
          'GPS reading is stale (${actualAgeSeconds}s old). A fresh location fix (< ${maxAllowableSeconds}s) is required.',
        );
}

class MockLocationDetectedException extends LocationException {
  const MockLocationDetectedException([
    super.message =
        'Simulated or mock location detected. Please disable mock location apps to record attendance.',
  ]);
}

/// Abstract contract for device location capabilities (enabling 100% test mocking).
abstract class LocationService {
  /// Checks whether location hardware services are enabled at the OS level.
  Future<bool> isLocationServiceEnabled();

  /// Checks current foreground permission status.
  Future<LocationPermissionStatus> checkPermissionStatus();

  /// Prompts user for foreground location permission.
  Future<LocationPermissionStatus> requestPermission();

  /// Obtains a fresh, high-accuracy location fix enforcing quality constraints.
  Future<LocationReading> getCurrentLocation({
    Duration timeout = const Duration(seconds: 15),
    int maxAccuracyMeters = 100,
    int maxLocationAgeSeconds = 30,
    bool checkMockLocation = true,
  });

  /// Opens application settings screen.
  Future<bool> openAppSettings();

  /// Opens system location settings screen.
  Future<bool> openLocationSettings();

  /// Calculates advisory great-circle distance in meters between two decimal degree points.
  double calculateDistanceMeters({
    required double startLatitude,
    required double startLongitude,
    required double endLatitude,
    required double endLongitude,
  });
}

/// Default implementation backed by the Flutter `geolocator` plugin.
class GeolocatorLocationService implements LocationService {
  const GeolocatorLocationService();

  @override
  Future<bool> isLocationServiceEnabled() async {
    return await Geolocator.isLocationServiceEnabled();
  }

  @override
  Future<LocationPermissionStatus> checkPermissionStatus() async {
    final serviceEnabled = await isLocationServiceEnabled();
    if (!serviceEnabled) {
      return LocationPermissionStatus.serviceDisabled;
    }

    final permission = await Geolocator.checkPermission();
    return _mapGeolocatorPermission(permission);
  }

  @override
  Future<LocationPermissionStatus> requestPermission() async {
    final permission = await Geolocator.requestPermission();
    return _mapGeolocatorPermission(permission);
  }

  @override
  Future<LocationReading> getCurrentLocation({
    Duration timeout = const Duration(seconds: 15),
    int maxAccuracyMeters = 100,
    int maxLocationAgeSeconds = 30,
    bool checkMockLocation = true,
  }) async {
    final serviceEnabled = await isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw const LocationServiceDisabledException();
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        throw const LocationPermissionDeniedException();
      }
    }

    if (permission == LocationPermission.deniedForever) {
      throw const LocationPermissionPermanentlyDeniedException();
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: timeout,
        ),
      );

      final reading = LocationReading(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyMeters: position.accuracy,
        timestamp: position.timestamp,
        isMocked: position.isMocked,
      );

      // 1. Mock location detection (where supported by platform)
      if (checkMockLocation && reading.isMocked) {
        throw const MockLocationDetectedException();
      }

      // 2. Horizontal accuracy validation
      if (!reading.isAccurate(maxAccuracyMeters: maxAccuracyMeters)) {
        throw LocationAccuracyException(
          actualAccuracy: reading.accuracyMeters,
          maxAllowable: maxAccuracyMeters,
        );
      }

      // 3. Freshness validation
      if (reading.isStale(maxAgeSeconds: maxLocationAgeSeconds)) {
        final age = DateTime.now()
            .toUtc()
            .difference(reading.timestamp.toUtc())
            .inSeconds
            .abs();
        throw LocationStaleException(
          actualAgeSeconds: age,
          maxAllowableSeconds: maxLocationAgeSeconds,
        );
      }

      return reading;
    } on TimeoutException {
      throw const LocationTimeoutException();
    } catch (e) {
      if (e is LocationException) rethrow;
      throw LocationException('Location acquisition error: $e');
    }
  }

  @override
  Future<bool> openAppSettings() async {
    return await Geolocator.openAppSettings();
  }

  @override
  Future<bool> openLocationSettings() async {
    return await Geolocator.openLocationSettings();
  }

  @override
  double calculateDistanceMeters({
    required double startLatitude,
    required double startLongitude,
    required double endLatitude,
    required double endLongitude,
  }) {
    const earthRadius = 6371000.0;
    final phi1 = startLatitude * (math.pi / 180.0);
    final phi2 = endLatitude * (math.pi / 180.0);
    final deltaPhi = (endLatitude - startLatitude) * (math.pi / 180.0);
    final deltaLambda = (endLongitude - startLongitude) * (math.pi / 180.0);

    final a = math.sin(deltaPhi / 2.0) * math.sin(deltaPhi / 2.0) +
        math.cos(phi1) *
            math.cos(phi2) *
            math.sin(deltaLambda / 2.0) *
            math.sin(deltaLambda / 2.0);
    final c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a));
    return earthRadius * c;
  }

  LocationPermissionStatus _mapGeolocatorPermission(
      LocationPermission permission) {
    switch (permission) {
      case LocationPermission.whileInUse:
      case LocationPermission.always:
        return LocationPermissionStatus.granted;
      case LocationPermission.deniedForever:
        return LocationPermissionStatus.permanentlyDenied;
      case LocationPermission.denied:
      case LocationPermission.unableToDetermine:
        return LocationPermissionStatus.denied;
    }
  }
}
