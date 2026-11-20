import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/errors/failure.dart';
import 'package:mobile/core/storage/secure_storage_service.dart';
import 'package:mobile/core/storage/token_manager.dart';
import 'package:mobile/features/auth/data/datasources/auth_remote_data_source.dart';
import 'package:mobile/features/auth/data/models/auth_tokens_model.dart';
import 'package:mobile/features/auth/data/models/user_profile_model.dart';
import 'package:mobile/features/auth/data/repositories/auth_repository_impl.dart';
import 'package:mocktail/mocktail.dart';

class MockAuthRemoteDataSource extends Mock implements AuthRemoteDataSource {}

class MockTokenManager extends Mock implements TokenManager {}

class MockSecureStorageService extends Mock implements SecureStorageService {}

void main() {
  late MockAuthRemoteDataSource mockRemoteDataSource;
  late MockTokenManager mockTokenManager;
  late MockSecureStorageService mockSecureStorage;
  late AuthRepositoryImpl repository;

  const testTokens = AuthTokensModel(
    accessToken: 'test-access-token',
    refreshToken: 'test-refresh-token',
    tokenType: 'bearer',
    expiresIn: 900,
  );

  const testUserProfile = UserProfileModel(
    user: UserModel(
      id: 'user-uuid-1',
      tenantId: 'tenant-uuid-1',
      fullName: 'Alice Smith',
      email: 'alice@acme.com',
      role: 'employee',
      status: 'active',
    ),
    tenant: TenantModel(
      id: 'tenant-uuid-1',
      slug: 'acme-corp',
      name: 'Acme Corp',
      companyEmail: 'contact@acme.com',
      countryCode: 'US',
      timezone: 'UTC',
    ),
  );

  setUp(() {
    mockRemoteDataSource = MockAuthRemoteDataSource();
    mockTokenManager = MockTokenManager();
    mockSecureStorage = MockSecureStorageService();

    when(() => mockSecureStorage.saveRefreshToken(any()))
        .thenAnswer((_) async {});
    when(() => mockSecureStorage.saveTenantSlug(any()))
        .thenAnswer((_) async {});
    when(() => mockSecureStorage.saveEmail(any())).thenAnswer((_) async {});
    when(() => mockSecureStorage.deleteRefreshToken()).thenAnswer((_) async {});
    when(() => mockTokenManager.setAccessToken(any())).thenReturn(null);
    when(() => mockTokenManager.clear()).thenReturn(null);

    repository = AuthRepositoryImpl(
      remoteDataSource: mockRemoteDataSource,
      tokenManager: mockTokenManager,
      secureStorage: mockSecureStorage,
    );
  });

  group('AuthRepositoryImpl.login', () {
    test('successfully authenticates, stores tokens, and returns AuthTokens',
        () async {
      when(() => mockRemoteDataSource.login(
            email: 'alice@acme.com',
            password: 'password123',
            tenantSlug: 'acme-corp',
          )).thenAnswer((_) async => testTokens);

      final result = await repository.login(
        email: 'alice@acme.com',
        password: 'password123',
        tenantSlug: 'acme-corp',
      );

      expect(result.isSuccess, isTrue);
      expect(result.data, testTokens);
      verify(() => mockTokenManager.setAccessToken('test-access-token'))
          .called(1);
      verify(() => mockSecureStorage.saveRefreshToken('test-refresh-token'))
          .called(1);
      verify(() => mockSecureStorage.saveTenantSlug('acme-corp')).called(1);
      verify(() => mockSecureStorage.saveEmail('alice@acme.com')).called(1);
    });

    test('returns AuthFailure when invalid credentials are provided', () async {
      when(() => mockRemoteDataSource.login(
                email: 'alice@acme.com',
                password: 'wrong',
                tenantSlug: 'acme-corp',
              ))
          .thenThrow(const AuthException(
              'Invalid credentials or inactive account',
              statusCode: 401));

      final result = await repository.login(
        email: 'alice@acme.com',
        password: 'wrong',
        tenantSlug: 'acme-corp',
      );

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<AuthFailure>());
      expect(result.failure?.statusCode, 401);
      verifyNever(() => mockTokenManager.setAccessToken(any()));
    });

    test('returns NetworkFailure on network connectivity error', () async {
      when(() => mockRemoteDataSource.login(
            email: 'alice@acme.com',
            password: 'password123',
            tenantSlug: 'acme-corp',
          )).thenThrow(const NetworkException());

      final result = await repository.login(
        email: 'alice@acme.com',
        password: 'password123',
        tenantSlug: 'acme-corp',
      );

      expect(result.isSuccess, isFalse);
      expect(result.failure, isA<NetworkFailure>());
    });
  });

  group('AuthRepositoryImpl.refreshToken', () {
    test('rotates tokens and updates volatile memory and secure storage',
        () async {
      when(() =>
              mockRemoteDataSource.refresh(refreshToken: 'old-refresh-token'))
          .thenAnswer((_) async => testTokens);

      final result = await repository.refreshToken('old-refresh-token');

      expect(result.isSuccess, isTrue);
      expect(result.data, testTokens);
      verify(() => mockTokenManager.setAccessToken('test-access-token'))
          .called(1);
      verify(() => mockSecureStorage.saveRefreshToken('test-refresh-token'))
          .called(1);
    });
  });

  group('AuthRepositoryImpl.getMe', () {
    test('returns UserProfile on success', () async {
      when(() => mockRemoteDataSource.getMe())
          .thenAnswer((_) async => testUserProfile);

      final result = await repository.getMe();

      expect(result.isSuccess, isTrue);
      expect(result.data, testUserProfile);
    });
  });

  group('AuthRepositoryImpl.logout', () {
    test('calls remote logout and clears tokens locally', () async {
      when(() =>
              mockRemoteDataSource.logout(refreshToken: 'test-refresh-token'))
          .thenAnswer((_) async {});

      final result =
          await repository.logout(refreshToken: 'test-refresh-token');

      expect(result.isSuccess, isTrue);
      verify(() => mockTokenManager.clear()).called(1);
      verify(() => mockSecureStorage.deleteRefreshToken()).called(1);
    });
  });
}
