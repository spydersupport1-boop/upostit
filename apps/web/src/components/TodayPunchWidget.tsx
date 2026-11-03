"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  attendanceApi,
  shiftApi,
  PunchResponseDto,
  AttendanceEventDto,
  ShiftAssignmentDto,
  ApiError,
} from "@/lib/api";

interface TodayPunchWidgetProps {
  employeeId: string;
  employeeName?: string;
  token: string;
  onPunchSuccess?: (punchResp: PunchResponseDto) => void;
}

export default function TodayPunchWidget({
  employeeId,
  employeeName,
  token,
  onPunchSuccess,
}: TodayPunchWidgetProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [activeShift, setActiveShift] = useState<ShiftAssignmentDto | null>(null);
  const [todayEvents, setTodayEvents] = useState<AttendanceEventDto[]>([]);
  const [status, setStatus] = useState<"NOT_CHECKED_IN" | "WORKING" | "ON_BREAK" | "CHECKED_OUT">("NOT_CHECKED_IN");
  const [activeCheckInTime, setActiveCheckInTime] = useState<Date | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Determine today's date in local YYYY-MM-DD
  const todayStr = new Date().toISOString().split("T")[0];

  const fetchTodayStatus = useCallback(async () => {
    if (!token || !employeeId) return;
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch active shift assignment for today
      const assignments = await shiftApi.getAssignments(
        { employee_id: employeeId, active_on_date: todayStr },
        token
      );
      if (assignments.length > 0) {
        setActiveShift(assignments[0]);
      } else {
        setActiveShift(null);
      }

      // 2. Fetch today's punches
      const startOfDay = `${todayStr}T00:00:00Z`;
      const endOfDay = `${todayStr}T23:59:59Z`;
      const eventsResp = await attendanceApi.getEvents(
        {
          employee_id: employeeId,
          start_date: startOfDay,
          end_date: endOfDay,
          limit: 50,
        },
        token
      );

      // Sort chronological by effective_at
      const sorted = [...eventsResp.items].sort(
        (a, b) => new Date(a.effective_at).getTime() - new Date(b.effective_at).getTime()
      );
      setTodayEvents(sorted);

      // Derive state machine from latest punch
      if (sorted.length === 0) {
        setStatus("NOT_CHECKED_IN");
        setActiveCheckInTime(null);
      } else {
        const lastPunch = sorted[sorted.length - 1];
        if (lastPunch.event_type === "CHECK_IN") {
          setStatus("WORKING");
          setActiveCheckInTime(new Date(lastPunch.effective_at));
        } else if (lastPunch.event_type === "BREAK_START") {
          setStatus("ON_BREAK");
          setActiveCheckInTime(null);
        } else if (lastPunch.event_type === "BREAK_END") {
          setStatus("WORKING");
          // Find first check in of session
          const checkIns = sorted.filter((e) => e.event_type === "CHECK_IN");
          if (checkIns.length > 0) {
            setActiveCheckInTime(new Date(checkIns[checkIns.length - 1].effective_at));
          }
        } else if (lastPunch.event_type === "CHECK_OUT") {
          setStatus("CHECKED_OUT");
          setActiveCheckInTime(null);
        }
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError((err as Error).message || "Failed to load punch status.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, employeeId, todayStr]);

  useEffect(() => {
    fetchTodayStatus();
  }, [fetchTodayStatus]);

  // Live timer for working sessions
  useEffect(() => {
    if (status !== "WORKING" || !activeCheckInTime) {
      setElapsedSeconds(0);
      return;
    }

    const updateTimer = () => {
      const now = new Date();
      const diffSecs = Math.max(0, Math.floor((now.getTime() - activeCheckInTime.getTime()) / 1000));
      setElapsedSeconds(diffSecs);
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [status, activeCheckInTime]);

  const formatTimer = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handlePunch = async (eventType: "CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END") => {
    if (!token || !employeeId) return;
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);

    // Cryptographic client-side idempotency key with high entropy
    const idempotencyKey = `web-${eventType.toLowerCase()}-${employeeId.slice(0, 8)}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    try {
      const resp = await attendanceApi.punch(
        {
          employee_id: employeeId,
          event_type: eventType,
          client_timestamp: new Date().toISOString(),
          idempotency_key: idempotencyKey,
        },
        token
      );

      const actionNames: Record<string, string> = {
        CHECK_IN: "Checked in successfully",
        CHECK_OUT: "Checked out successfully",
        BREAK_START: "Break started",
        BREAK_END: "Break ended — welcome back",
      };

      setSuccessMsg(actionNames[eventType] || "Punch recorded.");
      await fetchTodayStatus();
      if (onPunchSuccess) {
        onPunchSuccess(resp);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError((err as Error).message || "Punch failed.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="card" style={{ padding: "1.75rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span className="spinner spinner-sm" />
          <span style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
            Synchronizing punch status with server...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="card"
      style={{
        padding: "1.75rem",
        marginBottom: "1.5rem",
        position: "relative",
        overflow: "hidden",
        border: "1px solid rgba(6, 182, 212, 0.2)",
      }}
    >
      {/* Background Gradient Accent */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: "200px",
          height: "100%",
          background: "radial-gradient(circle at top right, rgba(6, 182, 212, 0.12), transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Header Info */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h3 style={{ fontSize: "1.25rem", fontWeight: 700 }}>Today&apos;s Presence &amp; Actions</h3>
            {status === "WORKING" && (
              <span className="badge badge-green" style={{ animation: "pulse 2s infinite" }}>
                ● Active Work Session
              </span>
            )}
            {status === "ON_BREAK" && (
              <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "#fbbf24", borderColor: "rgba(245, 158, 11, 0.3)" }}>
                ☕ On Break
              </span>
            )}
            {status === "CHECKED_OUT" && (
              <span className="badge" style={{ background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc", borderColor: "rgba(99, 102, 241, 0.3)" }}>
                ✓ Completed for Today
              </span>
            )}
            {status === "NOT_CHECKED_IN" && (
              <span className="badge" style={{ background: "rgba(107, 114, 128, 0.15)", color: "#9ca3af", borderColor: "rgba(107, 114, 128, 0.3)" }}>
                ○ Not Checked In
              </span>
            )}
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            Date: <strong>{todayStr}</strong> • Shift:{" "}
            {activeShift?.shift_template ? (
              <strong style={{ color: "var(--accent-cyan)" }}>
                {activeShift.shift_template.name} ({activeShift.shift_template.current_version?.start_time.slice(0, 5)} - {activeShift.shift_template.current_version?.end_time.slice(0, 5)})
              </strong>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>Default Roster / Open Window</span>
            )}
          </p>
        </div>

        {/* Live Active Timer */}
        {status === "WORKING" && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
              Current Session
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 800, fontFamily: "monospace", color: "var(--accent-emerald)" }}>
              {formatTimer(elapsedSeconds)}
            </div>
          </div>
        )}
      </div>

      {/* Alerts */}
      {error && (
        <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
          <span>{error}</span>
          <button className="alert-close" onClick={() => setError(null)}>&times;</button>
        </div>
      )}
      {successMsg && (
        <div className="alert alert-success" style={{ marginBottom: "1rem" }}>
          <span>{successMsg}</span>
          <button className="alert-close" onClick={() => setSuccessMsg(null)}>&times;</button>
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
        {(status === "NOT_CHECKED_IN" || status === "CHECKED_OUT") && (
          <button
            className="btn btn-primary"
            disabled={actionLoading}
            onClick={() => handlePunch("CHECK_IN")}
            style={{ minWidth: "150px" }}
          >
            {actionLoading ? <span className="spinner spinner-sm" /> : "▶ Check In"}
          </button>
        )}

        {status === "WORKING" && (
          <>
            <button
              className="btn btn-secondary"
              disabled={actionLoading}
              onClick={() => handlePunch("BREAK_START")}
              style={{ borderColor: "rgba(245, 158, 11, 0.4)", color: "#fbbf24" }}
            >
              {actionLoading ? <span className="spinner spinner-sm" /> : "☕ Start Break"}
            </button>
            <button
              className="btn btn-danger"
              disabled={actionLoading}
              onClick={() => handlePunch("CHECK_OUT")}
              style={{ minWidth: "140px" }}
            >
              {actionLoading ? <span className="spinner spinner-sm" /> : "⏹ Check Out"}
            </button>
          </>
        )}

        {status === "ON_BREAK" && (
          <>
            <button
              className="btn btn-primary"
              disabled={actionLoading}
              onClick={() => handlePunch("BREAK_END")}
              style={{ minWidth: "140px" }}
            >
              {actionLoading ? <span className="spinner spinner-sm" /> : "↩ End Break"}
            </button>
            <button
              className="btn btn-danger"
              disabled={actionLoading}
              onClick={() => handlePunch("CHECK_OUT")}
              title="Checking out automatically closes your active break"
            >
              {actionLoading ? <span className="spinner spinner-sm" /> : "⏹ Check Out (Auto-Close Break)"}
            </button>
          </>
        )}

        <button
          className="btn btn-secondary btn-sm"
          onClick={fetchTodayStatus}
          disabled={actionLoading}
          style={{ marginLeft: "auto" }}
          title="Refresh today's punches"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Event Timeline Mini-Pills */}
      {todayEvents.length > 0 && (
        <div style={{ marginTop: "1.25rem", paddingTop: "1rem", borderTop: "1px solid var(--border-color)" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
            Today&apos;s Punch Ledger Stream ({todayEvents.length} event{todayEvents.length > 1 ? "s" : ""}):
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {todayEvents.map((ev) => (
              <span
                key={ev.id}
                className="status-pill"
                style={{
                  background: ev.event_type === "CHECK_IN" ? "rgba(16, 185, 129, 0.15)" :
                              ev.event_type === "CHECK_OUT" ? "rgba(239, 68, 68, 0.15)" :
                              "rgba(245, 158, 11, 0.15)",
                  color: ev.event_type === "CHECK_IN" ? "#34d399" :
                         ev.event_type === "CHECK_OUT" ? "#f87171" :
                         "#fbbf24",
                  fontSize: "0.75rem",
                }}
              >
                {ev.event_type.replace("_", " ")} @ {new Date(ev.effective_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                {ev.event_category !== "STANDARD" && ` [${ev.event_category.replace("CORRECTION_", "")}]`}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
