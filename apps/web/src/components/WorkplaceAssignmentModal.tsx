"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  assignmentApi,
  EmployeeDto,
  LocationDto,
  WorkplaceAssignmentDto,
  ApiError,
} from "@/lib/api";

export interface WorkplaceAssignmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  employee: EmployeeDto | null;
  locations: LocationDto[];
  token: string | null;
  canManage?: boolean;
  onAssignmentsUpdated?: () => void;
}

export default function WorkplaceAssignmentModal({
  isOpen,
  onClose,
  employee,
  locations,
  token,
  canManage = true,
  onAssignmentsUpdated,
}: WorkplaceAssignmentModalProps) {
  const [assignments, setAssignments] = useState<WorkplaceAssignmentDto[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form State
  const [showAssignForm, setShowAssignForm] = useState(false);
  const [selectedLocationId, setSelectedLocationId] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);
  const [effectiveTo, setEffectiveTo] = useState("");

  // End Assignment State
  const [endingAssignmentId, setEndingAssignmentId] = useState<string | null>(null);
  const [endDateInput, setEndDateInput] = useState(new Date().toISOString().split("T")[0]);

  // Edit Assignment State
  const [editingAssignment, setEditingAssignment] = useState<WorkplaceAssignmentDto | null>(null);
  const [editIsPrimary, setEditIsPrimary] = useState(false);
  const [editEffectiveFrom, setEditEffectiveFrom] = useState("");
  const [editEffectiveTo, setEditEffectiveTo] = useState("");

  const fetchAssignments = useCallback(async () => {
    if (!employee || !token) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const resp = await assignmentApi.getEmployeeWorkplaces(employee.id, { page_size: 100 }, token);
      setAssignments(resp.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to load workplace assignments.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [employee, token]);

  useEffect(() => {
    if (isOpen && employee) {
      fetchAssignments();
      setShowAssignForm(false);
      setEndingAssignmentId(null);
      setEditingAssignment(null);
      setErrorMessage(null);
      setSuccessMessage(null);
      setSelectedLocationId(locations.length > 0 ? locations[0].id : "");
    }
  }, [isOpen, employee, fetchAssignments, locations]);

  const handleAssignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!employee || !token || !selectedLocationId) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await assignmentApi.assignWorkplace(
        employee.id,
        {
          location_id: selectedLocationId,
          is_primary: isPrimary,
          effective_from: effectiveFrom,
          effective_to: effectiveTo || null,
        },
        token
      );
      setSuccessMessage("Workplace location assigned successfully.");
      setShowAssignForm(false);
      await fetchAssignments();
      if (onAssignmentsUpdated) onAssignmentsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to assign workplace location.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEndAssignment = async (assignmentId: string) => {
    if (!employee || !token) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await assignmentApi.endAssignment(employee.id, assignmentId, endDateInput, token);
      setSuccessMessage("Workplace assignment ended successfully without deleting historical records.");
      setEndingAssignmentId(null);
      await fetchAssignments();
      if (onAssignmentsUpdated) onAssignmentsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to end workplace assignment.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdateAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!employee || !token || !editingAssignment) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await assignmentApi.updateAssignment(
        employee.id,
        editingAssignment.id,
        {
          is_primary: editIsPrimary,
          effective_from: editEffectiveFrom,
          effective_to: editEffectiveTo || null,
        },
        token
      );
      setSuccessMessage("Workplace assignment updated successfully.");
      setEditingAssignment(null);
      await fetchAssignments();
      if (onAssignmentsUpdated) onAssignmentsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to update workplace assignment.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen || !employee) return null;

  const todayStr = new Date().toISOString().split("T")[0];
  const activeAssignments = assignments.filter((a) => !a.effective_to || a.effective_to >= todayStr);
  const historicalAssignments = assignments.filter((a) => a.effective_to && a.effective_to < todayStr);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "720px", padding: "2.25rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "1.25rem" }}>📍</span>
              <h2 className="modal-title" style={{ margin: 0 }}>Workplace Assignments</h2>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              Employee: <strong style={{ color: "var(--text-primary)" }}>{employee.first_name} {employee.last_name}</strong> ({employee.employee_id}) • {employee.work_email}
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {/* Global Messages */}
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

        {/* Action Bar */}
        {canManage && !showAssignForm && !editingAssignment && (
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1.25rem" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => {
                setShowAssignForm(true);
                setErrorMessage(null);
                setSuccessMessage(null);
              }}
            >
              + Assign Workplace
            </button>
          </div>
        )}

        {/* Assign New Workplace Form */}
        {showAssignForm && (
          <div className="card" style={{ padding: "1.5rem", marginBottom: "1.75rem", background: "rgba(0,0,0,0.3)", border: "1px solid var(--accent-cyan)" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "1rem" }}>
              Assign New Workplace Location
            </h3>
            <form onSubmit={handleAssignSubmit}>
              <div className="form-group">
                <label className="form-label">Workplace Location *</label>
                <select
                  required
                  className="form-control"
                  value={selectedLocationId}
                  onChange={(e) => setSelectedLocationId(e.target.value)}
                >
                  <option value="" disabled>Select active location...</option>
                  {locations.filter((loc) => loc.is_active).map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.code}) — {loc.city || loc.country_code} [{loc.geofence_radius_meters}m radius]
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Effective From *</label>
                  <input
                    type="date"
                    required
                    className="form-control"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Effective To (Optional)</label>
                  <input
                    type="date"
                    className="form-control"
                    value={effectiveTo}
                    onChange={(e) => setEffectiveTo(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="checkbox"
                  id="is_primary_checkbox"
                  checked={isPrimary}
                  onChange={(e) => setIsPrimary(e.target.checked)}
                />
                <label htmlFor="is_primary_checkbox" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>
                  Designate as <strong>Primary Workplace</strong> for this date range
                </label>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.25rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowAssignForm(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !selectedLocationId}
                  className="btn btn-primary btn-sm"
                >
                  {isSubmitting ? "Assigning..." : "Save Assignment"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Edit Existing Assignment Form */}
        {editingAssignment && (
          <div className="card" style={{ padding: "1.5rem", marginBottom: "1.75rem", background: "rgba(0,0,0,0.3)", border: "1px solid var(--accent-blue)" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              Edit Assignment: {editingAssignment.location_name}
            </h3>
            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
              Location Code: {editingAssignment.location_code}
            </p>
            <form onSubmit={handleUpdateAssignment}>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Effective From *</label>
                  <input
                    type="date"
                    required
                    className="form-control"
                    value={editEffectiveFrom}
                    onChange={(e) => setEditEffectiveFrom(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Effective To (Optional)</label>
                  <input
                    type="date"
                    className="form-control"
                    value={editEffectiveTo}
                    onChange={(e) => setEditEffectiveTo(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="checkbox"
                  id="edit_is_primary"
                  checked={editIsPrimary}
                  onChange={(e) => setEditIsPrimary(e.target.checked)}
                />
                <label htmlFor="edit_is_primary" style={{ fontSize: "0.875rem", color: "var(--text-primary)", cursor: "pointer" }}>
                  Designate as <strong>Primary Workplace</strong> for this date range
                </label>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setEditingAssignment(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn btn-primary btn-sm"
                >
                  {isSubmitting ? "Updating..." : "Update Assignment"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="spinner-container" style={{ padding: "2rem 0", textAlign: "center" }}>
            <div className="spinner" style={{ margin: "0 auto 1rem" }} />
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading assignments...</p>
          </div>
        )}

        {/* Current Active Assignments Table */}
        {!isLoading && (
          <div>
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>Current & Upcoming Assignments ({activeAssignments.length})</span>
            </h3>

            {activeAssignments.length === 0 ? (
              <div className="card" style={{ textAlign: "center", padding: "1.75rem", marginBottom: "1.5rem", background: "rgba(0,0,0,0.15)" }}>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                  No active workplace locations assigned to this employee.
                </p>
              </div>
            ) : (
              <div className="table-container" style={{ marginBottom: "1.5rem" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Location</th>
                      <th>Primary</th>
                      <th>Effective Dates</th>
                      {canManage && <th style={{ textAlign: "right" }}>Actions</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {activeAssignments.map((assign) => (
                      <tr key={assign.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{assign.location_name}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Code: {assign.location_code}</div>
                        </td>
                        <td>
                          {assign.is_primary ? (
                            <span className="badge badge-green" style={{ fontSize: "0.75rem" }}>
                              ★ Primary
                            </span>
                          ) : (
                            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Secondary</span>
                          )}
                        </td>
                        <td style={{ fontSize: "0.825rem" }}>
                          <div>From: <strong>{assign.effective_from}</strong></div>
                          <div>To: <strong>{assign.effective_to || "Ongoing (Open-ended)"}</strong></div>
                        </td>
                        {canManage && (
                          <td style={{ textAlign: "right" }}>
                            {endingAssignmentId === assign.id ? (
                              <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                                <input
                                  type="date"
                                  className="form-control"
                                  style={{ padding: "0.3rem 0.5rem", fontSize: "0.775rem", width: "135px" }}
                                  value={endDateInput}
                                  onChange={(e) => setEndDateInput(e.target.value)}
                                />
                                <button
                                  type="button"
                                  className="btn btn-danger btn-sm"
                                  style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                                  disabled={isSubmitting}
                                  onClick={() => handleEndAssignment(assign.id)}
                                >
                                  Confirm End
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ padding: "0.3rem 0.5rem", fontSize: "0.75rem" }}
                                  onClick={() => setEndingAssignmentId(null)}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                                  onClick={() => {
                                    setEditingAssignment(assign);
                                    setEditIsPrimary(assign.is_primary);
                                    setEditEffectiveFrom(assign.effective_from);
                                    setEditEffectiveTo(assign.effective_to || "");
                                  }}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", color: "#f87171" }}
                                  onClick={() => {
                                    setEndingAssignmentId(assign.id);
                                    setEndDateInput(todayStr);
                                  }}
                                >
                                  End Assignment
                                </button>
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Historical Assignments Section */}
            {historicalAssignments.length > 0 && (
              <div style={{ marginTop: "1.75rem" }}>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                  Historical Workplace Assignments ({historicalAssignments.length})
                </h3>
                <div className="table-container">
                  <table className="data-table" style={{ opacity: 0.85 }}>
                    <thead>
                      <tr>
                        <th>Past Location</th>
                        <th>Status</th>
                        <th>Effective Period</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historicalAssignments.map((h) => (
                        <tr key={h.id}>
                          <td>
                            <div>{h.location_name}</div>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Code: {h.location_code}</div>
                          </td>
                          <td>
                            <span className="status-pill status-inactive">Ended</span>
                          </td>
                          <td style={{ fontSize: "0.825rem", color: "var(--text-secondary)" }}>
                            {h.effective_from} → {h.effective_to}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
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
