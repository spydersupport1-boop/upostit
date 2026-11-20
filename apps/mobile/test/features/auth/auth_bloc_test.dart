import 'package:bloc_test/bloc_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/errors/result.dart';
import 'package:mobile/core/storage/secure_storage_service.dart';
import 'package:mobile/features/auth/domain/entities/auth_tokens.dart';
import 'package:mobile/features/auth/domain/entities/user_profile.dart';
import 'package:mobile/features/auth/domain/repositories/auth_repository.dart';
import 'package:mobile/features/auth/domain/usecases/login_usecase.dart';
import 'package:mobile/features/auth/domain/usecases/logout_usecase.dart';
import 'package:mobile/features/auth/domain/usecases/restore_session_usecase.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_bloc.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_event.dart';
import 'package:mobile/features/auth/presentation/bloc/auth_state.dart';
import 'package:mocktail/mocktail.dart';

class MockLoginUseCase extends Mock implements LoginUseCase {}

class MockRestoreSessionUseCase extends Mock implements RestoreSessionUseCase {}

class MockLogoutUseCase extends Mock implements LogoutUseCase {}

class MockAuthRepository extends Mock implements AuthRepository {}

class MockSecureStorageService extends Mock implements SecureStorageService {}

void main() {
  late MockLoginUseCase mockLoginUseCase;
  late MockRestoreSessionUseCase mockRestoreSessionUseCase;
  late MockLogoutUseCase mockLogoutUseCase;
  late MockAuthRepository mockAuthRepository;
  late MockSecureStorageService mockSecureStorage;
  late AuthBloc authBloc;

  const testTokens = AuthTokens(
    accessToken: 'access-123',
    refreshToken: 'refresh-456',
    tokenType: 'bearer',
    expiresIn: 900,
  );

  const testUserProfile = UserProfile(
    user: UserEntity(
      id: 'user-uuid-1',
      tenantId: 'tenant-uuid-1',
      fullName: 'Jane Doe',
      email: 'jane@acme.com',
      role: 'employee',
      status: 'active',
    ),
    tenant: TenantEntity(
      id: 'tenant-uuid-1',
      slug: 'acme-corp',
      name: 'Acme Corp',
      companyEmail: 'contact@acme.com',
      countryCode: 'US',
      timezone: 'America/New_York',
    ),
  );

  setUp(() {
    mockLoginUseCase = MockLoginUseCase();
    mockRestoreSessionUseCase = MockRestoreSessionUseCase();
    mockLogoutUseCase = MockLogoutUseCase();
    mockAuthRepository = MockAuthRepository();
    mockSecureStorage = MockSecureStorageService();

    when(() => mockSecureStorage.getSavedTenantSlug())
        .thenAnswer((_) async => 'acme-corp');
    when(() => mockSecureStorage.getSavedEmail())
        .thenAnswer((_) async => 'jane@acme.com');

    authBloc = AuthBloc(
      loginUseCase: mockLoginUseCase,
      restoreSessionUseCase: mockRestoreSessionUseCase,
      logoutUseCase: mockLogoutUseCase,
      authRepository: mockAuthRepository,
      secureStorage: mockSecureStorage,
    );
  });

  tearDown(() {
    authBloc.close();
  });

  test('initial state is AuthInitial', () {
    expect(authBloc.state, const AuthInitial());
  });

  group('AuthCheckRequested (Session Restoration)', () {
    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, Authenticated] when session restoration succeeds',
      build: () {
        when(() => mockRestoreSessionUseCase())
            .thenAnswer((_) async => const Result.success(testTokens));
        when(() => mockAuthRepository.getMe())
            .thenAnswer((_) async => const Result.success(testUserProfile));
        return authBloc;
      },
      act: (bloc) => bloc.add(const AuthCheckRequested()),
      expect: () => [
        const AuthLoading(message: 'Restoring secure session...'),
        const Authenticated(userProfile: testUserProfile),
      ],
    );

    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, AuthRestoreError] when network connection is offline',
      build: () {
        when(() => mockRestoreSessionUseCase()).thenAnswer((_) async =>
            const Result.failure(NetworkFailure('Network unavailable')));
        return authBloc;
      },
      act: (bloc) => bloc.add(const AuthCheckRequested()),
      expect: () => [
        const AuthLoading(message: 'Restoring secure session...'),
        const AuthRestoreError(
            message: 'Network unavailable', isNetworkError: true),
      ],
    );

    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, Unauthenticated] when refresh token is invalid or expired',
      build: () {
        when(() => mockRestoreSessionUseCase()).thenAnswer(
          (_) async => const Result.failure(
            AuthFailure('Invalid refresh token', isSessionExpired: true),
          ),
        );
        return authBloc;
      },
      act: (bloc) => bloc.add(const AuthCheckRequested()),
      expect: () => [
        const AuthLoading(message: 'Restoring secure session...'),
        const Unauthenticated(
          infoMessage: 'Your session has expired. Please sign in.',
          savedTenantSlug: 'acme-corp',
          savedEmail: 'jane@acme.com',
        ),
      ],
    );
  });

  group('LoginSubmitted', () {
    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, Authenticated] on valid credentials',
      build: () {
        when(() => mockLoginUseCase(
              email: 'jane@acme.com',
              password: 'password123',
              tenantSlug: 'acme-corp',
            )).thenAnswer((_) async => const Result.success(testTokens));
        when(() => mockAuthRepository.getMe())
            .thenAnswer((_) async => const Result.success(testUserProfile));
        return authBloc;
      },
      act: (bloc) => bloc.add(const LoginSubmitted(
        email: 'jane@acme.com',
        password: 'password123',
        tenantSlug: 'acme-corp',
      )),
      expect: () => [
        const AuthLoading(message: 'Verifying credentials...'),
        const Authenticated(userProfile: testUserProfile),
      ],
    );

    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, Unauthenticated] on invalid credentials',
      build: () {
        when(() => mockLoginUseCase(
              email: 'jane@acme.com',
              password: 'wrongpassword',
              tenantSlug: 'acme-corp',
            )).thenAnswer(
          (_) async => const Result.failure(
            AuthFailure('Invalid credentials or inactive account',
                statusCode: 401),
          ),
        );
        return authBloc;
      },
      act: (bloc) => bloc.add(const LoginSubmitted(
        email: 'jane@acme.com',
        password: 'wrongpassword',
        tenantSlug: 'acme-corp',
      )),
      expect: () => [
        const AuthLoading(message: 'Verifying credentials...'),
        const Unauthenticated(
          errorMessage: 'Invalid credentials or inactive account',
          savedTenantSlug: 'acme-corp',
          savedEmail: 'jane@acme.com',
        ),
      ],
    );
  });

  group('LogoutRequested', () {
    blocTest<AuthBloc, AuthState>(
      'emits [AuthLoading, Unauthenticated] on successful logout',
      build: () {
        when(() => mockLogoutUseCase())
            .thenAnswer((_) async => const Result.success(null));
        return authBloc;
      },
      act: (bloc) => bloc.add(const LogoutRequested()),
      expect: () => [
        const AuthLoading(message: 'Signing out...'),
        const Unauthenticated(
          infoMessage: 'You have been signed out successfully.',
          savedTenantSlug: 'acme-corp',
          savedEmail: 'jane@acme.com',
        ),
      ],
    );
  });

  group('SessionExpiredDetected', () {
    blocTest<AuthBloc, AuthState>(
      'emits [Unauthenticated] with session expired notice',
      build: () => authBloc,
      act: (bloc) => bloc.add(const SessionExpiredDetected(
          'Session expired. Please log in again.')),
      expect: () => [
        const Unauthenticated(
          errorMessage: 'Session expired. Please log in again.',
          savedTenantSlug: 'acme-corp',
          savedEmail: 'jane@acme.com',
        ),
      ],
    );
  });
}
