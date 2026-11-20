import 'package:flutter/material.dart';

/// Centralized color tokens for UPOSTIT mobile client.
///
/// Implements WCAG AA compliant contrast for enterprise workforce interfaces.
class AppColors {
  // Brand & Primary Colors
  static const Color primary = Color(0xFF4F46E5); // Indigo 600
  static const Color primaryDark = Color(0xFF4338CA); // Indigo 700
  static const Color primaryLight = Color(0xFFEEF2FF); // Indigo 50
  static const Color secondary = Color(0xFF0F172A); // Slate 900
  static const Color accent = Color(0xFF06B6D4); // Cyan 500

  // Surface & Background Colors (Light Theme Primary)
  static const Color background = Color(0xFFF8FAFC); // Slate 50
  static const Color surface = Color(0xFFFFFFFF); // Pure White
  static const Color card = Color(0xFFFFFFFF); // Card White
  static const Color divider = Color(0xFFE2E8F0); // Slate 200

  // Text Colors
  static const Color textPrimary = Color(0xFF0F172A); // Slate 900
  static const Color textSecondary = Color(0xFF475569); // Slate 600
  static const Color textMuted = Color(0xFF94A3B8); // Slate 400
  static const Color textInverse = Color(0xFFFFFFFF); // White

  // Border & Input Colors
  static const Color border = Color(0xFFCBD5E1); // Slate 300
  static const Color borderFocused = Color(0xFF4F46E5); // Indigo 600
  static const Color borderLight = Color(0xFFE2E8F0); // Slate 200

  // Functional Status Colors
  static const Color success = Color(0xFF059669); // Emerald 600
  static const Color successLight = Color(0xFFECFDF5); // Emerald 50
  static const Color warning = Color(0xFFD97706); // Amber 600
  static const Color warningLight = Color(0xFFFFFBEB); // Amber 50
  static const Color error = Color(0xFFE11D48); // Rose 600
  static const Color errorLight = Color(0xFFFFF1F2); // Rose 50
  static const Color info = Color(0xFF0284C7); // Sky 600
  static const Color infoLight = Color(0xFFF0F9FF); // Sky 50

  // Dark Theme Palette Support
  static const Color darkBackground = Color(0xFF0A0E17);
  static const Color darkSurface = Color(0xFF111827);
  static const Color darkCard = Color(0xFF1E293B);
  static const Color darkTextPrimary = Color(0xFFF8FAFC);
  static const Color darkTextSecondary = Color(0xFF94A3B8);
  static const Color darkBorder = Color(0xFF334155);
}
