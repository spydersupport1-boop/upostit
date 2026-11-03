"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  attendanceApi,
  AttendanceEventAuditDto,
  ApiError,
} from "@/lib/api";

interface AttendanceAuditDrawerProps {
  recordId: string | null;
  employeeName?: string | null;
  attendanceDate?: string | null;
  token: string;
  onClose: () => void;
}

export default function AttendanceAuditDrawer({
  recordId,
  employeeName,
  attendanceDate,
  token,
  onClose,
}: AttendanceAuditDrawerProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [events, setEvents] = useState<AttendanceEventAuditDto[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchAuditEvents = useCallback(async () => {
    if (!recordId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await attendanceApi.getDayEvents(recordId, token);
      setEvents(resp.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError((err as Error).message || "Failed to load audit history.");
      }
    } finally {
      setLoading(false);
    }
  }, [recordId, token]);

  useEffect(() => {
    if (recordId) {
      fetchAuditEvents();
    }
  }, [recordId, fetchAuditEvents]);

  if (!recordId) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "680px", maxHeight: "88vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="modal-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 className="modal-title">Event Timeline & Audit Trail</h2>
              <span className="badge">Append-Only Ledger</span>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              {employeeName ? <strong>{employeeName}</strong> : "Employee"} • Date: <strong>{attendanceDate || "Target Date"}</strong>
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onClose} style={{ fontSize: "1.25rem", padding: "0.2rem 0.5rem" }}>
            &times;
          </button>
        </div>

        {/* Ledger Invariant Banner */}
        <div
          className="alert alert-info"
          style={{
            fontSize: "0.8rem",
            marginBottom: "1.25rem",
            background: "rgba(6, 182, 212, 0.08)",
            border: "1px solid rgba(6, 182, 212, 0.2)",
          }}
        >
          <span>
            🛡️ <strong>Ledger Immutability Guarantee:</strong> Original punch events are never mutated or deleted.
            Corrections append new records referencing prior events via <code style={{ color: "var(--accent-cyan)" }}>supersedes_event_id</code>.
          </span>
        </div>

        {/* Content Body */}
        {loading && (
          <div className="spinner-container" style={{ padding: "3rem 1rem" }}>
            <div className="spinner" />
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Loading audit stream from database ledger...
            </p>
          </div>
        )}

        {error && (
          <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
            <span>{error}</span>
            <button className="alert-close" onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        {!loading && !error && events.length === 0 && (
          <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-muted)" }}>
            <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📜</div>
            <p>No punch or correction events recorded for this attendance session.</p>
          </div>
        )}

        {!loading && events.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {events.map((ev, index) => {
              const isStandard = ev.event_category === "STANDARD";
              const isInsert = ev.event_category === "CORRECTION_INSERT";
              const isSupersede = ev.event_category === "CORRECTION_SUPERSEDE";
              const isVoid = ev.event_category === "CORRECTION_VOID";

              const isVoidedTarget = Boolean(ev.voided_by_event_id);
              const isSupersededTarget = Boolean(ev.superseded_by_event_id);
              const isActiveInCalc = ev.is_active && !isVoidedTarget && !isSupersededTarget && !isVoid;

              let cardBorder = "1px solid var(--border-color)";
              let statusBadge = null;

              if (isVoidedTarget) {
                cardBorder = "1px solid rgba(239, 68, 68, 0.4)";
                statusBadge = (
                  <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)" }}>
                    VOIDED IN CALCULATION
                  </span>
                );
              } else if (isSupersededTarget) {
                cardBorder = "1px solid rgba(245, 158, 11, 0.4)";
                statusBadge = (
                  <span className="badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "#fbbf24", borderColor: "rgba(245, 158, 11, 0.3)" }}>
                    SUPERSEDED BY CORRECTION
                  </span>
                );
              } else if (isVoid) {
                cardBorder = "1px solid rgba(239, 68, 68, 0.3)";
                statusBadge = (
                  <span className="badge" style={{ background: "rgba(239, 68, 68, 0.15)", color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)" }}>
                    CORRECTION VOID TOMBSTONE
                  </span>
                );
              } else if (isSupersede) {
                cardBorder = "1px solid rgba(99, 102, 241, 0.4)";
                statusBadge = (
                  <span className="badge" style={{ background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc", borderColor: "rgba(99, 102, 241, 0.3)" }}>
                    CORRECTION SUPERSEDE (ACTIVE)
                  </span>
                );
              } else if (isInsert) {
                cardBorder = "1px solid rgba(6, 182, 212, 0.4)";
                statusBadge = (
                  <span className="badge" style={{ background: "rgba(6, 182, 212, 0.15)", color: "#22d3ee", borderColor: "rgba(6, 182, 212, 0.3)" }}>
                    CORRECTION INSERT (ACTIVE)
                  </span>
                );
              } else if (isActiveInCalc) {
                cardBorder = "1px solid rgba(16, 185, 129, 0.3)";
                statusBadge = (
                  <span className="badge badge-green">
                    ACTIVE IN CALCULATION
                  </span>
                );
              }

              return (
                <div
                  key={ev.id}
                  style={{
                    background: "rgba(0, 0, 0, 0.3)",
                    border: cardBorder,
                    borderRadius: "10px",
                    padding: "1rem",
                    position: "relative",
                  }}
                >
                  {/* Top Bar */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-secondary)" }}>
                        #{index + 1}
                      </span>
                      <strong
                        style={{
                          fontSize: "1rem",
                          textDecoration: (isVoidedTarget || isSupersededTarget || isVoid) ? "line-through" : "none",
                          color: (isVoidedTarget || isSupersededTarget || isVoid) ? "var(--text-muted)" : "var(--text-primary)",
                        }}
                      >
                        {ev.event_type.replace("_", " ")}
                      </strong>
                      <span
                        className="status-pill"
                        style={{
                          background: isStandard ? "rgba(255, 255, 255, 0.05)" : "rgba(99, 102, 241, 0.15)",
                          color: isStandard ? "var(--text-secondary)" : "#a5b4fc",
                        }}
                      >
                        {ev.event_category}
                      </span>
                    </div>
                    {statusBadge}
                  </div>

                  {/* Timing & Metadata Grid */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.5rem", fontSize: "0.825rem", color: "var(--text-secondary)" }}>
                    <div>
                      Effective Time:{" "}
                      <strong style={{ color: "var(--text-primary)" }}>
                        {new Date(ev.effective_at).toLocaleString()}
                      </strong>
                    </div>
                    <div>
                      Server Received:{" "}
                      <span style={{ color: "var(--text-primary)" }}>
                        {new Date(ev.server_received_at).toLocaleTimeString()}
                      </span>
                    </div>
                    <div>
                      Source:{" "}
                      <span className="badge" style={{ padding: "0.1rem 0.4rem", fontSize: "0.7rem" }}>
                        {ev.source}
                      </span>
                    </div>
                    <div>
                      Review Status:{" "}
                      <span style={{ color: ev.review_status === "APPROVED" ? "#34d399" : "inherit" }}>
                        {ev.review_status}
                      </span>
                    </div>
                  </div>

                  {/* Correction Details & Reasons */}
                  {ev.correction_reason && (
                    <div
                      style={{
                        marginTop: "0.75rem",
                        padding: "0.5rem 0.75rem",
                        background: "rgba(99, 102, 241, 0.08)",
                        borderRadius: "6px",
                        borderLeft: "3px solid #6366f1",
                        fontSize: "0.825rem",
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "#a5b4fc", marginBottom: "0.15rem" }}>
                        Correction Reason (Audit Log):
                      </div>
                      <div style={{ color: "var(--text-primary)" }}>{ev.correction_reason}</div>
                      {ev.actor_user_id && (
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                          Submitted by User ID: <code style={{ color: "var(--accent-cyan)" }}>{ev.actor_user_id}</code>
                        </div>
                      )}
                    </div>
                  )}

                  {/* References */}
                  {ev.supersedes_event_id && (
                    <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Supersedes Event ID: <code style={{ color: "var(--accent-cyan)" }}>{ev.supersedes_event_id}</code>
                    </div>
                  )}
                  {ev.superseded_by_event_id && (
                    <div style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: "#fbbf24" }}>
                      ↳ Superseded by Event ID: <code>{ev.superseded_by_event_id}</code>
                    </div>
                  )}
                  {ev.voided_by_event_id && (
                    <div style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: "#f87171" }}>
                      ↳ Voided by Tombstone Event ID: <code>{ev.voided_by_event_id}</code>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div style={{ marginTop: "1.5rem", paddingTop: "1rem", borderTop: "1px solid var(--border-color)", textAlign: "right" }}>
          <button className="btn btn-secondary" onClick={onClose}>
            Close Audit Trail
          </button>
        </div>
      </div>
    </div>
  );
}
