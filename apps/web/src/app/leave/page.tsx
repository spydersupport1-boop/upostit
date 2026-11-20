"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  leaveApi,
  holidayApi,
  LeaveBalanceDto,
  LeaveRequestDto,
  LeaveTypeDto,
  UpcomingHolidayDto,
  ApiError,
} from "@/lib/api";

function getStatusBadge(status: string) {
  switch (status) {
    case "APPROVED":
      return <span className="badge badge-green">Approved</span>;
    case "PENDING_APPROVAL":
      return <span className="badge badge-yellow">Pending Approval</span>;
    case "REJECTED":
      return <span className="badge badge-red">Rejected</span>;
    case "CANCELLED":
      return <span className="badge">Cancelled</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

export default function LeaveDashboardPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, login, logout, error: authContextError } = useAuth();

  // Role detection
  const isEmployeeRole = user?.role === "employee";
  const isManagerOrAdmin = user?.role && ["manager", "hr", "admin", "owner"].includes(user.role);

  // Data States
  const [balances, setBalances] = useState<LeaveBalanceDto[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveTypeDto[]>([]);
  const [requests, setRequests] = useState<LeaveRequestDto[]>([]);
  const [upcomingHolidays, setUpcomingHolidays] = useState<UpcomingHolidayDto[]>([]);
  const [holidayResolutionSource, setHolidayResolutionSource] = useState<string>("NONE");
  const [loading, setLoading] = useState(true);

  // Alerts
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Application Modal State
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applySubmitting, setApplySubmitting] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  // Form State
  const todayStr = new Date().toISOString().split("T")[0];
  const [selectedLeaveTypeId, setSelectedLeaveTypeId] = useState<string>("");
  const [startDate, setStartDate] = useState<string>(todayStr);
  const [endDate, setEndDate] = useState<string>(todayStr);
  const [isHalfDay, setIsHalfDay] = useState<boolean>(false);
  const [halfDayPeriod, setHalfDayPeriod] = useState<"FIRST_HALF" | "SECOND_HALF">("FIRST_HALF");
  const [reason, setReason] = useState<string>("");

  // Cancellation State
  const [cancellingRequestId, setCancellingRequestId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [cancelSubmitting, setCancelSubmitting] = useState(false);

  // Inline Auth Form
  const [authTenantSlug, setAuthTenantSlug] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // ===========================================================================
  // Fetch Functions
  // ===========================================================================

  const fetchDashboardData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setPageError(null);
    try {
      // 1. Fetch Balances
      const balancesResp = await leaveApi.getMyBalances(token);
      setBalances(balancesResp.items || []);

      // 2. Fetch Active Leave Types
      const typesResp = await leaveApi.getLeaveTypes({ is_active: true, limit: 100 }, token);
      setLeaveTypes(typesResp.items || []);
      if (typesResp.items && typesResp.items.length > 0 && !selectedLeaveTypeId) {
        setSelectedLeaveTypeId(typesResp.items[0].id);
      }

      // 3. Fetch My Leave Requests
      const requestsResp = await leaveApi.getMyLeaveRequests({ limit: 50 }, token);
      setRequests(requestsResp.items || []);

      // 4. Fetch Upcoming Holidays
      const holidaysResp = await holidayApi.getUpcomingHolidays({ limit: 10 }, token);
      setUpcomingHolidays(holidaysResp.items || []);
      setHolidayResolutionSource(holidaysResp.resolution_source || "NONE");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to load leave dashboard data.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, selectedLeaveTypeId]);

  useEffect(() => {
    if (isAuthenticated && token) {
      fetchDashboardData();
    }
  }, [isAuthenticated, token, fetchDashboardData]);

  // Selected leave type details
  const selectedType = useMemo(
    () => leaveTypes.find((lt) => lt.id === selectedLeaveTypeId),
    [leaveTypes, selectedLeaveTypeId]
  );

  const selectedBalance = useMemo(
    () => balances.find((b) => b.leave_type_id === selectedLeaveTypeId),
    [balances, selectedLeaveTypeId]
  );

  // Working day estimate & holiday clash preview
  const holidaysInRange = useMemo(() => {
    if (!startDate || !endDate) return [];
    return upcomingHolidays.filter(
      (h) => h.holiday_date >= startDate && h.holiday_date <= endDate && h.holiday_type !== "OPTIONAL"
    );
  }, [startDate, endDate, upcomingHolidays]);

  // Handle Apply Submission
  const handleApplyLeave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!selectedLeaveTypeId) {
      setApplyError("Please select a leave category.");
      return;
    }
    if (reason.trim().length < 3) {
      setApplyError("Please provide an explanatory reason (minimum 3 characters).");
      return;
    }

    setApplySubmitting(true);
    setApplyError(null);

    try {
      await leaveApi.applyLeave(
        {
          leave_type_id: selectedLeaveTypeId,
          start_date: startDate,
          end_date: isHalfDay ? startDate : endDate,
          is_half_day: isHalfDay,
          half_day_period: isHalfDay ? halfDayPeriod : null,
          reason: reason.trim(),
        },
        token
      );

      setPageSuccess("Leave request submitted successfully and pending supervisor review.");
      setShowApplyModal(false);
      setReason("");
      await fetchDashboardData();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setApplyError(err.detail);
      } else {
        setApplyError("Failed to submit leave request.");
      }
    } finally {
      setApplySubmitting(false);
    }
  };

  // Handle Cancel Request
  const handleConfirmCancel = async () => {
    if (!token || !cancellingRequestId) return;
    setCancelSubmitting(true);
    setPageError(null);
    try {
      await leaveApi.cancelLeaveRequest(
        cancellingRequestId,
        { reason: cancelReason.trim() || undefined },
        token
      );
      setPageSuccess("Leave request cancelled successfully. Reserved balances have been restored.");
      setCancellingRequestId(null);
      setCancelReason("");
      await fetchDashboardData();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to cancel leave request.");
      }
    } finally {
      setCancelSubmitting(false);
    }
  };

  // Inline Auth Handler
  const handleInlineLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authEmail || !authPassword || !authTenantSlug) return;
    setAuthSubmitting(true);
    setAuthError(null);
    try {
      await login(authEmail.trim(), authPassword, authTenantSlug.trim());
      setPageSuccess("Successfully authenticated! Leave console ready.");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setAuthError(err.detail);
      } else {
        setAuthError((err as Error).message || "Authentication failed.");
      }
    } finally {
      setAuthSubmitting(false);
    }
  };

  // ===========================================================================
  // RENDER: Loading & Unauthenticated State
  // ===========================================================================

  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying secure session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="container">
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge">Leave & Balances</span>
          </div>
          <div>
            <Link href="/" className="btn btn-secondary btn-sm">
              ← Home
            </Link>
          </div>
        </nav>

        <div style={{ maxWidth: "480px", margin: "3rem auto" }}>
          <div className="card" style={{ padding: "2.5rem" }}>
            <div style={{ textAlign: "center", marginBottom: "2rem" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>🌴</div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}>Employee Leave Portal</h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
                Sign in with your enterprise credentials to view your leave balances, apply for time off, and track supervisor approvals.
              </p>
            </div>

            {(authError || authContextError) && (
              <div className="alert alert-danger" style={{ marginBottom: "1.5rem" }}>
                <span>{authError || authContextError}</span>
              </div>
            )}

            <form onSubmit={handleInlineLogin} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                  Tenant Identifier
                </label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. acme"
                  value={authTenantSlug}
                  onChange={(e) => setAuthTenantSlug(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                  Work Email
                </label>
                <input
                  type="email"
                  className="form-control"
                  placeholder="name@company.com"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "block", marginBottom: "0.25rem" }}>
                  Password
                </label>
                <input
                  type="password"
                  className="form-control"
                  placeholder="••••••••"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", marginTop: "0.5rem" }}
                disabled={authSubmitting}
              >
                {authSubmitting ? "Authenticating..." : "Sign In to Leave Portal"}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Authenticated Leave Dashboard
  // ===========================================================================

  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge badge-green">Leave Management</span>
          {tenant?.name && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
              • {tenant.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          {isManagerOrAdmin && (
            <Link href="/leave/approvals" className="btn btn-secondary btn-sm" style={{ borderColor: "#06b6d4", color: "#06b6d4" }}>
              ✓ Leave Approvals
            </Link>
          )}
          <Link href="/attendance" className="btn btn-secondary btn-sm">
            ⏱️ Attendance
          </Link>
          <Link href="/attendance/overtime" className="btn btn-secondary btn-sm">
            ⚡ Overtime
          </Link>
          {isManagerOrAdmin && (
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

      {/* Header and Apply Action */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Employee Leave Dashboard</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Track your leave quotas, view statutory holiday schedules, and submit time off applications.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowApplyModal(true);
            setApplyError(null);
          }}
        >
          🌴 Apply for Leave
        </button>
      </div>

      {/* Leave Balances Grid */}
      <div style={{ marginBottom: "2.5rem" }}>
        <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1rem" }}>
          Your Leave Balances ({new Date().getFullYear()})
        </h2>

        {loading ? (
          <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
            <p style={{ color: "var(--text-secondary)" }}>Loading leave allocations and available balances...</p>
          </div>
        ) : balances.length === 0 ? (
          <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
            <p style={{ color: "var(--text-secondary)" }}>
              No leave balances configured for this calendar year. Please contact your HR administrator.
            </p>
          </div>
        ) : (
          <div className="stats-grid">
            {balances.map((b) => (
              <div key={b.id} className="stat-card" style={{ flexDirection: "column", alignItems: "flex-start", gap: "0.75rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                  <span className="badge" style={{ fontSize: "0.75rem" }}>{b.leave_type_code}</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Year {b.year}</span>
                </div>
                <div style={{ width: "100%" }}>
                  <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>
                    {b.leave_type_name}
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", marginTop: "0.25rem" }}>
                    <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--accent-cyan)" }}>
                      {Number(b.available_balance).toFixed(1)}
                    </span>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>days available</span>
                  </div>
                </div>
                <div
                  style={{
                    width: "100%",
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1fr",
                    gap: "0.5rem",
                    paddingTop: "0.5rem",
                    borderTop: "1px solid var(--border-color)",
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  <div>
                    <span>Quota: </span>
                    <strong style={{ color: "var(--text-primary)" }}>{Number(b.annual_allocation).toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Used: </span>
                    <strong style={{ color: "var(--accent-emerald)" }}>{Number(b.used).toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Pending: </span>
                    <strong style={{ color: "var(--accent-amber)" }}>{Number(b.pending_approval).toFixed(1)}</strong>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Content Layout: History + Upcoming Holidays */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem", alignItems: "flex-start" }}>
        {/* Leave Requests History */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>My Leave Requests</h2>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {requests.length} total request{requests.length === 1 ? "" : "s"}
            </span>
          </div>

          {loading ? (
            <p style={{ color: "var(--text-secondary)", textAlign: "center", padding: "2rem" }}>
              Loading request history...
            </p>
          ) : requests.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--text-secondary)" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📄</div>
              <p>You have not submitted any leave requests yet.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Dates</th>
                    <th>Days</th>
                    <th>Status</th>
                    <th>Reason & Reviewer Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((req) => {
                    const isPending = req.status === "PENDING_APPROVAL";
                    const isFutureApproved = req.status === "APPROVED" && req.start_date > todayStr;
                    const canCancel = isPending || isFutureApproved;

                    return (
                      <tr key={req.id}>
                        <td>
                          <strong>{req.leave_type_code || req.leave_type_name || "Leave"}</strong>
                          {req.is_half_day && (
                            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                              {req.half_day_period === "FIRST_HALF" ? "1st Half" : "2nd Half"}
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
                          <div style={{ fontSize: "0.85rem", maxWidth: "240px", wordBreak: "break-word" }}>
                            <div>{req.reason}</div>
                            {req.reviewer_notes && (
                              <div style={{ marginTop: "0.25rem", color: "var(--accent-amber)", fontSize: "0.8rem" }}>
                                💬 <em>Feedback:</em> {req.reviewer_notes}
                              </div>
                            )}
                          </div>
                        </td>
                        <td>
                          {canCancel ? (
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => {
                                setCancellingRequestId(req.id);
                                setCancelReason("");
                              }}
                            >
                              Cancel
                            </button>
                          ) : (
                            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Upcoming Holidays Card */}
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>Upcoming Holidays</h2>
            <span className="badge" style={{ fontSize: "0.75rem" }}>
              {holidayResolutionSource}
            </span>
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
            Statutory holidays do not deduct from your annual leave quota.
          </p>

          {upcomingHolidays.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              No upcoming public holidays found for your workplace.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {upcomingHolidays.map((h) => (
                <div
                  key={h.id}
                  style={{
                    padding: "0.75rem",
                    borderRadius: "8px",
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid var(--border-color)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600 }}>{h.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      {h.holiday_date} • {h.calendar_name}
                    </div>
                  </div>
                  <span
                    className={
                      h.holiday_type === "PUBLIC"
                        ? "badge badge-purple"
                        : h.holiday_type === "COMPANY"
                        ? "badge badge-blue"
                        : "badge"
                    }
                    style={{ fontSize: "0.7rem" }}
                  >
                    {h.holiday_type}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* =======================================================================
          MODAL: Apply for Leave
          ======================================================================= */}
      {showApplyModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "560px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">🌴 Apply for Leave</h2>
              <button className="modal-close" onClick={() => setShowApplyModal(false)}>
                &times;
              </button>
            </div>

            {applyError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{applyError}</span>
              </div>
            )}

            <form onSubmit={handleApplyLeave}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {/* Leave Type Select */}
                <div>
                  <label className="form-label">Leave Category</label>
                  <select
                    className="form-control"
                    value={selectedLeaveTypeId}
                    onChange={(e) => setSelectedLeaveTypeId(e.target.value)}
                    required
                  >
                    {leaveTypes.map((lt) => (
                      <option key={lt.id} value={lt.id}>
                        {lt.name} ({lt.code}) {lt.is_paid ? "• Paid" : "• Unpaid"}
                      </option>
                    ))}
                  </select>
                  {selectedBalance && (
                    <div style={{ fontSize: "0.8rem", color: "var(--accent-cyan)", marginTop: "0.25rem" }}>
                      Current Available Balance: <strong>{Number(selectedBalance.available_balance).toFixed(1)} days</strong>
                    </div>
                  )}
                </div>

                {/* Half Day Checkbox (if permitted by policy) */}
                {selectedType?.allow_half_day && (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input
                      type="checkbox"
                      id="halfDayCheckbox"
                      checked={isHalfDay}
                      onChange={(e) => setIsHalfDay(e.target.checked)}
                    />
                    <label htmlFor="halfDayCheckbox" style={{ fontSize: "0.9rem", cursor: "pointer" }}>
                      Apply as Half-Day (0.50 day deduction)
                    </label>
                  </div>
                )}

                {/* Period Select for Half-Day */}
                {isHalfDay && (
                  <div>
                    <label className="form-label">Half-Day Session</label>
                    <select
                      className="form-control"
                      value={halfDayPeriod}
                      onChange={(e) => setHalfDayPeriod(e.target.value as "FIRST_HALF" | "SECOND_HALF")}
                    >
                      <option value="FIRST_HALF">First Half (Morning)</option>
                      <option value="SECOND_HALF">Second Half (Afternoon / Evening)</option>
                    </select>
                  </div>
                )}

                {/* Date Inputs */}
                <div style={{ display: "grid", gridTemplateColumns: isHalfDay ? "1fr" : "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">{isHalfDay ? "Date" : "Start Date"}</label>
                    <input
                      type="date"
                      className="form-control"
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        if (isHalfDay || e.target.value > endDate) {
                          setEndDate(e.target.value);
                        }
                      }}
                      required
                    />
                  </div>

                  {!isHalfDay && (
                    <div>
                      <label className="form-label">End Date</label>
                      <input
                        type="date"
                        className="form-control"
                        value={endDate}
                        min={startDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        required
                      />
                    </div>
                  )}
                </div>

                {/* Holiday clash notice */}
                {holidaysInRange.length > 0 && (
                  <div className="alert alert-info" style={{ fontSize: "0.85rem" }}>
                    ℹ️ Note: <strong>{holidaysInRange.map((h) => h.name).join(", ")}</strong> falls in this range and will not be deducted from your leave quota.
                  </div>
                )}

                {/* Reason Textarea */}
                <div>
                  <label className="form-label">Reason for Leave (Mandatory)</label>
                  <textarea
                    className="form-control"
                    rows={3}
                    placeholder="Briefly explain the reason for your time off..."
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    required
                  />
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                    Minimum 3 characters required.
                  </div>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowApplyModal(false)}
                  disabled={applySubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={applySubmitting}
                >
                  {applySubmitting ? "Submitting..." : "Submit Application"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Cancel Leave Request
          ======================================================================= */}
      {cancellingRequestId && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "460px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">Confirm Leave Cancellation</h2>
              <button className="modal-close" onClick={() => setCancellingRequestId(null)}>
                &times;
              </button>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "1rem" }}>
              Are you sure you want to cancel this leave application? Any reserved or committed balance will be restored immediately.
            </p>

            <div style={{ marginBottom: "1.5rem" }}>
              <label className="form-label">Optional Cancellation Note</label>
              <textarea
                className="form-control"
                rows={2}
                placeholder="Reason for cancelling..."
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
              />
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setCancellingRequestId(null)}
                disabled={cancelSubmitting}
              >
                Go Back
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleConfirmCancel}
                disabled={cancelSubmitting}
              >
                {cancelSubmitting ? "Cancelling..." : "Confirm Cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

