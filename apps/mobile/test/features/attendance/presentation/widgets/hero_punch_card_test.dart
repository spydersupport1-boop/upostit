import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_status.dart';
import 'package:mobile/features/attendance/presentation/widgets/hero_punch_card.dart';

void main() {
  Widget buildWidget({
    required AttendanceStatus status,
    required bool isSubmitting,
    AttendanceEventType? inFlightEventType,
    required void Function(AttendanceEventType) onPunchPressed,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: HeroPunchCard(
          status: status,
          isSubmitting: isSubmitting,
          inFlightEventType: inFlightEventType,
          onPunchPressed: onPunchPressed,
        ),
      ),
    );
  }

  testWidgets(
      'renders CHECK IN button when status is notCheckedIn and triggers callback on tap',
      (tester) async {
    AttendanceEventType? tappedType;

    await tester.pumpWidget(
      buildWidget(
        status: AttendanceStatus.notCheckedIn,
        isSubmitting: false,
        onPunchPressed: (type) => tappedType = type,
      ),
    );

    expect(find.byKey(const Key('hero_check_in_button')), findsOneWidget);
    expect(find.text('CHECK IN'), findsOneWidget);

    await tester.tap(find.byKey(const Key('hero_check_in_button')));
    await tester.pump();

    expect(tappedType, equals(AttendanceEventType.checkIn));
  });

  testWidgets(
      'renders CHECK OUT and START BREAK buttons when status is working',
      (tester) async {
    AttendanceEventType? tappedType;

    await tester.pumpWidget(
      buildWidget(
        status: AttendanceStatus.working,
        isSubmitting: false,
        onPunchPressed: (type) => tappedType = type,
      ),
    );

    expect(find.byKey(const Key('hero_check_out_button')), findsOneWidget);
    expect(find.byKey(const Key('break_start_button')), findsOneWidget);
    expect(find.text('CHECK OUT'), findsOneWidget);
    expect(find.text('START BREAK'), findsOneWidget);

    await tester.tap(find.byKey(const Key('break_start_button')));
    await tester.pump();

    expect(tappedType, equals(AttendanceEventType.breakStart));
  });

  testWidgets(
      'renders RESUME WORK and CHECK OUT buttons when status is onBreak',
      (tester) async {
    AttendanceEventType? tappedType;

    await tester.pumpWidget(
      buildWidget(
        status: AttendanceStatus.onBreak,
        isSubmitting: false,
        onPunchPressed: (type) => tappedType = type,
      ),
    );

    expect(find.byKey(const Key('hero_break_end_button')), findsOneWidget);
    expect(find.byKey(const Key('break_checkout_button')), findsOneWidget);
    expect(find.text('RESUME WORK'), findsOneWidget);

    await tester.tap(find.byKey(const Key('hero_break_end_button')));
    await tester.pump();

    expect(tappedType, equals(AttendanceEventType.breakEnd));
  });

  testWidgets(
      'disables punch buttons and displays progress indicator during in-flight submission',
      (tester) async {
    var tapCount = 0;

    await tester.pumpWidget(
      buildWidget(
        status: AttendanceStatus.notCheckedIn,
        isSubmitting: true,
        inFlightEventType: AttendanceEventType.checkIn,
        onPunchPressed: (_) => tapCount++,
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // Attempt double-tapping while submitting
    await tester.tap(find.byKey(const Key('hero_check_in_button')));
    await tester.pump();

    // Callback should NOT be invoked
    expect(tapCount, equals(0));
  });

  testWidgets('renders Shift Completed view when status is completed',
      (tester) async {
    await tester.pumpWidget(
      buildWidget(
        status: AttendanceStatus.completed,
        isSubmitting: false,
        onPunchPressed: (_) {},
      ),
    );

    expect(find.text('Shift Completed'), findsOneWidget);
    expect(find.byKey(const Key('re_check_in_button')), findsOneWidget);
  });
}
