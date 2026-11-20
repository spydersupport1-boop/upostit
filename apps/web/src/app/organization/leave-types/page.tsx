"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  leaveApi,
  LeaveTypeDto,
  LeaveTypeCreateRequestDto,
  LeaveTypeUpdateRequestDto,
  ApiError,
} from "@/lib/api";

export default function LeaveTypesConfigurationPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();

  // Role detection
  const isPrivilegedRole = user?.role && ["hr", "admin", "owner"].includes(user.role);

  // Data States
  const [leaveTypes, setLeaveTypes] = useState<LeaveTypeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("ALL");

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<LeaveTypeCreateRequestDto>({
    code: "",
    name: "",
    description: "",
    is_paid: true,
    requires_approval: true,
    allow_half_day: true,
    max_consecutive_days: 14,
    carry_forward_limit: 5,
    is_active: true,
  });

  // Edit Modal State
  const [editingType, setEditingType] = useState<LeaveTypeDto | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<LeaveTypeUpdateRequestDto>({});

  // Fetch Leave Types
  const fetchLeaveTypes = useCallback(async () => {
    if (!token || !isPrivilegedRole) return;
    setLoading(true);
    setPageError(null);
    try {
      const resp = await leaveApi.getLeaveTypes(
        {
          is_active: activeFilter === "ALL" ? undefined : activeFilter === "ACTIVE",
          search: searchQuery.trim() || undefined,
          limit: 100,
        },
        token
      );
      setLeaveTypes(resp.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to fetch organization leave types.");
      }
    } finally {
      setLoading(false);
    }
  }, [token, isPrivilegedRole, activeFilter, searchQuery]);

  useEffect(() => {
    if (isAuthenticated && token && isPrivilegedRole) {
      fetchLeaveTypes();
    }
  }, [isAuthenticated, token, isPrivilegedRole, fetchLeaveTypes]);

  // Handle Create Submit
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    if (!createForm.code.trim() || !createForm.name.trim()) {
      setCreateError("Code and Name are mandatory fields.");
      return;
    }

    setCreateSubmitting(true);
    setCreateError(null);

    try {
      await leaveApi.createLeaveType(
        {
          ...createForm,
          code: createForm.code.trim().toUpperCase(),
          name: createForm.name.trim(),
          description: createForm.description?.trim() || null,
        },
        token
      );

      setPageSuccess(`Leave category '${createForm.code.toUpperCase()}' successfully created.`);
      setShowCreateModal(false);
      setCreateForm({
        code: "",
        name: "",
        description: "",
        is_paid: true,
        requires_approval: true,
        allow_half_day: true,
        max_consecutive_days: 14,
        carry_forward_limit: 5,
        is_active: true,
      });
      await fetchLeaveTypes();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setCreateError(err.detail);
      } else {
        setCreateError("Failed to create leave type.");
      }
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Open Edit Modal
  const handleOpenEdit = (lt: LeaveTypeDto) => {
    setEditingType(lt);
    setEditForm({
      name: lt.name,
      description: lt.description || "",
      is_paid: lt.is_paid,
      requires_approval: lt.requires_approval,
      allow_half_day: lt.allow_half_day,
      max_consecutive_days: lt.max_consecutive_days,
      carry_forward_limit: Number(lt.carry_forward_limit),
      is_active: lt.is_active,
    });
    setEditError(null);
  };

  // Handle Edit Submit
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !editingType) return;

    setEditSubmitting(true);
    setEditError(null);

    try {
      await leaveApi.updateLeaveType(editingType.id, editForm, token);
      setPageSuccess(`Leave type '${editingType.code}' updated successfully.`);
      setEditingType(null);
      await fetchLeaveTypes();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setEditError(err.detail);
      } else {
        setEditError("Failed to update leave type.");
      }
    } finally {
      setEditSubmitting(false);
    }
  };

  // Toggle Active State
  const handleToggleActive = async (lt: LeaveTypeDto) => {
    if (!token) return;
    try {
      await leaveApi.updateLeaveType(lt.id, { is_active: !lt.is_active }, token);
      setPageSuccess(`Leave type '${lt.code}' is now ${!lt.is_active ? "Active" : "Inactive"}.`);
      await fetchLeaveTypes();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(err.detail);
      } else {
        setPageError("Failed to update leave status.");
      }
    }
  };

  // Delete Leave Type
  const handleDeleteType = async (lt: LeaveTypeDto) => {
    if (!token) return;
    const confirm = window.confirm(
      `Are you sure you want to delete leave type '${lt.code}'? If employees have balances or request history, deletion will be blocked.`
    );
    if (!confirm) return;

    try {
      await leaveApi.deleteLeaveType(lt.id, token);
      setPageSuccess(`Leave type '${lt.code}' was permanently deleted.`);
      await fetchLeaveTypes();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setPageError(
            `Cannot delete leave type '${lt.code}': It is referenced by employee balances or attendance records. Consider deactivating it instead.`
          );
        } else {
          setPageError(err.detail);
        }
      } else {
        setPageError("Failed to delete leave type.");
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
          <p>Verifying policy administrator credentials...</p>
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
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🔒</div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>HR Administration Required</h1>
            <p style={{ color: "var(--text-secondary)", marginTop: "0.75rem", fontSize: "0.95rem" }}>
              Leave policy configuration is restricted to HR Administrators and Tenant Owners.
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
  // RENDER: Leave Policy Configuration Page
  // ===========================================================================

  return (
    <div className="container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge badge-purple">Organization Leave Policies</span>
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
          <Link href="/organization" className="btn btn-secondary btn-sm">
            🏢 Organization
          </Link>
          <Link href="/organization/holidays" className="btn btn-secondary btn-sm">
            📅 Holidays
          </Link>
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

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.85rem", fontWeight: 800 }}>Leave Category Policies</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Define paid and unpaid leave categories, carry-forward rollover limits, and managerial approval requirements.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowCreateModal(true);
            setCreateError(null);
          }}
        >
          ➕ Configure New Leave Type
        </button>
      </div>

      {/* Search and Filters Toolbar */}
      <div className="card" style={{ padding: "1rem 1.25rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ minWidth: "220px" }}>
              <input
                type="text"
                className="form-control"
                placeholder="Search by code or title..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div>
              <select
                className="form-control"
                value={activeFilter}
                onChange={(e) => setActiveFilter(e.target.value)}
              >
                <option value="ALL">All Statuses</option>
                <option value="ACTIVE">Active Policies Only</option>
                <option value="INACTIVE">Inactive Policies Only</option>
              </select>
            </div>
          </div>

          <button className="btn btn-secondary btn-sm" onClick={fetchLeaveTypes} disabled={loading}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Leave Types Table */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 700 }}>Configured Leave Categories</h2>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {leaveTypes.length} categor{leaveTypes.length === 1 ? "y" : "ies"}
          </span>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "3rem" }}>
            <p style={{ color: "var(--text-secondary)" }}>Loading leave categories...</p>
          </div>
        ) : leaveTypes.length === 0 ? (
          <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-secondary)" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>📋</div>
            <p>No leave types match the active filter criteria.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Category Name</th>
                  <th>Type</th>
                  <th>Approval Mandate</th>
                  <th>Half-Day Allowed</th>
                  <th>Max Consecutive</th>
                  <th>Carry Forward</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {leaveTypes.map((lt) => (
                  <tr key={lt.id}>
                    <td>
                      <span className="badge" style={{ fontWeight: 700, fontSize: "0.8rem" }}>
                        {lt.code}
                      </span>
                    </td>
                    <td>
                      <strong>{lt.name}</strong>
                      {lt.description && (
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                          {lt.description}
                        </div>
                      )}
                    </td>
                    <td>
                      {lt.is_paid ? (
                        <span className="badge badge-green" style={{ fontSize: "0.75rem" }}>Paid</span>
                      ) : (
                        <span className="badge" style={{ fontSize: "0.75rem" }}>Unpaid</span>
                      )}
                    </td>
                    <td>
                      {lt.requires_approval ? (
                        <span style={{ color: "var(--accent-cyan)", fontSize: "0.85rem" }}>Required</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Auto-Approve</span>
                      )}
                    </td>
                    <td>
                      {lt.allow_half_day ? (
                        <span style={{ color: "var(--accent-emerald)", fontSize: "0.85rem" }}>Yes (0.5d)</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Full Only</span>
                      )}
                    </td>
                    <td>
                      <span style={{ fontSize: "0.85rem" }}>
                        {lt.max_consecutive_days ? `${lt.max_consecutive_days} days` : "Unlimited"}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: "0.85rem" }}>
                        {Number(lt.carry_forward_limit) > 0 ? `${Number(lt.carry_forward_limit)} days` : "None"}
                      </span>
                    </td>
                    <td>
                      {lt.is_active ? (
                        <span className="badge badge-green" style={{ fontSize: "0.75rem" }}>Active</span>
                      ) : (
                        <span className="badge" style={{ fontSize: "0.75rem" }}>Inactive</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleOpenEdit(lt)}
                          title="Edit policy details"
                        >
                          Edit
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleToggleActive(lt)}
                          title={lt.is_active ? "Deactivate policy" : "Activate policy"}
                        >
                          {lt.is_active ? "Deactivate" : "Activate"}
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDeleteType(lt)}
                          title="Delete category"
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

      {/* =======================================================================
          MODAL: Create Leave Type
          ======================================================================= */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "560px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">➕ Configure New Leave Category</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                &times;
              </button>
            </div>

            {createError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Category Code</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. CL, AL, SL"
                      maxLength={20}
                      value={createForm.code}
                      onChange={(e) => setCreateForm({ ...createForm, code: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Category Name</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. Casual Leave"
                      maxLength={100}
                      value={createForm.name}
                      onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="form-label">Policy Summary / Guidelines</label>
                  <textarea
                    className="form-control"
                    rows={2}
                    placeholder="Optional details visible to employees..."
                    value={createForm.description || ""}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Max Consecutive Days</label>
                    <input
                      type="number"
                      className="form-control"
                      min={1}
                      value={createForm.max_consecutive_days || ""}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          max_consecutive_days: e.target.value ? parseInt(e.target.value, 10) : null,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="form-label">Annual Rollover Limit (Days)</label>
                    <input
                      type="number"
                      className="form-control"
                      min={0}
                      step="0.5"
                      value={String(createForm.carry_forward_limit)}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          carry_forward_limit: parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={createForm.is_paid}
                      onChange={(e) => setCreateForm({ ...createForm, is_paid: e.target.checked })}
                    />
                    <span>Paid Time Off (PTO)</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={createForm.requires_approval}
                      onChange={(e) => setCreateForm({ ...createForm, requires_approval: e.target.checked })}
                    />
                    <span>Requires Supervisor Approval before Confirmation</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={createForm.allow_half_day}
                      onChange={(e) => setCreateForm({ ...createForm, allow_half_day: e.target.checked })}
                    />
                    <span>Allow Half-Day Increments (0.50 day)</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={createForm.is_active}
                      onChange={(e) => setCreateForm({ ...createForm, is_active: e.target.checked })}
                    />
                    <span>Active and Available for Employee Application</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  disabled={createSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={createSubmitting}
                >
                  {createSubmitting ? "Saving..." : "Create Category"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: Edit Leave Type
          ======================================================================= */}
      {editingType && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: "560px", width: "100%" }}>
            <div className="modal-header">
              <h2 className="modal-title">Edit Policy: {editingType.code}</h2>
              <button className="modal-close" onClick={() => setEditingType(null)}>
                &times;
              </button>
            </div>

            {editError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{editError}</span>
              </div>
            )}

            <form onSubmit={handleEditSubmit}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <label className="form-label">Category Name</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editForm.name || ""}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    required
                  />
                </div>

                <div>
                  <label className="form-label">Policy Summary</label>
                  <textarea
                    className="form-control"
                    rows={2}
                    value={editForm.description || ""}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label className="form-label">Max Consecutive Days</label>
                    <input
                      type="number"
                      className="form-control"
                      min={1}
                      value={editForm.max_consecutive_days || ""}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          max_consecutive_days: e.target.value ? parseInt(e.target.value, 10) : null,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="form-label">Annual Rollover Limit (Days)</label>
                    <input
                      type="number"
                      className="form-control"
                      min={0}
                      step="0.5"
                      value={String(editForm.carry_forward_limit ?? 0)}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          carry_forward_limit: parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={editForm.is_paid ?? true}
                      onChange={(e) => setEditForm({ ...editForm, is_paid: e.target.checked })}
                    />
                    <span>Paid Time Off (PTO)</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={editForm.requires_approval ?? true}
                      onChange={(e) => setEditForm({ ...editForm, requires_approval: e.target.checked })}
                    />
                    <span>Requires Supervisor Approval before Confirmation</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={editForm.allow_half_day ?? true}
                      onChange={(e) => setEditForm({ ...editForm, allow_half_day: e.target.checked })}
                    />
                    <span>Allow Half-Day Increments (0.50 day)</span>
                  </label>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                    <input
                      type="checkbox"
                      checked={editForm.is_active ?? true}
                      onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                    />
                    <span>Active and Available for Application</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer" style={{ marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setEditingType(null)}
                  disabled={editSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={editSubmitting}
                >
                  {editSubmitting ? "Updating..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

