import 'dart:async';
import 'package:dio/dio.dart';
import '../storage/secure_storage_service.dart';
import '../storage/token_manager.dart';
import 'api_endpoints.dart';

/// Concurrency-safe Dio interceptor for automatic Bearer token injection,
/// seamless refresh-token rotation, token reuse detection, and session cleanup.
class AuthInterceptor extends Interceptor {
  final TokenManager _tokenManager;
  final SecureStorageService _secureStorage;
  final Dio _rawDio;
  final void Function()? _onSessionExpired;

  /// Active mutex lock for in-flight token refresh requests.
  Completer<String?>? _refreshCompleter;

  AuthInterceptor({
    required TokenManager tokenManager,
    required SecureStorageService secureStorage,
    required Dio rawDio,
    void Function()? onSessionExpired,
  })  : _tokenManager = tokenManager,
        _secureStorage = secureStorage,
        _rawDio = rawDio,
        _onSessionExpired = onSessionExpired;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    // Skip attaching authorization headers to public or refresh routes
    final isPublicRoute = options.path.contains(ApiEndpoints.login) ||
        options.path.contains(ApiEndpoints.refresh);

    if (!isPublicRoute && _tokenManager.hasAccessToken) {
      options.headers['Authorization'] = 'Bearer ${_tokenManager.accessToken}';
    }

    handler.next(options);
  }

  @override
  Future<void> onError(
      DioException err, ErrorInterceptorHandler handler) async {
    final statusCode = err.response?.statusCode;
    final is401 = statusCode == 401;
    final isRetry = err.requestOptions.extra['isRetry'] == true;
    final isLogin = err.requestOptions.path.contains(ApiEndpoints.login);
    final isRefresh = err.requestOptions.path.contains(ApiEndpoints.refresh);

    // If not a 401, or already retried, or login failure: pass through error
    if (!is401 || isRetry || isLogin) {
      return handler.next(err);
    }

    // If the refresh endpoint itself returned 401, session is invalid/revoked
    if (isRefresh) {
      _tokenManager.clear();
      await _secureStorage.deleteRefreshToken();
      _onSessionExpired?.call();
      return handler.next(err);
    }

    // If another refresh operation is already in flight, wait for its completion
    if (_refreshCompleter != null) {
      try {
        final newAccessToken = await _refreshCompleter!.future;
        if (newAccessToken != null && newAccessToken.isNotEmpty) {
          final retryOptions = err.requestOptions;
          retryOptions.headers['Authorization'] = 'Bearer $newAccessToken';
          retryOptions.extra['isRetry'] = true;

          final response = await _rawDio.fetch(retryOptions);
          return handler.resolve(response);
        } else {
          return handler.next(err);
        }
      } catch (retryError) {
        if (retryError is DioException) {
          return handler.next(retryError);
        }
        return handler.next(err);
      }
    }

    // First request encountering 401: acquire refresh mutex
    final completer = Completer<String?>();
    _refreshCompleter = completer;

    try {
      final storedRefreshToken = await _secureStorage.getRefreshToken();
      if (storedRefreshToken == null || storedRefreshToken.isEmpty) {
        completer.complete(null);
        _refreshCompleter = null;
        _tokenManager.clear();
        _onSessionExpired?.call();
        return handler.next(err);
      }

      // Execute refresh using unintercepted rawDio
      final response = await _rawDio.post(
        ApiEndpoints.refresh,
        data: {'refresh_token': storedRefreshToken},
        options: Options(
          headers: {'Content-Type': 'application/json'},
          extra: {'noAuth': true},
        ),
      );

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        final newAccessToken = data['access_token'] as String;
        final newRefreshToken = data['refresh_token'] as String;

        _tokenManager.setAccessToken(newAccessToken);
        await _secureStorage.saveRefreshToken(newRefreshToken);

        completer.complete(newAccessToken);
        _refreshCompleter = null;

        // Replay original request with updated access token
        final retryOptions = err.requestOptions;
        retryOptions.headers['Authorization'] = 'Bearer $newAccessToken';
        retryOptions.extra['isRetry'] = true;

        final replayResponse = await _rawDio.fetch(retryOptions);
        return handler.resolve(replayResponse);
      } else {
        completer.complete(null);
        _refreshCompleter = null;
        _tokenManager.clear();
        await _secureStorage.deleteRefreshToken();
        _onSessionExpired?.call();
        return handler.next(err);
      }
    } on DioException catch (refreshErr) {
      completer.complete(null);
      _refreshCompleter = null;

      if (refreshErr.response?.statusCode == 401) {
        // Token expired, revoked, or reuse detected
        _tokenManager.clear();
        await _secureStorage.deleteRefreshToken();
        _onSessionExpired?.call();
      }
      return handler.next(err);
    } catch (_) {
      completer.complete(null);
      _refreshCompleter = null;
      return handler.next(err);
    }
  }
}
