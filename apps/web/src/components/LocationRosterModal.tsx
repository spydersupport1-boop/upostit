"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  locationApi,
  LocationDto,
  LocationEmployeeDto,
  ApiError,
} from "@/lib/api";

export interface LocationRosterModalProps {
  isOpen: boolean;
  onClose: () => void;
  location: LocationDto | null;
  token: string | null;
}

export default function LocationRosterModal({
  isOpen,
  onClose,
  location,
  token,
}: LocationRosterModalProps) {
  const [employees, setEmployees] = useState<LocationEmployeeDto[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 15;
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [primaryFilter, setPrimaryFilter] = useState<"all" | "primary" | "secondary">("all");
  const [currentFilter, setCurrentFilter] = useState<"all" | "current" | "past">("current");

  const fetchRoster = useCallback(async () => {
    if (!location || !token) return;
    setIsLoading(true);
    setErrorMessage(null);

    const isPrimaryParam =
      primaryFilter === "primary" ? true : primaryFilter === "secondary" ? false : undefined;
    const isCurrentParam =
      currentFilter === "current" ? true : currentFilter === "past" ? false : undefined;

    try {
      const resp = await locationApi.getLocationEmployees(
        location.id,
        {
          search: search.trim() || undefined,
          is_primary: isPrimaryParam,
          is_current: isCurrentParam,
          page,
          page_size: pageSize,
        },
        token
      );
      setEmployees(resp.items);
      setTotal(resp.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to load workplace employee roster.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [location, token, search, primaryFilter, currentFilter, page]);

  useEffect(() => {
    if (isOpen && location) {
      setPage(1);
      fetchRoster();
    }
  }, [isOpen, location, fetchRoster]);

  if (!isOpen || !location) return null;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "800px", padding: "2.25rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "1.25rem" }}>👥</span>
              <h2 className="modal-title" style={{ margin: 0 }}>Workplace Employee Roster</h2>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              Location: <strong style={{ color: "var(--text-primary)" }}>{location.name}</strong> ({location.code}) • {location.city || location.country_code} [{location.geofence_radius_meters}m radius]
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {/* Search & Filters */}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.25rem" }}>
          <input
            type="text"
            className="search-input"
            style={{ maxWidth: "260px" }}
            placeholder="Search employee name, code, email..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
          <select
            className="filter-select"
            value={primaryFilter}
            onChange={(e) => {
              setPrimaryFilter(e.target.value as "all" | "primary" | "secondary");
              setPage(1);
            }}
          >
            <option value="all">All Assignments</option>
            <option value="primary">Primary Workplace Only</option>
            <option value="secondary">Secondary Workplace Only</option>
          </select>
          <select
            className="filter-select"
            value={currentFilter}
            onChange={(e) => {
              setCurrentFilter(e.target.value as "all" | "current" | "past");
              setPage(1);
            }}
          >
            <option value="current">Currently Active</option>
            <option value="past">Historical Past</option>
            <option value="all">All Statuses</option>
          </select>
        </div>

        {errorMessage && (
          <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
            <span>{errorMessage}</span>
            <button className="alert-close" onClick={() => setErrorMessage(null)}>&times;</button>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="spinner-container" style={{ padding: "2.5rem 0", textAlign: "center" }}>
            <div className="spinner" style={{ margin: "0 auto 1rem" }} />
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading roster...</p>
          </div>
        )}

        {/* Roster Table */}
        {!isLoading && (
          <div>
            {employees.length === 0 ? (
              <div className="card" style={{ textAlign: "center", padding: "2.5rem 1rem", background: "rgba(0,0,0,0.15)", marginBottom: "1.5rem" }}>
                <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", margin: 0 }}>
                  No employees found matching the search and filter criteria for this location.
                </p>
              </div>
            ) : (
              <div className="table-container" style={{ maxHeight: "360px", overflowY: "auto", marginBottom: "1rem" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Dept & Role</th>
                      <th>Assignment</th>
                      <th>Effective Period</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((emp) => (
                      <tr key={emp.assignment_id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{emp.full_name}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {emp.employee_number} • {emp.email}
                          </div>
                        </td>
                        <td style={{ fontSize: "0.825rem" }}>
                          <div>{emp.department_name || "—"}</div>
                          <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                            {emp.designation_title || "—"}
                          </div>
                        </td>
                        <td>
                          {emp.is_primary ? (
                            <span className="badge badge-green" style={{ fontSize: "0.75rem" }}>
                              ★ Primary
                            </span>
                          ) : (
                            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                              Secondary
                            </span>
                          )}
                        </td>
                        <td style={{ fontSize: "0.8rem" }}>
                          <div>From: <strong>{emp.effective_from}</strong></div>
                          <div>To: <strong>{emp.effective_to || "Ongoing"}</strong></div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem" }}>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  Showing {employees.length} of {total} employees
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
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.5rem" }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
