import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/storage/token_manager.dart';

void main() {
  group('InMemoryTokenManager', () {
    late TokenManager tokenManager;

    setUp(() {
      tokenManager = InMemoryTokenManager();
    });

    test('initial state has no access token', () {
      expect(tokenManager.accessToken, isNull);
      expect(tokenManager.hasAccessToken, isFalse);
    });

    test('setAccessToken updates access token in memory', () {
      tokenManager.setAccessToken('sample-jwt-access-token');

      expect(tokenManager.accessToken, 'sample-jwt-access-token');
      expect(tokenManager.hasAccessToken, isTrue);
    });

    test('clear removes access token from memory', () {
      tokenManager.setAccessToken('sample-jwt-access-token');
      expect(tokenManager.hasAccessToken, isTrue);

      tokenManager.clear();

      expect(tokenManager.accessToken, isNull);
      expect(tokenManager.hasAccessToken, isFalse);
    });

    test('replaces old token on subsequent setAccessToken calls', () {
      tokenManager.setAccessToken('token-1');
      expect(tokenManager.accessToken, 'token-1');

      tokenManager.setAccessToken('token-2');
      expect(tokenManager.accessToken, 'token-2');
    });
  });
}
