import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/network/api_client.dart';
import 'package:mobile/core/network/api_endpoints.dart';
import 'package:mobile/features/notifications/data/datasources/notification_remote_data_source.dart';
import 'package:mobile/features/notifications/data/models/device_token_register_request_model.dart';

class MockApiClient extends Mock implements ApiClient {}

void main() {
  late MockApiClient mockApiClient;
  late NotificationRemoteDataSourceImpl dataSource;

  setUp(() {
    mockApiClient = MockApiClient();
    dataSource = NotificationRemoteDataSourceImpl(mockApiClient);
  });

  group('NotificationRemoteDataSource - registerDeviceToken', () {
    const request = DeviceTokenRegisterRequestModel(
      platform: 'ANDROID',
      token: 'sample_raw_fcm_token_1234567890',
      deviceModel: 'Pixel 8',
      osVersion: 'Android 14',
      appVersion: '1.0.0',
    );

    final mockResponseJson = {
      'id': 'd018788f-7c15-4fa2-bfda-9080b03763eb',
      'tenant_id': '6fa459ea-ee8a-4ca4-894e-db77e160355e',
      'user_id': '8ba55555-4444-3333-2222-111100000000',
      'employee_id': '11111111-2222-3333-4444-555555555555',
      'platform': 'ANDROID',
      'token_preview': 'device_token_hash:a3b5c7...',
      'device_model': 'Pixel 8',
      'os_version': 'Android 14',
      'app_version': '1.0.0',
      'status': 'ACTIVE',
      'last_seen_at': '2026-11-22T02:00:00Z',
      'created_at': '2026-11-22T02:00:00Z',
    };

    test('successfully registers device token and parses response', () async {
      when(() => mockApiClient.post(
            ApiEndpoints.notificationDevices,
            data: any(named: 'data'),
          )).thenAnswer((_) async => Response(
            requestOptions:
                RequestOptions(path: ApiEndpoints.notificationDevices),
            data: mockResponseJson,
            statusCode: 200,
          ));

      final result = await dataSource.registerDeviceToken(request);

      expect(result.id, 'd018788f-7c15-4fa2-bfda-9080b03763eb');
      expect(result.platform, 'ANDROID');
      expect(result.tokenPreview, 'device_token_hash:a3b5c7...');
      expect(result.status, 'ACTIVE');

      verify(() => mockApiClient.post(
            ApiEndpoints.notificationDevices,
            data: {
              'platform': 'ANDROID',
              'token': 'sample_raw_fcm_token_1234567890',
              'device_model': 'Pixel 8',
              'os_version': 'Android 14',
              'app_version': '1.0.0',
            },
          )).called(1);
    });

    test('throws ServerException on malformed response', () async {
      when(() => mockApiClient.post(
            ApiEndpoints.notificationDevices,
            data: any(named: 'data'),
          )).thenAnswer((_) async => Response(
            requestOptions:
                RequestOptions(path: ApiEndpoints.notificationDevices),
            data: 'malformed_string',
            statusCode: 200,
          ));

      expect(
        () => dataSource.registerDeviceToken(request),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('NotificationRemoteDataSource - listActiveDeviceTokens', () {
    test('returns active device token registrations list', () async {
      final mockListJson = [
        {
          'id': 'd-1',
          'tenant_id': 't-1',
          'user_id': 'u-1',
          'platform': 'ANDROID',
          'token_preview': 'device_token_hash:111...',
          'status': 'ACTIVE',
          'last_seen_at': '2026-11-22T02:00:00Z',
          'created_at': '2026-11-22T02:00:00Z',
        },
      ];

      when(() => mockApiClient.get(ApiEndpoints.notificationDevices))
          .thenAnswer((_) async => Response(
                requestOptions:
                    RequestOptions(path: ApiEndpoints.notificationDevices),
                data: mockListJson,
                statusCode: 200,
              ));

      final result = await dataSource.listActiveDeviceTokens();

      expect(result.length, 1);
      expect(result.first.id, 'd-1');
      expect(result.first.tokenPreview, 'device_token_hash:111...');
    });
  });

  group('NotificationRemoteDataSource - revocation endpoints', () {
    test('revokeDeviceToken posts raw token payload', () async {
      when(() => mockApiClient.post(
            ApiEndpoints.notificationDevicesRevoke,
            data: {'token': 'raw_token_xyz'},
          )).thenAnswer((_) async => Response(
            requestOptions:
                RequestOptions(path: ApiEndpoints.notificationDevicesRevoke),
            data: {'status': 'revoked'},
            statusCode: 200,
          ));

      await dataSource.revokeDeviceToken('raw_token_xyz');

      verify(() => mockApiClient.post(
            ApiEndpoints.notificationDevicesRevoke,
            data: {'token': 'raw_token_xyz'},
          )).called(1);
    });

    test('revokeDeviceTokenByHash issues DELETE to hash route', () async {
      when(() => mockApiClient.delete(
            ApiEndpoints.notificationDeviceByHash('hash_abc_123'),
          )).thenAnswer((_) async => Response(
            requestOptions: RequestOptions(
                path: ApiEndpoints.notificationDeviceByHash('hash_abc_123')),
            data: {'status': 'revoked'},
            statusCode: 200,
          ));

      await dataSource.revokeDeviceTokenByHash('hash_abc_123');

      verify(() => mockApiClient.delete(
            ApiEndpoints.notificationDeviceByHash('hash_abc_123'),
          )).called(1);
    });
  });

  group('NotificationRemoteDataSource - API Gap translation', () {
    test('translates 404 on inbox endpoint into ApiGapException', () async {
      when(() => mockApiClient.get(
            ApiEndpoints.notificationInbox,
            queryParameters: any(named: 'queryParameters'),
          )).thenThrow(const ServerException('Not found', statusCode: 404));

      expect(
        () => dataSource.getNotificationInbox(),
        throwsA(isA<ApiGapException>()),
      );
    });

    test('translates 404 on markNotificationAsRead into ApiGapException',
        () async {
      when(() => mockApiClient.post(
            '${ApiEndpoints.notificationInbox}/notif-1/read',
          )).thenThrow(const ServerException('Not found', statusCode: 404));

      expect(
        () => dataSource.markNotificationAsRead('notif-1'),
        throwsA(isA<ApiGapException>()),
      );
    });
  });
}
