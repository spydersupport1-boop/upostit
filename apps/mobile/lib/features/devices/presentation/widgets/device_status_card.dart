import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_spacing.dart';
import '../../../../core/constants/app_typography.dart';
import '../../domain/entities/device_binding_status.dart';
import '../../domain/entities/device_info.dart';
import '../bloc/device_bloc.dart';
import '../bloc/device_event.dart';
import '../bloc/device_state.dart';

/// Card widget displaying the employee's mobile device binding, authorization status, and actions.
class DeviceStatusCard extends StatelessWidget {
  final DeviceBloc? deviceBloc;

  const DeviceStatusCard({super.key, this.deviceBloc});

  DeviceBloc? _resolveBloc(BuildContext context) {
    if (deviceBloc != null) return deviceBloc;
    try {
      return context.read<DeviceBloc>();
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final bloc = _resolveBloc(context);
    if (bloc == null) {
      return const SizedBox.shrink();
    }

    return BlocBuilder<DeviceBloc, DeviceState>(
      bloc: bloc,
      builder: (context, state) {
        if (state is DeviceInitial) {
          bloc.add(const CheckDeviceStatusRequested());
          return _buildLoadingCard();
        }

        if (state is DeviceLoading) {
          return _buildLoadingCard();
        }

        if (state is DeviceFailure) {
          return _buildFailureCard(context, bloc, state);
        }

        if (state is DeviceLoaded) {
          return _buildLoadedCard(context, bloc, state);
        }

        return const SizedBox.shrink();
      },
    );
  }

  Widget _buildLoadingCard() {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.borderLight),
      ),
      child: const Padding(
        padding: AppSpacing.cardPadding,
        child: Center(
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: 16.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 12),
                Text('Checking device authorization...'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFailureCard(
      BuildContext context, DeviceBloc bloc, DeviceFailure state) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.errorLight),
      ),
      child: Padding(
        padding: AppSpacing.cardPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.error_outline_rounded,
                    color: AppColors.error, size: 24),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Device Authorization Error',
                    style: AppTypography.headingMedium
                        .copyWith(color: AppColors.error),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(state.message, style: AppTypography.bodySmall),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () {
                bloc.add(const CheckDeviceStatusRequested());
              },
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadedCard(
      BuildContext context, DeviceBloc bloc, DeviceLoaded state) {
    final status = state.status;
    final device = state.device;

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdBorderRadius,
        side: const BorderSide(color: AppColors.borderLight),
      ),
      child: Padding(
        padding: AppSpacing.cardPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: _getStatusBgColor(status),
                    borderRadius: AppRadius.smBorderRadius,
                  ),
                  child: Icon(
                    Icons.smartphone_rounded,
                    color: _getStatusTextColor(status),
                    size: 22,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Mobile Device Binding',
                          style: AppTypography.headingMedium),
                      const SizedBox(height: 2),
                      Text(
                        device != null
                            ? '${device.platform} • ${device.deviceModel ?? 'Standard Device'}'
                            : 'This Device',
                        style: AppTypography.bodySmall,
                      ),
                    ],
                  ),
                ),
                _buildStatusBadge(status),
              ],
            ),
            const SizedBox(height: 14),
            _buildStatusExplanation(status),
            if (device != null) ...[
              const SizedBox(height: 12),
              const Divider(height: 1),
              const SizedBox(height: 12),
              _buildDeviceDetails(device),
            ],
            if (state.actionMessage != null) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.successLight,
                  borderRadius: AppRadius.smBorderRadius,
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle_outline_rounded,
                        color: AppColors.success, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        state.actionMessage!,
                        style: AppTypography.bodySmall
                            .copyWith(color: AppColors.success),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (!state.isBound ||
                    status == DeviceBindingStatus.unregistered)
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: AppRadius.smBorderRadius,
                      ),
                    ),
                    onPressed: state.isRegistering
                        ? null
                        : () {
                            bloc.add(const RegisterCurrentDeviceRequested());
                          },
                    icon: state.isRegistering
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Icon(Icons.app_registration_rounded, size: 18),
                    label: Text(state.isRegistering
                        ? 'Registering...'
                        : 'Register This Device'),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: () {
                      bloc.add(const CheckDeviceStatusRequested());
                    },
                    icon: const Icon(Icons.sync_rounded, size: 18),
                    label: const Text('Refresh Status'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBadge(DeviceBindingStatus status) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: _getStatusBgColor(status),
        borderRadius: AppRadius.fullBorderRadius,
      ),
      child: Text(
        status.toDisplayString().toUpperCase(),
        style: AppTypography.caption.copyWith(
          color: _getStatusTextColor(status),
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildStatusExplanation(DeviceBindingStatus status) {
    String text;
    IconData icon;
    Color iconColor;

    switch (status) {
      case DeviceBindingStatus.active:
        text =
            'This device is bound to your account and authorized to record attendance punches.';
        icon = Icons.verified_user_rounded;
        iconColor = AppColors.success;
        break;
      case DeviceBindingStatus.pendingApproval:
        text =
            'Registration is pending HR administrator review and approval before punches can be recorded.';
        icon = Icons.hourglass_top_rounded;
        iconColor = AppColors.warning;
        break;
      case DeviceBindingStatus.revoked:
        text =
            'This device authorization has been revoked. Attendance punches from this device are blocked. Please contact HR.';
        icon = Icons.block_rounded;
        iconColor = AppColors.error;
        break;
      case DeviceBindingStatus.replaced:
        text =
            'This device was superseded by another authorized device binding for your account.';
        icon = Icons.swap_horiz_rounded;
        iconColor = AppColors.textSecondary;
        break;
      case DeviceBindingStatus.unregistered:
        text =
            'This device is not yet registered. Register this device to authorize attendance tracking.';
        icon = Icons.info_outline_rounded;
        iconColor = AppColors.primary;
        break;
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: iconColor),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: AppTypography.bodySmall
                .copyWith(color: AppColors.textSecondary),
          ),
        ),
      ],
    );
  }

  Widget _buildDeviceDetails(DeviceInfo device) {
    final dateFormat = DateFormat.yMMMd();
    return Column(
      children: [
        _buildDetailRow(
            'OS Version', '${device.osName ?? ''} ${device.osVersion ?? ''}'),
        const SizedBox(height: 6),
        _buildDetailRow('App Version', device.appVersion ?? '1.0.0+1'),
        const SizedBox(height: 6),
        _buildDetailRow(
            'Bound Date', dateFormat.format(device.registeredAt.toLocal())),
        if (device.revocationReason != null &&
            device.status == DeviceBindingStatus.revoked) ...[
          const SizedBox(height: 6),
          _buildDetailRow('Reason', device.revocationReason!, isWarning: true),
        ],
      ],
    );
  }

  Widget _buildDetailRow(String label, String value, {bool isWarning = false}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style:
              AppTypography.bodySmall.copyWith(color: AppColors.textSecondary),
        ),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.right,
            style: AppTypography.bodySmall.copyWith(
              fontWeight: FontWeight.w600,
              color: isWarning ? AppColors.error : AppColors.textPrimary,
            ),
          ),
        ),
      ],
    );
  }

  Color _getStatusBgColor(DeviceBindingStatus status) {
    switch (status) {
      case DeviceBindingStatus.active:
        return AppColors.successLight;
      case DeviceBindingStatus.pendingApproval:
        return AppColors.warningLight;
      case DeviceBindingStatus.revoked:
        return AppColors.errorLight;
      case DeviceBindingStatus.replaced:
        return AppColors.borderLight;
      case DeviceBindingStatus.unregistered:
        return AppColors.primaryLight;
    }
  }

  Color _getStatusTextColor(DeviceBindingStatus status) {
    switch (status) {
      case DeviceBindingStatus.active:
        return AppColors.success;
      case DeviceBindingStatus.pendingApproval:
        return AppColors.warning;
      case DeviceBindingStatus.revoked:
        return AppColors.error;
      case DeviceBindingStatus.replaced:
        return AppColors.textSecondary;
      case DeviceBindingStatus.unregistered:
        return AppColors.primary;
    }
  }
}
