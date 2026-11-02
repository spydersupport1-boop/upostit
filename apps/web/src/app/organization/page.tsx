"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  organizationApi,
  DepartmentDto,
  DesignationDto,
  EmployeeDto,
  ApiError,
} from "@/lib/api";

export default function OrganizationPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, login, logout, error: authContextError } = useAuth();

  // Tab State
  const [activeTab, setActiveTab] = useState<"overview" | "employees" | "departments" | "designations">("overview");

  // Data States
  const [departments, setDepartments] = useState<DepartmentDto[]>([]);
  const [designations, setDesignations] = useState<DesignationDto[]>([]);
  const [employees, setEmployees] = useState<EmployeeDto[]>([]);
  const [totalEmployees, setTotalEmployees] = useState(0);

  // Employee Self-Access State (for employee role)
  const [myProfile, setMyProfile] = useState<EmployeeDto | null>(null);
  const [myProfileLoading, setMyProfileLoading] = useState(false);
  const [myProfileError, setMyProfileError] = useState<string | null>(null);

  // Loading States
  const [loadingDepts, setLoadingDepts] = useState(false);
  const [loadingDesigs, setLoadingDesigs] = useState(false);
  const [loadingEmps, setLoadingEmps] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // General Error / Success Alerts
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSuccess, setPageSuccess] = useState<string | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [deptFilter, setDeptFilter] = useState("all");
  const [desigFilter, setDesigFilter] = useState("all");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  // Modals
  const [showAddEmpModal, setShowAddEmpModal] = useState(false);
  const [showEditEmpModal, setShowEditEmpModal] = useState(false);
  const [showAddDeptModal, setShowAddDeptModal] = useState(false);
  const [showEditDeptModal, setShowEditDeptModal] = useState(false);
  const [showAddDesigModal, setShowAddDesigModal] = useState(false);
  const [showEditDesigModal, setShowEditDesigModal] = useState(false);
  const [selectedEmp, setSelectedEmp] = useState<EmployeeDto | null>(null);
  const [editingDept, setEditingDept] = useState<DepartmentDto | null>(null);
  const [editingDesig, setEditingDesig] = useState<DesignationDto | null>(null);
  const [editingEmp, setEditingEmp] = useState<EmployeeDto | null>(null);

  // Inline Auth Form
  const [authTenantSlug, setAuthTenantSlug] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Form States - Employee
  const [empForm, setEmpForm] = useState({
    employee_id: "",
    first_name: "",
    last_name: "",
    work_email: "",
    phone_number: "",
    department_id: "",
    designation_id: "",
    reporting_manager_id: "",
    employment_type: "full_time",
    joining_date: new Date().toISOString().split("T")[0],
    work_location: "Headquarters",
    status: "active",
  });

  // Form States - Department
  const [deptForm, setDeptForm] = useState({
    name: "",
    code: "",
    description: "",
    manager_id: "",
  });

  // Form States - Designation
  const [desigForm, setDesigForm] = useState({
    title: "",
    code: "",
    description: "",
  });

  const isEmployeeRole = user?.role === "employee";

  // ===========================================================================
  // Fetch Functions
  // ===========================================================================

  const fetchDepartments = useCallback(async () => {
    if (!token) return;
    setLoadingDepts(true);
    setPageError(null);
    try {
      const resp = await organizationApi.getDepartments({ limit: 100 }, token);
      setDepartments(resp.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          // Employee role does not have VIEW_ORGANIZATION
        } else {
          setPageError(`Failed to load departments: ${err.detail}`);
        }
      }
    } finally {
      setLoadingDepts(false);
    }
  }, [token]);

  const fetchDesignations = useCallback(async () => {
    if (!token) return;
    setLoadingDesigs(true);
    setPageError(null);
    try {
      const resp = await organizationApi.getDesignations({ limit: 100 }, token);
      setDesignations(resp.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          // Employee role does not have VIEW_ORGANIZATION
        } else {
          setPageError(`Failed to load designations: ${err.detail}`);
        }
      }
    } finally {
      setLoadingDesigs(false);
    }
  }, [token]);

  const fetchEmployees = useCallback(async () => {
    if (!token) return;
    if (isEmployeeRole) return; // Employee role cannot list employees
    setLoadingEmps(true);
    setPageError(null);
    try {
      const params: {
        search?: string;
        department_id?: string;
        designation_id?: string;
        status?: string;
        page: number;
        page_size: number;
      } = {
        page,
        page_size: pageSize,
      };

      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (statusFilter !== "all") params.status = statusFilter;
      if (deptFilter !== "all") params.department_id = deptFilter;
      if (desigFilter !== "all") params.designation_id = desigFilter;

      const resp = await organizationApi.getEmployees(params, token);
      setEmployees(resp.items);
      setTotalEmployees(resp.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setPageError("You do not have permission to view the employee directory.");
        } else {
          setPageError(`Failed to load employees: ${err.detail}`);
        }
      }
    } finally {
      setLoadingEmps(false);
    }
  }, [token, isEmployeeRole, page, searchQuery, statusFilter, deptFilter, desigFilter]);

  const fetchMyProfile = useCallback(async () => {
    if (!token) return;
    setMyProfileLoading(true);
    setMyProfileError(null);
    try {
      const profile = await organizationApi.getMyProfile(token);
      setMyProfile(profile);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setMyProfileError("No employee profile is linked to your user account. Please contact your company HR or administrator.");
        } else {
          setMyProfileError(`Failed to load profile: ${err.detail}`);
        }
      }
    } finally {
      setMyProfileLoading(false);
    }
  }, [token]);

  // Initial and reactive data loads
  useEffect(() => {
    if (!isAuthenticated || !token) return;

    if (isEmployeeRole) {
      fetchMyProfile();
    } else {
      fetchDepartments();
      fetchDesignations();
      fetchEmployees();
    }
  }, [isAuthenticated, token, isEmployeeRole, fetchDepartments, fetchDesignations, fetchEmployees, fetchMyProfile]);

  // Tab switch handler
  useEffect(() => {
    if (!isAuthenticated || !token || isEmployeeRole) return;
    if (activeTab === "departments") fetchDepartments();
    if (activeTab === "designations") fetchDesignations();
    if (activeTab === "employees" || activeTab === "overview") fetchEmployees();
  }, [activeTab, isAuthenticated, token, isEmployeeRole, fetchDepartments, fetchDesignations, fetchEmployees]);

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
      setPageSuccess("Successfully authenticated! Organization workspace loaded.");
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
  // Department Handlers
  // ===========================================================================

  const handleCreateDepartment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.createDepartment(
        {
          name: deptForm.name.trim(),
          code: deptForm.code.trim().toUpperCase(),
          description: deptForm.description.trim() || undefined,
          manager_id: deptForm.manager_id || undefined,
        },
        token
      );
      setShowAddDeptModal(false);
      setDeptForm({ name: "", code: "", description: "", manager_id: "" });
      setPageSuccess("Department created successfully.");
      await fetchDepartments();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to create department.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateDepartment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !editingDept) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.updateDepartment(
        editingDept.id,
        {
          name: deptForm.name.trim(),
          code: deptForm.code.trim().toUpperCase(),
          description: deptForm.description.trim() || undefined,
          manager_id: deptForm.manager_id || undefined,
        },
        token
      );
      setShowEditDeptModal(false);
      setEditingDept(null);
      setPageSuccess("Department updated successfully.");
      await fetchDepartments();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to update department.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleDepartmentStatus = async (dept: DepartmentDto) => {
    if (!token) return;
    try {
      await organizationApi.updateDepartment(
        dept.id,
        { is_active: !dept.is_active },
        token
      );
      setPageSuccess(`Department "${dept.name}" ${dept.is_active ? "deactivated" : "activated"}.`);
      await fetchDepartments();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to update department status: ${err.detail}`);
      }
    }
  };

  const openEditDept = (dept: DepartmentDto) => {
    setEditingDept(dept);
    setDeptForm({
      name: dept.name,
      code: dept.code,
      description: dept.description || "",
      manager_id: dept.manager_id || "",
    });
    setModalError(null);
    setShowEditDeptModal(true);
  };

  // ===========================================================================
  // Designation Handlers
  // ===========================================================================

  const handleCreateDesignation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.createDesignation(
        {
          title: desigForm.title.trim(),
          code: desigForm.code.trim().toUpperCase(),
          description: desigForm.description.trim() || undefined,
        },
        token
      );
      setShowAddDesigModal(false);
      setDesigForm({ title: "", code: "", description: "" });
      setPageSuccess("Designation created successfully.");
      await fetchDesignations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError((err as Error).message || "Failed to create designation.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateDesignation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !editingDesig) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.updateDesignation(
        editingDesig.id,
        {
          title: desigForm.title.trim(),
          code: desigForm.code.trim().toUpperCase(),
          description: desigForm.description.trim() || undefined,
        },
        token
      );
      setShowEditDesigModal(false);
      setEditingDesig(null);
      setPageSuccess("Designation updated successfully.");
      await fetchDesignations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to update designation.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleDesignationStatus = async (desig: DesignationDto) => {
    if (!token) return;
    try {
      await organizationApi.updateDesignation(
        desig.id,
        { is_active: !desig.is_active },
        token
      );
      setPageSuccess(`Designation "${desig.title}" ${desig.is_active ? "deactivated" : "activated"}.`);
      await fetchDesignations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to update designation status: ${err.detail}`);
      }
    }
  };

  const openEditDesig = (desig: DesignationDto) => {
    setEditingDesig(desig);
    setDesigForm({
      title: desig.title,
      code: desig.code,
      description: desig.description || "",
    });
    setModalError(null);
    setShowEditDesigModal(true);
  };

  // ===========================================================================
  // Employee Handlers
  // ===========================================================================

  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.createEmployee(
        {
          employee_id: empForm.employee_id.trim().toUpperCase(),
          first_name: empForm.first_name.trim(),
          last_name: empForm.last_name.trim(),
          work_email: empForm.work_email.trim().toLowerCase(),
          phone_number: empForm.phone_number.trim() || undefined,
          department_id: empForm.department_id || undefined,
          designation_id: empForm.designation_id || undefined,
          reporting_manager_id: empForm.reporting_manager_id || undefined,
          employment_type: empForm.employment_type,
          joining_date: empForm.joining_date,
          status: empForm.status,
          work_location: empForm.work_location.trim() || undefined,
        },
        token
      );
      setShowAddEmpModal(false);
      setEmpForm({
        employee_id: "",
        first_name: "",
        last_name: "",
        work_email: "",
        phone_number: "",
        department_id: "",
        designation_id: "",
        reporting_manager_id: "",
        employment_type: "full_time",
        joining_date: new Date().toISOString().split("T")[0],
        work_location: "Headquarters",
        status: "active",
      });
      setPageSuccess("Employee onboarded successfully.");
      await fetchEmployees();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to onboard employee.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !editingEmp) return;
    setModalError(null);
    setActionLoading(true);
    try {
      await organizationApi.updateEmployee(
        editingEmp.id,
        {
          first_name: empForm.first_name.trim(),
          last_name: empForm.last_name.trim(),
          phone_number: empForm.phone_number.trim() || undefined,
          department_id: empForm.department_id || undefined,
          designation_id: empForm.designation_id || undefined,
          reporting_manager_id: empForm.reporting_manager_id || undefined,
          employment_type: empForm.employment_type,
          joining_date: empForm.joining_date,
          work_location: empForm.work_location.trim() || undefined,
        },
        token
      );
      setShowEditEmpModal(false);
      setEditingEmp(null);
      setPageSuccess("Employee profile updated successfully.");
      await fetchEmployees();
      if (selectedEmp && selectedEmp.id === editingEmp.id) {
        const refreshed = await organizationApi.getEmployeeById(editingEmp.id, token);
        setSelectedEmp(refreshed);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to update employee profile.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateEmployeeStatus = async (employeeId: string, newStatus: string) => {
    if (!token) return;
    try {
      const updated = await organizationApi.updateEmployeeStatus(employeeId, newStatus, token);
      setPageSuccess(`Employee status updated to "${newStatus.replace("_", " ")}".`);
      await fetchEmployees();
      if (selectedEmp && selectedEmp.id === employeeId) {
        setSelectedEmp(updated);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setPageError(`Failed to update status: ${err.detail}`);
      }
    }
  };

  const openEditEmp = (emp: EmployeeDto) => {
    setEditingEmp(emp);
    setEmpForm({
      employee_id: emp.employee_id,
      first_name: emp.first_name,
      last_name: emp.last_name,
      work_email: emp.work_email,
      phone_number: emp.phone_number || "",
      department_id: emp.department_id || "",
      designation_id: emp.designation_id || "",
      reporting_manager_id: emp.reporting_manager_id || "",
      employment_type: emp.employment_type,
      joining_date: emp.joining_date,
      work_location: emp.work_location || "",
      status: emp.status,
    });
    setModalError(null);
    setShowEditEmpModal(true);
  };

  // Pagination helpers
  const totalPages = Math.max(1, Math.ceil(totalEmployees / pageSize));

  // ===========================================================================
  // RENDER: Unauthenticated State
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
            <span className="badge">Organization</span>
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
              <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>🏢</div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}>Sign In to Organization</h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
                Authenticate with your company account to access departments, designations, and employee directory with multi-tenant isolation.
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
                  placeholder="admin@enterprise.com"
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
                disabled={authSubmitting}
                className="btn btn-primary"
                style={{ width: "100%", marginTop: "1rem" }}
              >
                {authSubmitting ? (
                  <>
                    <span className="spinner spinner-sm" />
                    Signing in...
                  </>
                ) : (
                  "Authenticate & Access Workspace"
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Authenticated Employee Self-Service View
  // ===========================================================================

  if (isEmployeeRole) {
    return (
      <div className="container">
        {/* Navigation Header */}
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge">Employee Self-Service</span>
          </div>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            <span className="badge badge-role-employee">Role: Employee</span>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {user?.full_name} ({tenant?.name})
            </span>
            <button className="btn btn-secondary btn-sm" onClick={logout}>
              Sign Out
            </button>
          </div>
        </nav>

        {/* Notice Banner */}
        <div className="alert alert-info" style={{ marginTop: "1.5rem" }}>
          <div>
            <strong>Employee Self-Access:</strong> Under company security policies (`VIEW_OWN_PROFILE`), your account has direct access to your personal employee record only. Full directory browsing is restricted to HR and management.
          </div>
        </div>

        {myProfileLoading && (
          <div className="spinner-container">
            <div className="spinner" />
            <p>Loading your employee profile...</p>
          </div>
        )}

        {myProfileError && (
          <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem", marginTop: "2rem" }}>
            <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>👤</div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>Profile Information</h2>
            <p style={{ color: "var(--text-secondary)", maxWidth: "450px", margin: "0 auto 1.5rem" }}>
              {myProfileError}
            </p>
            <button className="btn btn-secondary btn-sm" onClick={fetchMyProfile}>
              Retry Loading Profile
            </button>
          </div>
        )}

        {myProfile && (
          <div className="card" style={{ maxWidth: "720px", margin: "2rem auto", padding: "2.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", marginBottom: "2rem" }}>
              <div
                style={{
                  width: "64px",
                  height: "64px",
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.75rem",
                  fontWeight: 700,
                  color: "#fff",
                }}
              >
                {myProfile.first_name[0]}{myProfile.last_name[0]}
              </div>
              <div>
                <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>
                  {myProfile.first_name} {myProfile.last_name}
                </h1>
                <div style={{ color: "var(--accent-cyan)", fontSize: "0.95rem" }}>
                  {myProfile.designation_title || "Team Member"} • {myProfile.department_name || "General"}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Employee ID</div>
                <div style={{ fontWeight: 600, fontSize: "1.1rem" }}><code>{myProfile.employee_id}</code></div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Status</div>
                <span className={`status-pill status-${myProfile.status}`}>
                  ● {myProfile.status.replace("_", " ")}
                </span>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Work Email</div>
                <div>{myProfile.work_email}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Phone Number</div>
                <div>{myProfile.phone_number || "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Reporting Manager</div>
                <div>{myProfile.reporting_manager_name || "Direct to Executive"}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Work Location</div>
                <div>{myProfile.work_location || "Headquarters"}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Employment Type</div>
                <div style={{ textTransform: "capitalize" }}>{myProfile.employment_type.replace("_", " ")}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Joining Date</div>
                <div>{myProfile.joining_date}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ===========================================================================
  // RENDER: Full Organization Management (Owner / Admin / HR / Manager)
  // ===========================================================================

  return (
    <div className="container">
      {/* Navigation Header */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge">Organization</span>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <span className={`badge badge-role-${user?.role || "admin"}`}>
            Role: {user?.role ? user.role.toUpperCase() : "AUTHENTICATED"}
          </span>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {user?.full_name} ({tenant?.name})
          </span>
          <button className="btn btn-secondary btn-sm" onClick={logout}>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Hero Header */}
      <div style={{ marginBottom: "2rem", display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "2.25rem", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "0.5rem" }}>
            Organization & Workforce Management
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem" }}>
            Manage organizational hierarchy, departments, designations, and employee directory with live multi-tenant isolation.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowAddDeptModal(true)}>
            + Department
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowAddDesigModal(true)}>
            + Designation
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAddEmpModal(true)}>
            + Add Employee
          </button>
        </div>
      </div>

      {/* Global Alerts */}
      {pageError && (
        <div className="alert alert-danger">
          <span>{pageError}</span>
          <button className="alert-close" onClick={() => setPageError(null)}>
            &times;
          </button>
        </div>
      )}

      {pageSuccess && (
        <div className="alert alert-success">
          <span>{pageSuccess}</span>
          <button className="alert-close" onClick={() => setPageSuccess(null)}>
            &times;
          </button>
        </div>
      )}

      {/* Metric Stat Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">👥</div>
          <div className="stat-content">
            <div className="stat-val">{totalEmployees}</div>
            <div className="stat-label">Total Employees</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(16, 185, 129, 0.12)", color: "var(--accent-emerald)" }}>
            🏢
          </div>
          <div className="stat-content">
            <div className="stat-val">{departments.filter((d) => d.is_active).length}</div>
            <div className="stat-label">Active Departments</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(99, 102, 241, 0.12)", color: "var(--accent-indigo)" }}>
            🏷️
          </div>
          <div className="stat-content">
            <div className="stat-val">{designations.filter((d) => d.is_active).length}</div>
            <div className="stat-label">Designations</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon" style={{ background: "rgba(245, 158, 11, 0.12)", color: "var(--accent-amber)" }}>
            🏖️
          </div>
          <div className="stat-content">
            <div className="stat-val">{employees.filter((e) => e.status === "on_leave").length}</div>
            <div className="stat-label">On Leave Today</div>
          </div>
        </div>
      </div>

      {/* Section Tabs */}
      <div className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          Overview
        </button>
        <button
          className={`tab-btn ${activeTab === "employees" ? "active" : ""}`}
          onClick={() => setActiveTab("employees")}
        >
          Employee Directory ({totalEmployees})
        </button>
        <button
          className={`tab-btn ${activeTab === "departments" ? "active" : ""}`}
          onClick={() => setActiveTab("departments")}
        >
          Departments ({departments.length})
        </button>
        <button
          className={`tab-btn ${activeTab === "designations" ? "active" : ""}`}
          onClick={() => setActiveTab("designations")}
        >
          Designations ({designations.length})
        </button>
      </div>

      {/* =======================================================================
          TAB 1: OVERVIEW
          ======================================================================= */}
      {activeTab === "overview" && (
        <div>
          <div className="grid">
            <div className="card">
              <div className="card-title">
                <span>🏢</span> Departments Architecture
              </div>
              <p className="card-desc">
                Organize workforces into operational cost centers and reporting structures. Each department can appoint a manager from active employees.
              </p>
              <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab("departments")}>
                Manage Departments ({departments.length}) →
              </button>
            </div>

            <div className="card">
              <div className="card-title">
                <span>💼</span> Job Titles & Designations
              </div>
              <p className="card-desc">
                Standardize enterprise roles from executive leadership to shift supervisors. Provides uniform authorization and shift scheduling rules.
              </p>
              <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab("designations")}>
                Manage Designations ({designations.length}) →
              </button>
            </div>

            <div className="card">
              <div className="card-title">
                <span>🔒</span> Multi-Tenant Isolation
              </div>
              <p className="card-desc">
                All employee records, department codes, and designation entries are partitioned by tenant IDs with PostgreSQL Row-Level Security.
              </p>
              <div className="code-block">Tenant: {tenant?.slug || "active"} • RLS Forced</div>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>Recently Joined Employees</h2>
            <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab("employees")}>
              View All Directory →
            </button>
          </div>

          <div className="table-container">
            {loadingEmps ? (
              <div className="spinner-container">
                <div className="spinner" />
                <p>Loading workforce data...</p>
              </div>
            ) : employees.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">👥</div>
                <div className="empty-state-title">No employees onboarded yet</div>
                <p>Add your first employee to populate your directory.</p>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: "1rem" }}
                  onClick={() => setShowAddEmpModal(true)}
                >
                  + Add First Employee
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>ID</th>
                    <th>Department</th>
                    <th>Designation</th>
                    <th>Type</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.slice(0, 5).map((emp) => (
                    <tr key={emp.id} style={{ cursor: "pointer" }} onClick={() => setSelectedEmp(emp)}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{emp.first_name} {emp.last_name}</div>
                        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{emp.work_email}</div>
                      </td>
                      <td><code>{emp.employee_id}</code></td>
                      <td>{emp.department_name || "—"}</td>
                      <td>{emp.designation_title || "—"}</td>
                      <td style={{ textTransform: "capitalize" }}>{emp.employment_type.replace("_", " ")}</td>
                      <td>
                        <span className={`status-pill status-${emp.status}`}>
                          ● {emp.status.replace("_", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 2: EMPLOYEE DIRECTORY
          ======================================================================= */}
      {activeTab === "employees" && (
        <div>
          {/* Toolbar */}
          <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
            <input
              type="text"
              placeholder="Search by name, ID, or email..."
              className="search-input"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
            />
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <select
                className="filter-select"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All Statuses</option>
                <option value="active">Active</option>
                <option value="on_leave">On Leave</option>
                <option value="inactive">Inactive</option>
                <option value="terminated">Terminated</option>
              </select>

              <select
                className="filter-select"
                value={deptFilter}
                onChange={(e) => {
                  setDeptFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All Departments</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>

              <select
                className="filter-select"
                value={desigFilter}
                onChange={(e) => {
                  setDesigFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All Designations</option>
                {designations.map((des) => (
                  <option key={des.id} value={des.id}>
                    {des.title}
                  </option>
                ))}
              </select>

              <button className="btn btn-primary" onClick={() => setShowAddEmpModal(true)}>
                + New Employee
              </button>
            </div>
          </div>

          {/* Directory Table */}
          <div className="table-container">
            {loadingEmps ? (
              <div className="spinner-container">
                <div className="spinner" />
                <p>Loading employees...</p>
              </div>
            ) : employees.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🔍</div>
                <div className="empty-state-title">No employees found</div>
                <p>Try adjusting your search query or clear your filter criteria.</p>
              </div>
            ) : (
              <>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>ID</th>
                      <th>Department</th>
                      <th>Designation</th>
                      <th>Manager</th>
                      <th>Location</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((emp) => (
                      <tr key={emp.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{emp.first_name} {emp.last_name}</div>
                          <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{emp.work_email}</div>
                        </td>
                        <td><code>{emp.employee_id}</code></td>
                        <td>{emp.department_name || "—"}</td>
                        <td>{emp.designation_title || "—"}</td>
                        <td>{emp.reporting_manager_name || "—"}</td>
                        <td>{emp.work_location || "—"}</td>
                        <td>
                          <span className={`status-pill status-${emp.status}`}>
                            ● {emp.status.replace("_", " ")}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedEmp(emp)}>
                              View
                            </button>
                            <button className="btn btn-secondary btn-sm" onClick={() => openEditEmp(emp)}>
                              Edit
                            </button>
                            <button
                              className={`btn btn-sm ${emp.status === "active" ? "btn-danger" : "btn-secondary"}`}
                              onClick={() =>
                                handleUpdateEmployeeStatus(
                                  emp.id,
                                  emp.status === "active" ? "inactive" : "active"
                                )
                              }
                            >
                              {emp.status === "active" ? "Deactivate" : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Pagination Controls */}
                <div className="pagination-bar">
                  <div>
                    Showing {totalEmployees > 0 ? (page - 1) * pageSize + 1 : 0} to{" "}
                    {Math.min(page * pageSize, totalEmployees)} of {totalEmployees} employees
                  </div>
                  <div className="pagination-controls">
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      ← Previous
                    </button>
                    <span>
                      Page {page} of {totalPages}
                    </span>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage(page + 1)}
                    >
                      Next →
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 3: DEPARTMENTS
          ======================================================================= */}
      {activeTab === "departments" && (
        <div>
          <div className="toolbar">
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>Corporate Departments</h2>
            <button className="btn btn-primary" onClick={() => setShowAddDeptModal(true)}>
              + Add Department
            </button>
          </div>

          <div className="table-container">
            {loadingDepts ? (
              <div className="spinner-container">
                <div className="spinner" />
                <p>Loading departments...</p>
              </div>
            ) : departments.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🏢</div>
                <div className="empty-state-title">No departments created yet</div>
                <p>Create your organization’s first department to establish structure.</p>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: "1rem" }}
                  onClick={() => setShowAddDeptModal(true)}
                >
                  + Add First Department
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Department Name</th>
                    <th>Code</th>
                    <th>Description</th>
                    <th>Manager</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((d) => {
                    const manager = employees.find((e) => e.id === d.manager_id);
                    return (
                      <tr key={d.id}>
                        <td style={{ fontWeight: 600 }}>{d.name}</td>
                        <td><code>{d.code}</code></td>
                        <td style={{ color: "var(--text-secondary)" }}>{d.description || "—"}</td>
                        <td>{manager ? `${manager.first_name} ${manager.last_name}` : "—"}</td>
                        <td>
                          <span className={`status-pill ${d.is_active ? "status-active" : "status-inactive"}`}>
                            ● {d.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn btn-secondary btn-sm" onClick={() => openEditDept(d)}>
                              Edit
                            </button>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleToggleDepartmentStatus(d)}
                            >
                              {d.is_active ? "Deactivate" : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          TAB 4: DESIGNATIONS
          ======================================================================= */}
      {activeTab === "designations" && (
        <div>
          <div className="toolbar">
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>Job Titles & Designations</h2>
            <button className="btn btn-primary" onClick={() => setShowAddDesigModal(true)}>
              + Add Designation
            </button>
          </div>

          <div className="table-container">
            {loadingDesigs ? (
              <div className="spinner-container">
                <div className="spinner" />
                <p>Loading designations...</p>
              </div>
            ) : designations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🏷️</div>
                <div className="empty-state-title">No designations created yet</div>
                <p>Define standard job titles and roles for your workforce.</p>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: "1rem" }}
                  onClick={() => setShowAddDesigModal(true)}
                >
                  + Add First Designation
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Designation Title</th>
                    <th>Code</th>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {designations.map((des) => (
                    <tr key={des.id}>
                      <td style={{ fontWeight: 600 }}>{des.title}</td>
                      <td><code>{des.code}</code></td>
                      <td style={{ color: "var(--text-secondary)" }}>{des.description || "—"}</td>
                      <td>
                        <span className={`status-pill ${des.is_active ? "status-active" : "status-inactive"}`}>
                          ● {des.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => openEditDesig(des)}>
                            Edit
                          </button>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleToggleDesignationStatus(des)}
                          >
                            {des.is_active ? "Deactivate" : "Activate"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: ADD EMPLOYEE
          ======================================================================= */}
      {showAddEmpModal && (
        <div className="modal-overlay" onClick={() => setShowAddEmpModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Onboard New Employee</div>
              <button className="modal-close" onClick={() => setShowAddEmpModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleCreateEmployee}>
              <div className="form-group">
                <label className="form-label">Employee ID (Company unique)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. EMP-101"
                  className="form-control"
                  value={empForm.employee_id}
                  onChange={(e) => setEmpForm({ ...empForm, employee_id: e.target.value })}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">First Name</label>
                  <input
                    type="text"
                    required
                    placeholder="First name"
                    className="form-control"
                    value={empForm.first_name}
                    onChange={(e) => setEmpForm({ ...empForm, first_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Last Name</label>
                  <input
                    type="text"
                    required
                    placeholder="Last name"
                    className="form-control"
                    value={empForm.last_name}
                    onChange={(e) => setEmpForm({ ...empForm, last_name: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Work Email</label>
                <input
                  type="email"
                  required
                  placeholder="employee@enterprise.com"
                  className="form-control"
                  value={empForm.work_email}
                  onChange={(e) => setEmpForm({ ...empForm, work_email: e.target.value })}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Phone Number</label>
                  <input
                    type="tel"
                    placeholder="+1 (555) 000-0000"
                    className="form-control"
                    value={empForm.phone_number}
                    onChange={(e) => setEmpForm({ ...empForm, phone_number: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Work Location</label>
                  <input
                    type="text"
                    placeholder="Headquarters / Remote"
                    className="form-control"
                    value={empForm.work_location}
                    onChange={(e) => setEmpForm({ ...empForm, work_location: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Department</label>
                  <select
                    className="form-control"
                    value={empForm.department_id}
                    onChange={(e) => setEmpForm({ ...empForm, department_id: e.target.value })}
                  >
                    <option value="">Select Department (Optional)</option>
                    {departments.filter((d) => d.is_active).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Designation</label>
                  <select
                    className="form-control"
                    value={empForm.designation_id}
                    onChange={(e) => setEmpForm({ ...empForm, designation_id: e.target.value })}
                  >
                    <option value="">Select Designation (Optional)</option>
                    {designations.filter((des) => des.is_active).map((des) => (
                      <option key={des.id} value={des.id}>
                        {des.title} ({des.code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Reporting Manager</label>
                  <select
                    className="form-control"
                    value={empForm.reporting_manager_id}
                    onChange={(e) => setEmpForm({ ...empForm, reporting_manager_id: e.target.value })}
                  >
                    <option value="">None / Reports to Executive</option>
                    {employees.filter((emp) => emp.status === "active").map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.first_name} {emp.last_name} ({emp.employee_id})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Employment Type</label>
                  <select
                    className="form-control"
                    value={empForm.employment_type}
                    onChange={(e) => setEmpForm({ ...empForm, employment_type: e.target.value })}
                  >
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                    <option value="intern">Intern</option>
                    <option value="temporary">Temporary</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Joining Date</label>
                  <input
                    type="date"
                    required
                    className="form-control"
                    value={empForm.joining_date}
                    onChange={(e) => setEmpForm({ ...empForm, joining_date: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Initial Status</label>
                  <select
                    className="form-control"
                    value={empForm.status}
                    onChange={(e) => setEmpForm({ ...empForm, status: e.target.value })}
                  >
                    <option value="active">Active</option>
                    <option value="on_leave">On Leave</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </div>
              </div>

              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddEmpModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Saving..." : "Save & Onboard"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: EDIT EMPLOYEE
          ======================================================================= */}
      {showEditEmpModal && editingEmp && (
        <div className="modal-overlay" onClick={() => setShowEditEmpModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Edit Employee Profile ({editingEmp.employee_id})</div>
              <button className="modal-close" onClick={() => setShowEditEmpModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleUpdateEmployee}>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">First Name</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    value={empForm.first_name}
                    onChange={(e) => setEmpForm({ ...empForm, first_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Last Name</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    value={empForm.last_name}
                    onChange={(e) => setEmpForm({ ...empForm, last_name: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Phone Number</label>
                  <input
                    type="tel"
                    className="form-control"
                    value={empForm.phone_number}
                    onChange={(e) => setEmpForm({ ...empForm, phone_number: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Work Location</label>
                  <input
                    type="text"
                    className="form-control"
                    value={empForm.work_location}
                    onChange={(e) => setEmpForm({ ...empForm, work_location: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Department</label>
                  <select
                    className="form-control"
                    value={empForm.department_id}
                    onChange={(e) => setEmpForm({ ...empForm, department_id: e.target.value })}
                  >
                    <option value="">Select Department (Optional)</option>
                    {departments.filter((d) => d.is_active).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Designation</label>
                  <select
                    className="form-control"
                    value={empForm.designation_id}
                    onChange={(e) => setEmpForm({ ...empForm, designation_id: e.target.value })}
                  >
                    <option value="">Select Designation (Optional)</option>
                    {designations.filter((des) => des.is_active).map((des) => (
                      <option key={des.id} value={des.id}>
                        {des.title} ({des.code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Reporting Manager</label>
                  <select
                    className="form-control"
                    value={empForm.reporting_manager_id}
                    onChange={(e) => setEmpForm({ ...empForm, reporting_manager_id: e.target.value })}
                  >
                    <option value="">None / Reports to Executive</option>
                    {employees
                      .filter((emp) => emp.status === "active" && emp.id !== editingEmp.id)
                      .map((emp) => (
                        <option key={emp.id} value={emp.id}>
                          {emp.first_name} {emp.last_name} ({emp.employee_id})
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Employment Type</label>
                  <select
                    className="form-control"
                    value={empForm.employment_type}
                    onChange={(e) => setEmpForm({ ...empForm, employment_type: e.target.value })}
                  >
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                    <option value="intern">Intern</option>
                    <option value="temporary">Temporary</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Joining Date</label>
                <input
                  type="date"
                  required
                  className="form-control"
                  value={empForm.joining_date}
                  onChange={(e) => setEmpForm({ ...empForm, joining_date: e.target.value })}
                />
              </div>

              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditEmpModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Updating..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: ADD DEPARTMENT
          ======================================================================= */}
      {showAddDeptModal && (
        <div className="modal-overlay" onClick={() => setShowAddDeptModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Create Corporate Department</div>
              <button className="modal-close" onClick={() => setShowAddDeptModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleCreateDepartment}>
              <div className="form-group">
                <label className="form-label">Department Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Quality Assurance"
                  className="form-control"
                  value={deptForm.name}
                  onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Department Code (Unique per tenant)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. QA"
                  className="form-control"
                  value={deptForm.code}
                  onChange={(e) => setDeptForm({ ...deptForm, code: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Department Manager</label>
                <select
                  className="form-control"
                  value={deptForm.manager_id}
                  onChange={(e) => setDeptForm({ ...deptForm, manager_id: e.target.value })}
                >
                  <option value="">No appointed manager</option>
                  {employees.filter((emp) => emp.status === "active").map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.first_name} {emp.last_name} ({emp.employee_id})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <textarea
                  rows={3}
                  placeholder="Department scope and operations..."
                  className="form-control"
                  value={deptForm.description}
                  onChange={(e) => setDeptForm({ ...deptForm, description: e.target.value })}
                />
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddDeptModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Creating..." : "Create Department"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: EDIT DEPARTMENT
          ======================================================================= */}
      {showEditDeptModal && editingDept && (
        <div className="modal-overlay" onClick={() => setShowEditDeptModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Edit Department ({editingDept.code})</div>
              <button className="modal-close" onClick={() => setShowEditDeptModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleUpdateDepartment}>
              <div className="form-group">
                <label className="form-label">Department Name</label>
                <input
                  type="text"
                  required
                  className="form-control"
                  value={deptForm.name}
                  onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Department Code</label>
                <input
                  type="text"
                  required
                  className="form-control"
                  value={deptForm.code}
                  onChange={(e) => setDeptForm({ ...deptForm, code: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Department Manager</label>
                <select
                  className="form-control"
                  value={deptForm.manager_id}
                  onChange={(e) => setDeptForm({ ...deptForm, manager_id: e.target.value })}
                >
                  <option value="">No appointed manager</option>
                  {employees.filter((emp) => emp.status === "active").map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.first_name} {emp.last_name} ({emp.employee_id})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <textarea
                  rows={3}
                  className="form-control"
                  value={deptForm.description}
                  onChange={(e) => setDeptForm({ ...deptForm, description: e.target.value })}
                />
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditDeptModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Updating..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: ADD DESIGNATION
          ======================================================================= */}
      {showAddDesigModal && (
        <div className="modal-overlay" onClick={() => setShowAddDesigModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Create Job Designation</div>
              <button className="modal-close" onClick={() => setShowAddDesigModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleCreateDesignation}>
              <div className="form-group">
                <label className="form-label">Designation Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Lead QA Engineer"
                  className="form-control"
                  value={desigForm.title}
                  onChange={(e) => setDesigForm({ ...desigForm, title: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Designation Code (Unique per tenant)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. QA-LEAD"
                  className="form-control"
                  value={desigForm.code}
                  onChange={(e) => setDesigForm({ ...desigForm, code: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <textarea
                  rows={3}
                  placeholder="Role scope, duties, and qualifications..."
                  className="form-control"
                  value={desigForm.description}
                  onChange={(e) => setDesigForm({ ...desigForm, description: e.target.value })}
                />
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddDesigModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Creating..." : "Create Designation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: EDIT DESIGNATION
          ======================================================================= */}
      {showEditDesigModal && editingDesig && (
        <div className="modal-overlay" onClick={() => setShowEditDesigModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Edit Designation ({editingDesig.code})</div>
              <button className="modal-close" onClick={() => setShowEditDesigModal(false)}>
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleUpdateDesignation}>
              <div className="form-group">
                <label className="form-label">Designation Title</label>
                <input
                  type="text"
                  required
                  className="form-control"
                  value={desigForm.title}
                  onChange={(e) => setDesigForm({ ...desigForm, title: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Designation Code</label>
                <input
                  type="text"
                  required
                  className="form-control"
                  value={desigForm.code}
                  onChange={(e) => setDesigForm({ ...desigForm, code: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <textarea
                  rows={3}
                  className="form-control"
                  value={desigForm.description}
                  onChange={(e) => setDesigForm({ ...desigForm, description: e.target.value })}
                />
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditDesigModal(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading} className="btn btn-primary">
                  {actionLoading ? "Updating..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =======================================================================
          MODAL: VIEW EMPLOYEE PROFILE DETAILS
          ======================================================================= */}
      {selectedEmp && (
        <div className="modal-overlay" onClick={() => setSelectedEmp(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">Employee Profile</div>
              <button className="modal-close" onClick={() => setSelectedEmp(null)}>
                &times;
              </button>
            </div>

            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
                <div
                  style={{
                    width: "56px",
                    height: "56px",
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "1.5rem",
                    fontWeight: 700,
                    color: "#fff",
                  }}
                >
                  {selectedEmp.first_name[0]}{selectedEmp.last_name[0]}
                </div>
                <div>
                  <h3 style={{ fontSize: "1.25rem", fontWeight: 700 }}>
                    {selectedEmp.first_name} {selectedEmp.last_name}
                  </h3>
                  <div style={{ color: "var(--accent-cyan)", fontSize: "0.9rem" }}>
                    {selectedEmp.designation_title || "Team Member"}
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Employee ID</div>
                  <div style={{ fontWeight: 600 }}><code>{selectedEmp.employee_id}</code></div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Status</div>
                  <span className={`status-pill status-${selectedEmp.status}`}>
                    ● {selectedEmp.status.replace("_", " ")}
                  </span>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Department</div>
                  <div>{selectedEmp.department_name || "—"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Work Location</div>
                  <div>{selectedEmp.work_location || "—"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Work Email</div>
                  <div>{selectedEmp.work_email}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Phone Number</div>
                  <div>{selectedEmp.phone_number || "—"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Reporting Manager</div>
                  <div>{selectedEmp.reporting_manager_name || "—"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Employment Type</div>
                  <div style={{ textTransform: "capitalize" }}>{selectedEmp.employment_type.replace("_", " ")}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Joining Date</div>
                  <div>{selectedEmp.joining_date}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Created At</div>
                  <div>{new Date(selectedEmp.created_at).toLocaleDateString()}</div>
                </div>
              </div>

              <div className="form-actions" style={{ flexWrap: "wrap", justifyContent: "space-between" }}>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      const emp = selectedEmp;
                      setSelectedEmp(null);
                      openEditEmp(emp);
                    }}
                  >
                    Edit Profile
                  </button>
                  <button
                    type="button"
                    className={`btn ${selectedEmp.status === "active" ? "btn-danger" : "btn-primary"}`}
                    onClick={() =>
                      handleUpdateEmployeeStatus(
                        selectedEmp.id,
                        selectedEmp.status === "active" ? "inactive" : "active"
                      )
                    }
                  >
                    {selectedEmp.status === "active" ? "Deactivate" : "Activate"}
                  </button>
                </div>
                <button type="button" className="btn btn-secondary" onClick={() => setSelectedEmp(null)}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="footer" style={{ marginTop: "4rem" }}>
        <p>Attendance SaaS © 2026 • Phase 3: Organization Structure & Employee Management</p>
      </footer>
    </div>
  );
}
