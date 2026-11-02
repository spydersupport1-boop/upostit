/**
 * Centralized API client foundation for Next.js web application.
 *
 * Implements:
 * - Environment-driven API base URL configuration (NEXT_PUBLIC_API_URL)
 * - Safe token handling (header-based Authorization: Bearer <token>)
 * - Standardized error parsing and typing (including Pydantic validation errors)
 * - Zero secrets embedded in frontend code
 * - Full CRUD endpoints for Organization and Employees
 * - Authentication and token storage helpers
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  raw?: unknown;

  constructor(status: number, detail: string, raw?: unknown) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.raw = raw;
  }
}

export interface RequestOptions extends RequestInit {
  token?: string | null;
  params?: Record<string, string | number | boolean | undefined | null>;
  _isRetry?: boolean;
}

type TokenRefreshHandler = () => Promise<string | null>;
let globalRefreshHandler: TokenRefreshHandler | null = null;

export function setTokenRefreshHandler(handler: TokenRefreshHandler | null): void {
  globalRefreshHandler = handler;
}

/**
 * Low-level HTTP fetch wrapper with standard headers, credentials, and error parsing.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, params, headers, credentials = "include", _isRetry = false, ...customConfig } = options;

  let url = `${API_BASE_URL}/api/v1${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== "") {
        searchParams.append(key, String(val));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const defaultHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    defaultHeaders["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    credentials,
    ...customConfig,
    headers: {
      ...defaultHeaders,
      ...headers,
    },
  });

  // If unauthorized on a business endpoint and not already retrying, attempt transparent refresh
  if (
    response.status === 401 &&
    !endpoint.includes("/auth/") &&
    !_isRetry &&
    globalRefreshHandler
  ) {
    const newToken = await globalRefreshHandler();
    if (newToken) {
      return apiFetch<T>(endpoint, {
        ...options,
        token: newToken,
        _isRetry: true,
      });
    }
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    let rawError: unknown = null;
    try {
      const errJson = await response.json();
      rawError = errJson;
      if (typeof errJson.detail === "string") {
        detail = errJson.detail;
      } else if (Array.isArray(errJson.detail)) {
        detail = errJson.detail
          .map((e: { loc?: string[]; msg?: string }) => {
            const field = e.loc
              ? e.loc.filter((l) => l !== "body").join(".")
              : "";
            return field
              ? `${field}: ${e.msg || "invalid"}`
              : e.msg || JSON.stringify(e);
          })
          .join("; ");
      }
    } catch {
      // response was not JSON
    }
    throw new ApiError(response.status, detail, rawError);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// =============================================================================
// Token Storage Helpers (Legacy Cleanup Only)
// =============================================================================

/**
 * Token storage helper.
 *
 * Phase 3.3 Security Architecture:
 * - Refresh tokens are stored ONLY in browser HttpOnly cookies set by FastAPI.
 * - Access tokens reside in React memory context and are NEVER written to localStorage.
 * - JavaScript cannot access or read the HttpOnly cookie.
 * - This helper exists only to purge legacy tokens from prior development builds.
 */
export const tokenStorage = {
  clearLegacyTokens: (): void => {
    if (typeof window === "undefined" && typeof globalThis.localStorage === "undefined") return;
    try {
      localStorage.removeItem("attendance_access_token");
      localStorage.removeItem("attendance_refresh_token");
    } catch {
      // Storage access may be blocked in sandboxed or private contexts
    }
  },
};

// =============================================================================
// Authentication DTOs & Endpoints
// =============================================================================

export interface LoginRequestDto {
  email: string;
  password: string;
  tenant_slug: string;
}

export interface TokenResponseDto {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface UserDto {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "hr" | "manager" | "employee";
  status: "active" | "inactive";
  created_at: string;
  updated_at: string;
}

export interface TenantDto {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface UserProfileResponseDto {
  user: UserDto;
  tenant: TenantDto;
}

export const authApi = {
  login: (data: LoginRequestDto) =>
    apiFetch<TokenResponseDto>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  refresh: () =>
    apiFetch<TokenResponseDto>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  getMe: (token?: string) =>
    apiFetch<UserProfileResponseDto>("/auth/me", {
      token,
    }),

  logout: (token?: string) =>
    apiFetch<{ message: string }>("/auth/logout", {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),
};

// =============================================================================
// Organization DTOs & Endpoints
// =============================================================================

export interface DepartmentDto {
  id: string;
  tenant_id?: string;
  name: string;
  code: string;
  description?: string | null;
  manager_id?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DepartmentListResponseDto {
  items: DepartmentDto[];
  total: number;
}

export interface DepartmentCreateDto {
  name: string;
  code: string;
  description?: string | null;
  manager_id?: string | null;
}

export interface DepartmentUpdateDto {
  name?: string;
  code?: string;
  description?: string | null;
  manager_id?: string | null;
  is_active?: boolean;
}

export interface DesignationDto {
  id: string;
  tenant_id?: string;
  title: string;
  code: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DesignationListResponseDto {
  items: DesignationDto[];
  total: number;
}

export interface DesignationCreateDto {
  title: string;
  code: string;
  description?: string | null;
}

export interface DesignationUpdateDto {
  title?: string;
  code?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface EmployeeDto {
  id: string;
  tenant_id: string;
  user_id?: string | null;
  employee_id: string;
  first_name: string;
  last_name: string;
  work_email: string;
  phone_number?: string | null;
  department_id?: string | null;
  department_name?: string | null;
  designation_id?: string | null;
  designation_title?: string | null;
  reporting_manager_id?: string | null;
  reporting_manager_name?: string | null;
  employment_type: string;
  joining_date: string;
  status: "active" | "inactive" | "on_leave" | "terminated";
  work_location?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeListResponseDto {
  items: EmployeeDto[];
  total: number;
  page: number;
  page_size: number;
}

export interface EmployeeCreateDto {
  employee_id: string;
  first_name: string;
  last_name: string;
  work_email: string;
  phone_number?: string | null;
  department_id?: string | null;
  designation_id?: string | null;
  reporting_manager_id?: string | null;
  employment_type?: string;
  joining_date: string;
  status?: string;
  work_location?: string | null;
  user_id?: string | null;
}

export interface EmployeeUpdateDto {
  first_name?: string;
  last_name?: string;
  phone_number?: string | null;
  department_id?: string | null;
  designation_id?: string | null;
  reporting_manager_id?: string | null;
  employment_type?: string;
  joining_date?: string;
  work_location?: string | null;
  user_id?: string | null;
}

export const organizationApi = {
  // Departments
  getDepartments: (
    params?: { is_active?: boolean; search?: string; limit?: number; offset?: number },
    token?: string
  ) =>
    apiFetch<DepartmentListResponseDto>("/departments", {
      token,
      params,
    }),

  getDepartmentById: (id: string, token?: string) =>
    apiFetch<DepartmentDto>(`/departments/${id}`, {
      token,
    }),

  createDepartment: (data: DepartmentCreateDto, token?: string) =>
    apiFetch<DepartmentDto>("/departments", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateDepartment: (id: string, data: DepartmentUpdateDto, token?: string) =>
    apiFetch<DepartmentDto>(`/departments/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deactivateDepartment: (id: string, token?: string) =>
    apiFetch<DepartmentDto>(`/departments/${id}`, {
      method: "DELETE",
      token,
    }),

  // Designations
  getDesignations: (
    params?: { is_active?: boolean; search?: string; limit?: number; offset?: number },
    token?: string
  ) =>
    apiFetch<DesignationListResponseDto>("/designations", {
      token,
      params,
    }),

  getDesignationById: (id: string, token?: string) =>
    apiFetch<DesignationDto>(`/designations/${id}`, {
      token,
    }),

  createDesignation: (data: DesignationCreateDto, token?: string) =>
    apiFetch<DesignationDto>("/designations", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateDesignation: (id: string, data: DesignationUpdateDto, token?: string) =>
    apiFetch<DesignationDto>(`/designations/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deactivateDesignation: (id: string, token?: string) =>
    apiFetch<DesignationDto>(`/designations/${id}`, {
      method: "DELETE",
      token,
    }),

  // Employees
  getEmployees: (
    params?: {
      search?: string;
      department_id?: string;
      designation_id?: string;
      status?: string;
      employment_type?: string;
      page?: number;
      page_size?: number;
    },
    token?: string
  ) =>
    apiFetch<EmployeeListResponseDto>("/employees", {
      token,
      params,
    }),

  getMyProfile: (token?: string) =>
    apiFetch<EmployeeDto>("/employees/me", {
      token,
    }),

  getEmployeeById: (id: string, token?: string) =>
    apiFetch<EmployeeDto>(`/employees/${id}`, {
      token,
    }),

  createEmployee: (data: EmployeeCreateDto, token?: string) =>
    apiFetch<EmployeeDto>("/employees", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateEmployee: (id: string, data: EmployeeUpdateDto, token?: string) =>
    apiFetch<EmployeeDto>(`/employees/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  updateEmployeeStatus: (id: string, status: string, token?: string) =>
    apiFetch<EmployeeDto>(`/employees/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
      token,
    }),
};
