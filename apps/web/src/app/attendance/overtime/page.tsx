"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  overtimeApi,
  organizationApi,
  OvertimeRecordDto,
  OvertimeRuleDto,
  EmployeeDto,
  OvertimeRuleCreateRequestDto,
  OvertimeRuleUpdateRequestDto,
  ApiError,
} from "@/lib/api";

function formatMinutes(mins: number | null | undefined): string {
  if (mins === null || mins === undefined || mins <= 0) return "0m";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function getOvertimeStatusBadge(status: string) {
  switch (status) {
    case "AUTO_APPROVED":
      return <span className="badge badge-green">Auto-Approved</span>;
    case "APPROVED":
      return <span className="badge badge-green">Approved</span>;
    case "PENDING_APPROVAL":
      return <span className="badge badge-yellow">Pending Review</span>;
    case "REJECTED":
      return <span className="badge badge-red">Rejected</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

function getCategoryBadge(type: string) {
  switch (type) {
    case "HOLIDAY":
      return <span className="badge badge-purple">Statutory Holiday</span>;
    case "WEEK_OFF":
      return <span className="badge badge-blue">Weekly Off / Rest Day</span>;
    case "WORKDAY":
      return <span className="badge">Regular Workday</span>;
    default:
      return <span className="badge">{type}</span>;
  }
}

export default function OvertimeConsolePage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();

  // Role detection
  const isEmployeeRole = user?.role === "employee";
  const isManagerRole = user?.role === "manager";
  const isPrivilegedRole = user?.role && ["hr", "admin", "owner"].includes(user.role);

  // Tab State: "records" (supervisor queue / my records) vs "rules" (HR/Admin configuration)
  const [activeTab, setActiveTab] = useState<"records" | "rules">("records");

  // Records Data States
  const [records, setRecords] = useState<OvertimeRecordDto[]>([]);
  const [employees, setEmployees] = useState<EmployeeDto[]>([]);
  const [loadingRecords, setLoadingRecords] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Filter States
  const [statusFilter, setStatusFilter] = useState<string>(isEmployeeRole ? "ALL" : "PENDING_APPROVAL");
  const [employeeFilter, setEmployeeFilter] = useState<string>("");
  const [startDateFilter, setStartDateFilter] = useState<string>("");
  const [endDateFilter, setEndDateFilter] = useState<string>("");

  // Rules Data States
  const [rules, setRules] = useState<OvertimeRuleDto[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);

  // Adjudication Modal State
  const [selectedRecord, setSelectedRecord] = useState<OvertimeRecordDto | null>(null);
  const [decisionAction, setDecisionAction] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [decisionReason, setDecisionReason] = useState<string>("");
  const [adjustedMinutes, setAdjustedMinutes] = useState<number | null>(null);
  const [decisionSubmitting, setDecisionSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Rule Create / Edit Modal State
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRule, setEditingRule] = useState<OvertimeRuleDto | null>(null);
  const [ruleSubmitting, setRuleSubmitting] = useState(false);
  const [ruleError, setRuleError] = useState<string | null>(null);
  const [ruleForm, setRuleForm] = useState<OvertimeRuleCreateRequestDto>({
    name: "",
    min_overtime_threshold_minutes: 30,
    max_daily_overtime_minutes: 240,
    max_weekly_overtime_minutes: 720,
    workday_multiplier: 1.5,
    weekend_multiplier: 2.0,
    holiday_multiplier: 2.0,
    requires_manager_approval: true,
    requires_pre_approval: false,
    is_default: false,
    is_active: true,
  });

  // Check if current user is the employee for the selected record (Anti-Self-Approval)
  const isSelfRecord = useMemo(() => {
    if (!selectedRecord || !user) return false;
    const emp = employees.find((e) => e.id === selectedRecord.employee_id);
    return Boolean(
      (emp?.work_email && emp.work_email.toLowerCase() === user.email?.toLowerCase()) ||
      (emp?.user_id && emp.user_id === user.id) ||
      selectedRecord.employee_id === user.id
    );
  }, [selectedRecord, employees, user]);

  // ===========================================================================
  // Fetch Functions
  // ===========================================================================

  const fetchRecords = useCallback(async () => {
    if (!token) return;
    setLoadingRecords(true);
    setPageError(null);
    try {
      if (isEmployeeRole) {
        const resp = await overtimeApi.getMyRecords(
          {
            status: statusFilter === "ALL" ? undefined : statusFilter,
            start_date: startDateFilter || undefined,
            end_date: endDateFilter || undefined,
            limit: 100,
          },
          token
        );
        setRecords(resp.items || []);
      } else {
        const resp = await overtimeApi.getRecords(
          {
            status: statusFilter === "ALL" ? undefined : statusFilter,
            employee_id: employeeFilter || undefined,
            start_date: startDateFilter || undefined,
            end_date: endDateFilter || undefined,
            limit: 100,
          },
          token
        );
        setRecords(resp.items || []);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to fetch overtime records.");
      }
    } finally {
      setLoadingRecords(false);
    }
  }, [token, isEmployeeRole, statusFilter, employeeFilter, startDateFilter, endDateFilter]);

  const fetchRules = useCallback(async () => {
    if (!token || !isPrivilegedRole) return;
    setLoadingRules(true);
    try {
      const resp = await overtimeApi.getRules({ limit: 50 }, token);
      setRules(resp.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to fetch overtime rules.");
      }
    } finally {
      setLoadingRules(false);
    }
  }, [token, isPrivilegedRole]);

  // Load employee directory for filter dropdown
  useEffect(() => {
    if (!token || isEmployeeRole) return;
    organizationApi
      .getEmployees({ page_size: 200 }, token)
      .then((res) => setEmployees(res.items || []))
      .catch(() => {});
  }, [token, isEmployeeRole]);

  useEffect(() => {
    if (isAuthenticated && token) {
      if (activeTab === "records") {
        fetchRecords();
      } else if (activeTab === "rules" && isPrivilegedRole) {
        fetchRules();
      }
    }
  }, [isAuthenticated, token, activeTab, isPrivilegedRole, fetchRecords, fetchRules]);

  // ===========================================================================
  // Overtime Adjudication Handlers
  // ===========================================================================

  const handleOpenAdjudicate = (rec: OvertimeRecordDto) => {
    setSelectedRecord(rec);
    setDecisionAction("APPROVE");
    setDecisionReason("");
    setAdjustedMinutes(rec.approved_overtime_minutes > 0 ? rec.approved_overtime_minutes : rec.raw_overtime_minutes);
    setModalError(null);
  };

  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedRecord) return;

    if (decisionAction === "REJECT" && decisionReason.trim().length < 3) {
      setModalError("Rejection requires an explanatory reason (minimum 3 characters).");
      return;
    }

    setDecisionSubmitting(true);
    setModalError(null);

    try {
      await overtimeApi.adjudicateRecord(
        selectedRecord.id,
        {
          action: decisionAction,
          reason: decisionReason.trim() || undefined,
          approved_minutes: decisionAction === "APPROVE" ? adjustedMinutes : 0,
        },
        token
      );

      setPageSuccess(
        `Overtime on ${selectedRecord.attendance_date} for ${selectedRecord.employee_name || "employee"} was successfully ${
          decisionAction === "APPROVE" ? "approved" : "rejected"
        }.`
      );
      setSelectedRecord(null);
      await fetchRecords();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to submit overtime decision.");
      }
    } finally {
      setDecisionSubmitting(false);
    }
  };

  // ===========================================================================
  // Overtime Rule Management Handlers
  // ===========================================================================

  const handleOpenCreateRule = () => {
    setEditingRule(null);
    setRuleForm({
      name: "",
      min_overtime_threshold_minutes: 30,
      max_daily_overtime_minutes: 240,
      max_weekly_overtime_minutes: 720,
      workday_multiplier: 1.5,
      weekend_multiplier: 2.0,
      holiday_multiplier: 2.0,
      requires_manager_approval: true,
      requires_pre_approval: false,
      is_default: rules.length === 0,
      is_active: true,
    });
    setRuleError(null);
    setShowRuleModal(true);
  };

  const handleOpenEditRule = (rule: OvertimeRuleDto) => {
    setEditingRule(rule);
    setRuleForm({
      name: rule.name,
      min_overtime_threshold_minutes: rule.min_overtime_threshold_minutes,
      max_daily_overtime_minutes: rule.max_daily_overtime_minutes,
      max_weekly_overtime_minutes: rule.max_weekly_overtime_minutes,
      workday_multiplier: Number(rule.workday_multiplier),
      weekend_multiplier: Number(rule.weekend_multiplier),
      holiday_multiplier: Number(rule.holiday_multiplier),
      requires_manager_approval: rule.requires_manager_approval,
      requires_pre_approval: rule.requires_pre_approval,
      is_default: rule.is_default,
      is_active: rule.is_active,
    });
    setRuleError(null);
    setShowRuleModal(true);
  };

  const handleRuleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    if (!ruleForm.name?.trim()) {
      setRuleError("Rule title is required.");
      return;
    }

    setRuleSubmitting(true);
    setRuleError(null);

    try {
      if (editingRule) {
        await overtimeApi.updateRule(editingRule.id, ruleForm, token);
        setPageSuccess(`Overtime rule '${ruleForm.name}' updated.`);
      } else {
        await overtimeApi.createRule(ruleForm, token);
        setPageSuccess(`Overtime rule '${ruleForm.name}' created.`);
      }
      setShowRuleModal(false);
      await fetchRules();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setRuleError(err.detail);
      } else {
        setRuleError("Failed to save overtime rule.");
      }
    } finally {
      setRuleSubmitting(false);
    }
  };

  const handleDeleteRule = async (rule: OvertimeRuleDto) => {
    if (!token) return;
    const confirm = window.confirm(`Are you sure you want to delete rule '${rule.name}'?`);
    if (!confirm) return;

    try {
      await overtimeApi.deleteRule(rule.id, token);
      setPageSuccess(`Rule '${rule.name}' deleted.`);
      await fetchRules();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setPageError(`Cannot delete rule '${rule.name}': It is referenced by calculated overtime records.`);
        } else {
          setPageError(err.detail);
        }
      } else {
        setPageError("Failed to delete overtime rule.");
      }
    }
  };

  // ===========================================================================
  // RENDER: Loading & Unauthenticated
  // ===========================================================================

  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying session credentials...</p>
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
            <span className="badge badge-amber">Overtime Console</span>
          </div>
          <div>
            <Link href="/" className="btn btn-secondary btn-sm">
              ← Home
            </Link>
          </div>
        </nav>

        <div style={{ maxWidth: "480px", margin: "4rem auto", textAlign: "center" }}>
          <div className="card" style={{ padding: "3rem" }}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>⚡</div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>Authentication Required</h1>
            <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
              Please sign in to access overtime records, multipliers, and review workflows.
            </p>
            <div style={{ marginTop: "1.5rem" }}>
              <Link href="/attendance" className="btn btn-primary">
                Sign In via Attendance Console
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Overtime Administration Console
  // ===========================================================================

  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge badge-amber">
            {isEmployeeRole
              ? "My Overtime"
              : isManagerRole
              ? "Overtime Approvals"
              : "Overtime Administration"}
          </span>
          {tenant?.name && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 400 }}>
              • {tenant.name}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <Link href="/attendance" className="btn btn-secondary btn-sm">
            ⏱️ Attendance
          </Link>
          <Link href="/leave" className="btn btn-secondary btn-sm">
            🌴 Leave
          </Link>
          {isPrivilegedRole && (
            <>
              <Link href="/organization/leave-types" className="btn btn-secondary btn-sm">
                📋 Policies
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

      {/* Scope Alert */}
      {isManagerRole && (
        <div className="alert alert-info" style={{ marginBottom: "1.5rem" }}>
          <span>
            🛡️ <strong>Manager Review Scope:</strong> Showing calculated overtime records for your direct reports. Anti-self-approval security policy prevents adjudicating your own overtime records.
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

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Overtime & Rest-Day Multipliers</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Automated evaluation of daily work durations beyond shift windows, holiday rates, and supervisor approvals.
          </p>
        </div>
        {activeTab === "rules" && isPrivilegedRole && (
          <button className="btn btn-primary" onClick={handleOpenCreateRule}>
            ➕ Configure Overtime Rule
          </button>
        )}
      </div>

      {/* Tabs (for HR / Admin) */}
      {isPrivilegedRole && (
        <div className="tabs-nav">
          <button
            className={`tab-btn ${activeTab === "records" ? "active" : ""}`}
            onClick={() => setActiveTab("records")}
          >
            📋 Overtime Records & Approvals
          </button>
          <button
            className={`tab-btn ${activeTab === "rules" ? "active" : ""}`}
            onClick={() => setActiveTab("rules")}
          >
            ⚙️ Overtime Multiplier Policies
          </button>
        </div>
      )}

      {/* =======================================================================
          TAB 1: Records & Review Queue
          ======================================================================= */}
      {activeTab === "records" && (
        <>
          {/* Filters Toolbar */}
          <div className="card" style={{ padding: "1rem 1.25rem", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ minWidth: "180px" }}>
                <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Approval Status</label>
                <select
                  className="form-control"
                  style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="ALL">All Statuses</option>
                  <option value="PENDING_APPROVAL">Pending Review</option>
                  <option value="AUTO_APPROVED">Auto-Approved</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                </select>
              </div>

              {!isEmployeeRole && (
                <div style={{ minWidth: "200px" }}>
                  <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: "0.2rem" }}>Employee</label>
                  <select
                    className="form-control"
                    style={{ padding: "0.35rem 0.6rem", fontSize: "0.85rem" }}
                    value={employeeFilter}
                    onChange={(e) => setEmployeeFilter(e.target.value)}
                  >
                    <option value="">All Direct Reports / Employees</option>
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

              <div style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                <button className="btn btn-secondary btn-sm" onClick={fetchRecords} disabled={loadingRecords}>
                  🔄 Refresh
                </button>
              </div>
            </div>
          </div>

          {/* Records Table */}
          <div className="card" style={{ padding: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>
                {isEmployeeRole ? "My Overtime History" : "Calculated Overtime Records"}
              </h2>
              <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                {records.length} record{records.length === 1 ? "" : "s"}
              </span>
            </div>

            {loadingRecords ? (
              <div style={{ textAlign: "center", padding: "3rem" }}>
                <p style={{ color: "var(--text-secondary)" }}>Loading overtime calculations...</p>
              </div>
            ) : records.length === 0 ? (
              <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
                <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>⚡</div>
                <p>No overtime records found matching the active filter criteria.</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Date</th>
                      <th>Category</th>
                      <th>Raw OT</th>
                      <th>Multiplier</th>
                      <th>Payable OT</th>
                      <th>Status</th>
                      <th>Feedback / Notes</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((rec) => (
                      <tr key={rec.id}>
                        <td>
                          <strong>{rec.employee_name || "Employee"}</strong>
                        </td>
                        <td>
                          <strong>{rec.attendance_date}</strong>
                        </td>
                        <td>{getCategoryBadge(rec.overtime_type)}</td>
                        <td>
                          <span>{formatMinutes(rec.raw_overtime_minutes)}</span>
                          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                            ({rec.raw_overtime_minutes} min)
                          </div>
                        </td>
                        <td>
                          <span className="badge" style={{ fontSize: "0.75rem" }}>
                            {Number(rec.multiplier).toFixed(2)}x
                          </span>
                        </td>
                        <td>
                          <strong style={{ color: "var(--accent-cyan)" }}>
                            {formatMinutes(rec.payable_overtime_minutes)}
                          </strong>
                          <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)" }}>
                            ({rec.payable_overtime_minutes} min)
                          </div>
                        </td>
                        <td>{getOvertimeStatusBadge(rec.status)}</td>
                        <td>
                          <div style={{ fontSize: "0.8rem", maxWidth: "200px", color: "var(--text-secondary)" }}>
                            {rec.reviewer_notes || "—"}
                          </div>
                        </td>
                        <td>
                          {!isEmployeeRole && rec.status === "PENDING_APPROVAL" ? (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleOpenAdjudicate(rec)}
                            >
                              Review
                            </button>
                          ) : (
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleOpenAdjudicate(rec)}
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
        </>
      )}

      {/* =======================================================================
          TAB 2: Rules Configuration (HR / Admin Only)
          ======================================================================= */}
      {activeTab === "rules" && isPrivilegedRole && (
        <div className="card" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>Tenant Overtime Rules & Multipliers</h2>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {rules.length} rule{rules.length === 1 ? "" : "s"}
            </span>
          </div>

          {loadingRules ? (
            <div style={{ textAlign: "center", padding: "3rem" }}>
              <p style={{ color: "var(--text-secondary)" }}>Loading overtime policies...</p>
            </div>
          ) : rules.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>⚙️</div>
              <p>No custom overtime rules configured. The system will use standard shift thresholds.</p>
              <button className="btn btn-primary btn-sm" style={{ marginTop: "1rem" }} onClick={handleOpenCreateRule}>
                Create Default Rule
              </button>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Rule Title</th>
                    <th>Workday</th>
                    <th>Rest Day</th>
                    <th>Holiday</th>
                    <th>Min Threshold</th>
                    <th>Daily Cap</th>
                    <th>Approval Mandate</th>
                    <th>Default</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr key={rule.id}>
                      <td>
                        <strong>{rule.name}</strong>
                      </td>
                      <td>
                        <span className="badge">{Number(rule.workday_multiplier).toFixed(2)}x</span>
                      </td>
                      <td>
                        <span className="badge badge-blue">{Number(rule.weekend_multiplier).toFixed(2)}x</span>
                      </td>
                      <td>
                        <span className="badge badge-purple">{Number(rule.holiday_multiplier).toFixed(2)}x</span>
                      </td>
                      <td>{rule.min_overtime_threshold_minutes}m</td>
                      <td>{rule.max_daily_overtime_minutes ? `${rule.max_daily_overtime_minutes}m` : "Unlimited"}</td>
                      <td>
                        {rule.requires_pre_approval ? (
                          <span style={{ color: "var(--accent-amber)", fontSize: "0.8rem" }}>Pre-Approval</span>
                        ) : rule.requires_manager_approval ? (
                          <span style={{ color: "var(--accent-cyan)", fontSize: "0.8rem" }}>Manager Review</span>
                        ) : (
                          <span style={{ color: "var(--accent-emerald)", fontSize: "0.8rem" }}>Auto-Approved</span>
                        )}
                      </td>
                      <td>
                        {rule.is_default ? (
                          <span className="badge badge-green" style={{ fontSize: "0.7rem" }}>Default</span>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>—</span>
                        )}
                      </td>
                      <td>
                        {rule.is_active ? (
                          <span className="badge badge-green" style={{ fontSize: "0.7rem" }}>Active</span>
                        ) : (
                          <span className="badge" style={{ fontSize: "0.7rem" }}>Inactive</span>
                        )}
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleOpenEditRule(rule)}
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => handleDeleteRule(rule)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* =======================================================================
          MODAL: Review / Adjudicate Overtime Record
          ======================================================================= */}
      {selectedRecord && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "520px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {selectedRecord.status === "PENDING_APPROVAL" ? "Adjudicate Overtime Record" : "Overtime Calculation Details"}
              </h2>
              <button className="modal-close" onClick={() => setSelectedRecord(null)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            {isSelfRecord && selectedRecord.status === "PENDING_APPROVAL" && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                🛡️ <strong>Anti-Self-Approval Restriction:</strong> You cannot approve or reject your own overtime record. Another authorized manager or HR administrator must review this record.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Employee:</span>
                <strong>{selectedRecord.employee_name || "Employee"}</strong>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Attendance Date:</span>
                <strong>{selectedRecord.attendance_date}</strong>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Overtime Classification:</span>
                {getCategoryBadge(selectedRecord.overtime_type)}
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Raw Overtime Worked:</span>
                <span>
                  <strong>{formatMinutes(selectedRecord.raw_overtime_minutes)}</strong> ({selectedRecord.raw_overtime_minutes} min)
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Applicable Multiplier:</span>
                <span className="badge">{Number(selectedRecord.multiplier).toFixed(2)}x</span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>Payable Overtime Time:</span>
                <strong style={{ color: "var(--accent-cyan)", fontSize: "1.05rem" }}>
                  {formatMinutes(selectedRecord.payable_overtime_minutes)}
                </strong>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0" }}>
                <span style={{ color: "var(--text-secondary)" }}>Approval Status:</span>
                {getOvertimeStatusBadge(selectedRecord.status)}
              </div>
            </div>

            {!isEmployeeRole && selectedRecord.status === "PENDING_APPROVAL" ? (
              <form onSubmit={handleDecisionSubmit}>
                <div style={{ marginBottom: "1rem" }}>
                  <label className="form-label">Supervisor Decision</label>
                  <div style={{ display: "flex", gap: "1rem", marginTop: "0.25rem" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
                      <input
                        type="radio"
                        name="overtimeAction"
                        value="APPROVE"
                        checked={decisionAction === "APPROVE"}
                        onChange={() => setDecisionAction("APPROVE")}
                        disabled={isSelfRecord}
                      />
                      <span style={{ color: "var(--accent-emerald)", fontWeight: 600 }}>Approve Overtime</span>
                    </label>

                    <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
                      <input
                        type="radio"
                        name="overtimeAction"
                        value="REJECT"
                        checked={decisionAction === "REJECT"}
                        onChange={() => setDecisionAction("REJECT")}
                        disabled={isSelfRecord}
                      />
                      <span style={{ color: "#f87171", fontWeight: 600 }}>Reject Overtime</span>
                    </label>
                  </div>
                </div>

                {decisionAction === "APPROVE" && (
                  <div style={{ marginBottom: "1rem" }}>
                    <label className="form-label">Approved Minutes (Optional Adjustment)</label>
                    <input
                      type="number"
                      className="form-control"
                      min={0}
                      max={selectedRecord.raw_overtime_minutes}
                      value={adjustedMinutes ?? selectedRecord.raw_overtime_minutes}
                      onChange={(e) => setAdjustedMinutes(parseInt(e.target.value, 10) || 0)}
                      disabled={isSelfRecord}
                    />
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                      Cannot exceed raw worked overtime of {selectedRecord.raw_overtime_minutes} minutes.
                    </div>
                  </div>
                )}

                <div style={{ marginBottom: "1.5rem" }}>
                  <label className="form-label">
                    {decisionAction === "REJECT" ? "Rejection Reason (Mandatory)" : "Supervisor Notes (Optional)"}
                  </label>
                  <textarea
                    className="form-control"
                    rows={3}
                    placeholder={
                      decisionAction === "REJECT"
                        ? "State the reason for rejecting this overtime record (min 3 chars)..."
                        : "Optional feedback for payroll record..."
                    }
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    required={decisionAction === "REJECT"}
                    disabled={isSelfRecord}
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
                    onClick={() => setSelectedRecord(null)}
                    disabled={decisionSubmitting}
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    className={decisionAction === "APPROVE" ? "btn btn-primary" : "btn btn-danger"}
                    disabled={decisionSubmitting || isSelfRecord}
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
                  onClick={() => setSelectedRecord(null)}
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Create / Edit Overtime Rule
          ======================================================================= */}
      {showRuleModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "560px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {editingRule ? `Edit Rule: ${editingRule.name}` : "Configure New Overtime Policy"}
              </h2>
              <button className="modal-close" onClick={() => setShowRuleModal(false)}>
                &times;
              </button>
            </div>

            {ruleError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{ruleError}</span>
              </div>
            )}

            <form onSubmit={handleRuleSubmit}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <label className="form-label">Rule Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Standard Corporate Overtime Policy"
                    value={ruleForm.name}
                    onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
                    required
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem" }}>
                  <div>
                    <label className="form-label">Workday Multiplier</label>
                    <input
                      type="number"
                      step="0.05"
                      min={1.0}
                      max={5.0}
                      className="form-control"
                      value={String(ruleForm.workday_multiplier)}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, workday_multiplier: parseFloat(e.target.value) || 1.0 })
                      }
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Rest-Day Multiplier</label>
                    <input
                      type="number"
                      step="0.05"
                      min={1.0}
                      max={5.0}
                      className="form-control"
                      value={String(ruleForm.weekend_multiplier)}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, weekend_multiplier: parseFloat(e.target.value) || 1.0 })
                      }
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Holiday Multiplier</label>
                    <input
                      type="number"
                      step="0.05"
                      min={1.0}
                      max={5.0}
                      className="form-control"
                      value={String(ruleForm.holiday_multiplier)}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, holiday_multiplier: parseFloat(e.target.value) || 1.0 })
                      }
                      required
                    />
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Daily Eligibility Threshold (Mins)</label>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      className="form-control"
                      value={ruleForm.min_overtime_threshold_minutes ?? 30}
                      onChange={(e) =>
                        setRuleForm({
                          ...ruleForm,
                          min_overtime_threshold_minutes: parseInt(e.target.value, 10) || 0,
                        })
                      }
                    />
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                      Worked overtime below threshold yields 0 eligible minutes.
                    </div>
                  </div>

                  <div>
                    <label className="form-label">Maximum Daily Cap (Mins)</label>
                    <input
                      type="number"
                      min={1}
                      max={1440}
                      className="form-control"
                      value={ruleForm.max_daily_overtime_minutes || ""}
                      onChange={(e) =>
                        setRuleForm({
                          ...ruleForm,
                          max_daily_overtime_minutes: e.target.value ? parseInt(e.target.value, 10) : null,
                        })
                      }
                    />
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={ruleForm.requires_manager_approval ?? true}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, requires_manager_approval: e.target.checked })
                      }
                    />
                    <span>Requires Supervisor Post-Work Approval</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={ruleForm.requires_pre_approval ?? false}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, requires_pre_approval: e.target.checked })
                      }
                    />
                    <span>Requires Advance Pre-Approval</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={ruleForm.is_default ?? false}
                      onChange={(e) => setRuleForm({ ...ruleForm, is_default: e.target.checked })}
                    />
                    <span>Set as Tenant Default Overtime Rule</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={ruleForm.is_active ?? true}
                      onChange={(e) => setRuleForm({ ...ruleForm, is_active: e.target.checked })}
                    />
                    <span>Active and Enforced</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowRuleModal(false)}
                  disabled={ruleSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={ruleSubmitting}
                >
                  {ruleSubmitting ? "Saving..." : editingRule ? "Update Rule" : "Create Rule"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

