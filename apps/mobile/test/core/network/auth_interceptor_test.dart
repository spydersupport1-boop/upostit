import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/network/api_endpoints.dart';
import 'package:mobile/core/network/auth_interceptor.dart';
import 'package:mobile/core/storage/secure_storage_service.dart';
import 'package:mobile/core/storage/token_manager.dart';
import 'package:mocktail/mocktail.dart';

class MockTokenManager extends Mock implements TokenManager {}

class MockSecureStorageService extends Mock implements SecureStorageService {}

class MockDio extends Mock implements Dio {}

class MockErrorInterceptorHandler extends Mock
    implements ErrorInterceptorHandler {}

void main() {
  late MockTokenManager mockTokenManager;
  late MockSecureStorageService mockSecureStorage;
  late MockDio mockRawDio;
  late AuthInterceptor interceptor;
  late bool sessionExpiredCalled;

  setUpAll(() {
    registerFallbackValue(RequestOptions(path: ''));
    registerFallbackValue(Options());
    registerFallbackValue(
        Response<dynamic>(requestOptions: RequestOptions(path: '')));
    registerFallbackValue(
        DioException(requestOptions: RequestOptions(path: '')));
  });

  setUp(() {
    mockTokenManager = MockTokenManager();
    mockSecureStorage = MockSecureStorageService();
    mockRawDio = MockDio();
    sessionExpiredCalled = false;

    interceptor = AuthInterceptor(
      tokenManager: mockTokenManager,
      secureStorage: mockSecureStorage,
      rawDio: mockRawDio,
      onSessionExpired: () {
        sessionExpiredCalled = true;
      },
    );
  });

  group('AuthInterceptor - Request Header Injection', () {
    test('injects Bearer token when access token is present', () {
      when(() => mockTokenManager.hasAccessToken).thenReturn(true);
      when(() => mockTokenManager.accessToken).thenReturn('test-access-token');

      final options = RequestOptions(path: '/api/v1/auth/me');
      final handler = RequestInterceptorHandler();

      interceptor.onRequest(options, handler);

      expect(options.headers['Authorization'], 'Bearer test-access-token');
    });

    test('does not inject Bearer token on public login route', () {
      when(() => mockTokenManager.hasAccessToken).thenReturn(true);
      when(() => mockTokenManager.accessToken).thenReturn('test-access-token');

      final options = RequestOptions(path: ApiEndpoints.login);
      final handler = RequestInterceptorHandler();

      interceptor.onRequest(options, handler);

      expect(options.headers.containsKey('Authorization'), isFalse);
    });

    test('does not inject Bearer token on refresh route', () {
      when(() => mockTokenManager.hasAccessToken).thenReturn(true);
      when(() => mockTokenManager.accessToken).thenReturn('test-access-token');

      final options = RequestOptions(path: ApiEndpoints.refresh);
      final handler = RequestInterceptorHandler();

      interceptor.onRequest(options, handler);

      expect(options.headers.containsKey('Authorization'), isFalse);
    });
  });

  group('AuthInterceptor - Concurrency & Refresh Mutex', () {
    test(
        'concurrent 401 responses trigger exactly ONE refresh call and replay all requests',
        () async {
      when(() => mockSecureStorage.getRefreshToken())
          .thenAnswer((_) async => 'valid-refresh-token');
      when(() => mockSecureStorage.saveRefreshToken(any()))
          .thenAnswer((_) async {});
      when(() => mockTokenManager.setAccessToken(any())).thenReturn(null);

      int refreshCallCount = 0;
      final completer = Completer<Response>();

      // Mock rawDio.post for the refresh endpoint
      when(() => mockRawDio.post(
            ApiEndpoints.refresh,
            data: any(named: 'data'),
            options: any(named: 'options'),
          )).thenAnswer((_) async {
        refreshCallCount++;
        return completer.future;
      });

      // Mock rawDio.fetch for the replay requests
      when(() => mockRawDio.fetch(any())).thenAnswer((invocation) async {
        final opts = invocation.positionalArguments.first as RequestOptions;
        return Response(
          requestOptions: opts,
          statusCode: 200,
          data: {'success': true, 'path': opts.path},
        );
      });

      // Prepare 3 distinct requests that all encounter 401
      final err1 = DioException(
        requestOptions: RequestOptions(path: '/api/v1/employees/me'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/employees/me'),
          statusCode: 401,
        ),
      );
      final err2 = DioException(
        requestOptions: RequestOptions(path: '/api/v1/workplaces/me'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/workplaces/me'),
          statusCode: 401,
        ),
      );
      final err3 = DioException(
        requestOptions: RequestOptions(path: '/api/v1/attendance/shifts'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/attendance/shifts'),
          statusCode: 401,
        ),
      );

      final handler1 = MockErrorInterceptorHandler();
      final handler2 = MockErrorInterceptorHandler();
      final handler3 = MockErrorInterceptorHandler();

      // Fire 3 simultaneous onError calls
      final future1 = interceptor.onError(err1, handler1);
      final future2 = interceptor.onError(err2, handler2);
      final future3 = interceptor.onError(err3, handler3);

      // Allow async secureStorage.getRefreshToken() to resolve and dispatch refresh
      await Future<void>.delayed(const Duration(milliseconds: 20));

      // Verify that after launching all three, only ONE refresh call was dispatched
      expect(refreshCallCount, 1);

      // Now complete the pending refresh call
      completer.complete(
        Response(
          requestOptions: RequestOptions(path: ApiEndpoints.refresh),
          statusCode: 200,
          data: {
            'access_token': 'new-rotated-access-token',
            'refresh_token': 'new-rotated-refresh-token',
            'token_type': 'bearer',
            'expires_in': 900,
          },
        ),
      );

      await Future.wait([future1, future2, future3]);

      // Exactly ONE refresh executed despite 3 parallel failures
      expect(refreshCallCount, 1);
      verify(() => mockTokenManager.setAccessToken('new-rotated-access-token'))
          .called(1);
      verify(() =>
              mockSecureStorage.saveRefreshToken('new-rotated-refresh-token'))
          .called(1);

      // All 3 original requests were retried and resolved on handlers
      verify(() => mockRawDio.fetch(any())).called(3);
      verify(() => handler1.resolve(any())).called(1);
      verify(() => handler2.resolve(any())).called(1);
      verify(() => handler3.resolve(any())).called(1);
    });

    test('does not retry if request already has isRetry flag set', () async {
      final err = DioException(
        requestOptions: RequestOptions(
          path: '/api/v1/employees/me',
          extra: {'isRetry': true},
        ),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/employees/me'),
          statusCode: 401,
        ),
      );

      final handler = MockErrorInterceptorHandler();
      await interceptor.onError(err, handler);

      // Should not call refresh and should pass through to next
      verifyNever(() => mockRawDio.post(any(),
          data: any(named: 'data'), options: any(named: 'options')));
      verify(() => handler.next(err)).called(1);
    });

    test('clears tokens and notifies session expired when refresh returns 401',
        () async {
      when(() => mockSecureStorage.deleteRefreshToken())
          .thenAnswer((_) async {});
      when(() => mockTokenManager.clear()).thenReturn(null);

      final err = DioException(
        requestOptions: RequestOptions(path: ApiEndpoints.refresh),
        response: Response(
          requestOptions: RequestOptions(path: ApiEndpoints.refresh),
          statusCode: 401,
          data: {'detail': 'Invalid refresh token'},
        ),
      );

      final handler = MockErrorInterceptorHandler();
      await interceptor.onError(err, handler);

      verify(() => mockTokenManager.clear()).called(1);
      verify(() => mockSecureStorage.deleteRefreshToken()).called(1);
      expect(sessionExpiredCalled, isTrue);
      verify(() => handler.next(err)).called(1);
    });
  });
}
