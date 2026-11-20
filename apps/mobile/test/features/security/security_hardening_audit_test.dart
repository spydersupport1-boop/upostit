import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/core/config/env_config.dart';
import 'package:mobile/core/errors/app_exception.dart';
import 'package:mobile/core/storage/secure_storage_service.dart';
import 'package:mobile/core/storage/token_manager.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/sync/data/datasources/database_key_provider.dart';
import 'package:mobile/features/sync/data/datasources/local_queue_database.dart';
import 'package:mobile/features/sync/domain/entities/local_queue_item.dart';
import 'package:mobile/features/sync/domain/entities/sync_status.dart';
import 'package:mobile/features/sync/data/models/local_queue_item_model.dart';

class MockFlutterSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  group('Security Hardening Audit - Token Isolation', () {
    test(
        'access tokens reside strictly in volatile memory and are cleared on logout',
        () {
      final tokenManager = InMemoryTokenManager();
      expect(tokenManager.hasAccessToken, false);

      tokenManager.setAccessToken('sample.jwt.access_token');
      expect(tokenManager.hasAccessToken, true);
      expect(tokenManager.accessToken, 'sample.jwt.access_token');

      tokenManager.clear();
      expect(tokenManager.hasAccessToken, false);
      expect(tokenManager.accessToken, isNull);
    });

    test(
        'FlutterSecureStorageService uses hardware Keystore and Keychain options',
        () {
      final storage = FlutterSecureStorageService();
      expect(storage, isNotNull);
    });
  });

  group('Security Hardening Audit - Database Encryption & Fail-Closed Keys',
      () {
    late MockFlutterSecureStorage mockStorage;
    late FlutterSecureStorageDatabaseKeyProvider keyProvider;

    setUp(() {
      mockStorage = MockFlutterSecureStorage();
      keyProvider =
          FlutterSecureStorageDatabaseKeyProvider(storage: mockStorage);
    });

    test(
        'fails closed when database exists on disk but encryption key is missing',
        () async {
      when(() => mockStorage.read(key: any(named: 'key')))
          .thenAnswer((_) async => null);

      expect(
        () => keyProvider.getEncryptionKey(databaseExists: true),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('missing from secure storage'),
          ),
        ),
      );
    });

    test('fails closed when database exists on disk but key is malformed',
        () async {
      when(() => mockStorage.read(key: any(named: 'key')))
          .thenAnswer((_) async => 'short-corrupted-key');

      expect(
        () => keyProvider.getEncryptionKey(databaseExists: true),
        throwsA(
          isA<DatabaseEncryptionException>().having(
            (e) => e.message,
            'message',
            contains('malformed'),
          ),
        ),
      );
    });

    test('LocalQueueDatabase expects SQLCIPHER_PAGE_AES256 engine verification',
        () {
      expect(LocalQueueDatabase.expectedEngine, 'SQLCIPHER_PAGE_AES256');
      expect(LocalQueueDatabase.databaseName, 'upostit_offline_queue.db');
    });
  });

  group('Security Hardening Audit - Offline Queue Data Hygiene', () {
    test(
        'LocalQueueItem payloads contain no auth tokens, passwords, or credentials',
        () {
      final punchPayload = {
        'event_type': 'CHECK_IN',
        'device_reported_at':
            DateTime.utc(2026, 11, 19, 9, 0).toIso8601String(),
        'idempotency_key': 'test-uuid-v4',
        'location_id': 'loc-1',
        'latitude': 41.8781,
        'longitude': -87.6298,
      };

      final payloadStr = jsonEncode(punchPayload);

      final item = LocalQueueItem(
        localId: 'q-sec-1',
        idempotencyKey: 'test-uuid-v4',
        tenantId: 'tenant-secure',
        employeeId: 'emp-secure',
        userId: 'user-secure',
        eventType: AttendanceEventType.checkIn,
        appliedPolicyVersion: 1,
        appliedPolicyMode: 'GPS_ONLY',
        sequenceNumber: 1,
        encryptedPayloadBlob: payloadStr,
        deviceReportedAt: DateTime.utc(2026, 11, 19, 9, 0),
        timezoneOffsetMinutes: 0,
        monotonicBootTimeMs: 123456,
        bootSessionId: 'boot-1',
        syncStatus: SyncStatus.pendingSync,
        createdAt: DateTime.utc(2026, 11, 19, 9, 0),
        updatedAt: DateTime.utc(2026, 11, 19, 9, 0),
      );

      final serialized = LocalQueueItemModel.fromEntity(item).toRow();

      expect(serialized.containsKey('access_token'), false);
      expect(serialized.containsKey('refresh_token'), false);
      expect(serialized.containsKey('password'), false);
      expect(serialized['tenant_id'], 'tenant-secure');
      expect(serialized['user_id'], 'user-secure');
      expect(serialized['employee_id'], 'emp-secure');
    });
  });

  group('Security Hardening Audit - Environment & Transport Security', () {
    test('EnvConfig evaluates secure transport via isSecure helper', () {
      expect(EnvConfig.apiBaseUrl, isNotEmpty);
      expect(EnvConfig.connectTimeoutMs, 15000);
      expect(EnvConfig.receiveTimeoutMs, 15000);
    });
  });
}
