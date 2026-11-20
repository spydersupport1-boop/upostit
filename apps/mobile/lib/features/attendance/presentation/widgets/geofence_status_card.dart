import 'package:flutter/material.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../data/services/location_service.dart';
import '../../domain/entities/assigned_workplace.dart';
import '../../domain/entities/attendance_policy.dart';

/// Clean, employee-friendly card presenting assigned workplace geofence status
/// when GPS verification is required by company attendance policy.
class GeofenceStatusCard extends StatelessWidget {
  final AttendancePolicy? policy;
  final AssignedWorkplace? workplace;
  final LocationReading? lastReading;
  final double? advisoryDistanceMeters;
  final bool? isInsideGeofence;
  final bool isPermissionDenied;
  final bool isServiceDisabled;
  final String? inFlightStatusMessage;
  final VoidCallback? onResolvePermission;
  final VoidCallback? onProbeLocation;

  const GeofenceStatusCard({
    super.key,
    required this.policy,
    required this.workplace,
    this.lastReading,
    this.advisoryDistanceMeters,
    this.isInsideGeofence,
    this.isPermissionDenied = false,
    this.isServiceDisabled = false,
    this.inFlightStatusMessage,
    this.onResolvePermission,
    this.onProbeLocation,
  });

  @override
  Widget build(BuildContext context) {
    // Only render when company policy mandates GPS verification
    if (policy?.requiresGps != true) {
      return const SizedBox.shrink();
    }

    // 1. Permission or Hardware Service Disabled Alert State
    if (isServiceDisabled || isPermissionDenied) {
      return Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: AppSpacing.md),
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.warningLight,
          borderRadius: AppRadius.mdBorderRadius,
          border: Border.all(color: AppColors.warning.withValues(alpha: 0.4)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                color: AppColors.surface,
                shape: BoxShape.circle,
              ),
              child: Icon(
                isServiceDisabled
                    ? Icons.location_off_rounded
                    : Icons.location_searching_rounded,
                color: AppColors.warning,
                size: 20,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isServiceDisabled
                        ? 'Location Services Disabled'
                        : 'Location Permission Required',
                    style: AppTypography.labelLarge.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    isServiceDisabled
                        ? 'Enable device GPS to punch under company policy.'
                        : 'Grant location access to verify attendance.',
                    style: AppTypography.bodySmall.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            if (onResolvePermission != null) ...[
              const SizedBox(width: AppSpacing.xs),
              TextButton(
                key: const Key('resolve_location_permission_button'),
                onPressed: onResolvePermission,
                style: TextButton.styleFrom(
                  backgroundColor: AppColors.warning,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  isServiceDisabled ? 'Turn On' : 'Allow',
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 12),
                ),
              ),
            ],
          ],
        ),
      );
    }

    // 2. Active In-flight Status Bar
    if (inFlightStatusMessage != null) {
      return Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: AppSpacing.md),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: AppColors.primaryLight,
          borderRadius: AppRadius.mdBorderRadius,
          border: Border.all(color: AppColors.primary.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(AppColors.primary),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                inFlightStatusMessage!,
                style: AppTypography.bodySmall.copyWith(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      );
    }

    // 3. Standard Proximity & Geofence Card
    final workplaceName = workplace?.locationName ?? 'Assigned Workplace';
    final radius = workplace?.radiusMeters ?? policy?.maxAccuracyMeters ?? 100;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.mdBorderRadius,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: (isInsideGeofence == true)
                      ? AppColors.successLight
                      : (isInsideGeofence == false)
                          ? AppColors.warningLight
                          : AppColors.infoLight,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  (isInsideGeofence == true)
                      ? Icons.check_circle_rounded
                      : (isInsideGeofence == false)
                          ? Icons.wrong_location_rounded
                          : Icons.fmd_good_rounded,
                  color: (isInsideGeofence == true)
                      ? AppColors.success
                      : (isInsideGeofence == false)
                          ? AppColors.warning
                          : AppColors.info,
                  size: 18,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      workplaceName,
                      style: AppTypography.labelLarge.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      'Geofence perimeter: ${radius}m',
                      style: AppTypography.bodySmall.copyWith(
                        color: AppColors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
              if (onProbeLocation != null && isInsideGeofence == null) ...[
                IconButton(
                  key: const Key('check_proximity_icon_button'),
                  icon: const Icon(Icons.my_location_rounded, size: 18),
                  tooltip: 'Check proximity',
                  onPressed: onProbeLocation,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ],
          ),
          if (advisoryDistanceMeters != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: 4,
              ),
              decoration: BoxDecoration(
                color: (isInsideGeofence == true)
                    ? AppColors.successLight
                    : AppColors.warningLight,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    (isInsideGeofence == true)
                        ? Icons.verified_user_rounded
                        : Icons.info_outline_rounded,
                    size: 14,
                    color: (isInsideGeofence == true)
                        ? AppColors.success
                        : AppColors.warning,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    (isInsideGeofence == true)
                        ? 'Within geofence (~${advisoryDistanceMeters!.round()}m from center)'
                        : 'Outside geofence (~${advisoryDistanceMeters!.round()}m away)',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: (isInsideGeofence == true)
                          ? AppColors.success
                          : AppColors.warning,
                    ),
                  ),
                  if (lastReading != null) ...[
                    Text(
                      ' • ±${lastReading!.accuracyMeters.round()}m',
                      style: TextStyle(
                        fontSize: 11,
                        color: (isInsideGeofence == true)
                            ? AppColors.success
                            : AppColors.warning,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
