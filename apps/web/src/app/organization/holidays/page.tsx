"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  holidayApi,
  locationApi,
  organizationApi,
  HolidayCalendarDto,
  HolidayDto,
  LocationDto,
  DepartmentDto,
  HolidayCalendarCreateRequestDto,
  HolidayCreateRequestDto,
  HolidayUpdateRequestDto,
  ApiError,
} from "@/lib/api";

function getHolidayTypeBadge(type: string) {
  switch (type) {
    case "PUBLIC":
      return <span className="badge badge-purple">Public Holiday</span>;
    case "COMPANY":
      return <span className="badge badge-blue">Company Holiday</span>;
    case "OPTIONAL":
      return <span className="badge">Optional / Floating</span>;
    default:
      return <span className="badge">{type}</span>;
  }
}

export default function HolidaysAdministrationPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();

  // Role detection
  const isPrivilegedRole = user?.role && ["hr", "admin", "owner"].includes(user.role);

  // Filters & Selected State
  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState<number>(currentYear);
  const [calendars, setCalendars] = useState<HolidayCalendarDto[]>([]);
  const [selectedCalendarId, setSelectedCalendarId] = useState<string | null>(null);
  const [holidays, setHolidays] = useState<HolidayDto[]>([]);
  const [locations, setLocations] = useState<LocationDto[]>([]);
  const [departments, setDepartments] = useState<DepartmentDto[]>([]);

  // Loading States
  const [loadingCalendars, setLoadingCalendars] = useState<boolean>(true);
  const [loadingHolidays, setLoadingHolidays] = useState<boolean>(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Create Calendar Modal State
  const [showCreateCalendarModal, setShowCreateCalendarModal] = useState<boolean>(false);
  const [calendarSubmitting, setCalendarSubmitting] = useState<boolean>(false);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [calendarForm, setCalendarForm] = useState<HolidayCalendarCreateRequestDto>({
    year: currentYear,
    name: "",
    location_id: null,
    department_id: null,
    is_default: false,
  });

  // Add / Edit Holiday Modal State
  const [showHolidayModal, setShowHolidayModal] = useState<boolean>(false);
  const [editingHoliday, setEditingHoliday] = useState<HolidayDto | null>(null);
  const [holidaySubmitting, setHolidaySubmitting] = useState<boolean>(false);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [holidayForm, setHolidayForm] = useState<HolidayCreateRequestDto>({
    holiday_date: new Date().toISOString().split("T")[0],
    name: "",
    holiday_type: "PUBLIC",
    is_optional: false,
    description: "",
  });

  // ===========================================================================
  // Fetch Functions
  // ===========================================================================

  // 1. Fetch Calendars for Selected Year
  const fetchCalendars = useCallback(async () => {
    if (!token || !isPrivilegedRole) return;
    setLoadingCalendars(true);
    setPageError(null);
    try {
      const resp = await holidayApi.getCalendars({ year: selectedYear, limit: 100 }, token);
      const items = resp.items || [];
      setCalendars(items);
      if (items.length > 0) {
        if (!selectedCalendarId || !items.some((c) => c.id === selectedCalendarId)) {
          setSelectedCalendarId(items[0].id);
        }
      } else {
        setSelectedCalendarId(null);
        setHolidays([]);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to fetch holiday calendars.");
      }
    } finally {
      setLoadingCalendars(false);
    }
  }, [token, isPrivilegedRole, selectedYear, selectedCalendarId]);

  // 2. Fetch Holiday Entries for Selected Calendar
  const fetchHolidays = useCallback(async (calendarId: string) => {
    if (!token) return;
    setLoadingHolidays(true);
    try {
      const resp = await holidayApi.getHolidayEntries(calendarId, {}, token);
      setHolidays(resp.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to fetch holidays for selected calendar.");
      }
    } finally {
      setLoadingHolidays(false);
    }
  }, [token]);

  // 3. Load Locations & Departments for Scoping Dropdowns
  useEffect(() => {
    if (!token || !isPrivilegedRole) return;
    locationApi
      .getLocations({ is_active: true }, token)
      .then((res) => setLocations(res.items || []))
      .catch(() => {});

    organizationApi
      .getDepartments({ limit: 100 }, token)
      .then((res) => setDepartments(res.items || []))
      .catch(() => {});
  }, [token, isPrivilegedRole]);

  useEffect(() => {
    if (isAuthenticated && token && isPrivilegedRole) {
      fetchCalendars();
    }
  }, [isAuthenticated, token, isPrivilegedRole, fetchCalendars]);

  useEffect(() => {
    if (selectedCalendarId) {
      fetchHolidays(selectedCalendarId);
    }
  }, [selectedCalendarId, fetchHolidays]);

  // Active Calendar Object
  const selectedCalendar = calendars.find((c) => c.id === selectedCalendarId);

  // ===========================================================================
  // Action Handlers
  // ===========================================================================

  const handleCreateCalendarSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!calendarForm.name.trim()) {
      setCalendarError("Calendar name is required.");
      return;
    }

    setCalendarSubmitting(true);
    setCalendarError(null);

    try {
      const newCal = await holidayApi.createCalendar(
        {
          year: calendarForm.year,
          name: calendarForm.name.trim(),
          location_id: calendarForm.location_id || null,
          department_id: calendarForm.department_id || null,
          is_default: calendarForm.is_default || false,
        },
        token
      );

      setPageSuccess(`Holiday calendar '${newCal.name}' created for year ${newCal.year}.`);
      setShowCreateCalendarModal(false);
      setSelectedCalendarId(newCal.id);
      setCalendarForm({
        year: selectedYear,
        name: "",
        location_id: null,
        department_id: null,
        is_default: false,
      });
      await fetchCalendars();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setCalendarError(err.detail);
      } else {
        setCalendarError("Failed to create holiday calendar.");
      }
    } finally {
      setCalendarSubmitting(false);
    }
  };

  const handleDeleteCalendar = async (cal: HolidayCalendarDto) => {
    if (!token) return;
    const confirm = window.confirm(
      `Are you sure you want to delete calendar '${cal.name}' (${cal.year})? All associated holiday dates will also be deleted.`
    );
    if (!confirm) return;

    try {
      await holidayApi.deleteCalendar(cal.id, token);
      setPageSuccess(`Calendar '${cal.name}' deleted.`);
      if (selectedCalendarId === cal.id) {
        setSelectedCalendarId(null);
      }
      await fetchCalendars();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to delete calendar.");
      }
    }
  };

  const handleOpenAddHoliday = () => {
    setEditingHoliday(null);
    setHolidayForm({
      holiday_date: `${selectedYear}-01-01`,
      name: "",
      holiday_type: "PUBLIC",
      is_optional: false,
      description: "",
    });
    setHolidayError(null);
    setShowHolidayModal(true);
  };

  const handleOpenEditHoliday = (h: HolidayDto) => {
    setEditingHoliday(h);
    setHolidayForm({
      holiday_date: h.holiday_date,
      name: h.name,
      holiday_type: h.holiday_type,
      is_optional: h.is_optional,
      description: h.description || "",
    });
    setHolidayError(null);
    setShowHolidayModal(true);
  };

  const handleHolidaySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedCalendarId) return;

    if (!holidayForm.name.trim() || !holidayForm.holiday_date) {
      setHolidayError("Holiday date and name are required.");
      return;
    }

    setHolidaySubmitting(true);
    setHolidayError(null);

    try {
      if (editingHoliday) {
        await holidayApi.updateHolidayEntry(
          selectedCalendarId,
          editingHoliday.id,
          {
            holiday_date: holidayForm.holiday_date,
            name: holidayForm.name.trim(),
            holiday_type: holidayForm.holiday_type,
            is_optional: holidayForm.is_optional,
            description: holidayForm.description?.trim() || null,
          },
          token
        );
        setPageSuccess(`Updated holiday '${holidayForm.name.trim()}'.`);
      } else {
        await holidayApi.createHolidayEntry(
          selectedCalendarId,
          {
            holiday_date: holidayForm.holiday_date,
            name: holidayForm.name.trim(),
            holiday_type: holidayForm.holiday_type,
            is_optional: holidayForm.is_optional,
            description: holidayForm.description?.trim() || null,
          },
          token
        );
        setPageSuccess(`Added holiday '${holidayForm.name.trim()}'.`);
      }

      setShowHolidayModal(false);
      await fetchHolidays(selectedCalendarId);
      await fetchCalendars();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setHolidayError(err.detail);
      } else {
        setHolidayError("Failed to save holiday entry.");
      }
    } finally {
      setHolidaySubmitting(false);
    }
  };

  const handleDeleteHoliday = async (h: HolidayDto) => {
    if (!token || !selectedCalendarId) return;
    const confirm = window.confirm(`Delete holiday '${h.name}' on ${h.holiday_date}?`);
    if (!confirm) return;

    try {
      await holidayApi.deleteHolidayEntry(selectedCalendarId, h.id, token);
      setPageSuccess(`Holiday '${h.name}' deleted.`);
      await fetchHolidays(selectedCalendarId);
      await fetchCalendars();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to delete holiday entry.");
      }
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
          <p>Verifying calendar administrator credentials...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !isPrivilegedRole) {
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
              ← Leave Dashboard
            </Link>
          </div>
        </nav>

        <div style={{ maxWidth: "520px", margin: "4rem auto", textAlign: "center" }}>
          <div className="card" style={{ padding: "3rem" }}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📅</div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>HR Administration Required</h1>
            <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem", fontSize: "0.95rem" }}>
              Holiday calendar administration is restricted to HR Administrators and Tenant Owners.
            </p>
            <div style={{ marginTop: "2rem" }}>
              <Link href="/leave" className="btn btn-primary">
                Return to Leave Dashboard
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Holiday Calendar Administration Console
  // ===========================================================================

  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge badge-purple">Holiday Calendars</span>
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
          <Link href="/leave/approvals" className="btn btn-secondary btn-sm">
            ✓ Approvals
          </Link>
          <Link href="/organization/leave-types" className="btn btn-secondary btn-sm">
            📋 Leave Policies
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

      {/* Hierarchical Resolution Notice */}
      <div className="alert alert-info" style={{ marginBottom: "1.5rem" }}>
        <span>
          🏛️ <strong>Three-Tier Hierarchical Resolution:</strong> Employee holidays are automatically determined by precedence:{" "}
          <strong>Workplace Location</strong> → <strong>Department</strong> → <strong>Tenant Default</strong>. Non-working statutory holidays automatically exempt employees from daily absence and apply premium overtime multipliers.
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

      {/* Header and Actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Annual Holiday Calendars</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Configure national, regional, and company holidays for automated attendance and overtime calculations.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <select
            className="form-control"
            style={{ width: "110px", fontWeight: 700 }}
            value={selectedYear}
            onChange={(e) => setSelectedYear(parseInt(e.target.value, 10))}
          >
            {[currentYear - 1, currentYear, currentYear + 1, currentYear + 2].map((y) => (
              <option key={y} value={y}>
                Year {y}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary"
            onClick={() => {
              setCalendarForm({
                year: selectedYear,
                name: "",
                location_id: null,
                department_id: null,
                is_default: calendars.length === 0,
              });
              setCalendarError(null);
              setShowCreateCalendarModal(true);
            }}
          >
            ➕ Create Calendar
          </button>
        </div>
      </div>

      {/* Main Two-Column Layout: Calendars List + Selected Calendar Entries */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.5rem", alignItems: "flex-start" }}>
        {/* Calendars Column */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Calendars ({selectedYear})</h2>
            <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              {calendars.length} total
            </span>
          </div>

          {loadingCalendars ? (
            <p style={{ color: "var(--text-secondary)", textAlign: "center", padding: "2rem" }}>
              Loading annual calendars...
            </p>
          ) : calendars.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-secondary)" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📅</div>
              <p>No calendars configured for {selectedYear}.</p>
              <button
                className="btn btn-secondary btn-sm"
                style={{ marginTop: "0.75rem" }}
                onClick={() => setShowCreateCalendarModal(true)}
              >
                Create First Calendar
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {calendars.map((cal) => {
                const isSelected = cal.id === selectedCalendarId;
                const loc = locations.find((l) => l.id === cal.location_id);
                const dept = departments.find((d) => d.id === cal.department_id);

                return (
                  <div
                    key={cal.id}
                    onClick={() => setSelectedCalendarId(cal.id)}
                    style={{
                      padding: "0.85rem",
                      borderRadius: "10px",
                      cursor: "pointer",
                      border: isSelected
                        ? "1px solid var(--accent-cyan)"
                        : "1px solid var(--border-color)",
                      background: isSelected
                        ? "rgba(6, 182, 212, 0.08)"
                        : "rgba(255, 255, 255, 0.02)",
                      transition: "all 0.2s ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{cal.name}</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                          {cal.is_default ? (
                            <span className="badge badge-green" style={{ fontSize: "0.65rem" }}>Tenant Default</span>
                          ) : loc ? (
                            <span className="badge badge-blue" style={{ fontSize: "0.65rem" }}>📍 {loc.name}</span>
                          ) : dept ? (
                            <span className="badge badge-purple" style={{ fontSize: "0.65rem" }}>🏢 {dept.name}</span>
                          ) : (
                            <span className="badge" style={{ fontSize: "0.65rem" }}>Custom Scope</span>
                          )}
                        </div>
                      </div>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: "0.15rem 0.4rem", fontSize: "0.7rem", color: "#f87171" }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteCalendar(cal);
                        }}
                        title="Delete calendar"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Calendar Holidays Table */}
        <div className="card" style={{ padding: "1.5rem" }}>
          {selectedCalendar ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.5rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>{selectedCalendar.name}</h2>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                    Year {selectedCalendar.year} • {holidays.length} configured holiday{holidays.length === 1 ? "" : "s"}
                  </div>
                </div>
                <button className="btn btn-primary btn-sm" onClick={handleOpenAddHoliday}>
                  ➕ Add Holiday Date
                </button>
              </div>

              {loadingHolidays ? (
                <div style={{ textAlign: "center", padding: "3rem" }}>
                  <p style={{ color: "var(--text-secondary)" }}>Loading holiday dates...</p>
                </div>
              ) : holidays.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
                  <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🏖️</div>
                  <p>No holiday dates added to this calendar yet.</p>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: "0.75rem" }}
                    onClick={handleOpenAddHoliday}
                  >
                    Add First Holiday
                  </button>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Holiday Name</th>
                        <th>Classification</th>
                        <th>Optional / Floating</th>
                        <th>Notes</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holidays.map((h) => (
                        <tr key={h.id}>
                          <td>
                            <strong>{h.holiday_date}</strong>
                          </td>
                          <td>
                            <span style={{ fontWeight: 600 }}>{h.name}</span>
                          </td>
                          <td>{getHolidayTypeBadge(h.holiday_type)}</td>
                          <td>
                            {h.is_optional ? (
                              <span style={{ color: "var(--accent-amber)", fontSize: "0.85rem" }}>Yes (Floating)</span>
                            ) : (
                              <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Mandatory Off</span>
                            )}
                          </td>
                          <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                            {h.description || "—"}
                          </td>
                          <td>
                            <div style={{ display: "flex", gap: "0.4rem" }}>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleOpenEditHoliday(h)}
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={() => handleDeleteHoliday(h)}
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
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "4rem 2rem", color: "var(--text-secondary)" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>👈</div>
              <p>Select a calendar from the left or create a new annual calendar to manage holidays.</p>
            </div>
          )}
        </div>
      </div>

      {/* =======================================================================
          MODAL: Create Calendar
          ======================================================================= */}
      {showCreateCalendarModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "520px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">Create Annual Holiday Calendar</h2>
              <button className="modal-close" onClick={() => setShowCreateCalendarModal(false)}>
                &times;
              </button>
            </div>

            {calendarError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{calendarError}</span>
              </div>
            )}

            <form onSubmit={handleCreateCalendarSubmit}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Calendar Year</label>
                    <input
                      type="number"
                      className="form-control"
                      value={calendarForm.year}
                      onChange={(e) =>
                        setCalendarForm({ ...calendarForm, year: parseInt(e.target.value, 10) })
                      }
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Calendar Name</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. Headquarters 2026 Calendar"
                      value={calendarForm.name}
                      onChange={(e) => setCalendarForm({ ...calendarForm, name: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="form-label">Location Override (Optional)</label>
                  <select
                    className="form-control"
                    value={calendarForm.location_id || ""}
                    onChange={(e) =>
                      setCalendarForm({
                        ...calendarForm,
                        location_id: e.target.value || null,
                        department_id: e.target.value ? null : calendarForm.department_id,
                      })
                    }
                  >
                    <option value="">No Location Override (Tenant Wide or Dept)</option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        📍 {loc.name} ({loc.city || "Site"})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="form-label">Department Override (Optional)</label>
                  <select
                    className="form-control"
                    value={calendarForm.department_id || ""}
                    disabled={!!calendarForm.location_id}
                    onChange={(e) =>
                      setCalendarForm({ ...calendarForm, department_id: e.target.value || null })
                    }
                  >
                    <option value="">No Department Override</option>
                    {departments.map((dept) => (
                      <option key={dept.id} value={dept.id}>
                        🏢 {dept.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ marginTop: "0.5rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={calendarForm.is_default}
                      onChange={(e) =>
                        setCalendarForm({ ...calendarForm, is_default: e.target.checked })
                      }
                    />
                    <span>Set as Tenant Default Fallback Calendar</span>
                  </label>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                    Employees without specific location or department calendars will automatically fall back to this calendar.
                  </div>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCreateCalendarModal(false)}
                  disabled={calendarSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={calendarSubmitting}
                >
                  {calendarSubmitting ? "Creating..." : "Create Calendar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Add / Edit Holiday Entry
          ======================================================================= */}
      {showHolidayModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "500px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {editingHoliday ? "Edit Holiday Date" : "Add Holiday to Calendar"}
              </h2>
              <button className="modal-close" onClick={() => setShowHolidayModal(false)}>
                &times;
              </button>
            </div>

            {holidayError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{holidayError}</span>
              </div>
            )}

            <form onSubmit={handleHolidaySubmit}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Holiday Date</label>
                    <input
                      type="date"
                      className="form-control"
                      value={holidayForm.holiday_date}
                      onChange={(e) =>
                        setHolidayForm({ ...holidayForm, holiday_date: e.target.value })
                      }
                      required
                    />
                  </div>

                  <div>
                    <label className="form-label">Classification</label>
                    <select
                      className="form-control"
                      value={holidayForm.holiday_type}
                      onChange={(e) =>
                        setHolidayForm({ ...holidayForm, holiday_type: e.target.value })
                      }
                    >
                      <option value="PUBLIC">Public / Statutory</option>
                      <option value="COMPANY">Company Holiday</option>
                      <option value="OPTIONAL">Optional / Floating</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="form-label">Holiday Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. New Year's Day, Independence Day"
                    value={holidayForm.name}
                    onChange={(e) => setHolidayForm({ ...holidayForm, name: e.target.value })}
                    required
                  />
                </div>

                <div>
                  <label className="form-label">Notes (Optional)</label>
                  <textarea
                    className="form-control"
                    rows={2}
                    placeholder="Optional details or instructions..."
                    value={holidayForm.description || ""}
                    onChange={(e) =>
                      setHolidayForm({ ...holidayForm, description: e.target.value })
                    }
                  />
                </div>

                <div style={{ marginTop: "0.25rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={holidayForm.is_optional}
                      onChange={(e) =>
                        setHolidayForm({ ...holidayForm, is_optional: e.target.checked })
                      }
                    />
                    <span>Is Optional / Floating Holiday</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowHolidayModal(false)}
                  disabled={holidaySubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={holidaySubmitting}
                >
                  {holidaySubmitting ? "Saving..." : editingHoliday ? "Update Holiday" : "Add Holiday"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

