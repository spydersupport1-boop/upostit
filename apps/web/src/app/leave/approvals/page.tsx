"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  leaveApi,
  organizationApi,
  LeaveRequestDto,
  EmployeeDto,
  ApiError,
} from "@/lib/api";

function getStatusBadge(status: string) {
  switch (status) {
    case "APPROVED":
      return <span className="badge badge-green">Approved</span>;
    case "PENDING_APPROVAL":
      return <span className="badge badge-yellow">Pending Review</span>;
    case "REJECTED":
      return <span className="badge badge-red">Rejected</span>;
    case "CANCELLED":
      return <span className="badge">Cancelled</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

export default function LeaveApprovalsPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();

  // Role detection
  const isEmployeeRole = user?.role === "employee";
  const isManagerRole = user?.role === "manager";
  const isPrivilegedRole = user?.role && ["hr", "admin", "owner"].includes(user.role);

  // Data States
  const [requests, setRequests] = useState<LeaveRequestDto[]>([]);
  const [employees, setEmployees] = useState<EmployeeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("PENDING_APPROVAL");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>("");
  const [startDateFilter, setStartDateFilter] = useState<string>("");
  const [endDateFilter, setEndDateFilter] = useState<string>("");

  // Review Modal State
  const [selectedRequest, setSelectedRequest] = useState<LeaveRequestDto | null>(null);
  const [decisionAction, setDecisionAction] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [decisionReason, setDecisionReason] = useState<string>("");
  const [decisionSubmitting, setDecisionSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Check if current user is the applicant (Anti-Self-Approval)
  const isSelfRequest = useMemo(() => {
    if (!selectedRequest || !user) return false;
    const emp = employees.find((e) => e.id === selectedRequest.employee_id);
    return Boolean(
      (emp?.work_email && emp.work_email.toLowerCase() === user.email?.toLowerCase()) ||
      (emp?.user_id && emp.user_id === user.id) ||
      selectedRequest.employee_id === user.id
    );
  }, [selectedRequest, employees, user]);

  // Fetch Supervisor Queue
  const fetchQueue = useCallback(async () => {
    if (!token || isEmployeeRole) return;
    setLoading(true);
    setPageError(null);
    try {
      const resp = await leaveApi.getSupervisorQueue(
        {
          status: statusFilter === "ALL" ? undefined : statusFilter,
          employee_id: selectedEmployeeId || undefined,
          start_date: startDateFilter || undefined,
          end_date: endDateFilter || undefined,
          limit: 100,
        },
        token
      );
      setRequests(resp.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setPageError("Access Denied (403): You do not have permissions to review leave requests.");
        } else {
          setPageError(err.detail);
        }
      } else {
        setPageError("Failed to fetch supervisor leave queue.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, isEmployeeRole, statusFilter, selectedEmployeeId, startDateFilter, endDateFilter]);

  // Fetch Employees for Filter
  useEffect(() => {
    if (!token || isEmployeeRole) return;
    organizationApi
      .getEmployees({ page_size: 200 }, token)
      .then((res) => setEmployees(res.items || []))
      .catch(() => {});
  }, [token, isEmployeeRole]);

  useEffect(() => {
    if (isAuthenticated && token && !isEmployeeRole) {
      fetchQueue();
    }
  }, [isAuthenticated, token, isEmployeeRole, fetchQueue]);

  // Handle Decision Submit
  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedRequest) return;

    if (decisionAction === "REJECT" && decisionReason.trim().length < 3) {
      setModalError("Rejection requires a mandatory reason of at least 3 characters.");
      return;
    }

    setDecisionSubmitting(true);
    setModalError(null);

    try {
      await leaveApi.adjudicateLeaveRequest(
        selectedRequest.id,
        {
          action: decisionAction,
          reason: decisionReason.trim() || undefined,
        },
        token
      );

      setPageSuccess(
        `Leave request for ${selectedRequest.employee_name || "employee"} was successfully ${
          decisionAction === "APPROVE" ? "approved" : "rejected"
        }.`
      );
      setSelectedRequest(null);
      setDecisionReason("");
      await fetchQueue();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to submit leave decision.");
      }
    } finally {
      setDecisionSubmitting(false);
    }
  };

  // ===========================================================================
  // RENDER: Loading & Access Denied State
  // ===========================================================================

  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying supervisor credentials...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || isEmployeeRole) {
    return (
      <div className="container">
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge badge-red">Access Denied</span>
          </div>
          <div>
            <Link href="/leave" className="btn btn-secondary btn-sm">
              ← My Leave
            </Link>
          </div>
        </nav>

        <div style={{ maxWidth: "520px", margin: "4rem auto", textAlign: "center" }}>
          <div className="card" style={{ padding: "3rem" }}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🛡️</div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>Supervisor Access Required</h1>
            <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem", fontSize: "0.95rem" }}>
              The Leave Approvals Console is restricted to Managers, HR Personnel, and Tenant Administrators.
            </p>
            <div style={{ marginTop: "2rem" }}>
              <Link href="/leave" className="btn btn-primary">
                Return to My Leave
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Supervisor Leave Approvals Console
  // ===========================================================================

  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge badge-cyan">
            {isManagerRole ? "Manager Review Queue" : "HR Leave Console"}
          </span>
          {tenant?.name && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
              • {tenant.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <Link href="/leave" className="btn btn-secondary btn-sm">
            🌴 My Leave
          </Link>
          <Link href="/attendance" className="btn btn-secondary btn-sm">
            ⏱️ Attendance
          </Link>
          <Link href="/attendance/overtime" className="btn btn-secondary btn-sm">
            ⚡ Overtime
          </Link>
          {isPrivilegedRole && (
            <>
              <Link href="/organization/leave-types" className="btn btn-secondary btn-sm">
                📋 Leave Policies
              </Link>
              <Link href="/organization/holidays" className="btn btn-secondary btn-sm">
                📅 Holidays
              </Link>
            </>
          )}
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {user?.email} ({user?.role})
          </span>
          <button className="btn btn-secondary btn-sm" onClick={logout}>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Scope Alert Banner */}
      <div className="alert alert-info" style={{ marginBottom: "1.5rem" }}>
        <span>
          🛡️ <strong>{isManagerRole ? "Manager Direct-Report Scope" : "Tenant-Wide Administrative Scope"}:</strong>{" "}
          {isManagerRole
            ? "Showing leave applications submitted by your assigned direct reports. Anti-self-approval security policy prevents adjudicating your own applications."
            : "Showing leave requests across all departments and locations with atomic balance commit and daily attendance projection recalculation."}
        </span>
      </div>

      {/* Alerts */}
      {pageError && (
        <div className="alert alert-danger" style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between" }}>
          <span>{pageError}</span>
          <button className="alert-close" onClick={() => setPageError(null)}>
            &times;
          </button>
        </div>
      )}

      {pageSuccess && (
        <div className="alert alert-success" style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between" }}>
          <span>{pageSuccess}</span>
          <button className="alert-close" onClick={() => setPageSuccess(null)}>
            &times;
          </button>
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Leave Review & Adjudication</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Review pending employee leave applications, inspect deductible days, and approve or reject with audit trail.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchQueue} disabled={loading}>
          🔄 Refresh Queue
        </button>
      </div>

      {/* Filters Toolbar */}
      <div className="card" style={{ padding: "1rem 1.25rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ minWidth: "180px" }}>
            <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Status</label>
            <select
              className="form-control"
              style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="PENDING_APPROVAL">Pending Review Only</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="CANCELLED">Cancelled</option>
              <option value="ALL">All Statuses</option>
            </select>
          </div>

          {isPrivilegedRole && (
            <div style={{ minWidth: "200px" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Employee</label>
              <select
                className="form-control"
                style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
                value={selectedEmployeeId}
                onChange={(e) => setSelectedEmployeeId(e.target.value)}
              >
                <option value="">All Employees</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.first_name} {emp.last_name} ({emp.employee_id})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>From Date</label>
            <input
              type="date"
              className="form-control"
              style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
              value={startDateFilter}
              onChange={(e) => setStartDateFilter(e.target.value)}
            />
          </div>

          <div>
            <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>To Date</label>
            <input
              type="date"
              className="form-control"
              style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
              value={endDateFilter}
              onChange={(e) => setEndDateFilter(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Requests Table */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>
            {statusFilter === "PENDING_APPROVAL" ? "Pending Requests" : "Leave Applications Queue"}
          </h2>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {requests.length} record{requests.length === 1 ? "" : "s"} found
          </span>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <p style={{ color: "var(--text-secondary)" }}>Loading leave applications...</p>
          </div>
        ) : requests.length === 0 ? (
          <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-secondary)" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>✅</div>
            <p>No leave requests matching the active filter criteria.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Leave Type</th>
                  <th>Dates</th>
                  <th>Days</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Submitted</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req) => (
                  <tr key={req.id}>
                    <td>
                      <strong>{req.employee_name || "Employee"}</strong>
                    </td>
                    <td>
                      <span className="badge" style={{ fontSize: "0.75rem" }}>
                        {req.leave_type_code || req.leave_type_name}
                      </span>
                      {req.is_half_day && (
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                          {req.half_day_period === "FIRST_HALF" ? "Morning (1st Half)" : "Afternoon (2nd Half)"}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ fontSize: "0.9rem" }}>
                        {req.start_date}
                        {req.start_date !== req.end_date && ` → ${req.end_date}`}
                      </div>
                    </td>
                    <td>
                      <strong>{Number(req.total_days).toFixed(1)}</strong>
                    </td>
                    <td>{getStatusBadge(req.status)}</td>
                    <td>
                      <div style={{ fontSize: "0.85rem", maxWidth: "220px", wordBreak: "break-word" }}>
                        {req.reason}
                        {req.reviewer_notes && (
                          <div style={{ marginTop: "0.25rem", color: "var(--accent-amber)", fontSize: "0.75rem" }}>
                            💬 {req.reviewer_notes}
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      {req.created_at ? new Date(req.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td>
                      {req.status === "PENDING_APPROVAL" ? (
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            setSelectedRequest(req);
                            setDecisionAction("APPROVE");
                            setDecisionReason("");
                            setModalError(null);
                          }}
                        >
                          Review
                        </button>
                      ) : (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setSelectedRequest(req);
                            setDecisionAction("APPROVE");
                            setDecisionReason(req.reviewer_notes || "");
                            setModalError(null);
                          }}
                        >
                          Details
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* =======================================================================
          MODAL: Review / Adjudicate Leave Request
          ======================================================================= */}
      {selectedRequest && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "540px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {selectedRequest.status === "PENDING_APPROVAL" ? "Adjudicate Leave Application" : "Leave Application Details"}
              </h2>
              <button className="modal-close" onClick={() => setSelectedRequest(null)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            {isSelfRequest && selectedRequest.status === "PENDING_APPROVAL" && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                🛡️ <strong>Anti-Self-Approval Restriction:</strong> You cannot approve or reject your own leave application. Another authorized supervisor or HR administrator must adjudicate this request.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Employee:</span>
                <strong>{selectedRequest.employee_name || "Employee"}</strong>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Leave Category:</span>
                <span>
                  <strong>{selectedRequest.leave_type_name || selectedRequest.leave_type_code}</strong>{" "}
                  ({selectedRequest.leave_type_code})
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Requested Dates:</span>
                <span>
                  {selectedRequest.start_date}
                  {selectedRequest.start_date !== selectedRequest.end_date && ` to ${selectedRequest.end_date}`}
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Deductible Days:</span>
                <strong>{Number(selectedRequest.total_days).toFixed(1)} day(s)</strong>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Current Status:</span>
                {getStatusBadge(selectedRequest.status)}
              </div>

              <div style={{ padding: "0.5rem 0" }}>
                <span style={{ color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                  Employee Statement:
                </span>
                <div style={{ background: "rgba(255, 255, 255, 0.04)", padding: "0.75rem", borderRadius: "8px", fontStyle: "italic" }}>
                  &ldquo;{selectedRequest.reason}&rdquo;
                </div>
              </div>
            </div>

            {selectedRequest.status === "PENDING_APPROVAL" ? (
              <form onSubmit={handleDecisionSubmit}>
                <div style={{ marginBottom: "1rem" }}>
                  <label className="form-label">Supervisor Action</label>
                  <div style={{ display: "flex", gap: "1rem", marginTop: "0.25rem" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
                      <input
                        type="radio"
                        name="decisionAction"
                        value="APPROVE"
                        checked={decisionAction === "APPROVE"}
                        onChange={() => setDecisionAction("APPROVE")}
                        disabled={isSelfRequest}
                      />
                      <span style={{ color: "var(--accent-emerald)", fontWeight: 600 }}>Approve Application</span>
                    </label>

                    <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
                      <input
                        type="radio"
                        name="decisionAction"
                        value="REJECT"
                        checked={decisionAction === "REJECT"}
                        onChange={() => setDecisionAction("REJECT")}
                        disabled={isSelfRequest}
                      />
                      <span style={{ color: "#f87171", fontWeight: 600 }}>Reject Application</span>
                    </label>
                  </div>
                </div>

                <div style={{ marginBottom: "1.5rem" }}>
                  <label className="form-label">
                    {decisionAction === "REJECT" ? "Rejection Reason (Mandatory)" : "Supervisor Notes (Optional)"}
                  </label>
                  <textarea
                    className="form-control"
                    rows={3}
                    placeholder={
                      decisionAction === "REJECT"
                        ? "State the reason for rejecting this leave request (min 3 chars)..."
                        : "Optional feedback for employee..."
                    }
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    required={decisionAction === "REJECT"}
                    disabled={isSelfRequest}
                  />
                  {decisionAction === "REJECT" && (
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                      Minimum 3 characters required.
                    </div>
                  )}
                </div>

                <div className="modal-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setSelectedRequest(null)}
                    disabled={decisionSubmitting}
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    className={decisionAction === "APPROVE" ? "btn btn-primary" : "btn btn-danger"}
                    disabled={decisionSubmitting || isSelfRequest}
                  >
                    {decisionSubmitting
                      ? "Recording Decision..."
                      : decisionAction === "APPROVE"
                      ? "Confirm Approval"
                      : "Confirm Rejection"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setSelectedRequest(null)}
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
