"""Pydantic schemas for fraud signals, evidence telemetry, rules, risk scoring, and audit flags."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FraudSignalType(StrEnum):
    """Categorized fraud signal classifications."""

    MOCK_LOCATION_DETECTED = "MOCK_LOCATION_DETECTED"
    POOR_GPS_ACCURACY = "POOR_GPS_ACCURACY"
    STALE_GPS_LOCATION = "STALE_GPS_LOCATION"
    SUSPICIOUS_CLOCK_DRIFT = "SUSPICIOUS_CLOCK_DRIFT"
    IMPOSSIBLE_TRAVEL_VELOCITY = "IMPOSSIBLE_TRAVEL_VELOCITY"
    UNREGISTERED_DEVICE = "UNREGISTERED_DEVICE"
    DEVICE_MISMATCH = "DEVICE_MISMATCH"
    REVOKED_DEVICE = "REVOKED_DEVICE"
    REVOKED_DEVICE_ATTEMPT = "REVOKED_DEVICE_ATTEMPT"
    PENDING_APPROVAL_DEVICE = "PENDING_APPROVAL_DEVICE"


class FraudSignalSeverity(StrEnum):
    """Severity ratings for fraud signals."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(StrEnum):
    """Deterministic composite risk rating classifications."""

    NORMAL = "NORMAL"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class FraudSignal(BaseModel):
    """Structured fraud risk signal generated during punch verification."""

    signal_type: FraudSignalType
    severity: FraudSignalSeverity
    reason: str
    source: str
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class VelocityResult(BaseModel):
    """Result of sequential punch velocity calculation."""

    velocity_mps: float
    distance_meters: float
    elapsed_seconds: float
    is_impossible: bool
    threshold_mps: float = 250.0
    previous_event_id: str | None = None
    previous_event_time: datetime | None = None
    previous_latitude: float | None = None
    previous_longitude: float | None = None


class ClockDriftResult(BaseModel):
    """Result of clock drift analysis."""

    drift_seconds: float
    is_suspicious: bool
    status: str
    threshold_seconds: float = 300.0


class GpsEvidenceResult(BaseModel):
    """Evaluated GPS evidence outcome."""

    status: str
    is_mock_reported: bool = False
    is_stale: bool = False
    is_poor_accuracy: bool = False
    accuracy_meters: float | None = None
    fix_age_seconds: float | None = None


class FraudRuleCreateRequest(BaseModel):
    """Payload to register or override a tenant fraud rule."""

    rule_code: str = Field(..., min_length=2, max_length=64)
    rule_name: str = Field(..., min_length=2, max_length=128)
    description: str | None = None
    enabled: bool = True
    severity: FraudSignalSeverity = FraudSignalSeverity.HIGH
    risk_weight: int = Field(default=25, ge=0, le=100)
    threshold_config: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False


class FraudRuleUpdateRequest(BaseModel):
    """Payload to update an existing tenant fraud rule."""

    rule_name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = None
    enabled: bool | None = None
    severity: FraudSignalSeverity | None = None
    risk_weight: int | None = Field(default=None, ge=0, le=100)
    threshold_config: dict[str, Any] | None = None
    review_required: bool | None = None


class FraudRuleResponse(BaseModel):
    """Serialized representation of a tenant fraud rule."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    rule_code: str
    rule_name: str
    description: str | None = None
    enabled: bool
    severity: str
    risk_weight: int
    threshold_config: dict[str, Any]
    review_required: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class FraudRuleListResponse(BaseModel):
    """Paginated list of tenant fraud rules."""

    items: list[FraudRuleResponse]
    total: int


class FraudFlagResponse(BaseModel):
    """Serialized representation of an immutable fraud flag."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    attendance_event_id: uuid.UUID
    employee_id: uuid.UUID
    device_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    signal_code: str
    severity: str
    risk_weight: int
    description: str
    evidence_json: dict[str, Any]
    detected_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class FraudFlagListResponse(BaseModel):
    """Paginated list of immutable fraud flags."""

    items: list[FraudFlagResponse]
    total: int


class RiskScoreResult(BaseModel):
    """Deterministic risk score calculation outcome."""

    total_score: int = Field(ge=0, le=100)
    risk_category: RiskCategory
    is_review_required: bool
    applied_flags: list[FraudFlagResponse] = Field(default_factory=list)
    triggered_signals_count: int = 0


class FraudEvidenceAssessment(BaseModel):
    """Aggregated outcome of all Phase 7 fraud telemetry, rules, and scoring."""

    signals: list[FraudSignal] = Field(default_factory=list)
    review_status: str = "NOT_REQUIRED"
    risk_score_result: RiskScoreResult | None = None
    velocity_result: VelocityResult | None = None
    clock_drift_result: ClockDriftResult | None = None
    gps_evidence_result: GpsEvidenceResult | None = None
    device_validation_status: str | None = None
    device_id_uuid: uuid.UUID | None = None


class FraudReviewDecisionRequest(BaseModel):
    """Payload to adjudicate a pending fraud review with approval or rejection."""

    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$", description="Adjudication decision: APPROVED or REJECTED.")
    reason: str = Field(..., min_length=3, max_length=2000, description="Mandatory reason for decision (min 3 chars).")
    notes: str | None = Field(default=None, max_length=4000, description="Optional extra notes.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary audit metadata.")


class FraudReviewHistoryItem(BaseModel):
    """Historical audit entry of a reviewer decision on an attendance event."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    attendance_event_id: uuid.UUID
    reviewer_user_id: uuid.UUID
    reviewer_name: str | None = None
    reviewer_email: str | None = None
    reviewer_role: str
    decision: str
    reason: str
    notes: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class FraudReviewDecisionResponse(BaseModel):
    """Response payload returned upon successful adjudication of a fraud review."""

    success: bool = True
    message: str
    review: FraudReviewHistoryItem
    updated_review_status: str
    recalculated_day_id: uuid.UUID | None = None


class FraudEventReviewDetailResponse(BaseModel):
    """Comprehensive forensic detail for HR/Admin inspection of a flagged event."""

    attendance_event_id: uuid.UUID
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_code: str | None = None
    employee_department: str | None = None
    event_type: str
    effective_at: datetime
    server_received_at: datetime
    source: str
    review_status: str
    risk_score: int = 0
    risk_category: str = "NORMAL"
    timestamp_verification_status: str
    clock_drift_seconds: float | None = None
    location: dict[str, Any] | None = None
    device: dict[str, Any] | None = None
    shift: dict[str, Any] | None = None
    signals: list[FraudFlagResponse] = Field(default_factory=list)
    review_history: list[FraudReviewHistoryItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}

