"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  invitationApi,
  InvitationDto,
  ApiError,
} from "@/lib/api";

export interface InvitationsTabProps {
  token: string | null;
  canManage?: boolean;
}

export default function InvitationsTab({
  token,
  canManage = true,
}: InvitationsTabProps) {
  const [invitations, setInvitations] = useState<InvitationDto[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 15;
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Dialog States
  const [confirmResendInvite, setConfirmResendInvite] = useState<InvitationDto | null>(null);
  const [confirmRevokeInvite, setConfirmRevokeInvite] = useState<InvitationDto | null>(null);
  const [selectedErrorDetails, setSelectedErrorDetails] = useState<string | null>(null);

  const fetchInvitations = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setErrorMessage(null);

    const filter = statusFilter === "all" ? undefined : statusFilter;
    const skip = (page - 1) * pageSize;

    try {
      const resp = await invitationApi.getInvitations(
        {
          status: filter,
          skip,
          limit: pageSize,
        },
        token
      );
      setInvitations(resp.items);
      setTotal(resp.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to load employee invitations.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [token, statusFilter, page]);

  useEffect(() => {
    fetchInvitations();
  }, [fetchInvitations]);

  const handleResend = async () => {
    if (!token || !confirmResendInvite) return;
    setActionLoading(confirmResendInvite.id);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await invitationApi.resendInvitation(confirmResendInvite.id, token);
      setSuccessMessage(`Invitation to ${confirmResendInvite.email} has been regenerated and re-dispatched.`);
      setConfirmResendInvite(null);
      await fetchInvitations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to resend invitation.");
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevoke = async () => {
    if (!token || !confirmRevokeInvite) return;
    setActionLoading(confirmRevokeInvite.id);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await invitationApi.revokeInvitation(confirmRevokeInvite.id, token);
      setSuccessMessage(`Invitation for ${confirmRevokeInvite.email} has been revoked.`);
      setConfirmRevokeInvite(null);
      await fetchInvitations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to revoke invitation.");
      }
    } finally {
      setActionLoading(null);
    }
  };

  const filteredInvitations = invitations.filter((inv) => {
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    return (
      inv.email.toLowerCase().includes(query) ||
      (inv.employee_name && inv.employee_name.toLowerCase().includes(query)) ||
      (inv.employee_number && inv.employee_number.toLowerCase().includes(query))
    );
  });

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      {/* Tab Header & Search / Filters */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
            Employee Invitations & Onboarding
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
            Track outstanding single-use invitation tokens, delivery status, and account activation progress.
          </p>
        </div>
      </div>

      {/* Global Alerts */}
      {errorMessage && (
        <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
          <span>{errorMessage}</span>
          <button className="alert-close" onClick={() => setErrorMessage(null)}>&times;</button>
        </div>
      )}

      {successMessage && (
        <div className="alert alert-success" style={{ marginBottom: "1.25rem" }}>
          <span>{successMessage}</span>
          <button className="alert-close" onClick={() => setSuccessMessage(null)}>&times;</button>
        </div>
      )}

      {/* Filter Tabs Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {[
            { id: "all", label: "All Invitations" },
            { id: "pending", label: "Pending" },
            { id: "accepted", label: "Accepted" },
            { id: "expired", label: "Expired" },
            { id: "revoked", label: "Revoked" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`btn btn-sm ${statusFilter === tab.id ? "btn-primary" : "btn-secondary"}`}
              style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem" }}
              onClick={() => {
                setStatusFilter(tab.id);
                setPage(1);
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <input
          type="text"
          className="search-input"
          style={{ maxWidth: "280px" }}
          placeholder="Filter by email or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Loading Skeletons */}
      {isLoading ? (
        <div className="spinner-container" style={{ padding: "3rem 0", textAlign: "center" }}>
          <div className="spinner" style={{ margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading invitations...</p>
        </div>
      ) : filteredInvitations.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem", background: "rgba(0,0,0,0.15)" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>✉️</div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>No Invitations Found</h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", maxWidth: "420px", margin: "0 auto" }}>
            {statusFilter !== "all"
              ? `No invitations match the "${statusFilter}" filter criteria.`
              : "No employee invitations have been issued yet. Invite employees from the Employee Directory tab."}
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Recipient Email</th>
                <th>Status</th>
                <th>Delivery</th>
                <th>Attempts</th>
                <th>Expires</th>
                <th>Created</th>
                {canManage && <th style={{ textAlign: "right" }}>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {filteredInvitations.map((inv) => {
                const isPending = inv.status === "pending";
                const isExpired = inv.status === "expired" || (isPending && new Date(inv.expires_at) < new Date());
                const isRevoked = inv.status === "revoked";
                const isAccepted = inv.status === "accepted";

                return (
                  <tr key={inv.id}>
                    <td>
                      <div style={{ fontWeight: 600, color: "var(--accent-cyan)" }}>{inv.email}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        ID: {inv.employee_id.slice(0, 8)}...
                      </div>
                    </td>
                    <td>
                      {isAccepted ? (
                        <span className="status-pill status-active">Accepted</span>
                      ) : isRevoked ? (
                        <span className="status-pill status-terminated">Revoked</span>
                      ) : isExpired ? (
                        <span className="status-pill status-inactive">Expired</span>
                      ) : (
                        <span className="status-pill status-on_leave">Pending</span>
                      )}
                    </td>
                    <td>
                      {inv.delivery_status === "sent" ? (
                        <span style={{ color: "#34d399", fontSize: "0.825rem", fontWeight: 600 }}>✓ Delivered</span>
                      ) : inv.delivery_status === "failed" ? (
                        <button
                          type="button"
                          onClick={() => setSelectedErrorDetails(inv.delivery_error || "Unknown delivery failure")}
                          style={{
                            background: "rgba(239, 68, 68, 0.15)",
                            border: "1px solid rgba(239, 68, 68, 0.3)",
                            color: "#f87171",
                            padding: "2px 6px",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            fontWeight: 600,
                          }}
                        >
                          ✕ Failed (Details)
                        </button>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.825rem" }}>Queued</span>
                      )}
                    </td>
                    <td style={{ fontSize: "0.85rem", color: inv.attempt_count >= 5 ? "#f87171" : "inherit" }}>
                      {inv.attempt_count} / 5
                    </td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      {new Date(inv.expires_at).toLocaleDateString()}
                    </td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {new Date(inv.created_at).toLocaleDateString()}
                    </td>
                    {canManage && (
                      <td style={{ textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                          {isPending && !isExpired && (
                            <>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
                                disabled={actionLoading === inv.id}
                                onClick={() => setConfirmResendInvite(inv)}
                              >
                                Resend
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", color: "#f87171" }}
                                disabled={actionLoading === inv.id}
                                onClick={() => setConfirmRevokeInvite(inv)}
                              >
                                Revoke
                              </button>
                            </>
                          )}
                          {(isExpired || isRevoked) && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
                              disabled={actionLoading === inv.id}
                              onClick={() => setConfirmResendInvite(inv)}
                            >
                              Re-issue Invite
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Showing {filteredInvitations.length} of {total} invitations
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </button>
            <span style={{ fontSize: "0.85rem", padding: "0.3rem 0.6rem", color: "var(--text-secondary)" }}>
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Confirmation Dialog: Resend Invitation */}
      {confirmResendInvite && (
        <div className="modal-overlay" onClick={() => setConfirmResendInvite(null)}>
          <div className="modal-content" style={{ maxWidth: "460px", padding: "2rem" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.75rem" }}>
              Resend Invitation?
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: "1.6", marginBottom: "1.5rem" }}>
              This will regenerate a fresh cryptographic activation token, reset expiration to 7 days, clear failed attempt counters, and dispatch a new activation email to <strong>{confirmResendInvite.email}</strong>. Any previous token will be invalidated.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setConfirmResendInvite(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={actionLoading === confirmResendInvite.id}
                onClick={handleResend}
              >
                {actionLoading === confirmResendInvite.id ? "Dispatching..." : "Confirm & Resend"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Dialog: Revoke Invitation */}
      {confirmRevokeInvite && (
        <div className="modal-overlay" onClick={() => setConfirmRevokeInvite(null)}>
          <div className="modal-content" style={{ maxWidth: "460px", padding: "2rem" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f87171", marginBottom: "0.75rem" }}>
              Revoke Invitation?
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: "1.6", marginBottom: "1.5rem" }}>
              Are you sure you want to revoke the invitation for <strong>{confirmRevokeInvite.email}</strong>? The recipient will no longer be able to activate their account using the link.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setConfirmRevokeInvite(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                disabled={actionLoading === confirmRevokeInvite.id}
                onClick={handleRevoke}
              >
                {actionLoading === confirmRevokeInvite.id ? "Revoking..." : "Confirm Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delivery Error Details Dialog */}
      {selectedErrorDetails && (
        <div className="modal-overlay" onClick={() => setSelectedErrorDetails(null)}>
          <div className="modal-content" style={{ maxWidth: "480px", padding: "2rem" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f87171", marginBottom: "0.75rem" }}>
              Email Delivery Error Diagnostic
            </h3>
            <div style={{ background: "rgba(0,0,0,0.3)", padding: "1rem", borderRadius: "8px", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#fca5a5", fontSize: "0.85rem", marginBottom: "1.5rem", wordBreak: "break-all" }}>
              {selectedErrorDetails}
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedErrorDetails(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
