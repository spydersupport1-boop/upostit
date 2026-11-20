/// In-Memory Token Manager for short-lived JWT access tokens.
///
/// Security Invariant: Access tokens reside strictly in volatile memory and
/// are NEVER written to disk, SQLite, or SharedPreferences.
abstract class TokenManager {
  String? get accessToken;
  void setAccessToken(String? token);
  void clear();
  bool get hasAccessToken => accessToken != null && accessToken!.isNotEmpty;
}

class InMemoryTokenManager implements TokenManager {
  String? _accessToken;

  @override
  String? get accessToken => _accessToken;

  @override
  void setAccessToken(String? token) {
    _accessToken = token;
  }

  @override
  void clear() {
    _accessToken = null;
  }

  @override
  bool get hasAccessToken => _accessToken != null && _accessToken!.isNotEmpty;
}
