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

// =============================================================================
// Offline Attendance Conflict Adjudication (Phase 8)
// =============================================================================

export interface ConflictIncidentEmployeeDetailDto {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  work_email: string;
  department_name?: string | null;
  reporting_manager_id?: string | null;
}

export interface SupervisorConflictQueueItemDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department_name?: string | null;
  bundle_id: string;
  session_id?: string | null;
  status: "PENDING_REVIEW" | "APPROVED" | "REJECTED" | string;
  total_events_count: number;
  dependent_count?: number | null;
  primary_event_type: string;
  primary_device_reported_at: string;
  rejection_summary?: string | null;
  employee_notes?: string | null;
  submitted_at: string;
  conflict_code?: string | null;
  severity?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  classification?:
    | "AUTO_RESOLVABLE"
    | "NEEDS_EMPLOYEE_CLARIFICATION"
    | "NEEDS_MANAGER_REVIEW"
    | "INVALID_UNAUTHORIZED"
    | string;
  employee_clarification?: string | null;
  clarification_requested_at?: string | null;
  clarification_submitted_at?: string | null;
  decision?: "APPROVE" | "REJECT" | string | null;
  decision_reason?: string | null;
  reviewer_user_id?: string | null;
  decided_at?: string | null;
  resolved_correction_event_ids?: string[];
}

export interface SupervisorConflictQueueListResponseDto {
  items: SupervisorConflictQueueItemDto[];
  total: number;
  limit: number;
  cursor?: string | null;
  has_more: boolean;
}

export interface ConflictTelemetryEventDto {
  local_id?: string | null;
  idempotency_key?: string | null;
  event_type: string;
  device_reported_at?: string | null;
  event_id?: string | null;
  client_timestamp?: string | null;
  rejection_code?: number | null;
  rejection_reason?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  accuracy_meters?: number | null;
  device_id_hash?: string | null;
  device_model?: string | null;
  os_version?: string | null;
  is_mock_location?: boolean | null;
  server_rejection_code?: number | null;
  server_rejection_reason?: string | null;
  location_id?: string | null;
  wifi_ssid?: string | null;
  wifi_bssid?: string | null;
  [key: string]: unknown;
}

export interface AttendanceConflictIncidentDetailDto {
  id: string;
  tenant_id: string;
  bundle_id: string;
  bundle_fingerprint?: string | null;
  session_id?: string | null;
  status: "PENDING_REVIEW" | "APPROVED" | "REJECTED" | string;
  employee: ConflictIncidentEmployeeDetailDto;
  primary_rejected_event: ConflictTelemetryEventDto;
  dependent_events: ConflictTelemetryEventDto[];
  total_events_count: number;
  rejection_summary?: string | null;
  employee_notes?: string | null;
  submitted_at: string;
  conflict_code?: string | null;
  severity?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  classification?:
    | "AUTO_RESOLVABLE"
    | "NEEDS_EMPLOYEE_CLARIFICATION"
    | "NEEDS_MANAGER_REVIEW"
    | "INVALID_UNAUTHORIZED"
    | string;
  employee_clarification?: string | null;
  clarification_requested_at?: string | null;
  clarification_submitted_at?: string | null;
  assigned_reviewer_id?: string | null;
  decision?:
    | "APPROVE"
    | "REJECT"
    | "ACCEPT_SEQUENCE"
    | "REJECT_INVALID_EVENTS"
    | "REQUEST_CLARIFICATION"
    | "MARK_UNRESOLVED"
    | "ESCALATE_HR"
    | string
    | null;
  decision_reason?: string | null;
  reviewer_user_id?: string | null;
  decided_at?: string | null;
  resolved_correction_event_ids?: string[];
  metadata_json?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AttendanceConflictDecisionRequestDto {
  action:
    | "APPROVE"
    | "REJECT"
    | "ACCEPT_SEQUENCE"
    | "REJECT_INVALID_EVENTS"
    | "REQUEST_CLARIFICATION"
    | "MARK_UNRESOLVED"
    | "ESCALATE_HR"
    | string;
  reason: string;
  override_location_id?: string | null;
}

export interface AttendanceConflictDecisionResponseDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  bundle_id: string;
  session_id?: string | null;
  status: string;
  decision: string;
  decision_reason: string;
  reviewer_user_id: string;
  decided_at: string;
  resolved_correction_event_ids: string[];
  affected_attendance_dates: string[];
  recalculated_days_count: number;
}

export interface EmployeeConflictIncidentItemDto {
  id: string;
  bundle_id: string;
  session_id?: string | null;
  status: string;
  total_events_count: number;
  primary_event_type: string;
  primary_event_timestamp: string;
  rejection_summary?: string | null;
  employee_notes?: string | null;
  submitted_at: string;
  decision?: string | null;
  decision_reason?: string | null;
  decided_at?: string | null;
  resolved_events_count: number;
}

export interface EmployeeConflictIncidentListResponseDto {
  items: EmployeeConflictIncidentItemDto[];
  total: number;
  limit: number;
  cursor?: string | null;
  has_more: boolean;
}

export const conflictApi = {
  getSupervisorQueue: (
    params?: {
      status?: string;
      employee_id?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      cursor?: string;
    },
    token?: string
  ) =>
    apiFetch<SupervisorConflictQueueListResponseDto>("/attendance/offline-conflicts", {
      token,
      params,
    }),

  getIncidentDetail: (incidentId: string, token?: string) =>
    apiFetch<AttendanceConflictIncidentDetailDto>(`/attendance/offline-conflicts/${incidentId}`, {
      token,
    }),

  adjudicateIncident: (
    incidentId: string,
    data: AttendanceConflictDecisionRequestDto,
    token?: string
  ) =>
    apiFetch<AttendanceConflictDecisionResponseDto>(
      `/attendance/offline-conflicts/${incidentId}/decision`,
      {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }
    ),

  submitClarification: (
    incidentId: string,
    data: { clarification_notes: string },
    token?: string
  ) =>
    apiFetch<AttendanceConflictIncidentDetailDto>(
      `/attendance/offline-conflicts/${incidentId}/clarify`,
      {
        method: "POST",
        body: JSON.stringify(data),
        token,
      }
    ),

  getMyConflicts: (
    params?: {
      status?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      cursor?: string;
    },
    token?: string
  ) =>
    apiFetch<EmployeeConflictIncidentListResponseDto>("/attendance/offline-conflicts/my", {
      token,
      params,
    }),
};

// =============================================================================
// Phase 9: Leave Types, Holiday Calendars & Overtime DTOs and APIs
// =============================================================================

export interface LeaveTypeDto {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description?: string | null;
  is_paid: boolean;
  requires_approval: boolean;
  allow_half_day: boolean;
  max_consecutive_days?: number | null;
  carry_forward_limit: number | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LeaveTypeListResponseDto {
  items: LeaveTypeDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeaveTypeCreateRequestDto {
  code: string;
  name: string;
  description?: string | null;
  is_paid?: boolean;
  requires_approval?: boolean;
  allow_half_day?: boolean;
  max_consecutive_days?: number | null;
  carry_forward_limit?: number | string;
  is_active?: boolean;
}

export interface LeaveTypeUpdateRequestDto {
  name?: string;
  description?: string | null;
  is_paid?: boolean;
  requires_approval?: boolean;
  allow_half_day?: boolean;
  max_consecutive_days?: number | null;
  carry_forward_limit?: number | string;
  is_active?: boolean;
}

export interface HolidayDto {
  id: string;
  tenant_id: string;
  calendar_id: string;
  holiday_date: string;
  name: string;
  holiday_type: "PUBLIC" | "COMPANY" | "OPTIONAL" | string;
  is_optional: boolean;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface HolidayListResponseDto {
  items: HolidayDto[];
  total: number;
}

export interface HolidayCreateRequestDto {
  holiday_date: string;
  name: string;
  holiday_type?: string;
  is_optional?: boolean;
  description?: string | null;
}

export interface HolidayUpdateRequestDto {
  holiday_date?: string;
  name?: string;
  holiday_type?: string;
  is_optional?: boolean;
  description?: string | null;
}

export interface HolidayCalendarDto {
  id: string;
  tenant_id: string;
  year: number;
  name: string;
  location_id?: string | null;
  department_id?: string | null;
  is_default: boolean;
  holiday_count?: number;
  holidays?: HolidayDto[];
  created_at: string;
  updated_at: string;
}

export interface HolidayCalendarListResponseDto {
  items: HolidayCalendarDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface HolidayCalendarCreateRequestDto {
  year: number;
  name: string;
  location_id?: string | null;
  department_id?: string | null;
  is_default?: boolean;
}

export interface HolidayCalendarUpdateRequestDto {
  year?: number;
  name?: string;
  location_id?: string | null;
  department_id?: string | null;
  is_default?: boolean;
}

export interface UpcomingHolidayDto {
  id: string;
  holiday_date: string;
  name: string;
  holiday_type: string;
  is_optional: boolean;
  description?: string | null;
  calendar_id: string;
  calendar_name: string;
}

export interface UpcomingHolidaysResponseDto {
  items: UpcomingHolidayDto[];
  total: number;
  limit: number;
  offset: number;
  resolved_calendar_id?: string | null;
  resolved_calendar_name?: string | null;
  resolution_source: string;
}

export interface LeaveBalanceDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  leave_type_id: string;
  leave_type_code: string;
  leave_type_name: string;
  year: number;
  annual_allocation: number | string;
  carried_forward: number | string;
  accrued: number | string;
  used: number | string;
  pending_approval: number | string;
  available_balance: number | string;
  created_at: string;
  updated_at: string;
}

export interface LeaveBalanceListResponseDto {
  items: LeaveBalanceDto[];
  total: number;
}

export interface LeaveRequestDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name?: string | null;
  leave_type_id: string;
  leave_type_code?: string | null;
  leave_type_name?: string | null;
  start_date: string;
  end_date: string;
  is_half_day: boolean;
  half_day_period?: "FIRST_HALF" | "SECOND_HALF" | string | null;
  total_days: number | string;
  reason: string;
  document_url?: string | null;
  rejection_reason?: string | null;
  status: "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "CANCELLED" | string;
  reviewer_user_id?: string | null;
  decided_by_user_id?: string | null;
  reviewer_notes?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestListResponseDto {
  items: LeaveRequestDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeaveRequestCreateDto {
  leave_type_id: string;
  start_date: string;
  end_date: string;
  is_half_day?: boolean;
  half_day_period?: "FIRST_HALF" | "SECOND_HALF" | string | null;
  reason: string;
}

export interface LeaveRequestDecisionRequestDto {
  action: "APPROVE" | "REJECT" | string;
  reason?: string | null;
}

export interface LeaveRequestCancelRequestDto {
  reason?: string | null;
}

export interface OvertimeRuleDto {
  id: string;
  tenant_id: string;
  name: string;
  min_overtime_threshold_minutes: number;
  max_daily_overtime_minutes?: number | null;
  max_weekly_overtime_minutes?: number | null;
  workday_multiplier: number | string;
  weekend_multiplier: number | string;
  holiday_multiplier: number | string;
  requires_manager_approval: boolean;
  requires_pre_approval: boolean;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OvertimeRuleListResponseDto {
  items: OvertimeRuleDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface OvertimeRuleCreateRequestDto {
  name: string;
  min_overtime_threshold_minutes?: number;
  max_daily_overtime_minutes?: number | null;
  max_weekly_overtime_minutes?: number | null;
  workday_multiplier?: number | string;
  weekend_multiplier?: number | string;
  holiday_multiplier?: number | string;
  requires_manager_approval?: boolean;
  requires_pre_approval?: boolean;
  is_default?: boolean;
  is_active?: boolean;
}

export interface OvertimeRuleUpdateRequestDto {
  name?: string;
  min_overtime_threshold_minutes?: number;
  max_daily_overtime_minutes?: number | null;
  max_weekly_overtime_minutes?: number | null;
  workday_multiplier?: number | string;
  weekend_multiplier?: number | string;
  holiday_multiplier?: number | string;
  requires_manager_approval?: boolean;
  requires_pre_approval?: boolean;
  is_default?: boolean;
  is_active?: boolean;
}

export interface OvertimeRecordDto {
  id: string;
  tenant_id: string;
  employee_id: string;
  employee_name?: string | null;
  attendance_day_id: string;
  attendance_date: string;
  overtime_rule_id?: string | null;
  raw_overtime_minutes: number;
  approved_overtime_minutes: number;
  multiplier: number | string;
  payable_overtime_minutes: number;
  overtime_type: "WORKDAY" | "WEEK_OFF" | "HOLIDAY" | string;
  status: "AUTO_APPROVED" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | string;
  reviewer_user_id?: string | null;
  reviewer_notes?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OvertimeRecordListResponseDto {
  items: OvertimeRecordDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface OvertimeDecisionRequestDto {
  action: "APPROVE" | "REJECT" | string;
  reason?: string | null;
  approved_minutes?: number | null;
}

export const leaveApi = {
  // Leave Types
  getLeaveTypes: (
    params?: { is_active?: boolean; search?: string; limit?: number; offset?: number },
    token?: string
  ) =>
    apiFetch<LeaveTypeListResponseDto>("/leave/types", {
      token,
      params,
    }),

  createLeaveType: (data: LeaveTypeCreateRequestDto, token?: string) =>
    apiFetch<LeaveTypeDto>("/leave/types", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getLeaveType: (id: string, token?: string) =>
    apiFetch<LeaveTypeDto>(`/leave/types/${id}`, {
      token,
    }),

  updateLeaveType: (id: string, data: LeaveTypeUpdateRequestDto, token?: string) =>
    apiFetch<LeaveTypeDto>(`/leave/types/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deleteLeaveType: (id: string, token?: string) =>
    apiFetch<{ message?: string }>(`/leave/types/${id}`, {
      method: "DELETE",
      token,
    }),

  // Leave Balances & Requests
  getMyBalances: (token?: string) =>
    apiFetch<LeaveBalanceListResponseDto>("/leave/balances/my", {
      token,
    }),

  applyLeave: (data: LeaveRequestCreateDto, token?: string) =>
    apiFetch<LeaveRequestDto>("/leave/requests", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getMyLeaveRequests: (
    params?: {
      status?: string;
      leave_type_id?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<LeaveRequestListResponseDto>("/leave/requests/my", {
      token,
      params,
    }),

  getSupervisorQueue: (
    params?: {
      status?: string;
      employee_id?: string;
      leave_type_id?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<LeaveRequestListResponseDto>("/leave/requests", {
      token,
      params,
    }),

  getLeaveRequestDetail: (id: string, token?: string) =>
    apiFetch<LeaveRequestDto>(`/leave/requests/${id}`, {
      token,
    }),

  adjudicateLeaveRequest: (id: string, data: LeaveRequestDecisionRequestDto, token?: string) =>
    apiFetch<LeaveRequestDto>(`/leave/requests/${id}/decision`, {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  cancelLeaveRequest: (id: string, data?: LeaveRequestCancelRequestDto, token?: string) =>
    apiFetch<LeaveRequestDto>(`/leave/requests/${id}/cancel`, {
      method: "POST",
      body: data ? JSON.stringify(data) : JSON.stringify({}),
      token,
    }),
};

export const holidayApi = {
  getCalendars: (
    params?: {
      year?: number;
      location_id?: string;
      department_id?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<HolidayCalendarListResponseDto>("/holidays/calendars", {
      token,
      params,
    }),

  createCalendar: (data: HolidayCalendarCreateRequestDto, token?: string) =>
    apiFetch<HolidayCalendarDto>("/holidays/calendars", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getCalendar: (id: string, token?: string) =>
    apiFetch<HolidayCalendarDto>(`/holidays/calendars/${id}`, {
      token,
    }),

  updateCalendar: (id: string, data: HolidayCalendarUpdateRequestDto, token?: string) =>
    apiFetch<HolidayCalendarDto>(`/holidays/calendars/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deleteCalendar: (id: string, token?: string) =>
    apiFetch<{ message?: string }>(`/holidays/calendars/${id}`, {
      method: "DELETE",
      token,
    }),

  getHolidayEntries: (
    calendarId: string,
    params?: {
      holiday_type?: string;
      is_optional?: boolean;
      start_date?: string;
      end_date?: string;
    },
    token?: string
  ) =>
    apiFetch<HolidayListResponseDto>(`/holidays/calendars/${calendarId}/entries`, {
      token,
      params,
    }),

  createHolidayEntry: (calendarId: string, data: HolidayCreateRequestDto, token?: string) =>
    apiFetch<HolidayDto>(`/holidays/calendars/${calendarId}/entries`, {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateHolidayEntry: (
    calendarId: string,
    holidayId: string,
    data: HolidayUpdateRequestDto,
    token?: string
  ) =>
    apiFetch<HolidayDto>(`/holidays/calendars/${calendarId}/entries/${holidayId}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deleteHolidayEntry: (calendarId: string, holidayId: string, token?: string) =>
    apiFetch<{ message?: string }>(`/holidays/calendars/${calendarId}/entries/${holidayId}`, {
      method: "DELETE",
      token,
    }),

  getUpcomingHolidays: (
    params?: { limit?: number; offset?: number; year?: number },
    token?: string
  ) =>
    apiFetch<UpcomingHolidaysResponseDto>("/holidays/upcoming", {
      token,
      params,
    }),
};

export const overtimeApi = {
  getRules: (
    params?: { is_active?: boolean; limit?: number; offset?: number },
    token?: string
  ) =>
    apiFetch<OvertimeRuleListResponseDto>("/overtime/rules", {
      token,
      params,
    }),

  createRule: (data: OvertimeRuleCreateRequestDto, token?: string) =>
    apiFetch<OvertimeRuleDto>("/overtime/rules", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  getRule: (id: string, token?: string) =>
    apiFetch<OvertimeRuleDto>(`/overtime/rules/${id}`, {
      token,
    }),

  updateRule: (id: string, data: OvertimeRuleUpdateRequestDto, token?: string) =>
    apiFetch<OvertimeRuleDto>(`/overtime/rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  deleteRule: (id: string, token?: string) =>
    apiFetch<{ message?: string }>(`/overtime/rules/${id}`, {
      method: "DELETE",
      token,
    }),

  getRecords: (
    params?: {
      status?: string;
      employee_id?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<OvertimeRecordListResponseDto>("/overtime/records", {
      token,
      params,
    }),

  getMyRecords: (
    params?: {
      status?: string;
      start_date?: string;
      end_date?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<OvertimeRecordListResponseDto>("/overtime/records/my", {
      token,
      params,
    }),

  getRecordDetail: (id: string, token?: string) =>
    apiFetch<OvertimeRecordDto>(`/overtime/records/${id}`, {
      token,
    }),

  adjudicateRecord: (id: string, data: OvertimeDecisionRequestDto, token?: string) =>
    apiFetch<OvertimeRecordDto>(`/overtime/records/${id}/decision`, {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),
};

// =============================================================================
// Phase 10: Notification Administration DTOs & Endpoints (Milestone 10.5)
// =============================================================================

export interface NotificationDto {
  id: string;
  tenant_id: string;
  recipient_user_id?: string | null;
  recipient_employee_id?: string | null;
  event_type: string;
  channel: string;
  template_key?: string | null;
  recipient_destination: string;
  subject?: string | null;
  body: string;
  payload_json?: Record<string, unknown> | null;
  status: string;
  priority: string;
  scheduled_for: string;
  attempt_count: number;
  max_attempts: number;
  next_retry_at?: string | null;
  provider_name?: string | null;
  provider_message_id?: string | null;
  error_message?: string | null;
  idempotency_key?: string | null;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  failed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationOverviewDto {
  total_count: number;
  status_counts: Record<string, number>;
  channel_counts: Record<string, number>;
  recent_notifications: NotificationDto[];
  delivery_distinction_note: string;
}

export interface NotificationTemplateDto {
  id: string;
  tenant_id?: string | null;
  template_key: string;
  name: string;
  description?: string | null;
  event_type: string;
  channel: string;
  subject_template?: string | null;
  body_template: string;
  locale: string;
  is_active: boolean;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateCreateRequestDto {
  template_key: string;
  name: string;
  description?: string | null;
  event_type: string;
  channel: "PUSH" | "EMAIL" | "SMS";
  subject_template?: string | null;
  body_template: string;
  locale?: string;
  is_active?: boolean;
}

export interface TemplateUpdateRequestDto {
  name?: string;
  description?: string | null;
  subject_template?: string | null;
  body_template?: string;
  is_active?: boolean;
}

export interface NotificationPreferenceDto {
  id: string;
  tenant_id: string;
  user_id?: string | null;
  is_push_enabled: boolean;
  is_email_enabled: boolean;
  is_sms_enabled: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  timezone: string;
  category_preferences?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface PreferenceUpdateRequestDto {
  is_push_enabled?: boolean;
  is_email_enabled?: boolean;
  is_sms_enabled?: boolean;
  quiet_hours_enabled?: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  timezone?: string;
  category_preferences?: Record<string, unknown> | null;
}

export interface ChannelConfigItemDto {
  channel: "PUSH" | "EMAIL" | "SMS";
  is_enabled: boolean;
  provider_name: string;
  status: "CONFIGURED_UNVERIFIED" | "MOCK" | "UNCONFIGURED";
  description: string;
  details?: Record<string, unknown>;
}

export interface ChannelListResponseDto {
  channels: ChannelConfigItemDto[];
}

export interface NotificationActivityListDto {
  items: NotificationDto[];
  total: number;
  offset: number;
  limit: number;
}

export const notificationApi = {
  getOverview: (token?: string) =>
    apiFetch<NotificationOverviewDto>("/notifications/overview", {
      token,
    }),

  getTemplates: (token?: string) =>
    apiFetch<NotificationTemplateDto[]>("/notifications/templates", {
      token,
    }),

  createOrUpdateTemplate: (data: TemplateCreateRequestDto, token?: string) =>
    apiFetch<NotificationTemplateDto>("/notifications/templates", {
      method: "POST",
      body: JSON.stringify(data),
      token,
    }),

  updateTemplate: (templateId: string, data: TemplateUpdateRequestDto, token?: string) =>
    apiFetch<NotificationTemplateDto>(`/notifications/templates/${templateId}`, {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  getPreferences: (token?: string) =>
    apiFetch<NotificationPreferenceDto>("/notifications/preferences", {
      token,
    }),

  updatePreferences: (data: PreferenceUpdateRequestDto, token?: string) =>
    apiFetch<NotificationPreferenceDto>("/notifications/preferences", {
      method: "PUT",
      body: JSON.stringify(data),
      token,
    }),

  getChannels: (token?: string) =>
    apiFetch<ChannelListResponseDto>("/notifications/channels", {
      token,
    }),

  getActivity: (
    params?: {
      status?: string;
      channel?: string;
      event_type?: string;
      limit?: number;
      offset?: number;
    },
    token?: string
  ) =>
    apiFetch<NotificationActivityListDto>("/notifications/activity", {
      token,
      params,
    }),
};


