"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  attendanceApi,
  AttendanceDayDto,
  AttendanceEventAuditDto,
  AttendanceCorrectionType,
  ApiError,
} from "@/lib/api";

interface AttendanceCorrectionModalProps {
  employeeId: string;
  employeeName: string;
  attendanceDay: AttendanceDayDto | null;
  token: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AttendanceCorrectionModal({
  employeeId,
  employeeName,
  attendanceDay,
  token,
  onClose,
  onSuccess,
}: AttendanceCorrectionModalProps) {
  const [correctionType, setCorrectionType] = useState<AttendanceCorrectionType>("CORRECTION_INSERT");
  const [eventType, setEventType] = useState<"CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END">("CHECK_OUT");

  // Default effective datetime to the attendance date at 18:00
  const initialDateStr = attendanceDay?.attendance_date || new Date().toISOString().split("T")[0];
  const [effectiveDateTime, setEffectiveDateTime] = useState<string>(`${initialDateStr}T18:00`);
  const [correctionReason, setCorrectionReason] = useState<string>("");
  const [selectedTargetEventId, setSelectedTargetEventId] = useState<string>("");

  const [candidateEvents, setCandidateEvents] = useState<AttendanceEventAuditDto[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load candidate punches from target attendance day
  const fetchCandidateEvents = useCallback(async () => {
    if (!attendanceDay || !token) return;
    setLoadingCandidates(true);
    try {
      const resp = await attendanceApi.getDayEvents(attendanceDay.id, token);
      // Candidates for supersede/void: active events that are not already voided or superseded
      const validCandidates = resp.items.filter(
        (ev) => !ev.voided_by_event_id && !ev.superseded_by_event_id && ev.event_category !== "CORRECTION_VOID"
      );
      setCandidateEvents(validCandidates);
      if (validCandidates.length > 0 && !selectedTargetEventId) {
        setSelectedTargetEventId(validCandidates[0].id);
      }
    } catch {
      // Non-blocking fallback
    } finally {
      setLoadingCandidates(false);
    }
  }, [attendanceDay, token, selectedTargetEventId]);

  useEffect(() => {
    if (correctionType !== "CORRECTION_INSERT") {
      fetchCandidateEvents();
    }
  }, [correctionType, fetchCandidateEvents]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);

    // Validation
    const cleanReason = correctionReason.trim();
    if (cleanReason.length < 5) {
      setError("Correction reason must contain at least 5 non-whitespace characters.");
      return;
    }

    if (correctionType !== "CORRECTION_INSERT" && !selectedTargetEventId) {
      setError("Please select the target attendance event you wish to supersede or void.");
      return;
    }

    setSubmitting(true);

    // Generate unique client idempotency key
    const idempotencyKey = `corr-${correctionType.toLowerCase()}-${employeeId.slice(0, 8)}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    try {
      let isoTimestamp: string | undefined = undefined;
      if (correctionType !== "CORRECTION_VOID" && effectiveDateTime) {
        // Convert local datetime to UTC ISO string
        isoTimestamp = new Date(effectiveDateTime).toISOString();
      }

      await attendanceApi.createCorrection(
        {
          employee_id: employeeId,
          correction_type: correctionType,
          event_type: correctionType === "CORRECTION_VOID" ? undefined : eventType,
          effective_at: isoTimestamp,
          supersedes_event_id: correctionType === "CORRECTION_INSERT" ? null : selectedTargetEventId,
          correction_reason: cleanReason,
          idempotency_key: idempotencyKey,
        },
        token
      );

      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setError("Permission denied: You do not have authorization to correct this employee's attendance.");
        } else if (err.status === 409) {
          setError("Conflict: A concurrent correction or divergent payload was detected with this request.");
        } else {
          setError(err.detail);
        }
      } else {
        setError((err as Error).message || "Failed to submit attendance correction.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const selectedTarget = candidateEvents.find((e) => e.id === selectedTargetEventId);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "600px" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Administrative Attendance Correction</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              Target: <strong>{employeeName}</strong> • Date: <strong>{attendanceDay?.attendance_date || initialDateStr}</strong>
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onClose} style={{ fontSize: "1.25rem", padding: "0.2rem 0.5rem" }}>
            &times;
          </button>
        </div>

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
            <span>{error}</span>
            <button className="alert-close" onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Correction Mode Tabs */}
          <div className="form-group">
            <label className="form-label">Correction Operation</label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
              <button
                type="button"
                className={`btn btn-sm ${correctionType === "CORRECTION_INSERT" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setCorrectionType("CORRECTION_INSERT");
                  setError(null);
                }}
              >
                + Insert Missing
              </button>
              <button
                type="button"
                className={`btn btn-sm ${correctionType === "CORRECTION_SUPERSEDE" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setCorrectionType("CORRECTION_SUPERSEDE");
                  setError(null);
                }}
              >
                ✎ Supersede
              </button>
              <button
                type="button"
                className={`btn btn-sm ${correctionType === "CORRECTION_VOID" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setCorrectionType("CORRECTION_VOID");
                  setError(null);
                }}
              >
                ⊘ Void Punch
              </button>
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.4rem" }}>
              {correctionType === "CORRECTION_INSERT" && "Appends a missing punch event without altering past punches."}
              {correctionType === "CORRECTION_SUPERSEDE" && "Replaces an incorrect punch with a corrected event while keeping the original intact."}
              {correctionType === "CORRECTION_VOID" && "Marks an accidental punch as voided so it is excluded from calculations."}
            </p>
          </div>

          {/* Target Event Selection for Supersede and Void */}
          {correctionType !== "CORRECTION_INSERT" && (
            <div className="form-group" style={{ background: "rgba(0,0,0,0.25)", padding: "1rem", borderRadius: "8px", border: "1px solid var(--border-color)" }}>
              <label className="form-label">Target Punch to {correctionType === "CORRECTION_VOID" ? "Void" : "Supersede"}</label>
              {loadingCandidates ? (
                <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Loading punches for this day...</div>
              ) : candidateEvents.length === 0 ? (
                <div style={{ fontSize: "0.85rem", color: "#f87171" }}>
                  No active punches found on this attendance date to correct.
                </div>
              ) : (
                <select
                  className="filter-select"
                  style={{ width: "100%", marginBottom: "0.5rem" }}
                  value={selectedTargetEventId}
                  onChange={(e) => setSelectedTargetEventId(e.target.value)}
                  required
                >
                  {candidateEvents.map((ev) => (
                    <option key={ev.id} value={ev.id}>
                      {ev.event_type} @ {new Date(ev.effective_at).toLocaleTimeString()} ({ev.event_category})
                    </option>
                  ))}
                </select>
              )}

              {selectedTarget && (
                <div style={{ fontSize: "0.775rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
                  Selected: <strong>{selectedTarget.event_type}</strong> effective at{" "}
                  <strong>{new Date(selectedTarget.effective_at).toLocaleString()}</strong>
                  <div style={{ color: "var(--text-muted)", marginTop: "0.15rem" }}>
                    ID: <code>{selectedTarget.id}</code>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* New Event Type (Only for INSERT and SUPERSEDE) */}
          {correctionType !== "CORRECTION_VOID" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              <div className="form-group">
                <label className="form-label">Punch Type</label>
                <select
                  className="filter-select"
                  style={{ width: "100%" }}
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value as "CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END")}
                >
                  <option value="CHECK_IN">Check In</option>
                  <option value="CHECK_OUT">Check Out</option>
                  <option value="BREAK_START">Break Start</option>
                  <option value="BREAK_END">Break End</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Corrected Effective Date & Time</label>
                <input
                  type="datetime-local"
                  className="search-input"
                  style={{ width: "100%", maxWidth: "100%" }}
                  value={effectiveDateTime}
                  onChange={(e) => setEffectiveDateTime(e.target.value)}
                  required
                />
              </div>
            </div>
          )}

          {/* Mandatory Correction Reason */}
          <div className="form-group">
            <label className="form-label">
              Audit Reason <span style={{ color: "#f87171" }}>*</span>
            </label>
            <textarea
              className="search-input"
              style={{ width: "100%", maxWidth: "100%", minHeight: "80px", resize: "vertical" }}
              placeholder="Provide a specific audit reason (e.g., 'Employee badge failed at front desk', 'Approved manual punch per supervisor', minimum 5 characters)..."
              value={correctionReason}
              onChange={(e) => setCorrectionReason(e.target.value)}
              required
              minLength={5}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
              <span>Permanent audit trail record</span>
              <span>{correctionReason.trim().length} / 5 min characters</span>
            </div>
          </div>

          {/* Modal Actions */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || (correctionType !== "CORRECTION_INSERT" && !selectedTargetEventId)}
            >
              {submitting ? (
                <>
                  <span className="spinner spinner-sm" />
                  Applying Correction...
                </>
              ) : (
                "Apply & Recalculate Projection"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
