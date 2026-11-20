import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/assigned_workplace.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_evidence.dart';
import 'package:mobile/features/attendance/domain/entities/wifi_verification_result.dart';
import 'package:mobile/features/attendance/presentation/widgets/wifi_status_card.dart';

void main() {
  const sampleWorkplace = AssignedWorkplace(
    id: 'wp-1',
    locationId: 'loc-1',
    locationName: 'HQ Branch',
    locationCode: 'HQ-1',
    address: '123 Market St',
    city: 'San Francisco',
    countryCode: 'US',
    isPrimary: true,
    isCurrent: true,
  );

  const samplePolicy = AttendancePolicy(
    tenantId: 't-1',
    version: 1,
    defaultMode: 'WIFI_ONLY',
    allowedMethods: ['WIFI'],
    requiredMethods: ['WIFI'],
    combinationRule: 'OR',
    requiresGps: false,
    requiresWifi: true,
    wifiFallbackAction: 'GPS_FALLBACK',
  );

  Widget createWidgetUnderTest({
    bool isProbing = false,
    bool isPermissionDenied = false,
    WifiEvidence? evidence,
    WifiVerificationResult? verificationResult,
    String? inFlightMessage,
    VoidCallback? onProbe,
    VoidCallback? onResolvePermission,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: WifiStatusCard(
          policy: samplePolicy,
          workplace: sampleWorkplace,
          lastEvidence: evidence,
          lastVerificationResult: verificationResult,
          isProbing: isProbing,
          isPermissionDenied: isPermissionDenied,
          inFlightStatusMessage: inFlightMessage,
          onProbeWifi: onProbe ?? () {},
          onResolvePermission: onResolvePermission,
        ),
      ),
    );
  }

  group('WifiStatusCard Widget Tests', () {
    testWidgets('renders in-flight probing state with progress indicator',
        (tester) async {
      await tester.pumpWidget(createWidgetUnderTest(
        isProbing: true,
        inFlightMessage: 'Checking workplace Wi-Fi...',
      ));

      expect(find.text('Checking workplace Wi-Fi...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('renders verified state when access point is matched',
        (tester) async {
      final evidence = WifiEvidence(
        bssid: 'AA:BB:CC:DD:EE:01',
        ssid: 'Corp-Office-5G',
        signalStatus: WifiSignalStatus.available,
        deviceReportedAt: DateTime.now().toUtc(),
        platform: 'android',
      );

      const verification = WifiVerificationResult(
        locationId: 'loc-1',
        locationName: 'HQ Branch',
        locationCode: 'HQ-1',
        reportedBssid: 'AA:BB:CC:DD:EE:01',
        matchStatus: WifiMatchStatus.matched,
        isVerified: true,
        message: 'Connected to authorized workplace access point.',
      );

      await tester.pumpWidget(createWidgetUnderTest(
        evidence: evidence,
        verificationResult: verification,
      ));

      expect(find.text('Workplace Wi-Fi verified'), findsOneWidget);
      expect(find.textContaining('Corp-Office-5G'), findsOneWidget);
      expect(find.byIcon(Icons.wifi_password_rounded), findsOneWidget);
    });

    testWidgets(
        'renders unrecognized network error state when BSSID is mismatched',
        (tester) async {
      const verification = WifiVerificationResult(
        locationId: 'loc-1',
        locationName: 'HQ Branch',
        locationCode: 'HQ-1',
        reportedBssid: 'FF:FF:FF:FF:FF:FF',
        matchStatus: WifiMatchStatus.mismatched,
        isVerified: false,
        message: 'Connected Wi-Fi is unauthorized.',
      );

      await tester.pumpWidget(createWidgetUnderTest(
        verificationResult: verification,
      ));

      expect(find.text('Connected to an unrecognized network'), findsOneWidget);
      expect(find.byIcon(Icons.wifi_off_rounded), findsOneWidget);
    });

    testWidgets(
        'renders permission denied warning and calls onResolvePermission when tapped',
        (tester) async {
      bool permissionTapped = false;

      await tester.pumpWidget(createWidgetUnderTest(
        isPermissionDenied: true,
        onResolvePermission: () {
          permissionTapped = true;
        },
      ));

      expect(find.text('Wi-Fi permission required'), findsOneWidget);
      expect(find.byKey(const Key('wifi_resolve_permission_button')),
          findsOneWidget);

      await tester.tap(find.byKey(const Key('wifi_resolve_permission_button')));
      await tester.pump();

      expect(permissionTapped, isTrue);
    });

    testWidgets('triggers onProbeWifi when probe refresh button is tapped',
        (tester) async {
      bool probeTapped = false;

      await tester.pumpWidget(createWidgetUnderTest(
        onProbe: () {
          probeTapped = true;
        },
      ));

      expect(find.byKey(const Key('wifi_probe_button')), findsOneWidget);
      await tester.tap(find.byKey(const Key('wifi_probe_button')));
      await tester.pump();

      expect(probeTapped, isTrue);
    });
  });
}
