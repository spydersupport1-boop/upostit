import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('Welcome screen renders with title and status badge', (WidgetTester tester) async {
    await tester.pumpWidget(const AttendanceApp());

    // Verify app title renders
    expect(find.text('Attendance SaaS'), findsOneWidget);

    // Verify stage and phase badge
    expect(find.text('Stage A • Phase 1 Foundation'), findsOneWidget);

    // Verify action button exists
    expect(find.text('System Foundation Ready'), findsOneWidget);
  });
}
