import 'package:bloc_test/bloc_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/devices/domain/entities/device_binding_status.dart';
import 'package:mobile/features/devices/domain/entities/device_info.dart';
import 'package:mobile/features/devices/presentation/bloc/device_bloc.dart';
import 'package:mobile/features/devices/presentation/bloc/device_event.dart';
import 'package:mobile/features/devices/presentation/bloc/device_state.dart';
import 'package:mobile/features/devices/presentation/widgets/device_status_card.dart';
import 'package:mocktail/mocktail.dart';

class MockDeviceBloc extends MockBloc<DeviceEvent, DeviceState>
    implements DeviceBloc {}

void main() {
  late MockDeviceBloc mockDeviceBloc;

  final activeDeviceInfo = DeviceInfo(
    id: 'device-1',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    platform: 'ANDROID',
    deviceModel: 'Pixel 8',
    osName: 'Android',
    osVersion: '14',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.active,
    registeredAt: DateTime.utc(2026, 11, 1),
  );

  final revokedDeviceInfo = DeviceInfo(
    id: 'device-2',
    tenantId: 'tenant-1',
    employeeId: 'emp-1',
    platform: 'IOS',
    deviceModel: 'iPhone 15',
    osName: 'iOS',
    osVersion: '17.2',
    appVersion: '1.0.0+1',
    status: DeviceBindingStatus.revoked,
    registeredAt: DateTime.utc(2026, 10, 1),
    revokedAt: DateTime.utc(2026, 11, 10),
    revocationReason: 'Device stolen report',
  );

  setUp(() {
    mockDeviceBloc = MockDeviceBloc();
  });

  Widget buildWidget(DeviceState state) {
    when(() => mockDeviceBloc.state).thenReturn(state);
    return MaterialApp(
      home: Scaffold(
        body: DeviceStatusCard(deviceBloc: mockDeviceBloc),
      ),
    );
  }

  group('DeviceStatusCard Widget Tests', () {
    testWidgets('renders loading indicator when DeviceLoading', (tester) async {
      await tester.pumpWidget(buildWidget(const DeviceLoading()));

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Checking device authorization...'), findsOneWidget);
    });

    testWidgets('renders error banner and retry button on DeviceFailure',
        (tester) async {
      await tester.pumpWidget(buildWidget(const DeviceFailure(
        'Unable to reach server',
        isRetriable: true,
      )));

      expect(find.text('Device Authorization Error'), findsOneWidget);
      expect(find.text('Unable to reach server'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pump();

      verify(() => mockDeviceBloc.add(const CheckDeviceStatusRequested()))
          .called(1);
    });

    testWidgets('renders ACTIVE status badge, model, and refresh button',
        (tester) async {
      await tester.pumpWidget(buildWidget(DeviceLoaded(
        isBound: true,
        status: DeviceBindingStatus.active,
        device: activeDeviceInfo,
      )));

      expect(find.text('Mobile Device Binding'), findsOneWidget);
      expect(find.text('ACTIVE'), findsOneWidget);
      expect(find.text('ANDROID • Pixel 8'), findsOneWidget);
      expect(find.text('1.0.0+1'), findsOneWidget);
      expect(find.text('Refresh Status'), findsOneWidget);
      expect(
          find.text(
              'This device is bound to your account and authorized to record attendance punches.'),
          findsOneWidget);

      await tester.tap(find.text('Refresh Status'));
      await tester.pump();

      verify(() => mockDeviceBloc.add(const CheckDeviceStatusRequested()))
          .called(1);
    });

    testWidgets('renders PENDING APPROVAL badge and waiting explanation',
        (tester) async {
      await tester.pumpWidget(buildWidget(const DeviceLoaded(
        isBound: true,
        status: DeviceBindingStatus.pendingApproval,
        device: null,
      )));

      expect(find.text('PENDING APPROVAL'), findsOneWidget);
      expect(
          find.text(
              'Registration is pending HR administrator review and approval before punches can be recorded.'),
          findsOneWidget);
    });

    testWidgets(
        'renders REVOKED badge, revocation warning and reason when revoked',
        (tester) async {
      await tester.pumpWidget(buildWidget(DeviceLoaded(
        isBound: true,
        status: DeviceBindingStatus.revoked,
        device: revokedDeviceInfo,
      )));

      expect(find.text('REVOKED'), findsOneWidget);
      expect(
          find.text(
              'This device authorization has been revoked. Attendance punches from this device are blocked. Please contact HR.'),
          findsOneWidget);
      expect(find.text('Device stolen report'), findsOneWidget);
    });

    testWidgets('renders UNREGISTERED badge and Register This Device button',
        (tester) async {
      await tester.pumpWidget(buildWidget(const DeviceLoaded(
        isBound: false,
        status: DeviceBindingStatus.unregistered,
        device: null,
      )));

      expect(find.text('UNREGISTERED'), findsOneWidget);
      expect(find.text('Register This Device'), findsOneWidget);
      expect(
          find.text(
              'This device is not yet registered. Register this device to authorize attendance tracking.'),
          findsOneWidget);

      await tester.tap(find.text('Register This Device'));
      await tester.pump();

      verify(() => mockDeviceBloc.add(const RegisterCurrentDeviceRequested()))
          .called(1);
    });
  });
}
