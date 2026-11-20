import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';

void main() {
  group('LocationReading Quality Evaluation', () {
    test('isStale returns false for recent readings and true for old readings',
        () {
      final now = DateTime.now().toUtc();

      final freshReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 10.0,
        timestamp: now.subtract(const Duration(seconds: 5)),
      );
      expect(freshReading.isStale(maxAgeSeconds: 30), isFalse);

      final staleReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 10.0,
        timestamp: now.subtract(const Duration(seconds: 45)),
      );
      expect(staleReading.isStale(maxAgeSeconds: 30), isTrue);

      // Custom threshold test
      expect(freshReading.isStale(maxAgeSeconds: 3), isTrue);
    });

    test(
        'isAccurate returns true when accuracy is within threshold and false otherwise',
        () {
      final accurateReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 18.5,
        timestamp: DateTime.now().toUtc(),
      );
      expect(accurateReading.isAccurate(maxAccuracyMeters: 50), isTrue);
      expect(accurateReading.isAccurate(maxAccuracyMeters: 10), isFalse);

      final poorAccuracyReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 125.0,
        timestamp: DateTime.now().toUtc(),
      );
      expect(poorAccuracyReading.isAccurate(maxAccuracyMeters: 100), isFalse);
    });

    test('retains isMocked indicator correctly', () {
      final genuineReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 10.0,
        timestamp: DateTime.now().toUtc(),
        isMocked: false,
      );
      expect(genuineReading.isMocked, isFalse);

      final mockedReading = LocationReading(
        latitude: 40.7128,
        longitude: -74.0060,
        accuracyMeters: 10.0,
        timestamp: DateTime.now().toUtc(),
        isMocked: true,
      );
      expect(mockedReading.isMocked, isTrue);
    });
  });

  group('GeolocatorLocationService Haversine Distance Calculation', () {
    const service = GeolocatorLocationService();

    test('calculates 0 meters for identical coordinates', () {
      final distance = service.calculateDistanceMeters(
        startLatitude: 40.7128,
        startLongitude: -74.0060,
        endLatitude: 40.7128,
        endLongitude: -74.0060,
      );
      expect(distance, closeTo(0.0, 0.001));
    });

    test('calculates accurate distance between known coordinates', () {
      // Distance between NYC City Hall (40.7128, -74.0060) and Empire State (40.7484, -73.9857) ~4.3 km
      final distance = service.calculateDistanceMeters(
        startLatitude: 40.7128,
        startLongitude: -74.0060,
        endLatitude: 40.7484,
        endLongitude: -73.9857,
      );
      expect(distance, closeTo(4300, 200)); // Within 200 meters of 4.3km
    });

    test('distance calculation is symmetric', () {
      final d1 = service.calculateDistanceMeters(
        startLatitude: 51.5074,
        startLongitude: -0.1278,
        endLatitude: 48.8566,
        endLongitude: 2.3522,
      );
      final d2 = service.calculateDistanceMeters(
        startLatitude: 48.8566,
        startLongitude: 2.3522,
        endLatitude: 51.5074,
        endLongitude: -0.1278,
      );
      expect(d1, closeTo(d2, 0.001));
    });
  });

  group('Location Domain Exceptions', () {
    test('LocationServiceDisabledException has user-friendly message', () {
      const ex = LocationServiceDisabledException();
      expect(ex.message, contains('Location services (GPS) are turned off'));
      expect(ex.toString(), equals(ex.message));
    });

    test('LocationPermissionDeniedException has user-friendly message', () {
      const ex = LocationPermissionDeniedException();
      expect(ex.message, contains('Location permission is required'));
    });

    test(
        'LocationPermissionPermanentlyDeniedException has user-friendly message',
        () {
      const ex = LocationPermissionPermanentlyDeniedException();
      expect(ex.message, contains('permanently denied'));
    });

    test('LocationTimeoutException has user-friendly message', () {
      const ex = LocationTimeoutException();
      expect(ex.message, contains('GPS location acquisition timed out'));
    });

    test('LocationAccuracyException formats actual and allowable accuracy', () {
      final ex =
          LocationAccuracyException(actualAccuracy: 145.8, maxAllowable: 50);
      expect(ex.message, contains('145.8m'));
      expect(ex.message, contains('50m'));
    });

    test('LocationStaleException formats actual age and allowable age', () {
      final ex =
          LocationStaleException(actualAgeSeconds: 85, maxAllowableSeconds: 30);
      expect(ex.message, contains('85s'));
      expect(ex.message, contains('30s'));
    });

    test('MockLocationDetectedException has clear warning message', () {
      const ex = MockLocationDetectedException();
      expect(ex.message, contains('mock location'));
    });
  });
}
