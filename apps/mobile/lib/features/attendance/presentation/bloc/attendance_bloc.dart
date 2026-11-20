import 'dart:async';
import 'dart:convert';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import 'package:uuid/uuid.dart';
import '../../../../core/errors/failure.dart';
import '../../../sync/domain/entities/local_queue_item.dart';
import '../../../sync/domain/entities/sync_status.dart';
import '../../../sync/domain/repositories/local_queue_dao.dart';
import '../../../sync/domain/repositories/network_connectivity_service.dart';
import '../../../devices/data/services/device_identity_service.dart';
import '../../data/services/location_service.dart';
import '../../data/services/wifi_service.dart';
import '../../domain/entities/attendance_event.dart';
import '../../domain/entities/attendance_policy.dart';
import '../../domain/entities/attendance_status.dart';
import '../../domain/entities/wifi_evidence.dart';
import '../../domain/repositories/attendance_repository.dart';
import 'attendance_event.dart';
import 'attendance_state.dart';

/// Central BLoC managing attendance dashboard, policy-driven GPS/Wi-Fi punch lifecycle, and live timer ticker.
class AttendanceBloc extends Bloc<AttendanceBlocEvent, AttendanceState> {
  final AttendanceRepository repository;
  final LocationService locationService;
  final WifiService wifiService;
  final LocalQueueDao? localQueueDao;
  final NetworkConnectivityService? connectivityService;
  final DeviceIdentityService? deviceIdentityService;
  final String? tenantId;
  final String? userId;
  final String? employeeId;
  final Uuid _uuid;
  Timer? _tickerTimer;

  AttendanceBloc({
    required this.repository,
    this.locationService = const GeolocatorLocationService(),
    WifiService? wifiService,
    Uuid? uuid,
    this.localQueueDao,
    this.connectivityService,
    this.deviceIdentityService,
    this.tenantId,
    this.userId,
    this.employeeId,
  })  : wifiService = wifiService ??
            NetworkInfoWifiService(locationService: locationService),
        _uuid = uuid ?? const Uuid(),
        super(const AttendanceInitial()) {
    on<AttendanceDashboardRequested>(_onDashboardRequested);
    on<PunchActionSubmitted>(_onPunchActionSubmitted);
    on<PunchRetryRequested>(_onPunchRetryRequested);
    on<LiveTimerTicked>(_onLiveTimerTicked);
    on<DismissFeedbackNotice>(_onDismissFeedbackNotice);
    on<LocationPermissionResolutionRequested>(
        _onLocationPermissionResolutionRequested);
    on<LocationProbeRequested>(_onLocationProbeRequested);
    on<WifiProbeRequested>(_onWifiProbeRequested);
  }

  Future<void> _onDashboardRequested(
    AttendanceDashboardRequested event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) {
      emit(const AttendanceLoading());
    }

    final result = await repository.getTodayAttendanceDashboard();

    await result.fold(
      (failure) async {
        if (state is AttendanceLoaded) {
          final loaded = state as AttendanceLoaded;
          emit(loaded.copyWith(
            errorMessage: failure.message,
            isRetriable: failure is NetworkFailure,
          ));
        } else {
          emit(AttendanceLoadFailure(
            message: failure.message,
            isNetworkError: failure is NetworkFailure,
          ));
        }
      },
      (dashboard) async {
        emit(AttendanceLoaded(dashboard: dashboard));
        _manageTicker(dashboard.status);

        // Pre-check location permission state if GPS or Wi-Fi policy is active
        if (dashboard.policy?.requiresGps == true ||
            dashboard.policy?.requiresWifi == true) {
          final permStatus = await locationService.checkPermissionStatus();
          if (permStatus == LocationPermissionStatus.serviceDisabled) {
            emit((state as AttendanceLoaded)
                .copyWith(isLocationServiceDisabled: true));
          } else if (permStatus == LocationPermissionStatus.denied ||
              permStatus == LocationPermissionStatus.permanentlyDenied) {
            emit((state as AttendanceLoaded).copyWith(
              isLocationPermissionDenied: dashboard.policy?.requiresGps == true,
              isWifiPermissionDenied: dashboard.policy?.requiresWifi == true,
            ));
          }
        }
      },
    );
  }

  Future<void> _onPunchActionSubmitted(
    PunchActionSubmitted event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) return;
    final currentState = state as AttendanceLoaded;

    // Prevent duplicate submission while another punch request is actively in-flight
    if (currentState.isSubmittingPunch) return;

    // Generate UUID v4 idempotency key ONCE per punch attempt
    final idempotencyKey = event.customIdempotencyKey ?? _uuid.v4();

    emit(currentState.copyWith(
      isSubmittingPunch: true,
      inFlightEventType: event.eventType,
      inFlightIdempotencyKey: idempotencyKey,
      clearError: true,
      clearNotices: true,
      clearLocationStatus: true,
      clearWifiStatus: true,
    ));

    await _executePunch(
      eventType: event.eventType,
      idempotencyKey: idempotencyKey,
      emit: emit,
    );
  }

  Future<void> _onPunchRetryRequested(
    PunchRetryRequested event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) return;
    final currentState = state as AttendanceLoaded;

    final key = currentState.inFlightIdempotencyKey;
    final type = currentState.inFlightEventType;

    if (key == null || type == null || currentState.isSubmittingPunch) return;

    emit(currentState.copyWith(
      isSubmittingPunch: true,
      clearError: true,
      clearLocationStatus: true,
      clearWifiStatus: true,
    ));

    // REUSE the exact same idempotency key and exact same telemetry evidence on retry
    await _executePunch(
      eventType: type,
      idempotencyKey: key,
      retryLocationReading: currentState.inFlightLocationReading,
      retryWifiEvidence: currentState.inFlightWifiEvidence,
      emit: emit,
    );
  }

  Future<void> _executePunch({
    required AttendanceEventType eventType,
    required String idempotencyKey,
    LocationReading? retryLocationReading,
    WifiEvidence? retryWifiEvidence,
    required Emitter<AttendanceState> emit,
  }) async {
    final currentState = state as AttendanceLoaded;
    final policy =
        currentState.dashboard.policy ?? AttendancePolicy.defaultManual();

    // 1. Guard against unsupported company policy modes
    if (!policy.isSupportedInThisRelease) {
      emit((state as AttendanceLoaded).copyWith(
        isSubmittingPunch: false,
        errorMessage: policy.unsupportedMessage ??
            'Verification method "${policy.defaultMode}" is not supported in this mobile release.',
        isRetriable: false,
        clearInFlight: true,
      ));
      return;
    }

    String? locationId;
    double? latitude;
    double? longitude;
    double? accuracyMeters;
    String? wifiBssid;
    String? wifiSsid;
    String? wifiSignalStatus;
    DateTime deviceReportedAt = DateTime.now().toUtc();
    final Map<String, dynamic> metadata = {};

    LocationReading? capturedLocation = retryLocationReading;
    WifiEvidence? capturedWifi = retryWifiEvidence;

    final workplace = (state as AttendanceLoaded).dashboard.workplace;
    if (policy.requiresGps || policy.requiresWifi) {
      if (workplace == null) {
        emit((state as AttendanceLoaded).copyWith(
          isSubmittingPunch: false,
          errorMessage: policy.mode == PolicyVerificationMode.gpsOnly
              ? 'No assigned workplace location found for your profile. An active workplace assignment is required to verify GPS attendance.'
              : 'No assigned workplace location found for your profile. An active workplace assignment is required to verify attendance.',
          isRetriable: false,
        ));
        return;
      }
      locationId = workplace.locationId;
    }

    // =========================================================================
    // 2. Telemetry Collection based on Policy Mode
    // =========================================================================

    // Case A: Pure MANUAL Mode
    if (policy.mode == PolicyVerificationMode.manual) {
      // Manual policy accepts punches without coordinates or Wi-Fi evidence
    }

    // Case B: Pure GPS_ONLY Mode
    else if (policy.mode == PolicyVerificationMode.gpsOnly) {
      emit((state as AttendanceLoaded).copyWith(
        locationStatusMessage: 'Acquiring GPS location...',
      ));

      try {
        final reading = capturedLocation ??
            await locationService.getCurrentLocation(
              maxAccuracyMeters: policy.maxAccuracyMeters,
              maxLocationAgeSeconds: policy.maxLocationAgeSeconds,
            );
        capturedLocation = reading;

        latitude = reading.latitude;
        longitude = reading.longitude;
        accuracyMeters = reading.accuracyMeters;
        deviceReportedAt = reading.timestamp.toUtc();
        if (reading.isMocked) {
          metadata['is_mocked'] = true;
        }

        double? advisoryDistance;
        bool? isInside;
        if (workplace?.latitude != null && workplace?.longitude != null) {
          advisoryDistance = locationService.calculateDistanceMeters(
            startLatitude: latitude,
            startLongitude: longitude,
            endLatitude: workplace!.latitude!,
            endLongitude: workplace.longitude!,
          );
          if (workplace.radiusMeters != null) {
            isInside = advisoryDistance <= workplace.radiusMeters!;
          }
        }

        emit((state as AttendanceLoaded).copyWith(
          locationStatusMessage: 'Verifying workplace perimeter...',
          lastLocationReading: reading,
          inFlightLocationReading: reading,
          advisoryDistanceMeters: advisoryDistance,
          isInsideGeofence: isInside,
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
        ));
      } catch (e) {
        _handleLocationException(e, emit);
        return;
      }
    }

    // Case C: WIFI_ONLY Mode
    else if (policy.mode == PolicyVerificationMode.wifiOnly) {
      emit((state as AttendanceLoaded).copyWith(
        wifiStatusMessage: 'Checking workplace Wi-Fi...',
      ));

      final wifiEvidence =
          capturedWifi ?? await wifiService.getConnectedWifiEvidence();
      capturedWifi = wifiEvidence;
      wifiSignalStatus = wifiEvidence.signalStatus.toBackendString();
      deviceReportedAt = wifiEvidence.deviceReportedAt;

      emit((state as AttendanceLoaded).copyWith(
        lastWifiEvidence: wifiEvidence,
        inFlightWifiEvidence: wifiEvidence,
      ));

      if (wifiEvidence.isAvailable) {
        wifiBssid = wifiEvidence.bssid;
        wifiSsid = wifiEvidence.ssid;
      } else {
        // Wi-Fi is UNAVAILABLE, PERMISSION_DENIED, or UNSUPPORTED
        final fallback = policy.wifiFallbackAction;

        if (fallback == 'REJECT') {
          if (wifiEvidence.signalStatus == WifiSignalStatus.permissionDenied) {
            emit((state as AttendanceLoaded).copyWith(
              isSubmittingPunch: false,
              errorMessage:
                  'Wi-Fi permission is required to verify workplace attendance.',
              isRetriable: true,
              isWifiPermissionDenied: true,
              clearWifiStatus: true,
            ));
          } else {
            emit((state as AttendanceLoaded).copyWith(
              isSubmittingPunch: false,
              errorMessage: wifiEvidence.errorMessage ??
                  'Workplace Wi-Fi connection required. Device is not connected to recognized Wi-Fi.',
              isRetriable: true,
              clearWifiStatus: true,
            ));
          }
          return;
        } else if (fallback == 'GPS_FALLBACK') {
          emit((state as AttendanceLoaded).copyWith(
            wifiStatusMessage: 'Wi-Fi unavailable. Engaging GPS fallback...',
          ));

          try {
            final reading = capturedLocation ??
                await locationService.getCurrentLocation(
                  maxAccuracyMeters: policy.maxAccuracyMeters,
                  maxLocationAgeSeconds: policy.maxLocationAgeSeconds,
                );
            capturedLocation = reading;

            latitude = reading.latitude;
            longitude = reading.longitude;
            accuracyMeters = reading.accuracyMeters;
            deviceReportedAt = reading.timestamp.toUtc();

            emit((state as AttendanceLoaded).copyWith(
              lastLocationReading: reading,
              inFlightLocationReading: reading,
              wifiStatusMessage: 'GPS fallback acquired. Submitting punch...',
            ));
          } catch (e) {
            _handleLocationException(e, emit);
            return;
          }
        } else if (fallback == 'SUPERVISOR_REVIEW') {
          emit((state as AttendanceLoaded).copyWith(
            wifiStatusMessage:
                'Wi-Fi unavailable. Punch flagged for supervisor review...',
          ));
        } else if (fallback == 'MANUAL_FALLBACK') {
          emit((state as AttendanceLoaded).copyWith(
            wifiStatusMessage:
                'Wi-Fi unavailable. Submitting manual fallback...',
          ));
        }
      }
    }

    // Case D: COMBINED Mode (AND / OR)
    else if (policy.mode == PolicyVerificationMode.combined) {
      final isAndRule = policy.combinationRule == 'AND';

      if (isAndRule) {
        // Dual-Factor Presence: BOTH GPS AND Wi-Fi required!
        emit((state as AttendanceLoaded).copyWith(
          wifiStatusMessage: 'Checking workplace Wi-Fi (dual-factor)...',
          locationStatusMessage: 'Acquiring GPS location (dual-factor)...',
        ));

        // 1. Check Wi-Fi
        final wifiEvidence =
            capturedWifi ?? await wifiService.getConnectedWifiEvidence();
        capturedWifi = wifiEvidence;
        wifiSignalStatus = wifiEvidence.signalStatus.toBackendString();

        emit((state as AttendanceLoaded).copyWith(
          lastWifiEvidence: wifiEvidence,
          inFlightWifiEvidence: wifiEvidence,
        ));

        if (!wifiEvidence.isAvailable) {
          emit((state as AttendanceLoaded).copyWith(
            isSubmittingPunch: false,
            errorMessage:
                'Dual-factor attendance policy requires both GPS and Wi-Fi. Connected Wi-Fi is unavailable.',
            isRetriable: true,
            clearLocationStatus: true,
            clearWifiStatus: true,
          ));
          return;
        }
        wifiBssid = wifiEvidence.bssid;
        wifiSsid = wifiEvidence.ssid;

        // 2. Check GPS
        try {
          final reading = capturedLocation ??
              await locationService.getCurrentLocation(
                maxAccuracyMeters: policy.maxAccuracyMeters,
                maxLocationAgeSeconds: policy.maxLocationAgeSeconds,
              );
          capturedLocation = reading;

          latitude = reading.latitude;
          longitude = reading.longitude;
          accuracyMeters = reading.accuracyMeters;
          deviceReportedAt = reading.timestamp.toUtc();

          emit((state as AttendanceLoaded).copyWith(
            lastLocationReading: reading,
            inFlightLocationReading: reading,
          ));
        } catch (e) {
          _handleLocationException(e, emit);
          return;
        }
      } else {
        // COMBINED with OR rule: Either Wi-Fi OR GPS satisfies presence
        emit((state as AttendanceLoaded).copyWith(
          wifiStatusMessage: 'Checking workplace presence...',
        ));

        final wifiEvidence =
            capturedWifi ?? await wifiService.getConnectedWifiEvidence();
        capturedWifi = wifiEvidence;
        wifiSignalStatus = wifiEvidence.signalStatus.toBackendString();

        emit((state as AttendanceLoaded).copyWith(
          lastWifiEvidence: wifiEvidence,
          inFlightWifiEvidence: wifiEvidence,
        ));

        if (wifiEvidence.isAvailable) {
          wifiBssid = wifiEvidence.bssid;
          wifiSsid = wifiEvidence.ssid;
          deviceReportedAt = wifiEvidence.deviceReportedAt;
        } else {
          // Fall back to GPS
          emit((state as AttendanceLoaded).copyWith(
            wifiStatusMessage: 'Wi-Fi unavailable. Acquiring GPS location...',
          ));

          try {
            final reading = capturedLocation ??
                await locationService.getCurrentLocation(
                  maxAccuracyMeters: policy.maxAccuracyMeters,
                  maxLocationAgeSeconds: policy.maxLocationAgeSeconds,
                );
            capturedLocation = reading;

            latitude = reading.latitude;
            longitude = reading.longitude;
            accuracyMeters = reading.accuracyMeters;
            deviceReportedAt = reading.timestamp.toUtc();

            emit((state as AttendanceLoaded).copyWith(
              lastLocationReading: reading,
              inFlightLocationReading: reading,
            ));
          } catch (e) {
            _handleLocationException(e, emit);
            return;
          }
        }
      }
    }

    // =========================================================================
    // 3. Dispatch to Server-Authoritative Punch Ledger or Offline Queue
    // =========================================================================
    String? resolvedDeviceId;
    bool? isMockLocation;
    DateTime? locationCapturedAt;

    if (deviceIdentityService != null) {
      try {
        resolvedDeviceId =
            await deviceIdentityService!.getOrCreateInstallationId();
      } catch (_) {}
      isMockLocation = capturedLocation?.isMocked;
      locationCapturedAt = capturedLocation?.timestamp.toUtc();
    }

    final isDeviceOffline = connectivityService != null &&
        !await connectivityService!.isConnected();
    if (isDeviceOffline && localQueueDao != null) {
      await _persistOfflinePunch(
        eventType: eventType,
        idempotencyKey: idempotencyKey,
        deviceReportedAt: deviceReportedAt,
        locationId: locationId,
        latitude: latitude,
        longitude: longitude,
        accuracyMeters: accuracyMeters,
        wifiBssid: wifiBssid,
        wifiSsid: wifiSsid,
        wifiSignalStatus: wifiSignalStatus,
        deviceId: resolvedDeviceId,
        isMockLocation: isMockLocation,
        locationCapturedAt: locationCapturedAt,
        metadata: metadata,
        emit: emit,
      );
      return;
    }

    final result = await repository.recordPunch(
      eventType: eventType,
      idempotencyKey: idempotencyKey,
      deviceReportedAt: deviceReportedAt,
      locationId: locationId,
      latitude: latitude,
      longitude: longitude,
      accuracyMeters: accuracyMeters,
      wifiBssid: wifiBssid,
      wifiSsid: wifiSsid,
      wifiSignalStatus: wifiSignalStatus,
      deviceId: resolvedDeviceId,
      isMockLocation: isMockLocation,
      locationCapturedAt: locationCapturedAt,
      metadata: metadata.isEmpty ? const {} : metadata,
    );

    await result.fold(
      (failure) async {
        if (failure is NetworkFailure && localQueueDao != null) {
          await _persistOfflinePunch(
            eventType: eventType,
            idempotencyKey: idempotencyKey,
            deviceReportedAt: deviceReportedAt,
            locationId: locationId,
            latitude: latitude,
            longitude: longitude,
            accuracyMeters: accuracyMeters,
            wifiBssid: wifiBssid,
            wifiSsid: wifiSsid,
            wifiSignalStatus: wifiSignalStatus,
            deviceId: resolvedDeviceId,
            isMockLocation: isMockLocation,
            locationCapturedAt: locationCapturedAt,
            metadata: metadata,
            emit: emit,
          );
          return;
        }

        final isPayloadMismatch = failure.statusCode == 422;
        final isRevokedDevice = failure.statusCode == 403 &&
            (failure.message.toLowerCase().contains('revoked') ||
                failure.message.toLowerCase().contains('device'));
        final displayErrorMessage = isPayloadMismatch
            ? 'Idempotency key reused with mismatched request payload.'
            : (isRevokedDevice
                ? 'Device access revoked. Please contact HR to authorize this device.'
                : failure.message);

        emit((state as AttendanceLoaded).copyWith(
          isSubmittingPunch: false,
          errorMessage: displayErrorMessage,
          isRetriable: !isPayloadMismatch &&
              !isRevokedDevice &&
              (failure is NetworkFailure ||
                  (failure.statusCode != null && failure.statusCode! >= 500)),
          clearLocationStatus: true,
          clearWifiStatus: true,
          clearInFlight: isPayloadMismatch || isRevokedDevice,
        ));
      },
      (punchResult) async {
        final timeStr =
            DateFormat.jm().format(punchResult.event.effectiveAt.toLocal());
        final notice = '${eventType.displayName} recorded at $timeStr';
        String? reviewNotice;

        if (punchResult.event.isPendingReview) {
          reviewNotice =
              'Recorded but flagged for manager review (${punchResult.event.timestampVerificationStatus})';
        }

        // Refresh server-authoritative attendance state after punch
        final refreshedDashboardResult =
            await repository.getTodayAttendanceDashboard();

        refreshedDashboardResult.fold(
          (dashboardFailure) {
            emit((state as AttendanceLoaded).copyWith(
              isSubmittingPunch: false,
              lastPunchResult: punchResult,
              successNotice: notice,
              pendingReviewNotice: reviewNotice,
              clearInFlight: true,
              errorMessage: dashboardFailure.message,
              clearLocationStatus: true,
              clearWifiStatus: true,
            ));
          },
          (refreshedDashboard) {
            emit(AttendanceLoaded(
              dashboard: refreshedDashboard,
              isSubmittingPunch: false,
              lastPunchResult: punchResult,
              successNotice: notice,
              pendingReviewNotice: reviewNotice,
              inFlightEventType: null,
              inFlightIdempotencyKey: null,
              inFlightLocationReading: null,
              inFlightWifiEvidence: null,
            ));
            _manageTicker(refreshedDashboard.status);
          },
        );
      },
    );
  }

  Future<void> _persistOfflinePunch({
    required AttendanceEventType eventType,
    required String idempotencyKey,
    required DateTime? deviceReportedAt,
    required String? locationId,
    required double? latitude,
    required double? longitude,
    required double? accuracyMeters,
    required String? wifiBssid,
    required String? wifiSsid,
    required String? wifiSignalStatus,
    String? deviceId,
    bool? isMockLocation,
    DateTime? locationCapturedAt,
    required Map<String, dynamic> metadata,
    required Emitter<AttendanceState> emit,
  }) async {
    final currentState = state as AttendanceLoaded;
    final now = DateTime.now().toUtc();
    final effectiveDeviceTime = deviceReportedAt ?? now;

    final resolvedTenantId = tenantId ??
        currentState.dashboard.todayDay?.tenantId ??
        (currentState.dashboard.todayEvents.isNotEmpty
            ? currentState.dashboard.todayEvents.first.tenantId
            : 'tenant_default');

    final resolvedEmployeeId = employeeId ??
        currentState.dashboard.todayDay?.employeeId ??
        (currentState.dashboard.todayEvents.isNotEmpty
            ? currentState.dashboard.todayEvents.first.employeeId
            : 'employee_default');

    final resolvedUserId = userId ?? 'user_default';

    final combinedMetadata = Map<String, dynamic>.from(metadata);
    if (isMockLocation != null) {
      combinedMetadata['is_mock_location'] = isMockLocation;
    }
    if (locationCapturedAt != null) {
      combinedMetadata['location_captured_at'] =
          locationCapturedAt.toUtc().toIso8601String();
    }

    final queueItem = LocalQueueItem(
      localId: _uuid.v4(),
      idempotencyKey: idempotencyKey,
      sessionId: currentState.dashboard.shift?.id ??
          currentState.dashboard.todayDay?.id,
      tenantId: resolvedTenantId,
      employeeId: resolvedEmployeeId,
      userId: resolvedUserId,
      eventType: eventType,
      deviceReportedAt: effectiveDeviceTime,
      timezoneOffsetMinutes: DateTime.now().timeZoneOffset.inMinutes,
      monotonicBootTimeMs: DateTime.now().millisecondsSinceEpoch,
      bootSessionId: 'boot-${DateTime.now().millisecondsSinceEpoch}',
      isRebootDetected: false,
      locationId: locationId,
      latitude: latitude,
      longitude: longitude,
      accuracyMeters: accuracyMeters,
      wifiBssid: wifiBssid,
      wifiSsid: wifiSsid,
      wifiSignalStatus: wifiSignalStatus ?? 'AVAILABLE',
      deviceId: deviceId,
      appliedPolicyVersion: currentState.dashboard.policy?.version ?? 1,
      appliedPolicyMode:
          currentState.dashboard.policy?.mode.name.toUpperCase() ?? 'NONE',
      metadataJson: jsonEncode(combinedMetadata),
      sequenceNumber: 0,
      syncStatus: SyncStatus.pendingSync,
      createdAt: now,
      updatedAt: now,
    );

    try {
      await localQueueDao!.insertPendingEvent(queueItem);

      emit(currentState.copyWith(
        isSubmittingPunch: false,
        offlineNotice:
            'Punch saved locally. It will automatically synchronize when connection is restored.',
        clearLocationStatus: true,
        clearWifiStatus: true,
        clearInFlight: true,
      ));
    } catch (e) {
      emit(currentState.copyWith(
        isSubmittingPunch: false,
        errorMessage: 'Failed to queue offline punch: $e',
        clearLocationStatus: true,
        clearWifiStatus: true,
        clearInFlight: true,
      ));
    }
  }

  void _handleLocationException(Object e, Emitter<AttendanceState> emit) {
    if (e is LocationServiceDisabledException) {
      emit((state as AttendanceLoaded).copyWith(
        isSubmittingPunch: false,
        errorMessage: e.message,
        isRetriable: true,
        isLocationServiceDisabled: true,
        clearLocationStatus: true,
        clearWifiStatus: true,
      ));
    } else if (e is LocationPermissionDeniedException ||
        e is LocationPermissionPermanentlyDeniedException) {
      emit((state as AttendanceLoaded).copyWith(
        isSubmittingPunch: false,
        errorMessage: (e as LocationException).message,
        isRetriable: true,
        isLocationPermissionDenied: true,
        clearLocationStatus: true,
        clearWifiStatus: true,
      ));
    } else if (e is LocationAccuracyException ||
        e is LocationStaleException ||
        e is LocationTimeoutException ||
        e is LocationException) {
      emit((state as AttendanceLoaded).copyWith(
        isSubmittingPunch: false,
        errorMessage: (e as LocationException).message,
        isRetriable: e is! MockLocationDetectedException,
        clearLocationStatus: true,
        clearWifiStatus: true,
      ));
    } else {
      emit((state as AttendanceLoaded).copyWith(
        isSubmittingPunch: false,
        errorMessage: e.toString(),
        isRetriable: true,
        clearLocationStatus: true,
        clearWifiStatus: true,
      ));
    }
  }

  Future<void> _onWifiProbeRequested(
    WifiProbeRequested event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) return;
    final currentState = state as AttendanceLoaded;
    final workplace = currentState.dashboard.workplace;

    if (workplace == null) {
      emit(currentState.copyWith(
        errorMessage: 'No assigned workplace found to verify Wi-Fi against.',
      ));
      return;
    }

    emit(currentState.copyWith(
      isWifiProbing: true,
      wifiStatusMessage: 'Checking workplace Wi-Fi...',
      clearError: true,
    ));

    final wifiEvidence = await wifiService.getConnectedWifiEvidence();

    final probeResult = await repository.verifyWorkplaceWifi(
      locationId: workplace.locationId,
      bssid: wifiEvidence.bssid,
      ssid: wifiEvidence.ssid,
      signalStatus: wifiEvidence.signalStatus.toBackendString(),
      deviceReportedAt: wifiEvidence.deviceReportedAt,
      platform: wifiEvidence.platform,
    );

    probeResult.fold(
      (failure) {
        emit((state as AttendanceLoaded).copyWith(
          isWifiProbing: false,
          lastWifiEvidence: wifiEvidence,
          errorMessage: failure.message,
          clearWifiStatus: true,
        ));
      },
      (verification) {
        emit((state as AttendanceLoaded).copyWith(
          isWifiProbing: false,
          lastWifiEvidence: wifiEvidence,
          lastWifiVerificationResult: verification,
          wifiStatusMessage: verification.message,
        ));
      },
    );
  }

  void _onLiveTimerTicked(
    LiveTimerTicked event,
    Emitter<AttendanceState> emit,
  ) {
    if (state is! AttendanceLoaded) return;
    final loaded = state as AttendanceLoaded;
    final dashboard = loaded.dashboard;

    if (dashboard.status == AttendanceStatus.working) {
      final updated = dashboard.copyWith(
        workingDuration: dashboard.workingDuration + const Duration(seconds: 1),
      );
      emit(loaded.copyWith(dashboard: updated));
    } else if (dashboard.status == AttendanceStatus.onBreak) {
      final updated = dashboard.copyWith(
        breakDuration: dashboard.breakDuration + const Duration(seconds: 1),
      );
      emit(loaded.copyWith(dashboard: updated));
    }
  }

  void _onDismissFeedbackNotice(
    DismissFeedbackNotice event,
    Emitter<AttendanceState> emit,
  ) {
    if (state is! AttendanceLoaded) return;
    emit((state as AttendanceLoaded).copyWith(
      clearError: true,
      clearNotices: true,
      clearLocationStatus: true,
      clearWifiStatus: true,
    ));
  }

  Future<void> _onLocationPermissionResolutionRequested(
    LocationPermissionResolutionRequested event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) return;
    final loaded = state as AttendanceLoaded;

    if (loaded.isLocationServiceDisabled) {
      await locationService.openLocationSettings();
      return;
    }

    final status = await locationService.checkPermissionStatus();
    if (status == LocationPermissionStatus.serviceDisabled) {
      await locationService.openLocationSettings();
    } else if (status == LocationPermissionStatus.permanentlyDenied) {
      await locationService.openAppSettings();
    } else {
      final requested = await locationService.requestPermission();
      if (requested == LocationPermissionStatus.granted) {
        emit(loaded.copyWith(
          isLocationPermissionDenied: false,
          isLocationServiceDisabled: false,
          isWifiPermissionDenied: false,
          clearError: true,
        ));
      }
    }
  }

  Future<void> _onLocationProbeRequested(
    LocationProbeRequested event,
    Emitter<AttendanceState> emit,
  ) async {
    if (state is! AttendanceLoaded) return;
    final loaded = state as AttendanceLoaded;
    final workplace = loaded.dashboard.workplace;

    if (workplace == null) {
      emit(loaded.copyWith(
        errorMessage: 'No assigned workplace found to verify location against.',
      ));
      return;
    }

    try {
      final reading = await locationService.getCurrentLocation(
        maxAccuracyMeters: loaded.dashboard.policy?.maxAccuracyMeters ?? 100,
        maxLocationAgeSeconds:
            loaded.dashboard.policy?.maxLocationAgeSeconds ?? 30,
      );

      double? dist;
      bool? inside;
      if (workplace.latitude != null && workplace.longitude != null) {
        dist = locationService.calculateDistanceMeters(
          startLatitude: reading.latitude,
          startLongitude: reading.longitude,
          endLatitude: workplace.latitude!,
          endLongitude: workplace.longitude!,
        );
        if (workplace.radiusMeters != null) {
          inside = dist <= workplace.radiusMeters!;
        }
      }

      emit(loaded.copyWith(
        lastLocationReading: reading,
        advisoryDistanceMeters: dist,
        isInsideGeofence: inside,
        isLocationPermissionDenied: false,
        isLocationServiceDisabled: false,
        clearLocationStatus: true,
      ));
    } catch (e) {
      _handleLocationException(e, emit);
    }
  }

  void _manageTicker(AttendanceStatus status) {
    _tickerTimer?.cancel();
    if (status == AttendanceStatus.working ||
        status == AttendanceStatus.onBreak) {
      _tickerTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        add(const LiveTimerTicked());
      });
    }
  }

  @override
  Future<void> close() {
    _tickerTimer?.cancel();
    return super.close();
  }
}
