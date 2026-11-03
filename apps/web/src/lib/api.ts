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
  responseType?: "json" | "blob";
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
  const { token, params, headers, credentials = "include", _isRetry = false, responseType = "json", ...customConfig } = options;

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

  const defaultHeaders: Record<string, string> = {};

  // Do not set Content-Type if uploading FormData (browser sets boundary automatically)
  if (typeof FormData !== "undefined" && customConfig.body instanceof FormData) {
    // leave Content-Type unset
  } else if (!headers || !("Content-Type" in (headers as Record<string, string>))) {
    defaultHeaders["Content-Type"] = "application/json";
  }

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

  if (responseType === "blob") {
    return (await response.blob()) as unknown as T;
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

// =============================================================================
// Phase 4: Workplace Location DTOs & Endpoints
// =============================================================================

export interface LocationDto {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country_code: string;
  postal_code?: string | null;
  timezone: string;
  latitude: number;
  longitude: number;
  geofence_radius_meters: number;
  is_active: boolean;
  wifi_ssid?: string | null;
  wifi_bssid?: string | null;
  ip_range?: string | null;
  employee_count: number;
  created_at: string;
  updated_at: string;
}

export interface LocationCreateDto {
  name: string;
  code: string;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country_code: string;
  postal_code?: string | null;
  timezone: string;
  latitude: number;
  longitude: number;
  geofence_radius_meters?: number;
  is_active?: boolean;
  wifi_ssid?: string | null;
  wifi_bssid?: string | null;
  ip_range?: string | null;
}

export interface LocationUpdateDto {
  name?: string;
  code?: string;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country_code?: string;
  postal_code?: string | null;
  timezone?: string;
  latitude?: number;
  longitude?: number;
  geofence_radius_meters?: number;
  is_active?: boolean;
  wifi_ssid?: string | null;
  wifi_bssid?: string | null;
  ip_range?: string | null;
}

export interface LocationListResponseDto {
  items: LocationDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface GeofenceVerifyRequestDto {
  location_id: string;
  latitude: number;
  longitude: number;
}

export interface GeofenceVerifyResponseDto {
  is_inside: boolean;
  distance_meters: number;
  threshold_meters: number;
  details: Record<string, unknown>;
}

export interface LocationEmployeeDto {
  assignment_id: string;
  employee_id: string;
  employee_number: string;
  full_name: string;
  email: string;
  department_name?: string | null;
  designation_title?: string | null;
  is_primary: boolean;
  effective_from: string;
  effective_to?: string | null;
}

export interface LocationEmployeeListResponseDto {
  items: LocationEmployeeDto[];
  total: number;
  page: number;
  page_size: number;
}

export const locationApi = {
  getLocations: (
    params?: { search?: string; is_active?: boolean; limit?: number; offset?: number },
    token?: string
  ) =>
    apiFetch<LocationListResponseDto>("/locations", {
      token,
      params,
    }),

  getLocationById: (id: string, token?: string) =>
    apiFetch<LocationDto>(`/locations/${id}`, {
      token,
    }),

  createLocation: (data: LocationCreateDto, token?: string) =>
    apiFetch<LocationDto>("/locations", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateLocation: (id: string, data: LocationUpdateDto, token?: string) =>
    apiFetch<LocationDto>(`/locations/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deactivateLocation: (id: string, token?: string) =>
    apiFetch<LocationDto>(`/locations/${id}`, {
      method: "DELETE",
      token,
    }),

  verifyCoordinates: (data: GeofenceVerifyRequestDto, token?: string) =>
    apiFetch<GeofenceVerifyResponseDto>("/locations/verify-coordinates", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getLocationEmployees: (
    locationId: string,
    params?: { search?: string; is_primary?: boolean; is_current?: boolean; page?: number; page_size?: number },
    token?: string
  ) =>
    apiFetch<LocationEmployeeListResponseDto>(`/locations/${locationId}/employees`, {
      token,
      params,
    }),
};

// =============================================================================
// Phase 4: Employee Workplace Assignment DTOs & Endpoints
// =============================================================================

export interface WorkplaceAssignmentDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  location_id: string;
  location_name: string;
  location_code: string;
  is_primary: boolean;
  effective_from: string;
  effective_to?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkplaceAssignmentCreateDto {
  location_id: string;
  is_primary?: boolean;
  effective_from?: string;
  effective_to?: string | null;
}

export interface WorkplaceAssignmentUpdateDto {
  is_primary?: boolean;
  effective_from?: string;
  effective_to?: string | null;
}

export interface WorkplaceAssignmentListResponseDto {
  items: WorkplaceAssignmentDto[];
  total: number;
  page: number;
  page_size: number;
}

export const assignmentApi = {
  getEmployeeWorkplaces: (
    employeeId: string,
    params?: { is_current?: boolean; page?: number; page_size?: number },
    token?: string
  ) =>
    apiFetch<WorkplaceAssignmentListResponseDto>(`/employees/${employeeId}/workplaces`, {
      token,
      params,
    }),

  assignWorkplace: (
    employeeId: string,
    data: WorkplaceAssignmentCreateDto,
    token?: string
  ) =>
    apiFetch<WorkplaceAssignmentDto>(`/employees/${employeeId}/workplaces`, {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateAssignment: (
    employeeId: string,
    assignmentId: string,
    data: WorkplaceAssignmentUpdateDto,
    token?: string
  ) =>
    apiFetch<WorkplaceAssignmentDto>(`/employees/${employeeId}/workplaces/${assignmentId}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  endAssignment: (
    employeeId: string,
    assignmentId: string,
    endDate?: string,
    token?: string
  ) =>
    apiFetch<WorkplaceAssignmentDto>(
      `/employees/${employeeId}/workplaces/${assignmentId}${endDate ? `?end_date=${encodeURIComponent(endDate)}` : ""}`,
      {
        method: "DELETE",
        token,
      }
    ),

  getMyWorkplaces: (token?: string) =>
    apiFetch<WorkplaceAssignmentListResponseDto>("/employees/me/workplaces", {
      token,
    }),
};

// =============================================================================
// Phase 4: Bulk Employee Import DTOs & Endpoints
// =============================================================================

export interface ImportJobDto {
  id: string;
  tenant_id: string;
  created_by_user_id?: string | null;
  file_name: string;
  file_format: string;
  status: "queued" | "processing" | "completed" | "failed";
  total_rows: number;
  processed_rows: number;
  succeeded_rows: number;
  failed_rows: number;
  last_processed_row_index: number;
  error_summary?: Array<{ row_number: number; errors: string[] }> | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface ImportErrorsResponseDto {
  job_id: string;
  status: string;
  total_rows: number;
  failed_rows: number;
  errors: Array<{ row_number: number; errors: string[] }>;
}

export const importApi = {
  downloadTemplate: (format: "csv" | "xlsx" = "csv", token?: string) =>
    apiFetch<Blob>(`/employees/import/template?format=${format}`, {
      token,
      responseType: "blob",
    }),

  uploadFile: (file: File, token?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<ImportJobDto>("/employees/import", {
      method: "POST",
      body: formData,
      token,
    });
  },

  getJobStatus: (jobId: string, token?: string) =>
    apiFetch<ImportJobDto>(`/employees/import/${jobId}`, {
      token,
    }),

  getJobErrors: (jobId: string, token?: string) =>
    apiFetch<ImportErrorsResponseDto>(`/employees/import/${jobId}/errors`, {
      token,
    }),

  downloadErrorReport: (jobId: string, token?: string) =>
    apiFetch<Blob>(`/employees/import/${jobId}/errors/download`, {
      token,
      responseType: "blob",
    }),

  retryJob: (jobId: string, token?: string) =>
    apiFetch<ImportJobDto>(`/employees/import/${jobId}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),
};

// =============================================================================
// Phase 4: Employee Invitations & Account Activation DTOs & Endpoints
// =============================================================================

export interface InvitationDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name?: string | null;
  employee_number?: string | null;
  invited_by_user_id?: string | null;
  email: string;
  status: "pending" | "accepted" | "expired" | "revoked";
  delivery_status: "pending" | "sent" | "failed";
  delivery_error?: string | null;
  attempt_count: number;
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
  updated_at: string;
  preview_url?: string | null;
}

export interface InvitationListResponseDto {
  items: InvitationDto[];
  total: number;
  skip: number;
  limit: number;
}

export interface ValidateInvitationResponseDto {
  valid: boolean;
  email: string;
  employee_name: string;
  company_name: string;
  expires_at: string;
}

export interface ActivateAccountRequestDto {
  token: string;
  password: string;
  password_confirm: string;
}

export interface ActivateAccountResponseDto {
  success: boolean;
  message: string;
  user_id: string;
  email: string;
}

export const invitationApi = {
  // Administrative invitation endpoints
  inviteEmployee: (employeeId: string, token?: string) =>
    apiFetch<InvitationDto>(`/employees/${employeeId}/invite`, {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),

  getInvitations: (
    params?: { status?: string; employee_id?: string; skip?: number; limit?: number },
    token?: string
  ) =>
    apiFetch<InvitationListResponseDto>("/invitations", {
      token,
      params,
    }),

  getInvitationById: (id: string, token?: string) =>
    apiFetch<InvitationDto>(`/invitations/${id}`, {
      token,
    }),

  resendInvitation: (id: string, token?: string) =>
    apiFetch<InvitationDto>(`/invitations/${id}/resend`, {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),

  revokeInvitation: (id: string, token?: string) =>
    apiFetch<InvitationDto>(`/invitations/${id}/revoke`, {
      method: "POST",
      body: JSON.stringify({}),
      token,
    }),

  // Public activation endpoints (No authentication required)
  validateToken: (tokenStr: string) =>
    apiFetch<ValidateInvitationResponseDto>(`/auth/invitations/validate?token=${encodeURIComponent(tokenStr)}`),

  activateAccount: (data: ActivateAccountRequestDto) =>
    apiFetch<ActivateAccountResponseDto>("/auth/invitations/activate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// =============================================================================
// Phase 5: Attendance Engine, Shifts & Correction DTOs & Endpoints
// =============================================================================

export interface ShiftVersionDto {
  id: string;
  shift_template_id: string;
  version_number: number;
  version_effective_from: string;
  start_time: string;
  end_time: string;
  grace_period_minutes: number;
  early_exit_grace_minutes: number;
  early_arrival_allowance_minutes: number;
  late_departure_allowance_minutes: number;
  half_day_threshold_minutes: number;
  full_day_threshold_minutes: number;
  break_duration_minutes: number;
  is_overnight: boolean;
  is_flexible: boolean;
  weekly_off_days: number[];
  created_by_user_id?: string | null;
  created_at: string;
}

export interface ShiftTemplateDto {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
  description?: string | null;
  is_active: boolean;
  current_version_number: number;
  current_version?: ShiftVersionDto | null;
  created_at: string;
  updated_at: string;
}

export interface ShiftAssignmentDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  shift_template_id: string;
  effective_from: string;
  effective_to?: string | null;
  shift_template?: ShiftTemplateDto | null;
  created_at: string;
  updated_at: string;
}

export interface AttendanceEventDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  event_type: "CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END";
  event_category: "STANDARD" | "CORRECTION_INSERT" | "CORRECTION_SUPERSEDE" | "CORRECTION_VOID";
  supersedes_event_id?: string | null;
  correction_reason?: string | null;
  server_received_at: string;
  device_reported_at?: string | null;
  effective_at: string;
  clock_drift_seconds?: number | string | null;
  source: string;
  device_id?: string | null;
  timestamp_verification_status: string;
  review_status: string;
  idempotency_key: string;
  location_id?: string | null;
  latitude?: number | string | null;
  longitude?: number | string | null;
  accuracy_meters?: number | string | null;
  actor_user_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface PunchRequestDto {
  employee_id: string;
  event_type: "CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END";
  client_timestamp?: string;
  idempotency_key: string;
  location_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  accuracy_meters?: number | null;
}

export interface PunchResponseDto {
  event: AttendanceEventDto;
  additional_events: AttendanceEventDto[];
  idempotent_replay: boolean;
}

export interface AttendanceEventListResponseDto {
  items: AttendanceEventDto[];
  total: number;
  next_cursor?: string | null;
}

export interface AttendanceDayDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name?: string | null;
  employee_number?: string | null;
  attendance_date: string;
  shift_template_id?: string | null;
  shift_version_id?: string | null;
  shift_name?: string | null;
  first_check_in?: string | null;
  last_check_out?: string | null;
  total_working_minutes: number;
  total_break_minutes: number;
  net_working_minutes: number;
  actual_late_minutes: number;
  late_arrival_minutes: number;
  actual_early_minutes: number;
  early_departure_minutes: number;
  overtime_minutes: number;
  status: "PRESENT" | "LATE" | "HALF_DAY" | "ABSENT" | "INCOMPLETE" | "WEEK_OFF" | "ON_LEAVE" | "HOLIDAY" | "PENDING_REVIEW";
  calculation_status: "CALCULATED" | "INCOMPLETE" | "FLAGGED";
  calculation_version: number;
  is_incomplete: boolean;
  missing_punch: boolean;
  source_event_ids: string[];
  metadata?: Record<string, unknown>;
  last_calculated_at: string;
  created_at: string;
  updated_at: string;
}

export interface AttendanceDayListResponseDto {
  items: AttendanceDayDto[];
  total: number;
  next_cursor?: string | null;
}

export type AttendanceCorrectionType = "CORRECTION_INSERT" | "CORRECTION_SUPERSEDE" | "CORRECTION_VOID";

export interface AttendanceCorrectionCreateRequestDto {
  employee_id: string;
  correction_type: AttendanceCorrectionType;
  event_type?: "CHECK_IN" | "CHECK_OUT" | "BREAK_START" | "BREAK_END";
  effective_at?: string | null;
  supersedes_event_id?: string | null;
  correction_reason: string;
  idempotency_key: string;
  location_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface AttendanceCorrectionResponseDto {
  correction_event: AttendanceEventDto;
  affected_attendance_dates: string[];
  recalculated_days: AttendanceDayDto[];
  idempotent_replay: boolean;
}

export interface AttendanceEventAuditDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  event_type: string;
  event_category: string;
  effective_at: string;
  server_received_at: string;
  supersedes_event_id?: string | null;
  correction_reason?: string | null;
  actor_user_id?: string | null;
  source: string;
  review_status: string;
  timestamp_verification_status: string;
  is_active: boolean;
  superseded_by_event_id?: string | null;
  voided_by_event_id?: string | null;
  created_at: string;
}

export interface AttendanceEventAuditListResponseDto {
  items: AttendanceEventAuditDto[];
  total: number;
}

export interface AttendanceCorrectionListResponseDto {
  items: AttendanceEventDto[];
  total: number;
  next_cursor?: string | null;
}

export interface ReconciliationRequestDto {
  target_date?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  employee_id?: string | null;
  batch_size?: number;
}

export interface ReconciliationResponseDto {
  status: string;
  tenant_id: string;
  target_dates: string[];
  total_candidates: number;
  recalculated_count: number;
  failed_count: number;
  errors: string[];
}

export const shiftApi = {
  getShifts: (
    params?: { search?: string; is_active?: boolean; limit?: number },
    token?: string
  ) =>
    apiFetch<ShiftTemplateDto[]>("/shifts", {
      token,
      params,
    }),

  getShiftById: (id: string, token?: string) =>
    apiFetch<ShiftTemplateDto>(`/shifts/${id}`, {
      token,
    }),

  getAssignments: (
    params?: {
      employee_id?: string;
      shift_template_id?: string;
      active_on_date?: string;
      limit?: number;
    },
    token?: string
  ) =>
    apiFetch<ShiftAssignmentDto[]>("/shifts/assignments", {
      token,
      params,
    }),
};

export const attendanceApi = {
  // Daily attendance summaries
  getDays: (
    params?: {
      employee_id?: string;
      start_date?: string;
      end_date?: string;
      attendance_status?: string;
      limit?: number;
      cursor?: string;
    },
    token?: string
  ) =>
    apiFetch<AttendanceDayListResponseDto>("/attendance/days", {
      token,
      params,
    }),

  getDay: (employeeId: string, attendanceDate: string, token?: string) =>
    apiFetch<AttendanceDayDto>(`/attendance/days/${employeeId}/${attendanceDate}`, {
      token,
    }),

  recalculate: (employeeId: string, attendanceDate: string, token?: string) =>
    apiFetch<AttendanceDayDto>("/attendance/recalculate", {
      method: "POST",
      body: JSON.stringify({ employee_id: employeeId, attendance_date: attendanceDate }),
      token,
    }),

  // Employee punch action
  punch: (data: PunchRequestDto, token?: string) =>
    apiFetch<PunchResponseDto>("/attendance/punch", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  // Raw attendance events
  getEvents: (
    params?: {
      employee_id?: string;
      event_type?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      cursor?: string;
    },
    token?: string
  ) =>
    apiFetch<AttendanceEventListResponseDto>("/attendance/events", {
      token,
      params,
    }),

  getEventById: (eventId: string, token?: string) =>
    apiFetch<AttendanceEventDto>(`/attendance/events/${eventId}`, {
      token,
    }),

  // Administrative corrections & audit
  createCorrection: (data: AttendanceCorrectionCreateRequestDto, token?: string) =>
    apiFetch<AttendanceCorrectionResponseDto>("/attendance/corrections", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getCorrections: (
    params?: {
      employee_id?: string;
      correction_type?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      cursor?: string;
    },
    token?: string
  ) =>
    apiFetch<AttendanceCorrectionListResponseDto>("/attendance/corrections", {
      token,
      params,
    }),

  getDayEvents: (recordId: string, token?: string) =>
    apiFetch<AttendanceEventAuditListResponseDto>(`/attendance/records/${recordId}/events`, {
      token,
    }),

  // Batch reconciliation
  reconcile: (data: ReconciliationRequestDto, token?: string) =>
    apiFetch<ReconciliationResponseDto>("/attendance/reconcile", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),
};

