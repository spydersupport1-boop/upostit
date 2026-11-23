"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  notificationApi,
  NotificationOverviewDto,
  NotificationTemplateDto,
  TemplateCreateRequestDto,
  NotificationPreferenceDto,
  PreferenceUpdateRequestDto,
  ChannelListResponseDto,
  ChannelConfigItemDto,
  NotificationDto,
  NotificationActivityListDto,
  ApiError,
} from "@/lib/api";

type TabKey = "overview" | "templates" | "channels" | "preferences" | "activity";

// Helper for status badge styling
function getStatusBadge(status: string) {
  const norm = status.toUpperCase();
  switch (norm) {
    case "DELIVERED":
      return <span className="badge badge-green">Delivered</span>;
    case "SENT":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(59, 130, 246, 0.15)",
            color: "#60a5fa",
            border: "1px solid rgba(59, 130, 246, 0.3)",
          }}
          title="Accepted by provider for delivery"
        >
          Sent (Provider Ack)
        </span>
      );
    case "PENDING":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(245, 158, 11, 0.15)",
            color: "#fbbf24",
            border: "1px solid rgba(245, 158, 11, 0.3)",
          }}
        >
          Pending
        </span>
      );
    case "PROCESSING":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(168, 85, 247, 0.15)",
            color: "#c084fc",
            border: "1px solid rgba(168, 85, 247, 0.3)",
          }}
        >
          Processing
        </span>
      );
    case "RETRY_SCHEDULED":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(249, 115, 22, 0.15)",
            color: "#fb923c",
            border: "1px solid rgba(249, 115, 22, 0.3)",
          }}
        >
          Retry Scheduled
        </span>
      );
    case "FAILED":
      return <span className="badge badge-red">Failed</span>;
    case "CANCELLED":
      return <span className="badge">Cancelled</span>;
    default:
      return <span className="badge">{status}</span>;
  }
}

function getChannelBadge(channel: string) {
  const ch = channel.toUpperCase();
  switch (ch) {
    case "PUSH":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(6, 182, 212, 0.15)",
            color: "var(--accent-cyan)",
            border: "1px solid rgba(6, 182, 212, 0.3)",
          }}
        >
          📱 PUSH
        </span>
      );
    case "EMAIL":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(99, 102, 241, 0.15)",
            color: "var(--accent-indigo)",
            border: "1px solid rgba(99, 102, 241, 0.3)",
          }}
        >
          ✉️ EMAIL
        </span>
      );
    case "SMS":
      return (
        <span
          className="badge"
          style={{
            background: "rgba(156, 163, 175, 0.15)",
            color: "#d1d5db",
            border: "1px solid rgba(156, 163, 175, 0.3)",
          }}
        >
          💬 SMS
        </span>
      );
    default:
      return <span className="badge">{channel}</span>;
  }
}

// Canonical safe variables guide based on supported event schemas
const SAFE_VARIABLES_GUIDE: Record<string, { label: string; variables: string[]; description: string }> = {
  leave: {
    label: "Leave Management Events",
    variables: [
      "{employee_name}",
      "{leave_type}",
      "{start_date}",
      "{end_date}",
      "{duration_days}",
      "{reason}",
      "{supervisor_comment}",
      "{rejection_reason}",
      "{cancellation_reason}",
    ],
    description: "Supported for leave request submission, approval, rejection, and cancellation alerts.",
  },
  conflict: {
    label: "Attendance Conflict Events",
    variables: [
      "{employee_name}",
      "{conflict_count}",
      "{incident_id}",
      "{reason}",
      "{adjudication_comment}",
      "{rejection_reason}",
    ],
    description: "Supported for offline conflict submission, approvals, and rejections.",
  },
  fraud: {
    label: "Fraud Shield Security Events",
    variables: [
      "{employee_name}",
      "{risk_score}",
      "{risk_category}",
      "{event_type}",
      "{flag_summary}",
      "{velocity_mps}",
      "{distance_km}",
      "{elapsed_seconds}",
      "{device_id}",
      "{location_summary}",
    ],
    description: "High-risk fraud detection, impossible travel, and mock GPS alerts.",
  },
  invitation: {
    label: "Employee Invitation Events",
    variables: ["{recipient_name}", "{company_name}", "{activation_url}", "{expires_hours}"],
    description: "Used for employee onboarding and account activation.",
  },
  password_reset: {
    label: "Password Reset Security",
    variables: ["{user_name}", "{company_name}", "{reset_url}", "{expires_minutes}"],
    description: "Secure account recovery links with strict time limits.",
  },
};

export default function NotificationAdministrationPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, login, logout } = useAuth();

  // Active Tab
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  // RBAC permissions
  const isAdminOrOwner = useMemo(
    () => user?.role && ["owner", "admin"].includes(user.role),
    [user]
  );
  const canManageTemplates = useMemo(
    () => user?.role && ["owner", "admin", "hr"].includes(user.role),
    [user]
  );

  // Data States
  const [overview, setOverview] = useState<NotificationOverviewDto | null>(null);
  const [templates, setTemplates] = useState<NotificationTemplateDto[]>([]);
  const [channels, setChannels] = useState<ChannelConfigItemDto[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreferenceDto | null>(null);
  const [activity, setActivity] = useState<NotificationActivityListDto>({
    items: [],
    total: 0,
    offset: 0,
    limit: 15,
  });

  // Loading & Alert States
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Template Edit / Override Modal State
  const [selectedTemplate, setSelectedTemplate] = useState<NotificationTemplateDto | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [templateSubmitting, setTemplateSubmitting] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);

  // Preferences Form State
  const [prefPush, setPrefPush] = useState(true);
  const [prefEmail, setPrefEmail] = useState(true);
  const [prefSms, setPrefSms] = useState(false);
  const [prefQhEnabled, setPrefQhEnabled] = useState(false);
  const [prefQhStart, setPrefQhStart] = useState("22:00");
  const [prefQhEnd, setPrefQhEnd] = useState("07:00");
  const [prefTimezone, setPrefTimezone] = useState("UTC");
  const [prefSubmitting, setPrefSubmitting] = useState(false);

  // Activity Log Filter States
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterChannel, setFilterChannel] = useState<string>("");
  const [filterEventType, setFilterEventType] = useState<string>("");
  const [activityPageOffset, setActivityPageOffset] = useState<number>(0);
  const activityPageLimit = 15;

  // Notification Detail Modal
  const [inspectNotification, setInspectNotification] = useState<NotificationDto | null>(null);

  // Template Search Filter
  const [templateSearch, setTemplateSearch] = useState("");
  const [templateChannelFilter, setTemplateChannelFilter] = useState("");

  // Inline Auth Form (for development / unauthenticated access)
  const [authTenantSlug, setAuthTenantSlug] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // ===========================================================================
  // Data Fetching
  // ===========================================================================

  const fetchOverviewData = useCallback(async () => {
    if (!token) return;
    try {
      const data = await notificationApi.getOverview(token);
      setOverview(data);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to load notification overview.";
      setPageError(msg);
    }
  }, [token]);

  const fetchTemplatesData = useCallback(async () => {
    if (!token) return;
    try {
      const data = await notificationApi.getTemplates(token);
      setTemplates(data);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to load notification templates.";
      setPageError(msg);
    }
  }, [token]);

  const fetchChannelsData = useCallback(async () => {
    if (!token) return;
    try {
      const data = await notificationApi.getChannels(token);
      setChannels(data.channels);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to load channels status.";
      setPageError(msg);
    }
  }, [token]);

  const fetchPreferencesData = useCallback(async () => {
    if (!token) return;
    try {
      const data = await notificationApi.getPreferences(token);
      setPreferences(data);
      setPrefPush(data.is_push_enabled);
      setPrefEmail(data.is_email_enabled);
      setPrefSms(data.is_sms_enabled);
      setPrefQhEnabled(data.quiet_hours_enabled);
      setPrefQhStart(data.quiet_hours_start || "22:00");
      setPrefQhEnd(data.quiet_hours_end || "07:00");
      setPrefTimezone(data.timezone || "UTC");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to load tenant preferences.";
      setPageError(msg);
    }
  }, [token]);

  const fetchActivityData = useCallback(
    async (offset: number) => {
      if (!token) return;
      try {
        const data = await notificationApi.getActivity(
          {
            status: filterStatus || undefined,
            channel: filterChannel || undefined,
            event_type: filterEventType || undefined,
            limit: activityPageLimit,
            offset,
          },
          token
        );
        setActivity(data);
      } catch (err: unknown) {
        const msg = err instanceof ApiError ? err.detail : "Failed to load notification activity.";
        setPageError(msg);
      }
    },
    [token, filterStatus, filterChannel, filterEventType]
  );

  const loadAllData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setPageError(null);
    try {
      await Promise.all([
        fetchOverviewData(),
        fetchTemplatesData(),
        fetchChannelsData(),
        fetchPreferencesData(),
        fetchActivityData(activityPageOffset),
      ]);
    } finally {
      setLoading(false);
    }
  }, [
    token,
    fetchOverviewData,
    fetchTemplatesData,
    fetchChannelsData,
    fetchPreferencesData,
    fetchActivityData,
    activityPageOffset,
  ]);

  useEffect(() => {
    if (isAuthenticated && token) {
      loadAllData();
    } else {
      setLoading(false);
    }
  }, [isAuthenticated, token, loadAllData]);

  // Refetch activity when filters change
  useEffect(() => {
    if (isAuthenticated && token && activeTab === "activity") {
      setActivityPageOffset(0);
      fetchActivityData(0);
    }
  }, [filterStatus, filterChannel, filterEventType, isAuthenticated, token, activeTab, fetchActivityData]);

  // ===========================================================================
  // Handlers
  // ===========================================================================

  const handleInlineLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    setAuthSubmitting(true);
    try {
      await login(authEmail, authPassword, authTenantSlug);
    } catch (err: unknown) {
      setAuthError(err instanceof ApiError ? err.detail : "Authentication failed. Check credentials.");
    } finally {
      setAuthSubmitting(false);
    }
  };

  const handleOpenTemplateModal = (tpl: NotificationTemplateDto) => {
    setSelectedTemplate(tpl);
    setEditName(tpl.name);
    setEditDescription(tpl.description || "");
    setEditSubject(tpl.subject_template || "");
    setEditBody(tpl.body_template);
    setTemplateError(null);
  };

  const handleSaveTemplateOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedTemplate) return;
    if (!editName.trim()) {
      setTemplateError("Template name is required.");
      return;
    }
    if (!editBody.trim()) {
      setTemplateError("Template message body is required.");
      return;
    }

    setTemplateSubmitting(true);
    setTemplateError(null);
    try {
      if (!selectedTemplate.is_system && selectedTemplate.tenant_id) {
        // Direct update of existing tenant override by ID
        await notificationApi.updateTemplate(
          selectedTemplate.id,
          {
            name: editName.trim(),
            description: editDescription.trim() || undefined,
            subject_template: editSubject.trim() || undefined,
            body_template: editBody.trim(),
            is_active: true,
          },
          token
        );
        setPageSuccess(`Tenant template "${editName.trim()}" updated successfully.`);
      } else {
        // Creating a new tenant override from system default
        const payload: TemplateCreateRequestDto = {
          template_key: selectedTemplate.template_key,
          name: editName.trim(),
          description: editDescription.trim() || undefined,
          event_type: selectedTemplate.event_type,
          channel: selectedTemplate.channel as "PUSH" | "EMAIL" | "SMS",
          subject_template: editSubject.trim() || undefined,
          body_template: editBody.trim(),
          locale: selectedTemplate.locale || "en",
          is_active: true,
        };

        await notificationApi.createOrUpdateTemplate(payload, token);
        setPageSuccess(`Tenant override created successfully for "${selectedTemplate.name}".`);
      }
      setSelectedTemplate(null);
      await fetchTemplatesData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to save template override.";
      setTemplateError(msg);
    } finally {
      setTemplateSubmitting(false);
    }
  };

  const handleSavePreferences = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setPrefSubmitting(true);
    setPageError(null);
    setPageSuccess(null);

    try {
      const payload: PreferenceUpdateRequestDto = {
        is_push_enabled: prefPush,
        is_email_enabled: prefEmail,
        is_sms_enabled: prefSms,
        quiet_hours_enabled: prefQhEnabled,
        quiet_hours_start: prefQhStart,
        quiet_hours_end: prefQhEnd,
        timezone: prefTimezone,
      };

      const updated = await notificationApi.updatePreferences(payload, token);
      setPreferences(updated);
      setPageSuccess("Tenant default notification preferences updated successfully.");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.detail : "Failed to update preferences.";
      setPageError(msg);
    } finally {
      setPrefSubmitting(false);
    }
  };

  // Filtered Templates
  const filteredTemplates = useMemo(() => {
    return templates.filter((t) => {
      const matchesSearch =
        t.name.toLowerCase().includes(templateSearch.toLowerCase()) ||
        t.template_key.toLowerCase().includes(templateSearch.toLowerCase()) ||
        t.event_type.toLowerCase().includes(templateSearch.toLowerCase());
      const matchesChannel =
        !templateChannelFilter || t.channel.toUpperCase() === templateChannelFilter.toUpperCase();
      return matchesSearch && matchesChannel;
    });
  }, [templates, templateSearch, templateChannelFilter]);

  // Variables for selected event type
  const relevantVariables = useMemo(() => {
    if (!selectedTemplate) return [];
    const ev = selectedTemplate.event_type.toLowerCase();
    for (const [key, category] of Object.entries(SAFE_VARIABLES_GUIDE)) {
      if (ev.includes(key)) {
        return category.variables;
      }
    }
    return ["{employee_name}", "{company_name}", "{event_type}"];
  }, [selectedTemplate]);

  // ===========================================================================
  // Render: Unauthenticated Fallback
  // ===========================================================================
  if (!isAuthenticated && !isAuthLoading) {
    return (
      <div className="container" style={{ maxWidth: "540px", marginTop: "4rem" }}>
        <div className="card" style={{ padding: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}>
            <div className="logo-dot" />
            <h1 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Notification Administration</h1>
          </div>
          <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
            Sign in to access tenant notification delivery logs, custom templates, provider channels, and quiet-hours policies.
          </p>

          {authError && (
            <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
              {authError}
            </div>
          )}

          <form onSubmit={handleInlineLogin}>
            <div className="form-group">
              <label className="form-label">Tenant Slug</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. acme-corp"
                value={authTenantSlug}
                onChange={(e) => setAuthTenantSlug(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Administrator Email</label>
              <input
                type="email"
                className="form-control"
                placeholder="admin@example.com"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
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
              {authSubmitting ? "Authenticating..." : "Sign In to Notification Console"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // Render: Access Denied for Unprivileged Roles
  // ===========================================================================
  if (isAuthenticated && !canManageTemplates) {
    return (
      <div className="container" style={{ maxWidth: "540px", marginTop: "4rem" }}>
        <div className="card" style={{ padding: "2.5rem", textAlign: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🔒</div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            Access Denied
          </h1>
          <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
            Notification Administration is restricted to Owner, Admin, and HR roles. Your current account role ({user?.role?.toUpperCase() || "EMPLOYEE"}) does not have permission to view tenant notification activity or manage communication settings.
          </p>
          <Link href="/" className="btn btn-secondary">
            ← Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // Render: Authenticated Dashboard
  // ===========================================================================
  return (
    <div className="container" style={{ maxWidth: "1280px" }}>
      {/* Top Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">
            <span>Attendance SaaS</span>
          </Link>
          <span className="badge">Phase 10: Notifications</span>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <Link href="/leave" className="btn btn-secondary btn-sm">
            🌴 Leave & Balances
          </Link>
          <Link href="/attendance/overtime" className="btn btn-secondary btn-sm">
            ⚡ Overtime
          </Link>
          <Link href="/organization" className="btn btn-secondary btn-sm">
            🏢 Organization
          </Link>
          <Link href="/attendance" className="btn btn-secondary btn-sm">
            ⏱️ Attendance
          </Link>

          {user && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                marginLeft: "0.5rem",
                paddingLeft: "0.75rem",
                borderLeft: "1px solid var(--border-color)",
              }}
            >
              <span className="badge badge-blue" style={{ textTransform: "capitalize" }}>
                {user.role}
              </span>
              <button onClick={() => logout()} className="btn btn-secondary btn-sm" title="Log Out">
                Sign Out
              </button>
            </div>
          )}
        </div>
      </nav>

      {/* Header Banner */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
              🔔 Notification Administration
            </h1>
            <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.95rem" }}>
              Monitor delivery lifecycle, customize event templates, check channel readiness, and configure quiet hours.
            </p>
          </div>
          <button
            onClick={() => loadAllData()}
            className="btn btn-secondary btn-sm"
            style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
            disabled={loading}
          >
            🔄 Refresh Metrics
          </button>
        </div>
      </div>

      {/* Success and Error Alerts */}
      {pageSuccess && (
        <div
          className="alert alert-success"
          style={{
            marginBottom: "1.5rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>✓ {pageSuccess}</span>
          <button
            style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: "1.1rem" }}
            onClick={() => setPageSuccess(null)}
          >
            &times;
          </button>
        </div>
      )}

      {pageError && (
        <div
          className="alert alert-danger"
          style={{
            marginBottom: "1.5rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>⚠️ {pageError}</span>
          <button
            style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: "1.1rem" }}
            onClick={() => setPageError(null)}
          >
            &times;
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          borderBottom: "1px solid var(--border-color)",
          marginBottom: "1.5rem",
          overflowX: "auto",
        }}
      >
        <button
          className={`btn ${activeTab === "overview" ? "btn-primary" : "btn-secondary"} btn-sm`}
          style={{ borderRadius: "8px 8px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("overview")}
        >
          📊 Overview
        </button>
        <button
          className={`btn ${activeTab === "templates" ? "btn-primary" : "btn-secondary"} btn-sm`}
          style={{ borderRadius: "8px 8px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("templates")}
        >
          📜 Templates ({templates.length})
        </button>
        <button
          className={`btn ${activeTab === "channels" ? "btn-primary" : "btn-secondary"} btn-sm`}
          style={{ borderRadius: "8px 8px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("channels")}
        >
          📡 Channels ({channels.length})
        </button>
        <button
          className={`btn ${activeTab === "preferences" ? "btn-primary" : "btn-secondary"} btn-sm`}
          style={{ borderRadius: "8px 8px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("preferences")}
        >
          ⚙️ Tenant Preferences
        </button>
        <button
          className={`btn ${activeTab === "activity" ? "btn-primary" : "btn-secondary"} btn-sm`}
          style={{ borderRadius: "8px 8px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("activity")}
        >
          📋 Activity Log ({activity.total})
        </button>
      </div>

      {/* =======================================================================
          TAB 1: OVERVIEW
          ======================================================================= */}
      {activeTab === "overview" && (
        <div>
          {/* Key Metric Cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "1rem",
              marginBottom: "1.5rem",
            }}
          >
            <div className="card" style={{ padding: "1.25rem" }}>
              <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem", textTransform: "uppercase" }}>
                Total Dispatches
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.25rem" }}>
                {overview?.total_count ?? 0}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Outbound notifications
              </div>
            </div>

            <div className="card" style={{ padding: "1.25rem" }}>
              <div style={{ color: "#60a5fa", fontSize: "0.8rem", textTransform: "uppercase" }}>
                Sent (Provider Ack)
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.25rem", color: "#60a5fa" }}>
                {overview?.status_counts?.sent ?? 0}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Accepted by FCM / SMTP
              </div>
            </div>

            <div className="card" style={{ padding: "1.25rem" }}>
              <div style={{ color: "var(--accent-emerald)", fontSize: "0.8rem", textTransform: "uppercase" }}>
                Delivered (Device Confirmed)
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.25rem", color: "var(--accent-emerald)" }}>
                {overview?.status_counts?.delivered ?? 0}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Terminal delivery receipt
              </div>
            </div>

            <div className="card" style={{ padding: "1.25rem" }}>
              <div style={{ color: "#fbbf24", fontSize: "0.8rem", textTransform: "uppercase" }}>
                In Flight / Retrying
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.25rem", color: "#fbbf24" }}>
                {(overview?.status_counts?.pending ?? 0) +
                  (overview?.status_counts?.processing ?? 0) +
                  (overview?.status_counts?.retry_scheduled ?? 0)}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Pending or backoff retry
              </div>
            </div>

            <div className="card" style={{ padding: "1.25rem" }}>
              <div style={{ color: "#ef4444", fontSize: "0.8rem", textTransform: "uppercase" }}>
                Failed / Cancelled
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.25rem", color: "#ef4444" }}>
                {(overview?.status_counts?.failed ?? 0) + (overview?.status_counts?.cancelled ?? 0)}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                Terminal failures & dead-letter
              </div>
            </div>
          </div>

          {/* Delivery Milestone Clarification Alert */}
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              background: "rgba(6, 182, 212, 0.05)",
              border: "1px solid rgba(6, 182, 212, 0.25)",
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "flex-start",
              gap: "0.75rem",
            }}
          >
            <span style={{ fontSize: "1.25rem" }}>📌</span>
            <div style={{ fontSize: "0.85rem", lineHeight: "1.5" }}>
              <strong>Delivery Milestone Distinction:</strong>
              <div style={{ marginTop: "0.25rem", color: "var(--text-secondary)" }}>
                • <strong style={{ color: "#60a5fa" }}>SENT:</strong> The message has been successfully handed off and
                acknowledged by downstream dispatch providers (Firebase Cloud Messaging server, SMTP relay).
                <br />• <strong style={{ color: "var(--accent-emerald)" }}>DELIVERED:</strong> Confirmed receipt
                acknowledgment received from the recipient&apos;s active client application or terminal provider webhook.
              </div>
            </div>
          </div>

          {/* Channel Distribution & Status Breakdown Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginBottom: "1.5rem" }}>
            {/* Status Breakdown */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "1rem" }}>
                Lifecycle Status Breakdown
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {[
                  { label: "Delivered", count: overview?.status_counts?.delivered ?? 0, color: "var(--accent-emerald)" },
                  { label: "Sent (Provider Accepted)", count: overview?.status_counts?.sent ?? 0, color: "#60a5fa" },
                  { label: "Pending Scheduled", count: overview?.status_counts?.pending ?? 0, color: "#fbbf24" },
                  { label: "Processing (In-Flight)", count: overview?.status_counts?.processing ?? 0, color: "#c084fc" },
                  { label: "Retry Scheduled", count: overview?.status_counts?.retry_scheduled ?? 0, color: "#fb923c" },
                  { label: "Terminally Failed", count: overview?.status_counts?.failed ?? 0, color: "#ef4444" },
                  { label: "Cancelled", count: overview?.status_counts?.cancelled ?? 0, color: "var(--text-muted)" },
                ].map((s) => (
                  <div
                    key={s.label}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "0.4rem 0.5rem",
                      borderRadius: "6px",
                      background: "rgba(255, 255, 255, 0.02)",
                    }}
                  >
                    <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>{s.label}</span>
                    <span style={{ fontWeight: 700, color: s.color }}>{s.count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Channel Breakdown */}
            <div className="card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "1rem" }}>
                Channel Traffic Distribution
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div
                  style={{
                    padding: "0.85rem",
                    borderRadius: "8px",
                    background: "rgba(6, 182, 212, 0.05)",
                    border: "1px solid rgba(6, 182, 212, 0.2)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>📱 Mobile Push (FCM)</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      Real-time alerts to registered Android & iOS devices
                    </div>
                  </div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--accent-cyan)" }}>
                    {overview?.channel_counts?.push ?? 0}
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.85rem",
                    borderRadius: "8px",
                    background: "rgba(99, 102, 241, 0.05)",
                    border: "1px solid rgba(99, 102, 241, 0.2)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>✉️ Transactional Email</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      Invitations, leave approvals, password recovery
                    </div>
                  </div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--accent-indigo)" }}>
                    {overview?.channel_counts?.email ?? 0}
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.85rem",
                    borderRadius: "8px",
                    background: "rgba(156, 163, 175, 0.05)",
                    border: "1px solid rgba(156, 163, 175, 0.2)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "#9ca3af" }}>
                      💬 SMS Messaging (Deferred)
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Scheduled for post-Phase 10 deployment
                    </div>
                  </div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#9ca3af" }}>
                    {overview?.channel_counts?.sms ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Recent Outbound Activity Quick View */}
          <div className="card" style={{ padding: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Recent Outbound Activity</h2>
              <button onClick={() => setActiveTab("activity")} className="btn btn-secondary btn-sm">
                View Full Activity Log →
              </button>
            </div>

            {(!overview?.recent_notifications || overview.recent_notifications.length === 0) ? (
              <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                No recent outbound notifications found for this tenant.
              </p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ width: "100%", fontSize: "0.85rem" }}>
                  <thead>
                    <tr>
                      <th>Event Type</th>
                      <th>Channel</th>
                      <th>Destination</th>
                      <th>Status</th>
                      <th>Priority</th>
                      <th>Attempts</th>
                      <th>Time</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.recent_notifications.map((n) => (
                      <tr key={n.id}>
                        <td>
                          <span style={{ fontWeight: 600 }}>{n.event_type}</span>
                        </td>
                        <td>{getChannelBadge(n.channel)}</td>
                        <td>
                          <code style={{ fontSize: "0.75rem", color: "var(--accent-cyan)" }}>
                            {n.recipient_destination}
                          </code>
                        </td>
                        <td>{getStatusBadge(n.status)}</td>
                        <td>
                          <span className="badge" style={{ fontSize: "0.7rem" }}>
                            {n.priority}
                          </span>
                        </td>
                        <td>
                          {n.attempt_count} / {n.max_attempts}
                        </td>
                        <td style={{ color: "var(--text-secondary)" }}>
                          {new Date(n.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </td>
                        <td>
                          <button
                            className="btn btn-secondary btn-sm"
                            style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                            onClick={() => setInspectNotification(n)}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 2: TEMPLATES
          ======================================================================= */}
      {activeTab === "templates" && (
        <div>
          {/* Filter Bar */}
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              marginBottom: "1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
            }}
          >
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="text"
                className="form-control"
                placeholder="Search templates by key or name..."
                style={{ width: "280px" }}
                value={templateSearch}
                onChange={(e) => setTemplateSearch(e.target.value)}
              />
              <select
                className="form-control"
                style={{ width: "160px" }}
                value={templateChannelFilter}
                onChange={(e) => setTemplateChannelFilter(e.target.value)}
              >
                <option value="">All Channels</option>
                <option value="PUSH">📱 PUSH</option>
                <option value="EMAIL">✉️ EMAIL</option>
                <option value="SMS">💬 SMS</option>
              </select>
            </div>

            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Showing {filteredTemplates.length} of {templates.length} templates
            </div>
          </div>

          {/* Template Catalog */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {filteredTemplates.length === 0 ? (
              <div className="card" style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                No matching notification templates found.
              </div>
            ) : (
              filteredTemplates.map((t) => {
                const isTenantOverride = !t.is_system && Boolean(t.tenant_id);
                return (
                  <div
                    key={`${t.template_key}-${t.channel}-${t.id}`}
                    className="card"
                    style={{
                      padding: "1.25rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.75rem",
                      borderLeft: isTenantOverride
                        ? "4px solid var(--accent-emerald)"
                        : "4px solid var(--accent-blue)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                          <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>{t.name}</h3>
                          {getChannelBadge(t.channel)}
                          {isTenantOverride ? (
                            <span className="badge badge-green">🏢 Tenant Override</span>
                          ) : (
                            <span className="badge badge-blue">🌐 System Default</span>
                          )}
                        </div>
                        <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                          Key: <code style={{ color: "var(--accent-cyan)" }}>{t.template_key}</code> • Event:{" "}
                          <code>{t.event_type}</code> • Locale: <code>{t.locale}</code>
                        </div>
                      </div>

                      <div>
                        {canManageTemplates ? (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleOpenTemplateModal(t)}
                          >
                            {isTenantOverride ? "✏️ Edit Override" : "🛠️ Customize / Override"}
                          </button>
                        ) : (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleOpenTemplateModal(t)}
                          >
                            👁️ View Template
                          </button>
                        )}
                      </div>
                    </div>

                    {t.description && (
                      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>
                        {t.description}
                      </p>
                    )}

                    {t.subject_template && (
                      <div style={{ fontSize: "0.85rem", background: "rgba(0,0,0,0.25)", padding: "0.5rem 0.75rem", borderRadius: "6px" }}>
                        <span style={{ color: "var(--text-muted)", marginRight: "0.5rem" }}>Subject:</span>
                        <strong>{t.subject_template}</strong>
                      </div>
                    )}

                    <div
                      style={{
                        fontSize: "0.82rem",
                        background: "rgba(0,0,0,0.35)",
                        padding: "0.6rem 0.75rem",
                        borderRadius: "6px",
                        whiteSpace: "pre-wrap",
                        fontFamily: "monospace",
                        color: "var(--text-primary)",
                      }}
                    >
                      {t.body_template}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 3: CHANNELS
          ======================================================================= */}
      {activeTab === "channels" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              background: "rgba(255, 255, 255, 0.02)",
              border: "1px solid var(--border-color)",
            }}
          >
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              📡 Outbound Channel Infrastructure
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>
              Live runtime status for outbound alert delivery providers. Mock adapters operate in isolated sandbox
              mode without triggering live cellular or remote SMTP handshakes.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.5rem" }}>
            {channels.map((ch) => {
              const isConfiguredUnverified = ch.status === "CONFIGURED_UNVERIFIED";
              const isMock = ch.status === "MOCK";
              const isUnconfigured = ch.status === "UNCONFIGURED";

              return (
                <div
                  key={ch.channel}
                  className="card"
                  style={{
                    padding: "1.5rem",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    gap: "1rem",
                    borderTop: isConfiguredUnverified
                      ? "4px solid var(--accent-amber)"
                      : isMock
                      ? "4px solid var(--accent-indigo)"
                      : "4px solid #6b7280",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                      <span style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                        {ch.channel === "PUSH" ? "📱 Mobile Push" : ch.channel === "EMAIL" ? "✉️ Email Gateway" : "💬 SMS Messaging"}
                      </span>
                      {isConfiguredUnverified ? (
                        <span
                          className="badge"
                          style={{
                            background: "rgba(245, 158, 11, 0.15)",
                            color: "#fbbf24",
                            border: "1px solid rgba(245, 158, 11, 0.3)",
                          }}
                        >
                          ⚠️ Credentials Configured (Unverified Gateway)
                        </span>
                      ) : isMock ? (
                        <span
                          className="badge"
                          style={{
                            background: "rgba(99, 102, 241, 0.15)",
                            color: "var(--accent-indigo)",
                            border: "1px solid rgba(99, 102, 241, 0.3)",
                          }}
                        >
                          🧪 Mock / Sandbox Adapter
                        </span>
                      ) : (
                        <span className="badge" style={{ color: "#9ca3af" }}>
                          🔒 Deferred / Unconfigured
                        </span>
                      )}
                    </div>

                    <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                      {ch.description}
                    </div>

                    <div
                      style={{
                        padding: "0.75rem",
                        borderRadius: "6px",
                        background: "rgba(0, 0, 0, 0.3)",
                        fontSize: "0.8rem",
                        fontFamily: "monospace",
                        color: "var(--text-muted)",
                      }}
                    >
                      <div>
                        <strong>Provider:</strong> {ch.provider_name}
                      </div>
                      <div>
                        <strong>Mode:</strong> {ch.status}
                      </div>
                      {ch.details && Object.entries(ch.details).map(([k, v]) => (
                        <div key={k}>
                          <strong>{k}:</strong> {String(v)}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", lineHeight: "1.4" }}>
                    {ch.channel === "PUSH" && (
                      <>
                        {isConfiguredUnverified
                          ? "FCM gateway credentials configured. Note: Gateway handoff does not guarantee device delivery without registered active device tokens."
                          : "Simulated locally via mock push adapter; outbound payloads logged to delivery audit logs."}
                      </>
                    )}
                    {ch.channel === "EMAIL" && (
                      <>
                        {isConfiguredUnverified
                          ? "SMTP settings detected, but production email provider integration is unverified in this milestone. Local sandbox dispatch active."
                          : "Simulated locally via mock email / console output. Production email provider integration is deferred."}
                      </>
                    )}
                    {ch.channel === "SMS" && "SMS delivery provider integration is deferred per Phase 10 roadmap and unconfigured in this milestone."}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 4: PREFERENCES
          ======================================================================= */}
      {activeTab === "preferences" && (
        <div style={{ maxWidth: "720px" }}>
          <div className="card" style={{ padding: "1.75rem" }}>
            <div style={{ marginBottom: "1.5rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>⚙️ Tenant Notification Preferences</h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
                Establish tenant-wide default communication rules. These settings apply to all employees unless a
                user-level preference override is configured.
              </p>
            </div>

            {!isAdminOrOwner && (
              <div
                className="alert alert-warning"
                style={{
                  marginBottom: "1.5rem",
                  fontSize: "0.85rem",
                  background: "rgba(245, 158, 11, 0.1)",
                  border: "1px solid rgba(245, 158, 11, 0.25)",
                  color: "#fbbf24",
                }}
              >
                🔒 Read-Only Access: Only Organization Owners and Administrators can modify tenant-wide defaults.
              </div>
            )}

            <form onSubmit={handleSavePreferences}>
              {/* Channel Availability Toggles */}
              <div style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.75rem", color: "var(--text-secondary)" }}>
                  Enabled Outbound Channels
                </h3>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: isAdminOrOwner ? "pointer" : "not-allowed",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={prefPush}
                      onChange={(e) => setPrefPush(e.target.checked)}
                      disabled={!isAdminOrOwner}
                      style={{ width: "18px", height: "18px", accentColor: "var(--accent-cyan)" }}
                    />
                    <div>
                      <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>📱 Mobile Push Notifications</span>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        Allow dispatching real-time notifications to registered devices.
                      </div>
                    </div>
                  </label>

                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: isAdminOrOwner ? "pointer" : "not-allowed",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={prefEmail}
                      onChange={(e) => setPrefEmail(e.target.checked)}
                      disabled={!isAdminOrOwner}
                      style={{ width: "18px", height: "18px", accentColor: "var(--accent-cyan)" }}
                    />
                    <div>
                      <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>✉️ Email Alerts</span>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        Deliver leave approvals, supervisor digests, and conflict notices via email.
                      </div>
                    </div>
                  </label>

                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: "not-allowed",
                      opacity: 0.6,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={false}
                      disabled
                      style={{ width: "18px", height: "18px" }}
                    />
                    <div>
                      <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>💬 SMS Messaging</span>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        Disabled (Unconfigured provider in Phase 10).
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Quiet-Hours Configuration */}
              <div
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  background: "rgba(255, 255, 255, 0.02)",
                  border: "1px solid var(--border-color)",
                  marginBottom: "1.5rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <div>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>🌙 Quiet-Hours Enforcement</h3>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      Automatically defers non-emergency notifications outside work hours until morning.
                    </div>
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: isAdminOrOwner ? "pointer" : "not-allowed" }}>
                    <input
                      type="checkbox"
                      checked={prefQhEnabled}
                      onChange={(e) => setPrefQhEnabled(e.target.checked)}
                      disabled={!isAdminOrOwner}
                      style={{ width: "18px", height: "18px", accentColor: "var(--accent-cyan)" }}
                    />
                    <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Enable</span>
                  </label>
                </div>

                {prefQhEnabled && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label className="form-label">Quiet Hours Start (24h)</label>
                      <input
                        type="text"
                        className="form-control"
                        placeholder="22:00"
                        value={prefQhStart}
                        onChange={(e) => setPrefQhStart(e.target.value)}
                        disabled={!isAdminOrOwner}
                        pattern="^([01]\d|2[0-3]):[0-5]\d$"
                        title="24-hour format HH:MM (e.g. 22:00)"
                      />
                    </div>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label className="form-label">Quiet Hours End (24h)</label>
                      <input
                        type="text"
                        className="form-control"
                        placeholder="07:00"
                        value={prefQhEnd}
                        onChange={(e) => setPrefQhEnd(e.target.value)}
                        disabled={!isAdminOrOwner}
                        pattern="^([01]\d|2[0-3]):[0-5]\d$"
                        title="24-hour format HH:MM (e.g. 07:00)"
                      />
                    </div>
                  </div>
                )}

                <div className="form-group" style={{ marginTop: "1rem", marginBottom: 0 }}>
                  <label className="form-label">Tenant Default Timezone</label>
                  <select
                    className="form-control"
                    value={prefTimezone}
                    onChange={(e) => setPrefTimezone(e.target.value)}
                    disabled={!isAdminOrOwner}
                  >
                    <option value="UTC">UTC (Universal Coordinated Time)</option>
                    <option value="America/New_York">America/New_York (EST / EDT)</option>
                    <option value="America/Chicago">America/Chicago (CST / CDT)</option>
                    <option value="America/Los_Angeles">America/Los_Angeles (PST / PDT)</option>
                    <option value="Europe/London">Europe/London (GMT / BST)</option>
                    <option value="Europe/Paris">Europe/Paris (CET / CEST)</option>
                    <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                    <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
                    <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
                    <option value="Australia/Sydney">Australia/Sydney (AEST)</option>
                  </select>
                </div>
              </div>

              {isAdminOrOwner && (
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={prefSubmitting}
                  style={{ width: "100%" }}
                >
                  {prefSubmitting ? "Saving Preferences..." : "Save Tenant Notification Preferences"}
                </button>
              )}
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 5: ACTIVITY LOG
          ======================================================================= */}
      {activeTab === "activity" && (
        <div>
          {/* Filter Bar */}
          <div
            className="card"
            style={{
              padding: "1rem 1.25rem",
              marginBottom: "1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
            }}
          >
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              <select
                className="form-control"
                style={{ width: "160px" }}
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="PENDING">Pending</option>
                <option value="PROCESSING">Processing</option>
                <option value="RETRY_SCHEDULED">Retry Scheduled</option>
                <option value="SENT">Sent (Provider Ack)</option>
                <option value="DELIVERED">Delivered</option>
                <option value="FAILED">Failed</option>
                <option value="CANCELLED">Cancelled</option>
              </select>

              <select
                className="form-control"
                style={{ width: "140px" }}
                value={filterChannel}
                onChange={(e) => setFilterChannel(e.target.value)}
              >
                <option value="">All Channels</option>
                <option value="PUSH">📱 PUSH</option>
                <option value="EMAIL">✉️ EMAIL</option>
                <option value="SMS">💬 SMS</option>
              </select>

              <select
                className="form-control"
                style={{ width: "220px" }}
                value={filterEventType}
                onChange={(e) => setFilterEventType(e.target.value)}
              >
                <option value="">All Event Types</option>
                <option value="leave_request_submitted">Leave: Submitted</option>
                <option value="leave_request_approved">Leave: Approved</option>
                <option value="leave_request_rejected">Leave: Rejected</option>
                <option value="leave_request_cancelled">Leave: Cancelled</option>
                <option value="offline_conflict_submitted">Conflict: Submitted</option>
                <option value="attendance_conflict_approved">Conflict: Approved</option>
                <option value="attendance_conflict_rejected">Conflict: Rejected</option>
                <option value="high_risk_fraud_alert">Fraud: High Risk Alert</option>
                <option value="impossible_travel_signal">Fraud: Impossible Travel</option>
                <option value="mock_gps_detected">Fraud: Mock GPS</option>
                <option value="employee_invitation_created">Invitation: Created</option>
                <option value="password_reset_requested">Auth: Password Reset</option>
              </select>

              {(filterStatus || filterChannel || filterEventType) && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setFilterStatus("");
                    setFilterChannel("");
                    setFilterEventType("");
                  }}
                >
                  Clear Filters
                </button>
              )}
            </div>

            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Total Records: <strong>{activity.total}</strong>
            </div>
          </div>

          {/* Activity Data Table */}
          <div className="card" style={{ padding: "1.25rem" }}>
            {activity.items.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                No notifications match the active filter criteria.
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="table" style={{ width: "100%", fontSize: "0.85rem" }}>
                  <thead>
                    <tr>
                      <th>Event & Template</th>
                      <th>Channel</th>
                      <th>Recipient Destination</th>
                      <th>Status</th>
                      <th>Priority</th>
                      <th>Retries</th>
                      <th>Scheduled / Sent</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activity.items.map((n) => (
                      <tr key={n.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{n.event_type}</div>
                          {n.template_key && (
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {n.template_key}
                            </div>
                          )}
                        </td>
                        <td>{getChannelBadge(n.channel)}</td>
                        <td>
                          <code style={{ fontSize: "0.75rem", color: "var(--accent-cyan)" }}>
                            {n.recipient_destination}
                          </code>
                        </td>
                        <td>{getStatusBadge(n.status)}</td>
                        <td>
                          <span
                            className={
                              n.priority === "URGENT"
                                ? "badge badge-red"
                                : n.priority === "HIGH"
                                ? "badge badge-amber"
                                : "badge"
                            }
                            style={{ fontSize: "0.7rem" }}
                          >
                            {n.priority}
                          </span>
                        </td>
                        <td>
                          {n.attempt_count} / {n.max_attempts}
                        </td>
                        <td style={{ color: "var(--text-secondary)" }}>
                          {n.sent_at
                            ? new Date(n.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                            : new Date(n.scheduled_for).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </td>
                        <td>
                          <button
                            className="btn btn-secondary btn-sm"
                            style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                            onClick={() => setInspectNotification(n)}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination Controls */}
            {activity.total > activityPageLimit && (
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: "1.25rem",
                  paddingTop: "1rem",
                  borderTop: "1px solid var(--border-color)",
                }}
              >
                <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                  Showing {activityPageOffset + 1} to{" "}
                  {Math.min(activityPageOffset + activityPageLimit, activity.total)} of {activity.total} entries
                </div>

                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={activityPageOffset === 0}
                    onClick={() => {
                      const nextOff = Math.max(0, activityPageOffset - activityPageLimit);
                      setActivityPageOffset(nextOff);
                      fetchActivityData(nextOff);
                    }}
                  >
                    ← Previous
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={activityPageOffset + activityPageLimit >= activity.total}
                    onClick={() => {
                      const nextOff = activityPageOffset + activityPageLimit;
                      setActivityPageOffset(nextOff);
                      fetchActivityData(nextOff);
                    }}
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Template Editor / Override
          ======================================================================= */}
      {selectedTemplate && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "640px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {selectedTemplate.is_system ? "🛠️ Override System Template" : "✏️ Edit Tenant Template"}
              </h2>
              <button className="modal-close" onClick={() => setSelectedTemplate(null)}>
                &times;
              </button>
            </div>

            {templateError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                {templateError}
              </div>
            )}

            <form onSubmit={handleSaveTemplateOverride}>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Template Key</label>
                  <input
                    type="text"
                    className="form-control"
                    value={selectedTemplate.template_key}
                    disabled
                    style={{ opacity: 0.7 }}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Delivery Channel</label>
                  <input
                    type="text"
                    className="form-control"
                    value={selectedTemplate.channel}
                    disabled
                    style={{ opacity: 0.7 }}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Template Display Name</label>
                <input
                  type="text"
                  className="form-control"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  disabled={!canManageTemplates}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <input
                  type="text"
                  className="form-control"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  disabled={!canManageTemplates}
                />
              </div>

              {selectedTemplate.channel === "EMAIL" && (
                <div className="form-group">
                  <label className="form-label">Subject Template</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editSubject}
                    onChange={(e) => setEditSubject(e.target.value)}
                    disabled={!canManageTemplates}
                    placeholder="e.g. Leave Request Approved: {leave_type}"
                  />
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Body Template</label>
                <textarea
                  className="form-control"
                  rows={5}
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  disabled={!canManageTemplates}
                  required
                  style={{ fontFamily: "monospace", fontSize: "0.85rem" }}
                />
              </div>

              {/* Safe Template Variables Guide */}
              <div
                style={{
                  padding: "0.75rem",
                  borderRadius: "6px",
                  background: "rgba(6, 182, 212, 0.05)",
                  border: "1px solid rgba(6, 182, 212, 0.2)",
                  marginBottom: "1.25rem",
                }}
              >
                <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--accent-cyan)", marginBottom: "0.3rem" }}>
                  ℹ️ Safe Parameters for {selectedTemplate.event_type}:
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                  {relevantVariables.map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => canManageTemplates && setEditBody((b) => b + " " + v)}
                      style={{
                        background: "rgba(0,0,0,0.3)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)",
                        padding: "0.15rem 0.4rem",
                        borderRadius: "4px",
                        fontSize: "0.75rem",
                        fontFamily: "monospace",
                        cursor: canManageTemplates ? "pointer" : "default",
                      }}
                      title="Click to insert into body"
                    >
                      {v}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
                  Variables are sanitized automatically to prevent code injection. Passwords and secret tokens are never permitted.
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setSelectedTemplate(null)}
                >
                  Close
                </button>
                {canManageTemplates && (
                  <button type="submit" className="btn btn-primary" disabled={templateSubmitting}>
                    {templateSubmitting ? "Saving Override..." : "Save Template Override"}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Notification Inspector
          ======================================================================= */}
      {inspectNotification && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "600px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">🔍 Notification Details</h2>
              <button className="modal-close" onClick={() => setInspectNotification(null)}>
                &times;
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", fontSize: "0.85rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>ID:</span>{" "}
                  <code>{inspectNotification.id}</code>
                </div>
                {getStatusBadge(inspectNotification.status)}
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.75rem",
                  padding: "0.75rem",
                  borderRadius: "6px",
                  background: "rgba(0,0,0,0.25)",
                }}
              >
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Event Type:</strong>
                  <div>{inspectNotification.event_type}</div>
                </div>
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Channel:</strong>
                  <div>{getChannelBadge(inspectNotification.channel)}</div>
                </div>
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Priority:</strong>
                  <div>{inspectNotification.priority}</div>
                </div>
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Attempts:</strong>
                  <div>
                    {inspectNotification.attempt_count} / {inspectNotification.max_attempts}
                  </div>
                </div>
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Destination:</strong>
                  <div>
                    <code>{inspectNotification.recipient_destination}</code>
                  </div>
                </div>
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Provider Acknowledgment:</strong>
                  <div>
                    {inspectNotification.provider_name ? (
                      <span>
                        {inspectNotification.provider_name} (ID: {inspectNotification.provider_message_id || "ack"})
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>None yet</span>
                    )}
                  </div>
                </div>
              </div>

              {inspectNotification.subject && (
                <div>
                  <strong style={{ color: "var(--text-secondary)" }}>Subject:</strong>
                  <div style={{ padding: "0.4rem 0.6rem", background: "rgba(0,0,0,0.2)", borderRadius: "4px" }}>
                    {inspectNotification.subject}
                  </div>
                </div>
              )}

              <div>
                <strong style={{ color: "var(--text-secondary)" }}>Message Content:</strong>
                <div
                  style={{
                    padding: "0.6rem 0.75rem",
                    background: "rgba(0,0,0,0.35)",
                    borderRadius: "6px",
                    fontFamily: "monospace",
                    whiteSpace: "pre-wrap",
                    color: "var(--text-primary)",
                  }}
                >
                  {inspectNotification.body}
                </div>
              </div>

              {inspectNotification.error_message && (
                <div
                  style={{
                    padding: "0.6rem 0.75rem",
                    background: "rgba(239, 68, 68, 0.1)",
                    border: "1px solid rgba(239, 68, 68, 0.3)",
                    borderRadius: "6px",
                    color: "#f87171",
                  }}
                >
                  <strong>Provider Feedback / Error:</strong>
                  <div style={{ marginTop: "0.25rem", fontFamily: "monospace", fontSize: "0.8rem" }}>
                    {inspectNotification.error_message}
                  </div>
                </div>
              )}

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.5rem",
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  borderTop: "1px solid var(--border-color)",
                  paddingTop: "0.75rem",
                }}
              >
                <div>Created: {new Date(inspectNotification.created_at).toLocaleString()}</div>
                <div>Scheduled: {new Date(inspectNotification.scheduled_for).toLocaleString()}</div>
                {inspectNotification.sent_at && (
                  <div>Sent: {new Date(inspectNotification.sent_at).toLocaleString()}</div>
                )}
                {inspectNotification.delivered_at && (
                  <div>Delivered: {new Date(inspectNotification.delivered_at).toLocaleString()}</div>
                )}
                {inspectNotification.next_retry_at && (
                  <div>Next Retry: {new Date(inspectNotification.next_retry_at).toLocaleString()}</div>
                )}
              </div>
            </div>

            <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setInspectNotification(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

