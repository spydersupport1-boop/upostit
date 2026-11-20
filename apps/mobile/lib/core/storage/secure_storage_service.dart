import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../errors/app_exception.dart';

/// Contract for hardware-backed secure storage.
abstract class SecureStorageService {
  Future<String?> getRefreshToken();
  Future<void> saveRefreshToken(String token);
  Future<void> deleteRefreshToken();

  Future<String?> getSavedTenantSlug();
  Future<void> saveTenantSlug(String slug);
  Future<void> deleteSavedTenantSlug();

  Future<String?> getSavedEmail();
  Future<void> saveEmail(String email);

  Future<void> clearAll();
}

/// Implementation using [FlutterSecureStorage] with iOS Keychain & Android Keystore.
class FlutterSecureStorageService implements SecureStorageService {
  final FlutterSecureStorage _storage;

  static const String _keyRefreshToken = 'upostit_auth_refresh_token';
  static const String _keyTenantSlug = 'upostit_tenant_slug';
  static const String _keyUserEmail = 'upostit_user_email';

  FlutterSecureStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(
                encryptedSharedPreferences: true,
              ),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  @override
  Future<String?> getRefreshToken() async {
    try {
      return await _storage.read(key: _keyRefreshToken);
    } catch (e) {
      throw const StorageException('Failed to read secure refresh token');
    }
  }

  @override
  Future<void> saveRefreshToken(String token) async {
    try {
      await _storage.write(key: _keyRefreshToken, value: token);
    } catch (e) {
      throw const StorageException('Failed to persist secure refresh token');
    }
  }

  @override
  Future<void> deleteRefreshToken() async {
    try {
      await _storage.delete(key: _keyRefreshToken);
    } catch (e) {
      throw const StorageException('Failed to delete secure refresh token');
    }
  }

  @override
  Future<String?> getSavedTenantSlug() async {
    try {
      return await _storage.read(key: _keyTenantSlug);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> saveTenantSlug(String slug) async {
    try {
      await _storage.write(key: _keyTenantSlug, value: slug);
    } catch (_) {
      // Non-critical metadata write failure
    }
  }

  @override
  Future<void> deleteSavedTenantSlug() async {
    try {
      await _storage.delete(key: _keyTenantSlug);
    } catch (_) {}
  }

  @override
  Future<String?> getSavedEmail() async {
    try {
      return await _storage.read(key: _keyUserEmail);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> saveEmail(String email) async {
    try {
      await _storage.write(key: _keyUserEmail, value: email);
    } catch (_) {}
  }

  @override
  Future<void> clearAll() async {
    try {
      await _storage.delete(key: _keyRefreshToken);
      // We deliberately preserve tenant slug and email for login screen UX convenience
    } catch (e) {
      throw const StorageException('Failed to clear secure credentials');
    }
  }
}
