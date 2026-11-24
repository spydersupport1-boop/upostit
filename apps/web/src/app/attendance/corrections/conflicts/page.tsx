"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  conflictApi,
  organizationApi,
  SupervisorConflictQueueItemDto,
  EmployeeDto,
  ApiError,
} from "@/lib/api";
import ConflictIncidentDetailModal from "@/components/ConflictIncidentDetailModal";

export default function SupervisorConflictsPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout, login } = useAuth();

  // Role detection
  const isEmployeeRole = user?.role?.toLowerCase() === "employee";
  const isManagerRole = user?.role?.toLowerCase() === "manager";
  const isPrivilegedRole = user?.role && ["hr", "admin", "owner"].includes(user.role.toLowerCase());

  // Data states
  const [incidents, setIncidents] = useState<SupervisorConflictQueueItemDto[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [employeeFilter, setEmployeeFilter] = useState<string>("ALL");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [pageSize, setPageSize] = useState<number>(50);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);

  // Employee list for filter dropdown (if privileged)
  const [employees, setEmployees] = useState<EmployeeDto[]>([]);

  // Selected incident for forensic inspection modal
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);

  // Inline auth state for unauthenticated visitors
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authTenantSlug, setAuthTenantSlug] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Fetch queue items
  const fetchQueue = useCallback(async () => {
    if (!token || isEmployeeRole) return;
    setLoading(true);
    setPageError(null);
    try {
      const resp = await conflictApi.getSupervisorQueue(
        {
          status: statusFilter !== "ALL" ? statusFilter : undefined,
          employee_id: employeeFilter !== "ALL" ? employeeFilter : undefined,
          start_date: startDate ? startDate : undefined,
          end_date: endDate ? endDate : undefined,
          limit: pageSize,
          cursor: cursor || undefined,
        },
        token
      );

      setIncidents(resp.items || []);
      setTotalCount(resp.total);
      setHasMore(resp.has_more);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setPageError("Access Denied (403): You do not have permission to review attendance conflicts.");
        } else {
          setPageError(err.detail);
        }
      } else {
        setPageError("Failed to fetch conflict incidents queue.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, isEmployeeRole, statusFilter, employeeFilter, startDate, endDate, pageSize, cursor]);

  // Load employees list for dropdown
  useEffect(() => {
    if (!token || isEmployeeRole || !isPrivilegedRole) return;
    organizationApi
      .getEmployees({ page_size: 100 }, token)
      .then((res) => setEmployees(res.items || []))
      .catch(() => {});
  }, [token, isEmployeeRole, isPrivilegedRole]);

  useEffect(() => {
    if (isAuthenticated && token && !isEmployeeRole) {
      fetchQueue();
    }
  }, [isAuthenticated, token, isEmployeeRole, fetchQueue]);

  // Compute KPI counts across loaded queue
  const kpiMetrics = useMemo(() => {
    const pending = incidents.filter((i) => i.status === "PENDING_REVIEW").length;
    const approved = incidents.filter((i) => i.status === "APPROVED").length;
    const rejected = incidents.filter((i) => i.status === "REJECTED").length;
    return {
      total: totalCount || incidents.length,
      pending,
      approved,
      rejected,
    };
  }, [incidents, totalCount]);

  // Client search filter (by employee name, code, bundle ID)
  const filteredIncidents = useMemo(() => {
    if (!searchQuery.trim()) return incidents;
    const q = searchQuery.toLowerCase().trim();
    return incidents.filter((item) => {
      return (
        item.employee_name.toLowerCase().includes(q) ||
        item.employee_code.toLowerCase().includes(q) ||
        item.bundle_id.toLowerCase().includes(q) ||
        (item.department_name && item.department_name.toLowerCase().includes(q))
      );
    });
  }, [incidents, searchQuery]);

  const handleInlineLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authEmail || !authPassword || !authTenantSlug) return;
    setAuthSubmitting(true);
    setAuthError(null);
    try {
      await login(authEmail.trim(), authPassword, authTenantSlug.trim());
      setPageSuccess("Authenticated successfully. Loading supervisor console...");
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

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "PENDING_REVIEW":
        return <span className="badge badge-yellow">Pending Review</span>;
      case "APPROVED":
        return <span className="badge badge-green">Approved</span>;
      case "REJECTED":
        return <span className="badge badge-red">Rejected</span>;
      case "NEEDS_CLARIFICATION":
        return <span className="badge badge-purple">Needs Clarification</span>;
      case "UNRESOLVED":
        return <span className="badge badge-yellow" style={{ background: "rgba(249, 115, 22, 0.15)", color: "#f97316" }}>Unresolved</span>;
      case "ESCALATED_HR":
        return <span className="badge badge-red" style={{ fontWeight: 700 }}>Escalated to HR</span>;
      case "AUTO_RESOLVED":
        return <span className="badge badge-green">Auto-Resolved</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  const getSeverityBadge = (severity?: string | null) => {
    switch ((severity || "MEDIUM").toUpperCase()) {
      case "CRITICAL":
        return <span className="badge badge-red" style={{ fontWeight: 700 }}>CRITICAL</span>;
      case "HIGH":
        return <span className="badge badge-yellow" style={{ color: "#ea580c", fontWeight: 700 }}>HIGH</span>;
      case "LOW":
        return <span className="badge" style={{ opacity: 0.8 }}>LOW</span>;
      default:
        return <span className="badge badge-yellow">MEDIUM</span>;
    }
  };

  const formatDateTime = (iso: string | null | undefined): string => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
    } catch {
      return iso;
    }
  };

  // 1. Loading auth state
  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying secure supervisor session...</p>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated state
  if (!isAuthenticated) {
    return (
      <div className="container">
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge">Supervisor Console</span>
          </div>
          <div>
            <Link href="/attendance" className="btn btn-secondary btn-sm">
              ← Attendance
            </Link>
          </div>
        </nav>

        <div style={{ maxWidth: "480px", margin: "3rem auto" }}>
          <div className="card" style={{ padding: "2.5rem" }}>
            <div style={{ textAlign: "center", marginBottom: "2rem" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>🛡️</div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}>Supervisor Adjudication</h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
                Sign in with Manager or HR/Admin credentials to review and adjudicate offline sequence conflicts.
              </p>
            </div>

            {authError && (
              <div className="alert alert-danger">
                <span>{authError}</span>
              </div>
            )}

            <form onSubmit={handleInlineLogin}>
              <div className="form-group">
                <label className="form-label">Company Workspace Slug</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. acme-corp"
                  className="form-control"
                  value={authTenantSlug}
                  onChange={(e) => setAuthTenantSlug(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Work Email</label>
                <input
                  type="email"
                  required
                  placeholder="manager@enterprise.com"
                  className="form-control"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  className="form-control"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", marginTop: "1rem" }}
                disabled={authSubmitting}
              >
                {authSubmitting ? "Authenticating..." : "Sign In to Supervisor Console"}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // 3. Employee Access Denied View
  if (isEmployeeRole) {
    return (
      <div className="container">
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge badge-yellow">Access Restricted</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <Link href="/attendance" className="btn btn-secondary btn-sm">
              ← My Attendance
            </Link>
            <button className="btn btn-secondary btn-sm" onClick={logout}>
              Sign Out
            </button>
          </div>
        </nav>

        <div className="card" style={{ maxWidth: "600px", margin: "4rem auto", padding: "2.5rem", textAlign: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🚫</div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800, marginBottom: "0.75rem" }}>
            Supervisor Adjudication Queue Restricted
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", lineHeight: 1.6 }}>
            The offline attendance conflict adjudication queue is restricted to authorized Managers, HR, and Admin supervisors.
            Employees can track their submitted review requests directly in the mobile app.
          </p>
          <div style={{ marginTop: "2rem" }}>
            <Link href="/attendance" className="btn btn-primary">
              Return to My Attendance
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 4. Authorized Supervisor Console
  return (
    <div className="container">
      {/* Navigation */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge">
            {isManagerRole ? "Manager Review Queue" : "Supervisor Conflict Console"}
          </span>
          {tenant?.name && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
              • {tenant.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Link href="/attendance" className="btn btn-secondary btn-sm">
            ⏱️ Attendance Console
          </Link>
          <Link href="/organization" className="btn btn-secondary btn-sm">
            🏢 Organization
          </Link>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {user?.email} ({user?.role})
          </span>
          <button className="btn btn-secondary btn-sm" onClick={logout}>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Scope Alert for Manager */}
      {isManagerRole && (
        <div className="alert alert-info" style={{ marginBottom: "1.5rem" }}>
          <span>
            🛡️ <strong>Manager Reporting-Line Scope Active:</strong> The backend automatically scopes
            this queue to conflict incidents submitted by your direct reports. Self-adjudication is rejected
            by anti-self-approval enforcement.
          </span>
        </div>
      )}

      {/* Page Alerts */}
      {pageError && (
        <div
          className="alert alert-danger"
          style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between" }}
        >
          <span>{pageError}</span>
          <button className="alert-close" onClick={() => setPageError(null)}>
            &times;
          </button>
        </div>
      )}

      {pageSuccess && (
        <div
          className="alert alert-success"
          style={{ marginBottom: "1.5rem", display: "flex", justifyContent: "space-between" }}
        >
          <span>{pageSuccess}</span>
          <button className="alert-close" onClick={() => setPageSuccess(null)}>
            &times;
          </button>
        </div>
      )}

      {/* Header Banner */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Offline Conflict Review Queue</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Inspect, audit forensic evidence, and adjudicate attendance session conflicts submitted from mobile devices.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchQueue} disabled={loading}>
          {loading ? "Refreshing..." : "↻ Refresh Queue"}
        </button>
      </div>

      {/* KPI Metrics Cards */}
      <div className="stats-grid" style={{ marginBottom: "1.5rem" }}>
        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(99, 102, 241, 0.12)", color: "#818cf8" }}>
            ⚡
          </div>
          <div className="stat-content">
            <div className="stat-val">{kpiMetrics.total}</div>
            <div className="stat-label">Total Incidents</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(245, 158, 11, 0.12)", color: "#f59e0b" }}>
            ⏳
          </div>
          <div className="stat-content">
            <div className="stat-val" style={{ color: "#f59e0b" }}>{kpiMetrics.pending}</div>
            <div className="stat-label">Pending Review</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(16, 185, 129, 0.12)", color: "#34d399" }}>
            ✓
          </div>
          <div className="stat-content">
            <div className="stat-val" style={{ color: "#34d399" }}>{kpiMetrics.approved}</div>
            <div className="stat-label">Approved</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(239, 68, 68, 0.12)", color: "#f87171" }}>
            ✕
          </div>
          <div className="stat-content">
            <div className="stat-val" style={{ color: "#f87171" }}>{kpiMetrics.rejected}</div>
            <div className="stat-label">Rejected</div>
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="toolbar">
        <input
          type="text"
          className="search-input"
          placeholder="Search employee, ID, or bundle..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          {/* Status Filter */}
          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCursor(null);
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="PENDING_REVIEW">Pending Review</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="NEEDS_CLARIFICATION">Needs Clarification</option>
            <option value="UNRESOLVED">Unresolved</option>
            <option value="ESCALATED_HR">Escalated to HR</option>
            <option value="AUTO_RESOLVED">Auto-Resolved</option>
          </select>

          {/* Employee Filter (HR/Admin only) */}
          {isPrivilegedRole && (
            <select
              className="filter-select"
              value={employeeFilter}
              onChange={(e) => {
                setEmployeeFilter(e.target.value);
                setCursor(null);
              }}
            >
              <option value="ALL">All Employees</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.first_name} {emp.last_name} ({emp.employee_id})
                </option>
              ))}
            </select>
          )}

          {/* Date Filters */}
          <input
            type="date"
            className="filter-select"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setCursor(null);
            }}
            title="Submission Start Date"
          />
          <input
            type="date"
            className="filter-select"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setCursor(null);
            }}
            title="Submission End Date"
          />

          {/* Clear Filters Button */}
          {(statusFilter !== "ALL" || employeeFilter !== "ALL" || startDate || endDate || searchQuery) && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setStatusFilter("ALL");
                setEmployeeFilter("ALL");
                setStartDate("");
                setEndDate("");
                setSearchQuery("");
                setCursor(null);
              }}
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {/* Incidents Table */}
      <div className="table-container">
        {loading && incidents.length === 0 ? (
          <div className="spinner-container" style={{ padding: "4rem" }}>
            <div className="spinner" />
            <p style={{ color: "var(--text-secondary)", marginTop: "1rem" }}>
              Loading supervisor review queue...
            </p>
          </div>
        ) : filteredIncidents.length === 0 ? (
          <div style={{ padding: "3rem", textAlign: "center" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>✓</div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.25rem" }}>
              No Conflict Incidents Found
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              {statusFilter === "PENDING_REVIEW"
                ? "All offline attendance conflicts have been reviewed and adjudicated."
                : "No incidents matched your selected filter parameters."}
            </p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Conflict Type</th>
                <th>Severity</th>
                <th>Submitted</th>
                <th>Primary Punch</th>
                <th>Quarantined</th>
                <th>Rejection Summary</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredIncidents.map((inc) => (
                <tr key={inc.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{inc.employee_name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {inc.employee_code} • {inc.department_name || "General"}
                    </div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: "0.825rem", fontFamily: "monospace" }}>
                      {inc.conflict_code || "SEQUENCE_CONFLICT"}
                    </div>
                  </td>
                  <td>{getSeverityBadge(inc.severity)}</td>
                  <td style={{ fontSize: "0.85rem" }}>{formatDateTime(inc.submitted_at)}</td>
                  <td>
                    <span
                      className={`badge ${
                        inc.primary_event_type === "CHECK_IN" ? "badge-green" : "badge-yellow"
                      }`}
                    >
                      {inc.primary_event_type}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-purple">
                      {inc.total_events_count > 1
                        ? `+${inc.total_events_count - 1} punch${inc.total_events_count > 2 ? "es" : ""}`
                        : "0 punches"}
                    </span>
                  </td>
                  <td style={{ maxWidth: "220px" }}>
                    <div
                      style={{
                        fontSize: "0.825rem",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        color: "var(--text-secondary)",
                      }}
                      title={inc.rejection_summary || "Policy violation"}
                    >
                      {inc.rejection_summary || "Policy violation"}
                    </div>
                    {inc.employee_clarification && (
                      <div style={{ fontSize: "0.72rem", color: "#34d399", marginTop: "2px" }}>
                        💬 Clarification provided
                      </div>
                    )}
                  </td>
                  <td>{getStatusBadge(inc.status)}</td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setSelectedIncidentId(inc.id)}
                    >
                      {inc.status === "PENDING_REVIEW" ? "Inspect & Adjudicate" : "View Evidence"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
          marginBottom: "3rem",
        }}
      >
        <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
          Showing <strong>{filteredIncidents.length}</strong> of <strong>{totalCount}</strong> incidents
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <select
            className="filter-select"
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCursor(null);
            }}
          >
            <option value={20}>20 per page</option>
            <option value={50}>50 per page</option>
            <option value={100}>100 per page</option>
          </select>

          {hasMore && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                if (incidents.length > 0) {
                  setCursor(incidents[incidents.length - 1].submitted_at);
                }
              }}
              disabled={loading}
            >
              Next Page →
            </button>
          )}
        </div>
      </div>

      {/* Forensic Inspection Modal */}
      {selectedIncidentId && token && (
        <ConflictIncidentDetailModal
          incidentId={selectedIncidentId}
          token={token}
          currentUserRole={user?.role}
          currentUserId={user?.id}
          onClose={() => setSelectedIncidentId(null)}
          onDecisionSuccess={() => {
            fetchQueue();
          }}
        />
      )}
    </div>
  );
}
