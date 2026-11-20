import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/app.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_bloc.dart';
import 'package:mobile/features/attendance/presentation/bloc/attendance_state.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_bloc.dart';
import 'package:mobile/features/profile/presentation/bloc/profile_state.dart';
import 'package:mocktail/mocktail.dart';

class MockAuthBloc extends Mock implements AuthBloc {}

class MockProfileBloc extends Mock implements ProfileBloc {}

class MockAttendanceBloc extends Mock implements AttendanceBloc {}

void main() {
  late MockAuthBloc mockAuthBloc;
  late MockProfileBloc mockProfileBloc;
  late MockAttendanceBloc mockAttendanceBloc;

  setUp(() {
    mockAuthBloc = MockAuthBloc();
    mockProfileBloc = MockProfileBloc();
    mockAttendanceBloc = MockAttendanceBloc();

    when(() => mockAuthBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockAuthBloc.state).thenReturn(const AuthInitial());
    when(() => mockProfileBloc.stream).thenAnswer((_) => const Stream.empty());
    when(() => mockProfileBloc.state).thenReturn(const ProfileInitial());
    when(() => mockAttendanceBloc.stream)
        .thenAnswer((_) => const Stream.empty());
    when(() => mockAttendanceBloc.state).thenReturn(const AttendanceInitial());
  });

  testWidgets('AttendanceApp boots with Material 3 theme and initial route',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MultiBlocProvider(
        providers: [
          BlocProvider<AuthBloc>.value(value: mockAuthBloc),
          BlocProvider<ProfileBloc>.value(value: mockProfileBloc),
          BlocProvider<AttendanceBloc>.value(value: mockAttendanceBloc),
        ],
        child: const AttendanceApp(),
      ),
    );

    // Verify root MaterialApp mounts
    expect(find.byType(MaterialApp), findsOneWidget);
    // Verify splash screen branding renders on initial route
    expect(find.text('UPOSTIT'), findsOneWidget);
    expect(find.text('Workforce Attendance Platform'), findsOneWidget);
  });
}
