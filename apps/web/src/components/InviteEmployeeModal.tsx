"use client";

import React, { useState } from "react";
import { invitationApi, EmployeeDto, ApiError } from "@/lib/api";

export interface InviteEmployeeModalProps {
  isOpen: boolean;
  onClose: () => void;
  employee: EmployeeDto | null;
  token: string | null;
  onInvitationSent?: () => void;
}

export default function InviteEmployeeModal({
  isOpen,
  onClose,
  employee,
  token,
  onInvitationSent,
}: InviteEmployeeModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<{
    email: string;
    expires_at: string;
    preview_url?: string | null;
  } | null>(null);

  if (!isOpen || !employee) return null;

  const handleSendInvite = async () => {
    if (!token) return;
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const resp = await invitationApi.inviteEmployee(employee.id, token);
      setSuccessResult({
        email: resp.email,
        expires_at: resp.expires_at,
        preview_url: resp.preview_url,
      });
      if (onInvitationSent) onInvitationSent();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to send employee invitation.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "520px", padding: "2.25rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "1.25rem" }}>✉️</span>
            <h2 className="modal-title" style={{ margin: 0 }}>Invite Employee</h2>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {errorMessage && (
          <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
            <span>{errorMessage}</span>
            <button className="alert-close" onClick={() => setErrorMessage(null)}>&times;</button>
          </div>
        )}

        {successResult ? (
          <div style={{ textAlign: "center", padding: "1rem 0" }}>
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "rgba(16, 185, 129, 0.15)",
                color: "#10b981",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.5rem",
                margin: "0 auto 1rem",
              }}
            >
              ✓
            </div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#34d399", marginBottom: "0.5rem" }}>
              Invitation Dispatched!
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem" }}>
              An invitation with a single-use activation link was queued for <strong>{successResult.email}</strong>.
            </p>

            {successResult.preview_url && (
              <div style={{ background: "rgba(0,0,0,0.3)", padding: "0.75rem", borderRadius: "8px", border: "1px solid var(--border-color)", marginBottom: "1.25rem", textAlign: "left" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>Local Preview / Test Link</div>
                <div style={{ fontSize: "0.8rem", color: "var(--accent-cyan)", wordBreak: "break-all" }}>
                  <a href={successResult.preview_url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "underline" }}>
                    {successResult.preview_url}
                  </a>
                </div>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  setSuccessResult(null);
                  onClose();
                }}
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="card" style={{ padding: "1.25rem", background: "rgba(0,0,0,0.25)", marginBottom: "1.5rem" }}>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>Employee</div>
              <div style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "1.05rem" }}>
                {employee.first_name} {employee.last_name}
              </div>
              <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.825rem", color: "var(--text-secondary)" }}>
                <div>ID: <strong style={{ color: "var(--text-primary)" }}>{employee.employee_id}</strong></div>
                <div>Email: <strong style={{ color: "var(--accent-cyan)" }}>{employee.work_email}</strong></div>
              </div>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: "1.6", marginBottom: "1.75rem" }}>
              An invitation email containing a secure cryptographic activation link will be sent to the employee&apos;s work email address. The token will expire in 7 days.
            </p>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={isSubmitting}
                onClick={handleSendInvite}
              >
                {isSubmitting ? "Sending Invitation..." : "Send Invitation"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
