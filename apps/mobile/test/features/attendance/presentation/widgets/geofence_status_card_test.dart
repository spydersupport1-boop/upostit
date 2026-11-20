import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/services/location_service.dart';
import 'package:mobile/features/attendance/domain/entities/assigned_workplace.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';
import 'package:mobile/features/attendance/presentation/widgets/geofence_status_card.dart';

void main() {
  const manualPolicy = AttendancePolicy(
    tenantId: 'tenant-1',
    version: 1,
    defaultMode: 'MANUAL',
    allowedMethods: ['MANUAL'],
    requiredMethods: ['MANUAL'],
    combinationRule: 'OR',
    requiresGps: false,
  );

  const gpsPolicy = AttendancePolicy(
    tenantId: 'tenant-1',
    version: 1,
    defaultMode: 'GPS_ONLY',
    allowedMethods: ['GPS_ONLY'],
    requiredMethods: ['GPS_ONLY'],
    combinationRule: 'OR',
    requiresGps: true,
  );

  const workplace = AssignedWorkplace(
    id: 'wp-1',
    locationId: 'loc-1',
    locationName: 'Corporate Headquarters',
    locationCode: 'HQ-1',
    address: '100 Main St',
    city: 'San Francisco',
    countryCode: 'US',
    isPrimary: true,
    isCurrent: true,
    latitude: 37.7749,
    longitude: -122.4194,
    radiusMeters: 100,
  );

  Widget createWidget({
    AttendancePolicy? policy = gpsPolicy,
    AssignedWorkplace? wp = workplace,
    LocationReading? lastReading,
    double? advisoryDistanceMeters,
    bool? isInsideGeofence,
    bool isPermissionDenied = false,
    bool isServiceDisabled = false,
    String? inFlightStatusMessage,
    VoidCallback? onResolvePermission,
    VoidCallback? onProbeLocation,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: GeofenceStatusCard(
          policy: policy,
          workplace: wp,
          lastReading: lastReading,
          advisoryDistanceMeters: advisoryDistanceMeters,
          isInsideGeofence: isInsideGeofence,
          isPermissionDenied: isPermissionDenied,
          isServiceDisabled: isServiceDisabled,
          inFlightStatusMessage: inFlightStatusMessage,
          onResolvePermission: onResolvePermission,
          onProbeLocation: onProbeLocation,
        ),
      ),
    );
  }

  group('GeofenceStatusCard Widget Tests', () {
    testWidgets(
        'renders SizedBox.shrink when policy is MANUAL (zero UI clutter)',
        (tester) async {
      await tester.pumpWidget(createWidget(policy: manualPolicy));

      expect(find.byType(GeofenceStatusCard), findsOneWidget);
      expect(find.text('Corporate Headquarters'), findsNothing);
      expect(find.textContaining('Geofence perimeter'), findsNothing);
    });

    testWidgets(
        'renders workplace details and geofence radius when policy is GPS_ONLY',
        (tester) async {
      await tester.pumpWidget(createWidget(policy: gpsPolicy));

      expect(find.text('Corporate Headquarters'), findsOneWidget);
      expect(find.text('Geofence perimeter: 100m'), findsOneWidget);
    });

    testWidgets('renders permission denied alert banner with Allow button',
        (tester) async {
      bool permissionResolved = false;

      await tester.pumpWidget(createWidget(
        isPermissionDenied: true,
        onResolvePermission: () => permissionResolved = true,
      ));

      expect(find.text('Location Permission Required'), findsOneWidget);
      expect(find.text('Allow'), findsOneWidget);

      await tester.tap(find.text('Allow'));
      expect(permissionResolved, isTrue);
    });

    testWidgets(
        'renders location services disabled alert banner with Turn On button',
        (tester) async {
      bool permissionResolved = false;

      await tester.pumpWidget(createWidget(
        isServiceDisabled: true,
        onResolvePermission: () => permissionResolved = true,
      ));

      expect(find.text('Location Services Disabled'), findsOneWidget);
      expect(find.text('Turn On'), findsOneWidget);

      await tester.tap(find.text('Turn On'));
      expect(permissionResolved, isTrue);
    });

    testWidgets(
        'displays inside perimeter status when advisory distance is within radius',
        (tester) async {
      await tester.pumpWidget(createWidget(
        isInsideGeofence: true,
        advisoryDistanceMeters: 25.0,
      ));

      expect(find.textContaining('Within geofence (~25m from center)'),
          findsOneWidget);
    });

    testWidgets(
        'displays outside perimeter status when advisory distance exceeds radius',
        (tester) async {
      await tester.pumpWidget(createWidget(
        isInsideGeofence: false,
        advisoryDistanceMeters: 180.0,
      ));

      expect(
          find.textContaining('Outside geofence (~180m away)'), findsOneWidget);
    });

    testWidgets(
        'renders in-flight verification status message and progress spinner',
        (tester) async {
      await tester.pumpWidget(createWidget(
        inFlightStatusMessage: 'Acquiring GPS location...',
      ));

      expect(find.text('Acquiring GPS location...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('triggers onProbeLocation when refresh button is tapped',
        (tester) async {
      bool probed = false;

      await tester.pumpWidget(createWidget(
        onProbeLocation: () => probed = true,
      ));

      final refreshBtn = find.byKey(const Key('check_proximity_icon_button'));
      expect(refreshBtn, findsOneWidget);

      await tester.tap(refreshBtn);
      expect(probed, isTrue);
    });
  });
}
