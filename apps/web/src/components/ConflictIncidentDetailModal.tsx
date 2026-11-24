"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  conflictApi,
  locationApi,
  AttendanceConflictIncidentDetailDto,
  LocationDto,
  ApiError,
} from "@/lib/api";

interface ConflictIncidentDetailModalProps {
  incidentId: string;
  token: string;
  currentUserRole?: string | null;
  currentUserId?: string | null;
  onClose: () => void;
  onDecisionSuccess?: () => void;
}

export default function ConflictIncidentDetailModal({
  incidentId,
  token,
  currentUserRole,
  currentUserId,
  onClose,
  onDecisionSuccess,
}: ConflictIncidentDetailModalProps) {
  const [incident, setIncident] = useState<AttendanceConflictIncidentDetailDto | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Adjudication form state
  const [decisionAction, setDecisionAction] = useState<
    | "APPROVE"
    | "REJECT"
    | "ACCEPT_SEQUENCE"
    | "REJECT_INVALID_EVENTS"
    | "REQUEST_CLARIFICATION"
    | "MARK_UNRESOLVED"
    | "ESCALATE_HR"
    | null
  >(null);
  const [decisionReason, setDecisionReason] = useState<string>("");
  const [overrideLocationId, setOverrideLocationId] = useState<string>("");
  const [locations, setLocations] = useState<LocationDto[]>([]);
  const [submittingDecision, setSubmittingDecision] = useState<boolean>(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionSuccess, setDecisionSuccess] = useState<string | null>(null);

  const fetchIncidentDetail = useCallback(async () => {
    if (!incidentId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await conflictApi.getIncidentDetail(incidentId, token);
      setIncident(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError((err as Error).message || "Failed to load incident detail.");
      }
    } finally {
      setLoading(false);
    }
  }, [incidentId, token]);

  useEffect(() => {
    fetchIncidentDetail();
  }, [fetchIncidentDetail]);

  // Load locations if user wants to override location on approval
  useEffect(() => {
    if (!token || currentUserRole === "employee") return;
    locationApi
      .getLocations({ is_active: true }, token)
      .then((res) => setLocations(res.items || []))
      .catch(() => {});
  }, [token, currentUserRole]);

  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decisionAction || !incidentId || !token) return;

    const trimmedReason = decisionReason.trim();
    if (trimmedReason.length < 3) {
      setDecisionError("Decision reason must contain at least 3 non-whitespace characters.");
      return;
    }

    setSubmittingDecision(true);
    setDecisionError(null);
    setDecisionSuccess(null);

    try {
      const resp = await conflictApi.adjudicateIncident(
        incidentId,
        {
          action: decisionAction,
          reason: trimmedReason,
          override_location_id: overrideLocationId ? overrideLocationId : null,
        },
        token
      );

      setDecisionSuccess(
        `Incident successfully ${resp.decision === "APPROVE" ? "APPROVED" : "REJECTED"}. ${
          resp.decision === "APPROVE"
            ? `Attendance recalculated (${resp.recalculated_days_count} day(s) updated).`
            : "Ledger left intact."
        }`
      );
      setDecisionAction(null);
      setDecisionReason("");
      setOverrideLocationId("");

      // Refresh incident forensic view
      await fetchIncidentDetail();

      if (onDecisionSuccess) {
        onDecisionSuccess();
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setDecisionError("Conflict Error (409): This incident was already adjudicated by another supervisor.");
        } else if (err.status === 403) {
          setDecisionError(`Authorization Denied (403): ${err.detail}`);
        } else if (err.status === 422) {
          setDecisionError(`Validation Error (422): ${err.detail}`);
        } else {
          setDecisionError(err.detail);
        }
      } else {
        setDecisionError("Network error while submitting adjudication decision.");
      }
    } finally {
      setSubmittingDecision(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "PENDING_REVIEW":
        return <span className="badge badge-yellow">Pending Review</span>;
      case "APPROVED":
        return <span className="badge badge-green">Approved</span>;
      case "REJECTED":
        return <span className="badge badge-red">Rejected</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  const formatTimestamp = (iso: string | null | undefined): string => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })}`;
    } catch {
      return iso;
    }
  };

  const canAdjudicate =
    currentUserRole &&
    ["manager", "hr", "admin", "owner"].includes(currentUserRole.toLowerCase()) &&
    incident?.status === "PENDING_REVIEW" &&
    incident?.employee?.id !== currentUserId;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "780px", maxHeight: "90vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="modal-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 className="modal-title">Offline Attendance Conflict Detail</h2>
              {incident && getStatusBadge(incident.status)}
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              Bundle ID: <code style={{ color: "var(--accent-cyan)" }}>{incident?.bundle_id || incidentId}</code>
            </p>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onClose}
            style={{ fontSize: "1.25rem", padding: "0.2rem 0.5rem" }}
          >
            &times;
          </button>
        </div>

        {/* Loading / Error States */}
        {loading && (
          <div className="spinner-container" style={{ padding: "3rem" }}>
            <div className="spinner" />
            <p style={{ color: "var(--text-secondary)", marginTop: "1rem" }}>
              Loading forensic conflict telemetry...
            </p>
          </div>
        )}

        {error && (
          <div className="alert alert-danger" style={{ margin: "1rem 0" }}>
            <span>{error}</span>
          </div>
        )}

        {decisionSuccess && (
          <div className="alert alert-success" style={{ margin: "1rem 0" }}>
            <span>{decisionSuccess}</span>
          </div>
        )}

        {incident && !loading && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginTop: "1rem" }}>
            {/* 1. Employee Info Card */}
            <div
              className="card"
              style={{
                padding: "1rem 1.25rem",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "0.75rem",
              }}
            >
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Employee</div>
                <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                  {incident.employee.first_name} {incident.employee.last_name}
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  {incident.employee.employee_code} • {incident.employee.work_email}
                </div>
              </div>

              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Department</div>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  {incident.employee.department_name || "—"}
                </div>
              </div>

              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Submission Timestamp</div>
                <div style={{ fontSize: "0.85rem" }}>
                  {formatTimestamp(incident.submitted_at)}
                </div>
              </div>

              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Session ID</div>
                <div style={{ fontSize: "0.85rem", fontFamily: "monospace" }}>
                  {incident.session_id ? incident.session_id.substring(0, 13) : "Offline Session"}
                </div>
              </div>
            </div>

            {/* Phase 11.5 Conflict Code, Severity, and Classification */}
            <div
              style={{
                display: "flex",
                gap: "0.75rem",
                flexWrap: "wrap",
                alignItems: "center",
                background: "rgba(255, 255, 255, 0.02)",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid var(--border-color)",
              }}
            >
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Conflict Classification:
              </div>
              <span className="badge badge-yellow" style={{ fontFamily: "monospace", fontWeight: 700 }}>
                {incident.conflict_code || "SEQUENCE_CONFLICT"}
              </span>
              <span
                className={`badge ${
                  incident.severity === "CRITICAL"
                    ? "badge-red"
                    : incident.severity === "HIGH"
                    ? "badge-yellow"
                    : "badge"
                }`}
                style={{ fontWeight: 700 }}
              >
                Severity: {incident.severity || "MEDIUM"}
              </span>
              <span className="badge badge-purple">
                {incident.classification || "NEEDS_MANAGER_REVIEW"}
              </span>
            </div>

            {/* Employee Clarification (if submitted) */}
            {incident.employee_clarification && (
              <div
                style={{
                  background: "rgba(16, 185, 129, 0.08)",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                  borderRadius: "8px",
                  padding: "0.85rem 1.25rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.8rem", color: "#34d399", fontWeight: 700 }}>
                    💬 Employee Clarification:
                  </span>
                  {incident.clarification_submitted_at && (
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Submitted {formatTimestamp(incident.clarification_submitted_at)}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: "0.9rem", marginTop: "0.35rem", color: "var(--text-primary)" }}>
                  {incident.employee_clarification}
                </p>
              </div>
            )}

            {/* Employee Explanation Notes (if any) */}
            {incident.employee_notes && (
              <div
                style={{
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid var(--border-color)",
                  borderRadius: "8px",
                  padding: "0.85rem 1.25rem",
                }}
              >
                <div style={{ fontSize: "0.75rem", color: "var(--accent-cyan)", fontWeight: 700 }}>
                  Employee Context Note:
                </div>
                <p style={{ fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)" }}>
                  {incident.employee_notes}
                </p>
              </div>
            )}

            {/* 2. Adjudication Summary (if decided) */}
            {incident.decision && (
              <div
                className={`alert ${
                  incident.decision === "APPROVE" ? "alert-success" : "alert-danger"
                }`}
                style={{ margin: 0 }}
              >
                <div>
                  <div style={{ fontWeight: 700, marginBottom: "0.25rem" }}>
                    Supervisor Decision: {incident.decision}
                  </div>
                  <div style={{ fontSize: "0.85rem" }}>
                    Reason: <em>&ldquo;{incident.decision_reason}&rdquo;</em>
                  </div>
                  <div style={{ fontSize: "0.75rem", opacity: 0.8, marginTop: "0.35rem" }}>
                    Decided at: {formatTimestamp(incident.decided_at)} • Reviewer UUID:{" "}
                    <code>{incident.reviewer_user_id || "System"}</code>
                  </div>
                  {incident.resolved_correction_event_ids &&
                    incident.resolved_correction_event_ids.length > 0 && (
                      <div style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                        Resolved Corrections: {incident.resolved_correction_event_ids.join(", ")}
                      </div>
                    )}
                </div>
              </div>
            )}

            {/* 3. Forensic Event Timeline */}
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.75rem" }}>
                Chronological Forensic Timeline ({incident.total_events_count} events in session)
              </h3>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {/* Primary Rejected Event */}
                <div
                  style={{
                    border: "1px solid rgba(239, 68, 68, 0.4)",
                    background: "rgba(239, 68, 68, 0.05)",
                    borderRadius: "8px",
                    padding: "1rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className="badge badge-red">
                          {incident.primary_rejected_event.event_type || "CHECK_IN"}
                        </span>
                        <span style={{ fontWeight: 700, color: "#f87171", fontSize: "0.9rem" }}>
                          Primary Rejected Punch
                        </span>
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                        Device Timestamp:{" "}
                        <strong>{formatTimestamp(incident.primary_rejected_event.device_reported_at)}</strong>
                      </div>
                    </div>
                    <span className="badge">Sequence #1</span>
                  </div>

                  {/* Rejection Details */}
                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.3)",
                      padding: "0.6rem 0.85rem",
                      borderRadius: "6px",
                      marginTop: "0.75rem",
                      fontSize: "0.825rem",
                    }}
                  >
                    <div style={{ color: "#f87171", fontWeight: 600 }}>
                      Server Rejection Reason:{" "}
                      {incident.primary_rejected_event.server_rejection_reason ||
                        incident.rejection_summary ||
                        "Policy rejection"}
                    </div>
                    {incident.primary_rejected_event.server_rejection_code && (
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        Status Code: {incident.primary_rejected_event.server_rejection_code}
                      </div>
                    )}
                  </div>

                  {/* Telemetry Evidence Grid */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                      gap: "0.5rem",
                      marginTop: "0.75rem",
                      fontSize: "0.775rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <div>
                      📍 GPS:{" "}
                      {incident.primary_rejected_event.latitude !== null &&
                      incident.primary_rejected_event.latitude !== undefined
                        ? `${incident.primary_rejected_event.latitude?.toFixed(4)}, ${incident.primary_rejected_event.longitude?.toFixed(4)} (±${incident.primary_rejected_event.accuracy_meters}m)`
                        : "No GPS coordinates"}
                    </div>
                    <div>
                      🛡️ Mock GPS:{" "}
                      {incident.primary_rejected_event.is_mock_location ? (
                        <span style={{ color: "#f87171", fontWeight: 700 }}>DETECTED (MOCKED)</span>
                      ) : (
                        <span style={{ color: "#34d399" }}>Genuine (Hardware)</span>
                      )}
                    </div>
                    <div>
                      📶 Wi-Fi:{" "}
                      {incident.primary_rejected_event.wifi_ssid
                        ? `${incident.primary_rejected_event.wifi_ssid} (${incident.primary_rejected_event.wifi_bssid || "BSSID"})`
                        : "No Wi-Fi telemetry"}
                    </div>
                    <div>
                      📱 Device:{" "}
                      {incident.primary_rejected_event.device_model || "Mobile Device"} (
                      {incident.primary_rejected_event.os_version || "OS"})
                    </div>
                    <div style={{ gridColumn: "1 / -1", wordBreak: "break-all" }}>
                      🔑 Idempotency Key: <code>{incident.primary_rejected_event.idempotency_key}</code>
                    </div>
                  </div>
                </div>

                {/* Dependent Quarantined Events */}
                {incident.dependent_events && incident.dependent_events.length > 0 ? (
                  incident.dependent_events.map((dep, idx) => (
                    <div
                      key={dep.local_id || idx}
                      style={{
                        border: "1px solid rgba(99, 102, 241, 0.3)",
                        background: "rgba(99, 102, 241, 0.04)",
                        borderRadius: "8px",
                        padding: "0.85rem 1rem",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span className="badge badge-purple">{dep.event_type}</span>
                          <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "#a5b4fc" }}>
                            Quarantined Downstream Punch
                          </span>
                        </div>
                        <span className="badge">Sequence #{idx + 2}</span>
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                          gap: "0.4rem",
                          marginTop: "0.5rem",
                          fontSize: "0.775rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <div>
                          Device Time: <strong>{formatTimestamp(dep.device_reported_at)}</strong>
                        </div>
                        <div>
                          GPS:{" "}
                          {dep.latitude !== null && dep.latitude !== undefined
                            ? `${dep.latitude?.toFixed(4)}, ${dep.longitude?.toFixed(4)}`
                            : "—"}
                        </div>
                        <div style={{ gridColumn: "1 / -1", wordBreak: "break-all" }}>
                          Idempotency: <code>{dep.idempotency_key}</code>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div
                    style={{
                      padding: "0.75rem",
                      textAlign: "center",
                      color: "var(--text-muted)",
                      fontSize: "0.85rem",
                    }}
                  >
                    No downstream dependent events were quarantined in this session.
                  </div>
                )}
              </div>
            </div>

            {/* 4. Adjudication Action Area (for authorized supervisors) */}
            {canAdjudicate && (
              <div
                style={{
                  borderTop: "1px solid var(--border-color)",
                  paddingTop: "1.25rem",
                  marginTop: "0.5rem",
                }}
              >
                {!decisionAction ? (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "1rem",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>Supervisor Adjudication</div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        Select resolution action. Approval creates audited correction events and recalculates daily timesheets.
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setDecisionAction("REQUEST_CLARIFICATION");
                          setDecisionError(null);
                        }}
                      >
                        Request Clarification
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ color: "#f97316", borderColor: "rgba(249, 115, 22, 0.4)" }}
                        onClick={() => {
                          setDecisionAction("MARK_UNRESOLVED");
                          setDecisionError(null);
                        }}
                      >
                        Mark Unresolved
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ color: "#ef4444", borderColor: "rgba(239, 68, 68, 0.4)" }}
                        onClick={() => {
                          setDecisionAction("ESCALATE_HR");
                          setDecisionError(null);
                        }}
                      >
                        Escalate HR
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => {
                          setDecisionAction("REJECT_INVALID_EVENTS");
                          setDecisionError(null);
                        }}
                      >
                        Reject Events
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ background: "#059669", borderColor: "#059669" }}
                        onClick={() => {
                          setDecisionAction("ACCEPT_SEQUENCE");
                          setDecisionError(null);
                        }}
                      >
                        Accept Sequence
                      </button>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleDecisionSubmit}>
                    <div
                      style={{
                        background: "rgba(0, 0, 0, 0.25)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "8px",
                        padding: "1rem",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: "0.75rem",
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 700,
                            color:
                              decisionAction === "APPROVE" || decisionAction === "ACCEPT_SEQUENCE"
                                ? "#34d399"
                                : "#f87171",
                          }}
                        >
                          Confirm Action: {decisionAction}
                        </span>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setDecisionAction(null)}
                        >
                          Cancel
                        </button>
                      </div>

                      {decisionError && (
                        <div className="alert alert-danger" style={{ marginBottom: "0.75rem" }}>
                          <span>{decisionError}</span>
                        </div>
                      )}

                      <div className="form-group">
                        <label className="form-label">
                          Mandatory Decision Reason <span style={{ color: "#f87171" }}>*</span>
                        </label>
                        <textarea
                          required
                          rows={3}
                          className="form-control"
                          placeholder="Explain reason for this decision (minimum 3 characters)..."
                          value={decisionReason}
                          onChange={(e) => setDecisionReason(e.target.value)}
                        />
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: "0.75rem",
                            color: "var(--text-muted)",
                            marginTop: "0.25rem",
                          }}
                        >
                          <span>Minimum 3 non-whitespace characters required</span>
                          <span>{decisionReason.trim().length} chars</span>
                        </div>
                      </div>

                      {(decisionAction === "APPROVE" || decisionAction === "ACCEPT_SEQUENCE") && locations.length > 0 && (
                        <div className="form-group" style={{ marginTop: "0.75rem" }}>
                          <label className="form-label">Workplace Location Override (Optional)</label>
                          <select
                            className="form-control"
                            value={overrideLocationId}
                            onChange={(e) => setOverrideLocationId(e.target.value)}
                          >
                            <option value="">Keep original reported / policy location</option>
                            {locations.map((loc) => (
                              <option key={loc.id} value={loc.id}>
                                {loc.name} {loc.code ? `(${loc.code})` : ""}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      <div
                        style={{
                          display: "flex",
                          justifyContent: "flex-end",
                          gap: "0.75rem",
                          marginTop: "1rem",
                        }}
                      >
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => setDecisionAction(null)}
                          disabled={submittingDecision}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className={`btn ${
                            decisionAction === "APPROVE" ? "btn-primary" : "btn-danger"
                          }`}
                          style={
                            decisionAction === "APPROVE"
                              ? { background: "#059669", borderColor: "#059669" }
                              : {}
                          }
                          disabled={submittingDecision || decisionReason.trim().length < 3}
                        >
                          {submittingDecision
                            ? "Submitting..."
                            : `Confirm & ${decisionAction === "APPROVE" ? "Approve" : "Reject"}`}
                        </button>
                      </div>
                    </div>
                  </form>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
