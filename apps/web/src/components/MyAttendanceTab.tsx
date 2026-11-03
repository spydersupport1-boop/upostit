"use client";

import React, { useState, useEffect, useCallback } from "react";
import { attendanceApi, AttendanceDayDto, ApiError } from "@/lib/api";

interface MyAttendanceTabProps {
  employeeId: string;
  token: string;
  onViewTimeline: (day: AttendanceDayDto) => void;
}

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

export default function MyAttendanceTab({
  employeeId,
  token,
  onViewTimeline,
}: MyAttendanceTabProps) {
  // Date range defaults: current month
  const now = new Date();
  const firstDayOfMonth = new Date(now.getFullYear(), now.getMonth(), 1)
    .toISOString()
    .split("T")[0];
  const todayStr = now.toISOString().split("T")[0];

  const [startDate, setStartDate] = useState(firstDayOfMonth);
  const [endDate, setEndDate] = useState(todayStr);
  const [statusFilter, setStatusFilter] = useState("all");

  const [days, setDays] = useState<AttendanceDayDto[]>([]);
  const [totalRecords, setTotalRecords] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMyDays = useCallback(async () => {
    if (!token || !employeeId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await attendanceApi.getDays(
        {
          employee_id: employeeId,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          attendance_status: statusFilter !== "all" ? statusFilter : undefined,
          limit: 100,
        },
        token
      );
      setDays(resp.items);
      setTotalRecords(resp.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Failed to load attendance records: ${err.detail}`);
      } else {
        setError("Network error while loading your attendance records.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, employeeId, startDate, endDate, statusFilter]);

  useEffect(() => {
    fetchMyDays();
  }, [fetchMyDays]);

  // Aggregate stats from current view
  const presentCount = days.filter((d) => d.status === "PRESENT" || d.status === "HALF_DAY" || d.status === "LATE").length;
  const lateCount = days.filter((d) => d.late_arrival_minutes > 0 || d.status === "LATE").length;
  const earlyCount = days.filter((d) => d.early_departure_minutes > 0).length;
  const totalNetMinutes = days.reduce((acc, d) => acc + (d.net_working_minutes || 0), 0);
  const incompleteCount = days.filter((d) => d.is_incomplete || d.status === "INCOMPLETE").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* KPI Summary Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "1rem",
        }}
      >
        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Days Present
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--color-success, #10b981)" }}>
            {presentCount}
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Late Arrivals
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, color: lateCount > 0 ? "var(--color-warning, #f59e0b)" : "var(--text-primary)" }}>
            {lateCount}
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Early Departures
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, color: earlyCount > 0 ? "var(--color-warning, #f59e0b)" : "var(--text-primary)" }}>
            {earlyCount}
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Total Working Time
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--color-primary, #6366f1)" }}>
            {formatMinutes(totalNetMinutes)}
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", textAlign: "center" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
            Incomplete Days
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, color: incompleteCount > 0 ? "var(--color-danger, #ef4444)" : "var(--text-secondary)" }}>
            {incompleteCount}
          </div>
        </div>
      </div>

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
              From:
            </label>
            <input
              type="date"
              className="form-control"
              style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "auto" }}
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
              To:
            </label>
            <input
              type="date"
              className="form-control"
              style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "auto" }}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
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
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={() => fetchMyDays()}
          disabled={loading}
          style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
        >
          <span>🔄</span> {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Error alert */}
      {error && (
        <div className="alert alert-danger" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>{error}</span>
          <button className="alert-close" onClick={() => setError(null)}>
            &times;
          </button>
        </div>
      )}

      {/* Records Table */}
      <div className="card" style={{ padding: "0", overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table className="table" style={{ width: "100%", margin: 0 }}>
            <thead>
              <tr>
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
              {loading ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", padding: "3rem" }}>
                    <div className="spinner-container" style={{ margin: 0 }}>
                      <div className="spinner" />
                      <p>Loading attendance history...</p>
                    </div>
                  </td>
                </tr>
              ) : days.length === 0 ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", padding: "3rem" }}>
                    <div style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
                      📅 No attendance records found for this period ({totalRecords} records).
                    </div>
                  </td>
                </tr>
              ) : (
                days.map((day) => (
                  <tr key={day.id || day.attendance_date}>
                    <td style={{ fontWeight: 600 }}>{day.attendance_date}</td>
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
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onViewTimeline(day)}
                        style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                        title="View immutable event timeline"
                      >
                        ⏱️ Timeline
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
