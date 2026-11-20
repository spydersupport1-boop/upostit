import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/assigned_workplace.dart';
import '../../domain/entities/attendance_policy.dart';
import '../../domain/entities/wifi_evidence.dart';
import '../../domain/entities/wifi_verification_result.dart';

/// Card displaying connected Wi-Fi presence status and policy-driven fallback indicators.
class WifiStatusCard extends StatelessWidget {
  final AttendancePolicy? policy;
  final AssignedWorkplace? workplace;
  final WifiEvidence? lastEvidence;
  final WifiVerificationResult? lastVerificationResult;
  final bool isProbing;
  final bool isPermissionDenied;
  final String? inFlightStatusMessage;
  final VoidCallback onProbeWifi;
  final VoidCallback? onResolvePermission;

  const WifiStatusCard({
    super.key,
    required this.policy,
    required this.workplace,
    this.lastEvidence,
    this.lastVerificationResult,
    this.isProbing = false,
    this.isPermissionDenied = false,
    this.inFlightStatusMessage,
    required this.onProbeWifi,
    this.onResolvePermission,
  });

  @override
  Widget build(BuildContext context) {
    final isVerified = lastVerificationResult?.isVerified ?? false;
    final matchStatus = lastVerificationResult?.matchStatus;

    // Determine card background and border colors
    final Color cardBg;
    final Color cardBorder;
    final Color iconColor;
    final IconData statusIcon;
    final String statusTitle;
    final String statusSubtitle;

    if (isProbing || inFlightStatusMessage != null) {
      cardBg = AppColors.infoLight;
      cardBorder = AppColors.info.withValues(alpha: 0.3);
      iconColor = AppColors.info;
      statusIcon = Icons.wifi_find_rounded;
      statusTitle = inFlightStatusMessage ?? 'Checking workplace Wi-Fi...';
      statusSubtitle = 'Detecting connected network access point';
    } else if (isPermissionDenied) {
      cardBg = AppColors.warningLight;
      cardBorder = AppColors.warning.withValues(alpha: 0.3);
      iconColor = AppColors.warning;
      statusIcon = Icons.location_disabled_rounded;
      statusTitle = 'Wi-Fi permission required';
      statusSubtitle =
          'Location access is required by OS to identify connected Wi-Fi';
    } else if (isVerified) {
      cardBg = AppColors.successLight;
      cardBorder = AppColors.success.withValues(alpha: 0.3);
      iconColor = AppColors.success;
      statusIcon = Icons.wifi_password_rounded;
      statusTitle = 'Workplace Wi-Fi verified';
      final ssidText =
          lastEvidence?.ssid != null ? ' "${lastEvidence!.ssid}"' : '';
      statusSubtitle = 'Connected to authorized workplace network$ssidText';
    } else if (matchStatus == WifiMatchStatus.mismatched) {
      cardBg = AppColors.errorLight;
      cardBorder = AppColors.error.withValues(alpha: 0.3);
      iconColor = AppColors.error;
      statusIcon = Icons.wifi_off_rounded;
      statusTitle = 'Connected to an unrecognized network';
      statusSubtitle =
          'Please connect to your company-authorized Wi-Fi access point';
    } else if (lastEvidence?.signalStatus == WifiSignalStatus.unavailable) {
      cardBg = AppColors.warningLight;
      cardBorder = AppColors.warning.withValues(alpha: 0.3);
      iconColor = AppColors.warning;
      statusIcon = Icons.signal_wifi_bad_rounded;
      statusTitle = 'Wi-Fi information unavailable';
      statusSubtitle = _deriveFallbackSubtitle();
    } else if (lastEvidence?.signalStatus == WifiSignalStatus.unsupported) {
      cardBg = AppColors.surface;
      cardBorder = AppColors.border;
      iconColor = AppColors.textSecondary;
      statusIcon = Icons.wifi_tethering_off_rounded;
      statusTitle = 'Wi-Fi verification unsupported on this device';
      statusSubtitle = _deriveFallbackSubtitle();
    } else {
      cardBg = AppColors.surface;
      cardBorder = AppColors.border;
      iconColor = AppColors.primary;
      statusIcon = Icons.wifi_rounded;
      statusTitle = 'Workplace Wi-Fi Verification';
      statusSubtitle =
          'Tap to check connection against ${workplace?.locationName ?? 'workplace'}';
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: cardBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(AppSpacing.xs),
                decoration: BoxDecoration(
                  color: iconColor.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: isProbing
                    ? SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: iconColor,
                        ),
                      )
                    : Icon(statusIcon, color: iconColor, size: 20),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      statusTitle,
                      style: AppTypography.labelLarge.copyWith(
                        color: AppColors.textPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      statusSubtitle,
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                key: const Key('wifi_probe_button'),
                icon: const Icon(Icons.refresh_rounded, size: 20),
                color: AppColors.primary,
                tooltip: 'Check workplace Wi-Fi',
                onPressed: isProbing ? null : onProbeWifi,
              ),
            ],
          ),
          if (isPermissionDenied && onResolvePermission != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                key: const Key('wifi_resolve_permission_button'),
                onPressed: onResolvePermission,
                icon: const Icon(Icons.security_rounded, size: 16),
                label: const Text('Grant Wi-Fi Permission'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _deriveFallbackSubtitle() {
    final fallback = policy?.wifiFallbackAction;
    switch (fallback) {
      case 'GPS_FALLBACK':
        return 'GPS fallback required when Wi-Fi is disconnected.';
      case 'SUPERVISOR_REVIEW':
        return 'Supervisor review required if punching without Wi-Fi.';
      case 'MANUAL_FALLBACK':
        return 'Manual fallback enabled under attendance policy.';
      case 'REJECT':
      default:
        return 'Connect to office Wi-Fi to record attendance.';
    }
  }
}
