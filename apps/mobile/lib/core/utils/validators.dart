/// Input validation helpers for mobile forms.
class Validators {
  static final RegExp _emailRegExp = RegExp(
    r'^[a-zA-Z0-9.!#$%&’*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$',
  );

  static final RegExp _slugRegExp = RegExp(r'^[a-z0-9-]+$');

  /// Validates work email formatting.
  static String? validateEmail(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Email address is required';
    }
    final trimmed = value.trim();
    if (!_emailRegExp.hasMatch(trimmed)) {
      return 'Please enter a valid work email address';
    }
    return null;
  }

  /// Validates password field presence.
  static String? validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters';
    }
    return null;
  }

  /// Validates company workspace code / tenant slug.
  static String? validateTenantSlug(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Company code is required';
    }
    final trimmed = value.trim().toLowerCase();
    if (trimmed.length < 2) {
      return 'Company code must be at least 2 characters';
    }
    if (!_slugRegExp.hasMatch(trimmed)) {
      return 'Company code can only contain lowercase letters, numbers, and hyphens';
    }
    return null;
  }
}
