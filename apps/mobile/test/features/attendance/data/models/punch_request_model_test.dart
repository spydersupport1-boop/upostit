import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/attendance/data/models/attendance_day_model.dart';
import 'package:mobile/features/attendance/data/models/attendance_event_model.dart';
import 'package:mobile/features/attendance/data/models/attendance_policy_model.dart';
import 'package:mobile/features/attendance/data/models/employee_workplace_model.dart';
import 'package:mobile/features/attendance/data/models/punch_request_model.dart';
import 'package:mobile/features/attendance/data/models/punch_response_model.dart';
import 'package:mobile/features/attendance/data/models/shift_assignment_model.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_event.dart';
import 'package:mobile/features/attendance/domain/entities/attendance_policy.dart';

void main() {
  group('PunchRequestModel Serialization', () {
    test(
        'serializes CHECK_IN payload with strict UTC ISO timestamp and idempotency key',
        () {
      final now = DateTime.utc(2026, 11, 4, 9, 30, 0);
      final model = PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-uuid-v4-12345678',
        deviceReportedAt: now,
        deviceId: 'pixel-8-pro-id',
        metadata: {'platform': 'android'},
      );

      final json = model.toJson();

      expect(json['event_type'], equals('CHECK_IN'));
      expect(json['idempotency_key'], equals('idem-uuid-v4-12345678'));
      expect(json['device_reported_at'], equals('2026-11-04T09:30:00.000Z'));
      expect(json['device_id'], equals('pixel-8-pro-id'));
      expect(json['metadata'], equals({'platform': 'android'}));
    });

    test(
        'serializes GPS location payload with coordinates, accuracy, and location_id',
        () {
      final now = DateTime.utc(2026, 11, 5, 8, 30, 0);
      final model = PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-gps-uuid-1',
        deviceReportedAt: now,
        locationId: 'loc-hq-uuid',
        latitude: 40.7531,
        longitude: -73.9745,
        accuracyMeters: 12.5,
        metadata: {'is_mocked': false},
      );

      final json = model.toJson();

      expect(json['event_type'], equals('CHECK_IN'));
      expect(json['idempotency_key'], equals('idem-gps-uuid-1'));
      expect(json['device_reported_at'], equals('2026-11-05T08:30:00.000Z'));
      expect(json['location_id'], equals('loc-hq-uuid'));
      expect(json['latitude'], equals(40.7531));
      expect(json['longitude'], equals(-73.9745));
      expect(json['accuracy_meters'], equals(12.5));
      expect(json['metadata'], equals({'is_mocked': false}));
    });

    test('omits null GPS coordinates from json for MANUAL punch', () {
      const model = PunchRequestModel(
        eventType: AttendanceEventType.checkIn,
        idempotencyKey: 'idem-manual-1',
      );

      final json = model.toJson();

      expect(json.containsKey('latitude'), isFalse);
      expect(json.containsKey('longitude'), isFalse);
      expect(json.containsKey('accuracy_meters'), isFalse);
      expect(json.containsKey('location_id'), isFalse);
    });

    test(
        'serializes BREAK_START, BREAK_END, and CHECK_OUT event types correctly',
        () {
      final breakStart = const PunchRequestModel(
        eventType: AttendanceEventType.breakStart,
        idempotencyKey: 'idem-break-start-1234',
      ).toJson();
      expect(breakStart['event_type'], equals('BREAK_START'));

      final breakEnd = const PunchRequestModel(
        eventType: AttendanceEventType.breakEnd,
        idempotencyKey: 'idem-break-end-1234',
      ).toJson();
      expect(breakEnd['event_type'], equals('BREAK_END'));

      final checkOut = const PunchRequestModel(
        eventType: AttendanceEventType.checkOut,
        idempotencyKey: 'idem-check-out-1234',
      ).toJson();
      expect(checkOut['event_type'], equals('CHECK_OUT'));
    });
  });

  group('AttendanceEventModel Deserialization', () {
    test('parses server AttendanceEventResponse JSON correctly', () {
      final json = {
        'id': 'evt-100',
        'tenant_id': 'tenant-200',
        'employee_id': 'emp-300',
        'event_type': 'CHECK_IN',
        'event_category': 'STANDARD',
        'server_received_at': '2026-11-04T09:00:00Z',
        'device_reported_at': '2026-11-04T08:59:58Z',
        'effective_at': '2026-11-04T09:00:00Z',
        'clock_drift_seconds': 2.0,
        'source': 'MOBILE',
        'device_id': 'iphone-15-pro',
        'timestamp_verification_status': 'SERVER_AUTHORITATIVE',
        'review_status': 'NOT_REQUIRED',
        'idempotency_key': 'key-abc-123',
        'location_id': 'loc-1',
        'metadata': {'battery': 95},
        'created_at': '2026-11-04T09:00:00Z',
      };

      final model = AttendanceEventModel.fromJson(json);

      expect(model.id, equals('evt-100'));
      expect(model.eventType, equals(AttendanceEventType.checkIn));
      expect(model.timestampVerificationStatus, equals('SERVER_AUTHORITATIVE'));
      expect(model.reviewStatus, equals('NOT_REQUIRED'));
      expect(model.isPendingReview, isFalse);
      expect(model.isApproved, isTrue);
      expect(model.clockDriftSeconds, equals(2.0));
      expect(model.metadata, equals({'battery': 95}));
    });

    test('flags PENDING_REVIEW when review_status is PENDING_REVIEW', () {
      final json = {
        'id': 'evt-101',
        'tenant_id': 'tenant-200',
        'employee_id': 'emp-300',
        'event_type': 'CHECK_IN',
        'event_category': 'STANDARD',
        'server_received_at': '2026-11-04T09:00:00Z',
        'effective_at': '2026-11-04T09:00:00Z',
        'source': 'MOBILE',
        'timestamp_verification_status': 'SUSPICIOUS_CLOCK_DRIFT',
        'review_status': 'PENDING_REVIEW',
        'idempotency_key': 'key-xyz-789',
        'created_at': '2026-11-04T09:00:00Z',
      };

      final model = AttendanceEventModel.fromJson(json);
      expect(model.isPendingReview, isTrue);
      expect(model.isApproved, isFalse);
    });
  });

  group('PunchResponseModel Deserialization', () {
    test('parses primary event and additional events from PunchResponse', () {
      final json = {
        'event': {
          'id': 'evt-main',
          'tenant_id': 'tenant-1',
          'employee_id': 'emp-1',
          'event_type': 'CHECK_OUT',
          'server_received_at': '2026-11-04T18:00:00Z',
          'effective_at': '2026-11-04T18:00:00Z',
          'source': 'MOBILE',
          'timestamp_verification_status': 'SERVER_AUTHORITATIVE',
          'review_status': 'NOT_REQUIRED',
          'idempotency_key': 'idem-checkout-1',
          'created_at': '2026-11-04T18:00:00Z',
        },
        'additional_events': [
          {
            'id': 'evt-auto-break',
            'tenant_id': 'tenant-1',
            'employee_id': 'emp-1',
            'event_type': 'BREAK_END',
            'server_received_at': '2026-11-04T18:00:00Z',
            'effective_at': '2026-11-04T18:00:00Z',
            'source': 'MOBILE',
            'timestamp_verification_status': 'SERVER_AUTHORITATIVE',
            'review_status': 'NOT_REQUIRED',
            'idempotency_key': 'idem-checkout-1:auto_break_end',
            'created_at': '2026-11-04T18:00:00Z',
          }
        ],
        'idempotent_replay': false,
      };

      final response = PunchResponseModel.fromJson(json);

      expect(response.event.id, equals('evt-main'));
      expect(response.event.eventType, equals(AttendanceEventType.checkOut));
      expect(response.additionalEvents.length, equals(1));
      expect(response.additionalEvents.first.eventType,
          equals(AttendanceEventType.breakEnd));
      expect(response.isIdempotentReplay, isFalse);
    });
  });

  group('AttendanceDayModel, ShiftAssignmentModel, EmployeeWorkplaceModel', () {
    test('AttendanceDayModel parses projection response', () {
      final json = {
        'id': 'day-1',
        'tenant_id': 'tenant-1',
        'employee_id': 'emp-1',
        'attendance_date': '2026-11-04',
        'total_working_minutes': 480,
        'total_break_minutes': 60,
        'net_working_minutes': 420,
        'status': 'PRESENT',
        'calculation_status': 'CALCULATED',
        'last_calculated_at': '2026-11-04T18:05:00Z',
      };

      final model = AttendanceDayModel.fromJson(json);

      expect(model.id, equals('day-1'));
      expect(model.totalWorkingMinutes, equals(480));
      expect(model.totalBreakMinutes, equals(60));
      expect(model.netWorkingMinutes, equals(420));
      expect(model.status, equals('PRESENT'));
    });

    test('ShiftAssignmentModel parses shift details with formatted hours', () {
      final json = {
        'id': 'shift-assign-1',
        'shift_name': 'Morning Regular',
        'shift_code': 'MORN-REG',
        'start_time': '09:00:00',
        'end_time': '18:00:00',
        'grace_period_minutes': 15,
      };

      final model = ShiftAssignmentModel.fromJson(json);

      expect(model.name, equals('Morning Regular'));
      expect(model.formattedHours, equals('9:00 AM – 6:00 PM'));
      expect(model.gracePeriodMinutes, equals(15));
    });

    test(
        'EmployeeWorkplaceModel parses workplace details with coordinates and geofence radius',
        () {
      final json = {
        'id': 'wp-assign-1',
        'location_id': 'loc-1',
        'location_name': 'Headquarters Tower',
        'location_code': 'HQ-TWR',
        'location_address': '450 Lexington Ave',
        'location_city': 'New York',
        'location_country_code': 'US',
        'is_primary': true,
        'is_current': true,
        'latitude': 40.7531,
        'longitude': -73.9745,
        'radius_meters': 75.0,
      };

      final model = EmployeeWorkplaceModel.fromJson(json);

      expect(model.locationName, equals('Headquarters Tower'));
      expect(model.city, equals('New York'));
      expect(model.isPrimary, isTrue);
      expect(model.latitude, equals(40.7531));
      expect(model.longitude, equals(-73.9745));
      expect(model.radiusMeters, equals(75.0));
      expect(model.shortDisplay, equals('Headquarters Tower, New York'));
    });
  });

  group('AttendancePolicyModel Deserialization', () {
    test('parses GPS policy with verification constraints', () {
      final json = {
        'tenant_id': 'tenant-uuid-1',
        'version': 3,
        'default_mode': 'GPS_ONLY',
        'allowed_methods': ['GPS_ONLY'],
        'required_methods': ['GPS_ONLY'],
        'combination_rule': 'OR',
        'requires_gps': true,
        'requires_wifi': false,
        'requires_biometric': false,
        'requires_face': false,
        'max_accuracy_meters': 50,
        'max_location_age_seconds': 20,
      };

      final model = AttendancePolicyModel.fromJson(json);

      expect(model.tenantId, equals('tenant-uuid-1'));
      expect(model.version, equals(3));
      expect(model.defaultMode, equals('GPS_ONLY'));
      expect(model.requiresGps, isTrue);
      expect(model.maxAccuracyMeters, equals(50));
      expect(model.maxLocationAgeSeconds, equals(20));
      expect(model.mode, equals(PolicyVerificationMode.gpsOnly));
      expect(model.isSupportedInThisRelease, isTrue);
      expect(model.unsupportedMessage, isNull);
    });

    test('parses MANUAL policy correctly', () {
      final json = {
        'tenant_id': 'tenant-uuid-2',
        'version': 1,
        'default_mode': 'MANUAL',
        'allowed_methods': ['MANUAL'],
        'required_methods': ['MANUAL'],
        'combination_rule': 'OR',
        'requires_gps': false,
      };

      final model = AttendancePolicyModel.fromJson(json);

      expect(model.mode, equals(PolicyVerificationMode.manual));
      expect(model.requiresGps, isFalse);
      expect(model.isSupportedInThisRelease, isTrue);
      expect(model.unsupportedMessage, isNull);
    });

    test(
        'verifies WIFI_ONLY is supported and BIOMETRIC_ONLY remains unsupported',
        () {
      final wifiPolicy = AttendancePolicyModel.fromJson(const {
        'tenant_id': 'tenant-1',
        'version': 1,
        'default_mode': 'WIFI_ONLY',
        'allowed_methods': ['WIFI'],
        'required_methods': ['WIFI'],
        'combination_rule': 'OR',
        'requires_wifi': true,
        'wifi_fallback_action': 'GPS_FALLBACK',
      });

      expect(wifiPolicy.isSupportedInThisRelease, isTrue);
      expect(wifiPolicy.unsupportedMessage, isNull);
      expect(wifiPolicy.wifiFallbackAction, equals('GPS_FALLBACK'));

      final bioPolicy = AttendancePolicyModel.fromJson(const {
        'tenant_id': 'tenant-1',
        'version': 1,
        'default_mode': 'BIOMETRIC_ONLY',
        'allowed_methods': ['BIOMETRIC_ONLY'],
        'required_methods': ['BIOMETRIC_ONLY'],
        'combination_rule': 'OR',
        'requires_biometric': true,
      });

      expect(bioPolicy.isSupportedInThisRelease, isFalse);
      expect(bioPolicy.unsupportedMessage, contains('biometric'));
    });
  });
}
