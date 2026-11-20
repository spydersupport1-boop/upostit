"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  organizationApi,
  attendanceApi,
  DepartmentDto,
  EmployeeDto,
  AttendanceDayDto,
  AttendanceEventDto,
  ApiError,
} from "@/lib/api";
import TodayPunchWidget from "@/components/TodayPunchWidget";
import MyAttendanceTab from "@/components/MyAttendanceTab";
import AttendanceCorrectionModal from "@/components/AttendanceCorrectionModal";
import AttendanceAuditDrawer from "@/components/AttendanceAuditDrawer";

function formatMinutes(mins: number | null | undefined): string {
  if (mins === null || mins === undefined || mins <= 0) return "0m";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function formatTime(isoStr: string | null | undefined): string {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoStr;
  }
}

function getStatusBadge(status: string) {
  switch (status) {
    case "PRESENT":
      return <span className="badge badge-green">Present</span>;
    case "LATE":
      return <span className="badge badge-yellow">Late</span>;
    case "ABSENT":
      return <span className="badge badge-red">Absent</span>;
    case "HALF_DAY":
      return <span className="badge badge-yellow">Half Day</span>;
    case "INCOMPLETE":
      return <span className="badge badge-orange">Incomplete</span>;
    case "ON_LEAVE":
      return <span className="badge badge-blue">On Leave</span>;
    case "HOLIDAY":
      return <span className="badge badge-purple">Holiday</span>;
    case "WEEK_OFF":
      return <span className="badge">Week Off</span>;
    case "PENDING_REVIEW":
      return <span className="badge badge-yellow">Pending Review</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

function getCorrectionTypeBadge(category: string) {
  switch (category) {
    case "CORRECTION_INSERT":
      return <span className="badge badge-green">INSERT</span>;
    case "CORRECTION_SUPERSEDE":
      return <span className="badge badge-yellow">SUPERSEDE</span>;
    case "CORRECTION_VOID":
      return <span className="badge badge-red">VOID</span>;
    default:
      return <span className="badge">{category}</span>;
  }
}

export default function AttendancePage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, login, logout, error: authContextError } = useAuth();

  // Role detection
  const isEmployeeRole = user?.role === "employee";
  const isManagerRole = user?.role === "manager";

  // Navigation tab state for Admin / Manager
  const [activeTab, setActiveTab] = useState<"records" | "corrections" | "my_attendance">("records");

  // Filter States
  const todayStr = new Date().toISOString().split("T")[0];
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [departmentFilter, setDepartmentFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Data States
  const [days, setDays] = useState<AttendanceDayDto[]>([]);
  const [totalDays, setTotalDays] = useState(0);
  const [corrections, setCorrections] = useState<AttendanceEventDto[]>([]);
  const [totalCorrections, setTotalCorrections] = useState(0);
  const [departments, setDepartments] = useState<DepartmentDto[]>([]);
  const [allEmployees, setAllEmployees] = useState<EmployeeDto[]>([]);
  const [myProfile, setMyProfile] = useState<EmployeeDto | null>(null);

  // Loading States
  const [loadingDays, setLoadingDays] = useState(false);
  const [loadingCorrections, setLoadingCorrections] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Modals & Drawers
  const [showCorrectionModal, setShowCorrectionModal] = useState(false);
  const [correctionTarget, setCorrectionTarget] = useState<{
    employee: EmployeeDto;
    day: AttendanceDayDto | null;
  } | null>(null);

  const [drawerTarget, setDrawerTarget] = useState<{
    recordId: string | null;
    employeeName: string;
    attendanceDate: string;
  } | null>(null);

  // Inline Auth Form
  const [authTenantSlug, setAuthTenantSlug] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // ===========================================================================
  // Fetch Functions
  // ===========================================================================

  const fetchMyProfile = useCallback(async () => {
    if (!token) return;
    try {
      const profile = await organizationApi.getMyProfile(token);
      setMyProfile(profile);
    } catch {
      // Non-blocking
    }
  }, [token]);

  const fetchDepartments = useCallback(async () => {
    if (!token) return;
    try {
      const resp = await organizationApi.getDepartments({ limit: 100 }, token);
      setDepartments(resp.items);
    } catch {
      // Non-blocking
    }
  }, [token]);

  const fetchEmployees = useCallback(async () => {
    if (!token) return;
    try {
      const resp = await organizationApi.getEmployees({ page_size: 200 }, token);
      setAllEmployees(resp.items);
    } catch {
      // Non-blocking
    }
  }, [token]);

  // Determine authorized employee IDs based on role
  // If manager, only their direct reports + optionally themselves
  const managerEmployeeId = myProfile?.id;
  const authorizedEmployees = useMemo(() => {
    if (!isManagerRole) return allEmployees;
    if (!managerEmployeeId) {
      // Fallback: match by user's email if myProfile hasn't loaded yet
      const match = allEmployees.find((e) => e.work_email === user?.email);
      if (!match) return [];
      return allEmployees.filter(
        (e) => e.reporting_manager_id === match.id || e.id === match.id
      );
    }
    return allEmployees.filter(
      (e) => e.reporting_manager_id === managerEmployeeId || e.id === managerEmployeeId
    );
  }, [isManagerRole, allEmployees, managerEmployeeId, user?.email]);

  const authorizedEmpIdSet = useMemo(() => {
    if (!isManagerRole) return null;
    return new Set(authorizedEmployees.map((e) => e.id));
  }, [isManagerRole, authorizedEmployees]);

  const fetchDays = useCallback(async () => {
    if (!token) return;
    setLoadingDays(true);
    setPageError(null);
    try {
      const resp = await attendanceApi.getDays(
        {
          start_date: selectedDate,
          end_date: selectedDate,
          attendance_status: statusFilter !== "all" ? statusFilter : undefined,
          limit: 100,
        },
        token
      );

      // Apply manager scoping filter if role is manager
      let items = resp.items;
      if (isManagerRole && authorizedEmpIdSet) {
        items = items.filter((d) => authorizedEmpIdSet.has(d.employee_id));
      }

      // Apply department filter client-side if selected
      if (departmentFilter !== "all") {
        const empIdsInDept = new Set(
          allEmployees.filter((e) => e.department_id === departmentFilter).map((e) => e.id)
        );
        items = items.filter((d) => empIdsInDept.has(d.employee_id));
      }

      setDays(items);
      setTotalDays(items.length);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to load attendance records: ${err.detail}`);
      } else {
        setPageError("Network error while loading attendance records.");
      }
    } finally {
      setLoadingDays(false);
    }
  }, [token, selectedDate, departmentFilter, statusFilter, isManagerRole, authorizedEmpIdSet, allEmployees]);

  const fetchCorrections = useCallback(async () => {
    if (!token) return;
    setLoadingCorrections(true);
    try {
      const resp = await attendanceApi.getCorrections(
        { limit: 50 },
        token
      );

      let items = resp.items;
      if (isManagerRole && authorizedEmpIdSet) {
        items = items.filter((c) => authorizedEmpIdSet.has(c.employee_id));
      }

      setCorrections(items);
      setTotalCorrections(items.length);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to load corrections audit: ${err.detail}`);
      }
    } finally {
      setLoadingCorrections(false);
    }
  }, [token, isManagerRole, authorizedEmpIdSet]);

  // Initial & reactive effect
  useEffect(() => {
    if (!isAuthenticated || !token) return;
    fetchMyProfile();
    if (!isEmployeeRole) {
      fetchDepartments();
      fetchEmployees();
    }
  }, [isAuthenticated, token, isEmployeeRole, fetchMyProfile, fetchDepartments, fetchEmployees]);

  useEffect(() => {
    if (!isAuthenticated || !token || isEmployeeRole) return;
    if (activeTab === "records") {
      fetchDays();
    } else if (activeTab === "corrections") {
      fetchCorrections();
    }
  }, [activeTab, isAuthenticated, token, isEmployeeRole, fetchDays, fetchCorrections]);

  // ===========================================================================
  // Step 2: Dashboard Metrics (Calculated from live day records)
  // ===========================================================================
  const metrics = useMemo(() => {
    const present = days.filter((d) => d.status === "PRESENT" || d.status === "HALF_DAY" || d.status === "LATE").length;
    const absent = days.filter((d) => d.status === "ABSENT").length;
    const late = days.filter((d) => d.status === "LATE" || d.late_arrival_minutes > 0).length;
    const incomplete = days.filter((d) => d.status === "INCOMPLETE" || d.is_incomplete).length;
    const pendingVerification = days.filter((d) => d.status === "PENDING_REVIEW").length;
    const currentlyWorking = days.filter(
      (d) => d.first_check_in && !d.last_check_out && !d.is_incomplete
    ).length;
    const unresolvedSessions = days.filter(
      (d) => d.status === "INCOMPLETE" || d.is_incomplete || (d.first_check_in && !d.last_check_out)
    ).length;

    return {
      present,
      absent,
      late,
      incomplete,
      pendingVerification,
      currentlyWorking,
      unresolvedSessions,
    };
  }, [days]);

  // Client-side search filter
  const displayedDays = useMemo(() => {
    if (!searchQuery.trim()) return days;
    const q = searchQuery.toLowerCase().trim();
    return days.filter((d) => {
      const emp = allEmployees.find((e) => e.id === d.employee_id);
      const name = emp ? `${emp.first_name} ${emp.last_name}`.toLowerCase() : "";
      const code = emp ? emp.employee_id.toLowerCase() : "";
      return name.includes(q) || code.includes(q) || d.employee_id.toLowerCase().includes(q);
    });
  }, [days, searchQuery, allEmployees]);

  // Recalculate Day handler (via batch reconciliation)
  const handleRecalculateDate = async () => {
    if (!token) return;
    setRecalculating(true);
    setPageError(null);
    setPageSuccess(null);
    try {
      const res = await attendanceApi.reconcile(
        { target_date: selectedDate },
        token
      );
      setPageSuccess(
        `Attendance reconciled successfully for ${selectedDate}. Evaluated: ${res.total_candidates}, Recalculated: ${res.recalculated_count}, Failed: ${res.failed_count}.`
      );
      await fetchDays();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Recalculation failed: ${err.detail}`);
      } else {
        setPageError("Failed to trigger recalculation.");
      }
    } finally {
      setRecalculating(false);
    }
  };

  // Recalculate specific employee day handler
  const handleRecalculateSingle = async (employeeId: string, date: string) => {
    if (!token) return;
    try {
      await attendanceApi.recalculate(employeeId, date, token);
      setPageSuccess(`Recalculated attendance projection for ${date}.`);
      await fetchDays();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to recalculate: ${err.detail}`);
      }
    }
  };

  // ===========================================================================
  // Inline Auth Handler
  // ===========================================================================
  const handleInlineLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authEmail || !authPassword || !authTenantSlug) return;
    setAuthSubmitting(true);
    setAuthError(null);
    try {
      await login(authEmail.trim(), authPassword, authTenantSlug.trim());
      setPageSuccess("Successfully authenticated! Attendance console ready.");
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
  // RENDER: Unauthenticated State
  // ===========================================================================
  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying secure attendance session...</p>
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
            <span className="badge">Attendance</span>
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
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>⏱️</div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}>Attendance Console</h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
                Sign in with your enterprise credentials to access your punch card, daily attendance records, and audit timelines.
              </p>
            </div>

            {(authError || authContextError) && (
              <div className="alert alert-danger">
                <span>{authError || authContextError}</span>
                <button className="alert-close" onClick={() => setAuthError(null)}>
                  &times;
                </button>
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
                  placeholder="name@enterprise.com"
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
                  placeholder="••••••••••••"
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
                {authSubmitting ? "Authenticating..." : "Sign In to Attendance"}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Employee Self-Service View
  // ===========================================================================
  if (isEmployeeRole) {
    return (
      <div className="container">
        {/* Navigation Bar */}
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge badge-green">Employee Self-Service</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <Link href="/leave" className="btn btn-secondary btn-sm">
              🌴 Leave & Balances
            </Link>
            <Link href="/attendance/overtime" className="btn btn-secondary btn-sm">
              ⚡ Overtime
            </Link>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {user?.email}
            </span>
            <button className="btn btn-secondary btn-sm" onClick={logout}>
              Sign Out
            </button>
          </div>
        </nav>

        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          {/* Header Banner */}
          <div>
            <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>My Attendance</h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
              Record check-ins, monitor active working time, and inspect your immutable event timeline.
            </p>
          </div>

          {/* Today's Punch Widget */}
          {myProfile ? (
            <TodayPunchWidget
              employeeId={myProfile.id}
              employeeName={`${myProfile.first_name} ${myProfile.last_name}`}
              token={token!}
            />
          ) : (
            <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
              <p style={{ color: "var(--text-secondary)" }}>
                Loading your employee profile...
              </p>
            </div>
          )}

          {/* Personal Attendance History Tab */}
          {myProfile && (
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1rem" }}>
                Attendance Records History
              </h2>
              <MyAttendanceTab
                employeeId={myProfile.id}
                token={token!}
                onViewTimeline={(day) => {
                  setDrawerTarget({
                    recordId: day.id,
                    employeeName: `${myProfile.first_name} ${myProfile.last_name}`,
                    attendanceDate: day.attendance_date,
                  });
                }}
              />
            </div>
          )}
        </div>

        {/* Audit Drawer */}
        {drawerTarget && token && (
          <AttendanceAuditDrawer
            recordId={drawerTarget.recordId}
            employeeName={drawerTarget.employeeName}
            attendanceDate={drawerTarget.attendanceDate}
            token={token}
            onClose={() => setDrawerTarget(null)}
          />
        )}
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Admin / HR / Manager Console
  // ===========================================================================
  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge">
            {isManagerRole ? "Manager Console" : "Attendance Console"}
          </span>
          {tenant?.name && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
              • {tenant.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <Link href="/leave" className="btn btn-secondary btn-sm">
            🌴 Leave
          </Link>
          <Link href="/attendance/overtime" className="btn btn-secondary btn-sm">
            ⚡ Overtime
          </Link>
          <Link
            href="/attendance/corrections/conflicts"
            className="btn btn-secondary btn-sm"
            style={{ borderColor: "rgba(245, 158, 11, 0.4)", color: "#f59e0b" }}
          >
            ⚡ Conflicts
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
            🛡️ <strong>Manager Scope Active:</strong> Viewing attendance and authorized corrections
            for direct reports ({authorizedEmployees.length} employees). Self-correction is blocked by security policy.
          </span>
        </div>
      )}

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

      {/* Header with Title and Global Actions */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Workforce Attendance</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Live presence monitoring, calculation engine reconciliation, and auditable correction management.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          {authorizedEmployees.length > 0 && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                // Select first authorized employee by default
                const firstEmp = authorizedEmployees[0];
                setCorrectionTarget({
                  employee: firstEmp,
                  day: null,
                });
                setShowCorrectionModal(true);
              }}
            >
              ✏️ New Correction
            </button>
          )}

          <button
            className="btn btn-secondary btn-sm"
            onClick={handleRecalculateDate}
            disabled={recalculating}
          >
            {recalculating ? "Reconciling..." : "⚙️ Reconcile Day"}
          </button>
        </div>
      </div>

      {/* Step 2: KPI Metrics Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Present
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-success, #10b981)" }}>
            {metrics.present}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Absent
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-danger, #ef4444)" }}>
            {metrics.absent}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Late
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-warning, #f59e0b)" }}>
            {metrics.late}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Incomplete
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-orange, #f97316)" }}>
            {metrics.incomplete}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Pending Verification
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-purple, #a855f7)" }}>
            {metrics.pendingVerification}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Currently Working
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "var(--color-primary, #6366f1)" }}>
            {metrics.currentlyWorking}
          </div>
        </div>

        <div className="card" style={{ padding: "1rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Unresolved
          </div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: metrics.unresolvedSessions > 0 ? "var(--color-danger, #ef4444)" : "var(--text-secondary)" }}>
            {metrics.unresolvedSessions}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === "records" ? "active" : ""}`}
          onClick={() => setActiveTab("records")}
        >
          📅 Daily Attendance Records ({totalDays})
        </button>
        <button
          className={`tab-btn ${activeTab === "corrections" ? "active" : ""}`}
          onClick={() => setActiveTab("corrections")}
        >
          🔍 Corrections Audit Log ({totalCorrections})
        </button>
        <Link
          href="/attendance/corrections/conflicts"
          className="tab-btn"
          style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
        >
          ⚡ Offline Conflicts
        </Link>
        {myProfile && (
          <button
            className={`tab-btn ${activeTab === "my_attendance" ? "active" : ""}`}
            onClick={() => setActiveTab("my_attendance")}
          >
            👤 My Attendance Punch
          </button>
        )}
      </div>

      {/* TAB 1: ATTENDANCE RECORDS */}
      {activeTab === "records" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Filter Bar */}
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "1rem",
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  Date:
                </label>
                <input
                  type="date"
                  className="form-control"
                  style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "auto" }}
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                />
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  Department:
                </label>
                <select
                  className="form-control"
                  style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "auto" }}
                  value={departmentFilter}
                  onChange={(e) => setDepartmentFilter(e.target.value)}
                >
                  <option value="all">All Departments</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.code})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  Status:
                </label>
                <select
                  className="form-control"
                  style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "auto" }}
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">All Statuses</option>
                  <option value="PRESENT">Present</option>
                  <option value="LATE">Late</option>
                  <option value="HALF_DAY">Half Day</option>
                  <option value="ABSENT">Absent</option>
                  <option value="INCOMPLETE">Incomplete</option>
                  <option value="ON_LEAVE">On Leave</option>
                  <option value="HOLIDAY">Holiday</option>
                  <option value="WEEK_OFF">Week Off</option>
                  <option value="PENDING_REVIEW">Pending Review</option>
                </select>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="text"
                  placeholder="Search employee..."
                  className="form-control"
                  style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", minWidth: "160px" }}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>

            <button
              className="btn btn-secondary btn-sm"
              onClick={() => fetchDays()}
              disabled={loadingDays}
            >
              <span>🔄</span> {loadingDays ? "Loading..." : "Refresh"}
            </button>
          </div>

          {/* Records Table */}
          <div className="card" style={{ padding: "0", overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ width: "100%", margin: 0 }}>
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Date</th>
                    <th>Shift</th>
                    <th>Actual In / Out</th>
                    <th>Gross</th>
                    <th>Break</th>
                    <th>Net Work</th>
                    <th>Late</th>
                    <th>Early Exit</th>
                    <th>Overtime</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingDays ? (
                    <tr>
                      <td colSpan={12} style={{ textAlign: "center", padding: "3rem" }}>
                        <div className="spinner-container" style={{ margin: 0 }}>
                          <div className="spinner" />
                          <p>Loading attendance records for {selectedDate}...</p>
                        </div>
                      </td>
                    </tr>
                  ) : displayedDays.length === 0 ? (
                    <tr>
                      <td colSpan={12} style={{ textAlign: "center", padding: "3rem" }}>
                        <div style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
                          No attendance records found matching filters for {selectedDate}.
                        </div>
                      </td>
                    </tr>
                  ) : (
                    displayedDays.map((day) => {
                      const emp = allEmployees.find((e) => e.id === day.employee_id);
                      const isSelf = myProfile?.id === day.employee_id;
                      const canCorrect = !isManagerRole || !isSelf;

                      return (
                        <tr key={day.id || `${day.employee_id}-${day.attendance_date}`}>
                          <td>
                            <div style={{ fontWeight: 600 }}>
                              {emp ? `${emp.first_name} ${emp.last_name}` : (day.employee_name || day.employee_id.slice(0, 8))}
                            </div>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                              {emp ? emp.employee_id : (day.employee_number || day.employee_id)}
                            </div>
                          </td>
                          <td style={{ fontSize: "0.85rem" }}>{day.attendance_date}</td>
                          <td>
                            {day.shift_name ? (
                              <span style={{ fontSize: "0.85rem" }}>{day.shift_name}</span>
                            ) : (
                              <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>—</span>
                            )}
                          </td>
                          <td style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>
                            {day.first_check_in ? (
                              <>
                                <span style={{ color: "var(--color-success, #10b981)" }}>
                                  {formatTime(day.first_check_in)}
                                </span>
                                {" → "}
                                <span style={{ color: day.last_check_out ? "var(--color-primary, #6366f1)" : "var(--text-secondary)" }}>
                                  {day.last_check_out ? formatTime(day.last_check_out) : "Active"}
                                </span>
                              </>
                            ) : (
                              <span style={{ color: "var(--text-secondary)" }}>—</span>
                            )}
                          </td>
                          <td style={{ fontSize: "0.85rem" }}>{formatMinutes(day.total_working_minutes)}</td>
                          <td style={{ fontSize: "0.85rem" }}>{formatMinutes(day.total_break_minutes)}</td>
                          <td style={{ fontSize: "0.85rem", fontWeight: 600 }}>
                            {formatMinutes(day.net_working_minutes)}
                          </td>
                          <td>
                            {day.late_arrival_minutes > 0 ? (
                              <span className="badge badge-yellow" style={{ fontSize: "0.75rem" }}>
                                +{day.late_arrival_minutes}m
                              </span>
                            ) : (
                              <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>—</span>
                            )}
                          </td>
                          <td>
                            {day.early_departure_minutes > 0 ? (
                              <span className="badge badge-orange" style={{ fontSize: "0.75rem" }}>
                                -{day.early_departure_minutes}m
                              </span>
                            ) : (
                              <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>—</span>
                            )}
                          </td>
                          <td>
                            {day.overtime_minutes && day.overtime_minutes > 0 ? (
                              <span className="badge badge-purple" style={{ fontSize: "0.75rem" }}>
                                +{formatMinutes(day.overtime_minutes)}
                              </span>
                            ) : (
                              <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>—</span>
                            )}
                          </td>
                          <td>{getStatusBadge(day.status)}</td>
                          <td style={{ textAlign: "right" }}>
                            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.4rem" }}>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setDrawerTarget({
                                  recordId: day.id,
                                  employeeName: emp ? `${emp.first_name} ${emp.last_name}` : (day.employee_name || day.employee_id),
                                  attendanceDate: day.attendance_date,
                                })}
                                style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                                title="Inspect audit timeline"
                              >
                                ⏱️
                              </button>
                              {canCorrect && emp && (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => {
                                    setCorrectionTarget({
                                      employee: emp,
                                      day: day,
                                    });
                                    setShowCorrectionModal(true);
                                  }}
                                  style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                                  title="Create attendance correction"
                                >
                                  ✏️
                                </button>
                              )}
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleRecalculateSingle(day.employee_id, day.attendance_date)}
                                style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                                title="Recalculate day projection"
                              >
                                ⚙️
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: CORRECTIONS AUDIT LOG */}
      {activeTab === "corrections" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Attendance Corrections Audit Trail</h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                Immutable correction events with mandatory reason justification and actor tracking.
              </p>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => fetchCorrections()}
              disabled={loadingCorrections}
            >
              <span>🔄</span> {loadingCorrections ? "Loading..." : "Refresh"}
            </button>
          </div>

          <div className="card" style={{ padding: "0", overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ width: "100%", margin: 0 }}>
                <thead>
                  <tr>
                    <th>Created At</th>
                    <th>Employee</th>
                    <th>Type</th>
                    <th>Reason</th>
                    <th>Effective At</th>
                    <th>Target Event</th>
                    <th>Actor ID</th>
                    <th style={{ textAlign: "right" }}>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingCorrections ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "3rem" }}>
                        <div className="spinner-container" style={{ margin: 0 }}>
                          <div className="spinner" />
                          <p>Loading correction history...</p>
                        </div>
                      </td>
                    </tr>
                  ) : corrections.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "3rem" }}>
                        <div style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
                          No correction audit entries found.
                        </div>
                      </td>
                    </tr>
                  ) : (
                    corrections.map((c) => {
                      const emp = allEmployees.find((e) => e.id === c.employee_id);
                      return (
                        <tr key={c.id}>
                          <td style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>
                            {formatTime(c.created_at)} ({c.created_at.slice(0, 10)})
                          </td>
                          <td>
                            <div style={{ fontWeight: 600 }}>
                              {emp ? `${emp.first_name} ${emp.last_name}` : c.employee_id.slice(0, 8)}
                            </div>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                              {emp ? emp.employee_id : c.employee_id}
                            </div>
                          </td>
                          <td>{getCorrectionTypeBadge(c.event_category)}</td>
                          <td style={{ maxWidth: "260px" }}>
                            <div
                              style={{
                                fontSize: "0.85rem",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                              title={c.correction_reason || ""}
                            >
                              &ldquo;{c.correction_reason}&rdquo;
                            </div>
                          </td>
                          <td style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>
                            {c.effective_at ? formatTime(c.effective_at) : "—"}
                          </td>
                          <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                            {c.supersedes_event_id ? c.supersedes_event_id.slice(0, 8) : "—"}
                          </td>
                          <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                            {c.actor_user_id ? c.actor_user_id.slice(0, 8) : "—"}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => {
                                const effDate = c.effective_at ? c.effective_at.slice(0, 10) : selectedDate;
                                setDrawerTarget({
                                  recordId: null,
                                  employeeName: emp ? `${emp.first_name} ${emp.last_name}` : c.employee_id,
                                  attendanceDate: effDate,
                                });
                              }}
                              style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                            >
                              ⏱️ Timeline
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: PERSONAL PUNCH FOR ADMIN / MANAGER */}
      {activeTab === "my_attendance" && myProfile && (
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          <TodayPunchWidget
            employeeId={myProfile.id}
            employeeName={`${myProfile.first_name} ${myProfile.last_name}`}
            token={token!}
          />
          <div className="card" style={{ padding: "1.5rem" }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1rem" }}>
              My Personal Attendance History
            </h2>
            <MyAttendanceTab
              employeeId={myProfile.id}
              token={token!}
              onViewTimeline={(day) => {
                setDrawerTarget({
                  recordId: day.id,
                  employeeName: `${myProfile.first_name} ${myProfile.last_name}`,
                  attendanceDate: day.attendance_date,
                });
              }}
            />
          </div>
        </div>
      )}

      {/* Modals and Drawers */}
      {showCorrectionModal && token && correctionTarget && (
        <AttendanceCorrectionModal
          employeeId={correctionTarget.employee.id}
          employeeName={`${correctionTarget.employee.first_name} ${correctionTarget.employee.last_name}`}
          attendanceDay={correctionTarget.day}
          token={token}
          onClose={() => {
            setShowCorrectionModal(false);
            setCorrectionTarget(null);
          }}
          onSuccess={() => {
            setPageSuccess("Attendance correction applied and registered in audit log.");
            fetchDays();
            fetchCorrections();
          }}
        />
      )}

      {drawerTarget && token && (
        <AttendanceAuditDrawer
          recordId={drawerTarget.recordId}
          employeeName={drawerTarget.employeeName}
          attendanceDate={drawerTarget.attendanceDate}
          token={token}
          onClose={() => setDrawerTarget(null)}
        />
      )}
    </div>
  );
}
