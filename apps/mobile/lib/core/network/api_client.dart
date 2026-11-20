import 'package:dio/dio.dart';
import '../config/env_config.dart';
import '../errors/app_exception.dart';
import '../storage/secure_storage_service.dart';
import '../storage/token_manager.dart';
import 'auth_interceptor.dart';

/// Centralized HTTP client wrapper providing Dio configuration and error mapping.
class ApiClient {
  late final Dio dio;
  late final Dio rawDio;
  final TokenManager tokenManager;
  final SecureStorageService secureStorage;
  final void Function()? onSessionExpired;

  ApiClient({
    required this.tokenManager,
    required this.secureStorage,
    this.onSessionExpired,
    Dio? customDio,
    Dio? customRawDio,
  }) {
    final baseOptions = BaseOptions(
      baseUrl: EnvConfig.apiBaseUrl,
      connectTimeout: const Duration(milliseconds: EnvConfig.connectTimeoutMs),
      receiveTimeout: const Duration(milliseconds: EnvConfig.receiveTimeoutMs),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    );

    rawDio = customRawDio ?? Dio(baseOptions);
    dio = customDio ?? Dio(baseOptions);

    dio.interceptors.add(
      AuthInterceptor(
        tokenManager: tokenManager,
        secureStorage: secureStorage,
        rawDio: rawDio,
        onSessionExpired: onSessionExpired,
      ),
    );
  }

  /// Sends a GET request and maps responses or exceptions.
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await dio.get<T>(
        path,
        queryParameters: queryParameters,
        options: options,
      );
    } on DioException catch (e) {
      throw _handleDioError(e);
    } catch (e) {
      throw ServerException(e.toString());
    }
  }

  /// Sends a POST request and maps responses or exceptions.
  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await dio.post<T>(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
    } on DioException catch (e) {
      throw _handleDioError(e);
    } catch (e) {
      throw ServerException(e.toString());
    }
  }

  /// Translates [DioException] into strongly typed [AppException].
  AppException _handleDioError(DioException error) {
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout ||
        error.type == DioExceptionType.connectionError) {
      return const NetworkException();
    }

    final response = error.response;
    if (response != null) {
      final statusCode = response.statusCode;
      String message = 'An unexpected server error occurred';

      if (response.data is Map) {
        final data = response.data as Map<String, dynamic>;
        if (data.containsKey('detail')) {
          final detail = data['detail'];
          if (detail is String) {
            message = detail;
          } else if (detail is List) {
            // Pydantic validation error format
            message = detail
                .map((e) => e is Map && e.containsKey('msg')
                    ? e['msg'].toString()
                    : e.toString())
                .join('; ');
          }
        } else if (data.containsKey('message')) {
          message = data['message'].toString();
        }
      } else if (response.data is String &&
          (response.data as String).isNotEmpty) {
        message = response.data as String;
      }

      if (statusCode == 401) {
        final isReuse = message.toLowerCase().contains('reuse');
        return AuthException(
          message,
          statusCode: 401,
          details: response.data,
          isSessionExpired: true,
          isReuseDetected: isReuse,
        );
      }

      return ServerException(
        message,
        statusCode: statusCode,
        details: response.data,
      );
    }

    return ServerException(error.message ?? 'Unknown connection error');
  }
}
