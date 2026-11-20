import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_event.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mobile/features/auth/presentation/screens/login_screen.dart';
import 'package:mocktail/mocktail.dart';

class MockAuthBloc extends Mock implements AuthBloc {}

void main() {
  late MockAuthBloc mockAuthBloc;

  setUpAll(() {
    registerFallbackValue(const AuthCheckRequested());
  });

  setUp(() {
    mockAuthBloc = MockAuthBloc();
    when(() => mockAuthBloc.stream).thenAnswer((_) => const Stream.empty());
  });

  Widget buildTestWidget() {
    return MaterialApp(
      theme: AppTheme.lightTheme,
      home: BlocProvider<AuthBloc>.value(
        value: mockAuthBloc,
        child: const LoginScreen(),
      ),
    );
  }

  testWidgets('renders all required login form fields and submit button',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(const Unauthenticated());

    await tester.pumpWidget(buildTestWidget());

    expect(find.text('Sign in to UPOSTIT'), findsOneWidget);
    expect(find.text('Company Workspace Code'), findsOneWidget);
    expect(find.text('Work Email Address'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Sign In to Workspace'), findsOneWidget);
  });

  testWidgets('displays validation error messages when fields are empty',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(const Unauthenticated());

    await tester.pumpWidget(buildTestWidget());

    // Scroll to and tap sign in without filling form
    await tester.ensureVisible(find.text('Sign In to Workspace'));
    await tester.tap(find.text('Sign In to Workspace'));
    await tester.pumpAndSettle();

    expect(find.text('Company code is required'), findsOneWidget);
    expect(find.text('Email address is required'), findsOneWidget);
    expect(find.text('Password is required'), findsOneWidget);

    verifyNever(() => mockAuthBloc.add(any()));
  });

  testWidgets('dispatches LoginSubmitted when valid credentials are submitted',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(const Unauthenticated());

    await tester.pumpWidget(buildTestWidget());

    // Enter valid credentials
    await tester.enterText(find.byType(TextFormField).at(0), 'acme-corp');
    await tester.enterText(find.byType(TextFormField).at(1), 'alice@acme.com');
    await tester.enterText(find.byType(TextFormField).at(2), 'password123');

    await tester.ensureVisible(find.text('Sign In to Workspace'));
    await tester.tap(find.text('Sign In to Workspace'));
    await tester.pumpAndSettle();

    verify(() => mockAuthBloc.add(
          const LoginSubmitted(
            email: 'alice@acme.com',
            password: 'password123',
            tenantSlug: 'acme-corp',
          ),
        )).called(1);
  });

  testWidgets('displays error banner when state contains an error message',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const Unauthenticated(
          errorMessage: 'Invalid credentials or inactive account'),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(
        find.text('Invalid credentials or inactive account'), findsOneWidget);
  });

  testWidgets('displays loading indicator when state is AuthLoading',
      (tester) async {
    when(() => mockAuthBloc.state).thenReturn(
      const AuthLoading(message: 'Verifying credentials...'),
    );

    await tester.pumpWidget(buildTestWidget());

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
