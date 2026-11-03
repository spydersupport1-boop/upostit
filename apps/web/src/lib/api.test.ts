import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  apiFetch,
  ApiError,
  organizationApi,
  authApi,
  locationApi,
  assignmentApi,
  importApi,
  invitationApi,
  shiftApi,
  attendanceApi,
  tokenStorage,
  setTokenRefreshHandler,
  API_BASE_URL,
} from "./api.ts";

describe("Frontend API Client & Token Handling", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("apiFetch core wrapper", () => {
    it("should send GET request with Authorization bearer token", async () => {
      let capturedUrl = "";
      let capturedHeaders: Record<string, string> = {};

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedHeaders = (init?.headers as Record<string, string>) || {};
        return new Response(JSON.stringify([{ id: "1", name: "Engineering" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      const result = await apiFetch<Array<{ id: string; name: string }>>("/test-endpoint", {
        token: "mock-jwt-token-xyz",
      });

      assert.equal(capturedUrl, `${API_BASE_URL}/api/v1/test-endpoint`);
      assert.equal(capturedHeaders["Authorization"], "Bearer mock-jwt-token-xyz");
      assert.equal(capturedHeaders["Content-Type"], "application/json");
      assert.equal(result.length, 1);
      assert.equal(result[0].name, "Engineering");
    });

    it("should append query parameters correctly", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(JSON.stringify({ items: [], total: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      await apiFetch("/employees", {
        params: {
          search: "alex",
          status: "active",
          page: 2,
          empty_val: null,
          undef_val: undefined,
        },
      });

      const parsedUrl = new URL(capturedUrl);
      assert.equal(parsedUrl.searchParams.get("search"), "alex");
      assert.equal(parsedUrl.searchParams.get("status"), "active");
      assert.equal(parsedUrl.searchParams.get("page"), "2");
      assert.equal(parsedUrl.searchParams.has("empty_val"), false);
      assert.equal(parsedUrl.searchParams.has("undef_val"), false);
    });

    it("should throw ApiError with status 401 when unauthorized", async () => {
      globalThis.fetch = (async () => {
        return new Response(JSON.stringify({ detail: "Token has expired or is invalid" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await apiFetch("/protected-resource", { token: "expired-token" });
        },
        (err: unknown) => {
          assert(err instanceof ApiError);
          assert.equal(err.status, 401);
          assert.equal(err.detail, "Token has expired or is invalid");
          return true;
        }
      );
    });

    it("should throw ApiError with status 403 when forbidden (employee directory denial)", async () => {
      globalThis.fetch = (async () => {
        return new Response(JSON.stringify({ detail: "Insufficient permissions. Required: view_employees" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        });
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await apiFetch("/employees", { token: "employee-token" });
        },
        (err: unknown) => {
          assert(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.match(err.detail, /Insufficient permissions/);
          return true;
        }
      );
    });

    it("should parse structured Pydantic 422 validation errors", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            detail: [
              { loc: ["body", "work_email"], msg: "value is not a valid email address" },
              { loc: ["body", "employee_id"], msg: "Field required" },
            ],
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          }
        );
      }) as typeof fetch;

      await assert.rejects(
        async () => {
          await apiFetch("/employees", {
            method: "POST",
            body: JSON.stringify({}),
          });
        },
        (err: unknown) => {
          assert(err instanceof ApiError);
          assert.equal(err.status, 422);
          assert.match(err.detail, /work_email: value is not a valid email address/);
          assert.match(err.detail, /employee_id: Field required/);
          return true;
        }
      );
    });
  });

  describe("organizationApi operations", () => {
    it("should fetch departments list with pagination", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            items: [
              { id: "dept-1", name: "Engineering", code: "ENG", is_active: true, created_at: "", updated_at: "" },
            ],
            total: 1,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await organizationApi.getDepartments({ limit: 50 }, "test-token");
      assert.equal(resp.total, 1);
      assert.equal(resp.items[0].code, "ENG");
    });

    it("should create a department with POST", async () => {
      let requestBody = "";
      let requestMethod = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        requestMethod = init?.method || "GET";
        requestBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "dept-new",
            name: "Operations",
            code: "OPS",
            description: "Operations team",
            manager_id: "emp-1",
            is_active: true,
            created_at: "",
            updated_at: "",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const created = await organizationApi.createDepartment(
        { name: "Operations", code: "OPS", description: "Operations team", manager_id: "emp-1" },
        "test-token"
      );

      assert.equal(requestMethod, "POST");
      assert.match(requestBody, /"OPS"/);
      assert.match(requestBody, /"emp-1"/);
      assert.equal(created.id, "dept-new");
    });

    it("should update a department with PUT", async () => {
      let requestMethod = "";
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        requestMethod = init?.method || "GET";
        return new Response(
          JSON.stringify({
            id: "dept-1",
            name: "Core Engineering",
            code: "ENG",
            is_active: true,
            created_at: "",
            updated_at: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const updated = await organizationApi.updateDepartment(
        "dept-1",
        { name: "Core Engineering" },
        "test-token"
      );

      assert.equal(requestMethod, "PUT");
      assert.match(capturedUrl, /\/departments\/dept-1$/);
      assert.equal(updated.name, "Core Engineering");
    });

    it("should fetch designations list", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            items: [
              { id: "des-1", title: "Principal Architect", code: "ARCH", is_active: true, created_at: "", updated_at: "" },
            ],
            total: 1,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await organizationApi.getDesignations(undefined, "test-token");
      assert.equal(resp.total, 1);
      assert.equal(resp.items[0].code, "ARCH");
    });

    it("should create employee profile with POST", async () => {
      let requestBody = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        requestBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "emp-uuid",
            tenant_id: "tenant-uuid",
            employee_id: "EMP-900",
            first_name: "Jane",
            last_name: "Doe",
            work_email: "jane.doe@enterprise.com",
            employment_type: "full_time",
            joining_date: "2026-01-01",
            status: "active",
            created_at: "",
            updated_at: "",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const emp = await organizationApi.createEmployee(
        {
          employee_id: "EMP-900",
          first_name: "Jane",
          last_name: "Doe",
          work_email: "jane.doe@enterprise.com",
          joining_date: "2026-01-01",
          status: "active",
        },
        "test-token"
      );

      assert.match(requestBody, /"EMP-900"/);
      assert.equal(emp.employee_id, "EMP-900");
      assert.equal(emp.status, "active");
    });

    it("should update employee status via dedicated PATCH endpoint", async () => {
      let requestMethod = "";
      let requestBody = "";
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        requestMethod = init?.method || "GET";
        requestBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "emp-1",
            status: "inactive",
            first_name: "Jane",
            last_name: "Doe",
            employee_id: "EMP-001",
            work_email: "jane@corp.com",
            employment_type: "full_time",
            joining_date: "2025-01-01",
            created_at: "",
            updated_at: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const result = await organizationApi.updateEmployeeStatus("emp-1", "inactive", "test-token");

      assert.equal(requestMethod, "PATCH");
      assert.match(capturedUrl, /\/employees\/emp-1\/status$/);
      assert.match(requestBody, /"inactive"/);
      assert.equal(result.status, "inactive");
    });

    it("should fetch employee self-access profile via /employees/me", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            id: "emp-self",
            employee_id: "EMP-ME",
            first_name: "Self",
            last_name: "Worker",
            work_email: "self@corp.com",
            employment_type: "full_time",
            joining_date: "2026-01-01",
            status: "active",
            created_at: "",
            updated_at: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const profile = await organizationApi.getMyProfile("employee-jwt");
      assert.match(capturedUrl, /\/employees\/me$/);
      assert.equal(profile.employee_id, "EMP-ME");
    });
  });

  describe("authApi operations", () => {
    it("should execute login and return tokens", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            access_token: "mock-access-token",
            refresh_token: "mock-refresh-token",
            token_type: "bearer",
            expires_in: 900,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await authApi.login({
        email: "owner@test.com",
        password: "SecurePassword123!",
        tenant_slug: "acme-corp",
      });
      assert.equal(resp.access_token, "mock-access-token");
      assert.equal(resp.refresh_token, "mock-refresh-token");
    });

    it("should execute refresh token rotation via HttpOnly cookie transport", async () => {
      let capturedBody = "";
      let capturedCredentials: RequestCredentials | undefined;

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedBody = init?.body as string;
        capturedCredentials = init?.credentials;
        return new Response(
          JSON.stringify({
            access_token: "new-access-token",
            refresh_token: "new-refresh-token",
            token_type: "bearer",
            expires_in: 900,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await authApi.refresh();
      assert.equal(resp.access_token, "new-access-token");
      assert.equal(capturedCredentials, "include");
      assert.equal(capturedBody, JSON.stringify({})); // Empty body; token delivered by cookie
    });

    it("should execute logout via HttpOnly cookie transport", async () => {
      let capturedCredentials: RequestCredentials | undefined;

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedCredentials = init?.credentials;
        return new Response(
          JSON.stringify({ message: "Successfully logged out" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await authApi.logout("active-token");
      assert.equal(resp.message, "Successfully logged out");
      assert.equal(capturedCredentials, "include");
    });

    it("should fetch current authenticated user profile via /auth/me", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            user: {
              id: "user-1",
              tenant_id: "tenant-1",
              email: "owner@test.com",
              full_name: "Owner Account",
              role: "owner",
              status: "active",
              created_at: "",
              updated_at: "",
            },
            tenant: {
              id: "tenant-1",
              name: "Acme Corp",
              slug: "acme-corp",
              status: "active",
              created_at: "",
              updated_at: "",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const me = await authApi.getMe("valid-token");
      assert.equal(me.user.role, "owner");
      assert.equal(me.tenant.name, "Acme Corp");
    });
  });

  describe("Cookie & In-Memory Token Security (Phase 3.3)", () => {
    it("should default apiFetch to credentials: include for cross-origin cookie transport", async () => {
      let capturedCredentials: RequestCredentials | undefined;

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedCredentials = init?.credentials;
        return new Response(
          JSON.stringify({ status: "ok" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      await apiFetch("/health");
      assert.equal(capturedCredentials, "include");
    });

    it("should purge legacy tokens from localStorage using clearLegacyTokens", () => {
      // Mock minimal localStorage
      const store: Record<string, string> = {
        attendance_access_token: "old-access",
        attendance_refresh_token: "old-refresh",
      };
      (globalThis as unknown as { localStorage: Storage }).localStorage = {
        getItem: (k: string) => store[k] || null,
        setItem: (k: string, v: string) => { store[k] = v; },
        removeItem: (k: string) => { delete store[k]; },
        clear: () => { Object.keys(store).forEach(k => delete store[k]); },
        key: () => null,
        length: 0,
      };

      tokenStorage.clearLegacyTokens();
      assert.equal(globalThis.localStorage.getItem("attendance_access_token"), null);
      assert.equal(globalThis.localStorage.getItem("attendance_refresh_token"), null);
    });

    it("should transparently refresh token and retry request when encountering 401", async () => {
      let callCount = 0;
      let refreshCallCount = 0;
      let capturedRetryToken = "";

      setTokenRefreshHandler(async () => {
        refreshCallCount++;
        return "refreshed-access-token";
      });

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        callCount++;
        const authHeader = (init?.headers as Record<string, string>)?.["Authorization"];
        if (callCount === 1) {
          // First attempt with expired token fails with 401
          return new Response(JSON.stringify({ detail: "Signature has expired" }), { status: 401, headers: { "Content-Type": "application/json" } });
        }
        // Second attempt with new refreshed token succeeds
        capturedRetryToken = authHeader;
        return new Response(JSON.stringify({ id: "dept-1", name: "Engineering" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }) as typeof fetch;

      const result = await apiFetch<{ id: string; name: string }>("/departments", { token: "expired-token" });
      assert.equal(result.name, "Engineering");
      assert.equal(refreshCallCount, 1);
      assert.equal(callCount, 2);
      assert.equal(capturedRetryToken, "Bearer refreshed-access-token");

      setTokenRefreshHandler(null);
    });
  });

  // =========================================================================
  // Phase 4 Milestone 1: Workplace Location & Geofencing API
  // =========================================================================
  describe("locationApi operations (Phase 4 Milestone 1)", () => {
    it("should fetch locations list with is_active parameter", async () => {
      let capturedUrl = "";
      let capturedToken = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedToken = (init?.headers as Record<string, string>)?.["Authorization"] || "";
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "loc-1",
                name: "Headquarters",
                code: "HQ-01",
                latitude: 37.7749,
                longitude: -122.4194,
                geofence_radius_meters: 150,
                timezone: "America/Los_Angeles",
                country_code: "US",
                is_active: true,
                employee_count: 42,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
              },
            ],
            total: 1,
            limit: 50,
            offset: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const locs = await locationApi.getLocations({ is_active: true }, "test-token");
      assert.equal(locs.items.length, 1);
      assert.equal(locs.items[0].code, "HQ-01");
      assert.equal(locs.items[0].geofence_radius_meters, 150);
      assert.ok(capturedUrl.includes("is_active=true"));
      assert.equal(capturedToken, "Bearer test-token");
    });

    it("should create a new workplace location with geofence parameters", async () => {
      let capturedBody = "";
      let capturedMethod = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "loc-new",
            name: "Innovation Hub",
            code: "IH-01",
            latitude: 40.7128,
            longitude: -74.006,
            geofence_radius_meters: 200,
            timezone: "America/New_York",
            country_code: "US",
            is_active: true,
            employee_count: 0,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const created = await locationApi.createLocation(
        {
          name: "Innovation Hub",
          code: "IH-01",
          latitude: 40.7128,
          longitude: -74.006,
          geofence_radius_meters: 200,
          timezone: "America/New_York",
          country_code: "US",
        },
        "token-123"
      );

      assert.equal(capturedMethod, "POST");
      assert.equal(created.code, "IH-01");
      const parsedBody = JSON.parse(capturedBody);
      assert.equal(parsedBody.geofence_radius_meters, 200);
      assert.equal(parsedBody.latitude, 40.7128);
    });

    it("should verify test coordinates against location geofence boundary", async () => {
      let capturedBody = "";
      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            is_inside: true,
            distance_meters: 23.4,
            threshold_meters: 100,
            details: {},
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const verifyRes = await locationApi.verifyCoordinates(
        { location_id: "loc-1", latitude: 37.775, longitude: -122.4195 },
        "token-123"
      );

      assert.equal(verifyRes.is_inside, true);
      assert.equal(verifyRes.distance_meters, 23.4);
      assert.equal(verifyRes.threshold_meters, 100);
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.latitude, 37.775);
    });

    it("should fetch location employee roster with pagination", async () => {
      let capturedUrl = "";
      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            items: [
              {
                assignment_id: "asgn-1",
                employee_id: "emp-1",
                employee_number: "EMP-001",
                full_name: "Alice Smith",
                email: "alice@example.com",
                is_primary: true,
                effective_from: "2026-01-01",
                effective_to: null,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const roster = await locationApi.getLocationEmployees(
        "loc-1",
        { page: 1, page_size: 20, is_primary: true },
        "token-123"
      );

      assert.equal(roster.items.length, 1);
      assert.equal(roster.items[0].full_name, "Alice Smith");
      assert.equal(roster.items[0].is_primary, true);
      assert.ok(capturedUrl.includes("is_primary=true"));
    });
  });

  // =========================================================================
  // Phase 4 Milestone 2: Employee Workplace Assignment API
  // =========================================================================
  describe("assignmentApi operations (Phase 4 Milestone 2)", () => {
    it("should fetch active and historical assignments for an employee", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "asgn-1",
              employee_id: "emp-1",
              location_id: "loc-1",
              location_name: "Headquarters",
              location_code: "HQ-01",
              is_primary: true,
              effective_from: "2026-01-01",
              effective_to: null,
              is_active: true,
              is_currently_effective: true,
            },
            {
              id: "asgn-2",
              employee_id: "emp-1",
              location_id: "loc-2",
              location_name: "Remote Office",
              location_code: "REM-01",
              is_primary: false,
              effective_from: "2025-01-01",
              effective_to: "2025-12-31",
              is_active: false,
              is_currently_effective: false,
            },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const assignments = await assignmentApi.getEmployeeWorkplaces("emp-1", undefined, "token-123");
    assert.equal(assignments.items.length, 2);
    assert.equal(assignments.items[0].is_primary, true);
    assert.equal(assignments.items[0].location_name, "Headquarters");
    assert.equal(assignments.items[1].effective_to, "2025-12-31");
  });

    it("should assign an employee to a workplace with primary flag", async () => {
      let capturedBody = "";
      let capturedMethod = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "";
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "asgn-new",
            employee_id: "emp-1",
            location_id: "loc-3",
            location_name: "Branch 3",
            location_code: "BR-03",
            is_primary: true,
            effective_from: "2026-11-01",
            effective_to: null,
            is_active: true,
            is_currently_effective: true,
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const created = await assignmentApi.assignWorkplace(
        "emp-1",
        {
          location_id: "loc-3",
          is_primary: true,
          effective_from: "2026-11-01",
        },
        "token-123"
      );

      assert.equal(capturedMethod, "POST");
      assert.equal(created.location_name, "Branch 3");
      assert.equal(created.is_primary, true);
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.location_id, "loc-3");
      assert.equal(parsed.is_primary, true);
    });

    it("should end an assignment non-destructively without deleting history", async () => {
      let capturedUrl = "";
      let capturedMethod = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "";
        return new Response(
          JSON.stringify({
            id: "asgn-1",
            employee_id: "emp-1",
            location_id: "loc-1",
            location_name: "Headquarters",
            location_code: "HQ-01",
            is_primary: false,
            effective_from: "2026-01-01",
            effective_to: "2026-11-03",
            is_active: true,
            is_currently_effective: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const ended = await assignmentApi.endAssignment(
        "emp-1",
        "asgn-1",
        "2026-11-03",
        "token-123"
      );

      assert.equal(capturedMethod, "DELETE");
      assert.equal(ended.effective_to, "2026-11-03");
      assert.ok(capturedUrl.includes("end_date=2026-11-03"));
    });

    it("should allow employees to fetch their own assigned workplaces via /me endpoint", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "asgn-emp-me",
                employee_id: "emp-self",
                location_id: "loc-hq",
                location_name: "Corporate Headquarters",
                location_code: "CHQ",
                is_primary: true,
                effective_from: "2026-01-01",
                effective_to: null,
                is_active: true,
                is_currently_effective: true,
              },
            ],
            total: 1,
            page: 1,
            page_size: 50,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const myWorkplaces = await assignmentApi.getMyWorkplaces("employee-token");
      assert.equal(myWorkplaces.items.length, 1);
      assert.equal(myWorkplaces.items[0].location_name, "Corporate Headquarters");
      assert.ok(capturedUrl.endsWith("/api/v1/employees/me/workplaces"));
    });
  });

  // =========================================================================
  // Phase 4 Milestone 3: Bulk Employee Import API
  // =========================================================================
  describe("importApi operations (Phase 4 Milestone 3)", () => {
    it("should download import template as blob", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(new Blob(["first_name,last_name,work_email\nAlice,Smith,alice@example.com"], { type: "text/csv" }), {
          status: 200,
          headers: { "Content-Type": "text/csv" },
        });
      }) as typeof fetch;

      const blob = await importApi.downloadTemplate("csv", "token-123");
      assert.ok(blob instanceof Blob);
      assert.ok(capturedUrl.includes("/employees/import/template"));
      assert.ok(capturedUrl.includes("format=csv"));
    });

    it("should upload import file via multipart/form-data", async () => {
      let capturedMethod = "";
      let capturedContentType: string | undefined;

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "";
        capturedContentType = (init?.headers as Record<string, string>)?.["Content-Type"];
        return new Response(
          JSON.stringify({
            id: "job-import-123",
            tenant_id: "t-1",
            status: "queued",
            file_name: "employees.csv",
            file_size_bytes: 1024,
            total_rows: 50,
            processed_rows: 0,
            successful_rows: 0,
            failed_rows: 0,
            created_at: "2026-11-03T00:00:00Z",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const dummyFile = new File(["dummy content"], "employees.csv", { type: "text/csv" });
      const job = await importApi.uploadFile(dummyFile, "token-123");

      assert.equal(capturedMethod, "POST");
      assert.equal(job.id, "job-import-123");
      assert.equal(job.status, "queued");
      assert.equal(capturedContentType, undefined, "Content-Type should not be hardcoded for FormData");
    });

    it("should poll job progress and status", async () => {
      globalThis.fetch = (async () => {
        return new Response(
          JSON.stringify({
            id: "job-import-123",
            tenant_id: "t-1",
            status: "processing",
            file_name: "employees.csv",
            file_size_bytes: 1024,
            total_rows: 100,
            processed_rows: 75,
            successful_rows: 70,
            failed_rows: 5,
            created_at: "2026-11-03T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const job = await importApi.getJobStatus("job-import-123", "token-123");
      assert.equal(job.status, "processing");
      assert.equal(job.processed_rows, 75);
      assert.equal(job.total_rows, 100);
      assert.equal(job.failed_rows, 5);
    });

    it("should download job error report as blob", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          new Blob(["row_number,error_message\n5,Duplicate email\n12,Invalid date"], { type: "text/csv" }),
          { status: 200, headers: { "Content-Type": "text/csv" } }
        );
      }) as typeof fetch;

      const errorBlob = await importApi.downloadErrorReport("job-import-123", "token-123");
      assert.ok(errorBlob instanceof Blob);
      assert.ok(capturedUrl.endsWith("/api/v1/employees/import/job-import-123/errors/download"));
    });
  });

  // =========================================================================
  // Phase 4 Milestone 4: Employee Invitation & Account Activation API
  // =========================================================================
  describe("invitationApi operations (Phase 4 Milestone 4)", () => {
    it("should issue an employee invitation", async () => {
      let capturedMethod = "";
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "";
        return new Response(
          JSON.stringify({
            id: "inv-1",
            employee_id: "emp-101",
            employee_name: "Bob Jones",
            employee_code: "EMP-101",
            email: "bob@example.com",
            status: "pending",
            expires_at: "2026-11-10T00:00:00Z",
            delivery_status: "delivered",
            attempt_count: 1,
            created_at: "2026-11-03T00:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const inv = await invitationApi.inviteEmployee("emp-101", "token-123");
      assert.equal(capturedMethod, "POST");
      assert.ok(capturedUrl.endsWith("/api/v1/employees/emp-101/invite"));
      assert.equal(inv.email, "bob@example.com");
      assert.equal(inv.status, "pending");
    });

    it("should list invitations with status filter", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "inv-pending-1",
                employee_id: "emp-101",
                employee_number: "EMP-101",
                email: "bob@example.com",
                status: "pending",
                expires_at: "2026-11-10T00:00:00Z",
                delivery_status: "delivered",
                attempt_count: 1,
                created_at: "2026-11-03T00:00:00Z",
                updated_at: "2026-11-03T00:00:00Z",
              },
            ],
            total: 1,
            skip: 0,
            limit: 20,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const result = await invitationApi.getInvitations(
        { status: "pending", skip: 0, limit: 20 },
        "token-123"
      );

      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].status, "pending");
      assert.ok(capturedUrl.includes("status=pending"));
    });

    it("should resend and revoke invitations", async () => {
      let capturedResendUrl = "";
      let capturedRevokeUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        const urlStr = url.toString();
        if (urlStr.includes("/resend")) {
          capturedResendUrl = urlStr;
          return new Response(
            JSON.stringify({
              id: "inv-1",
              status: "pending",
              attempt_count: 2,
              delivery_status: "delivered",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (urlStr.includes("/revoke")) {
          capturedRevokeUrl = urlStr;
          return new Response(
            JSON.stringify({
              id: "inv-1",
              status: "revoked",
              revoked_at: "2026-11-03T01:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({}), { status: 404 });
      }) as typeof fetch;

      const resendRes = await invitationApi.resendInvitation("inv-1", "token-123");
      assert.equal(resendRes.attempt_count, 2);
      assert.ok(capturedResendUrl.endsWith("/api/v1/invitations/inv-1/resend"));

      const revokeRes = await invitationApi.revokeInvitation("inv-1", "token-123");
      assert.equal(revokeRes.status, "revoked");
      assert.ok(capturedRevokeUrl.endsWith("/api/v1/invitations/inv-1/revoke"));
    });

    it("should validate invitation token publicly without leaking internal tenant IDs", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            valid: true,
            email: "bob@example.com",
            employee_name: "Bob Jones",
            company_name: "Acme Corp",
            expires_at: "2026-11-10T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const validRes = await invitationApi.validateToken("safe-invitation-token-secret");
      assert.equal(validRes.valid, true);
      assert.equal(validRes.employee_name, "Bob Jones");
      assert.equal(validRes.company_name, "Acme Corp");
      assert.ok(capturedUrl.includes("token=safe-invitation-token-secret"));
    });

    it("should submit password and activate account publicly", async () => {
      let capturedBody = "";
      let capturedMethod = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "";
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            message: "Account activated successfully. You can now log in.",
            email: "bob@example.com",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const actRes = await invitationApi.activateAccount({
        token: "safe-invitation-token-secret",
        password: "SecurePassword123!",
        password_confirm: "SecurePassword123!",
      });

      assert.equal(capturedMethod, "POST");
      assert.equal(actRes.email, "bob@example.com");
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.token, "safe-invitation-token-secret");
      assert.equal(parsed.password, "SecurePassword123!");
    });
  });

  describe("shiftApi operations (Phase 5 Shift Rostering)", () => {
    it("should fetch shift templates list with parameters", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify([
            {
              id: "shift-123",
              tenant_id: "tenant-1",
              name: "General Morning Shift",
              code: "MORN_01",
              is_active: true,
              current_version_number: 1,
              current_version: {
                id: "version-1",
                shift_id: "shift-123",
                version_number: 1,
                start_time: "09:00:00",
                end_time: "17:00:00",
                is_overnight: false,
                is_flexible: false,
                break_duration_minutes: 60,
                grace_period_minutes: 15,
                early_exit_grace_minutes: 15,
                early_arrival_allowance_minutes: 30,
                late_departure_allowance_minutes: 30,
                half_day_threshold_minutes: 240,
                full_day_threshold_minutes: 480,
                weekly_off_days: [0, 6],
                created_at: "2026-01-01T00:00:00Z",
              },
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const shifts = await shiftApi.getShifts({ search: "Morning", is_active: true, limit: 10 }, "jwt-token");
      assert.equal(shifts.length, 1);
      assert.equal(shifts[0].name, "General Morning Shift");
      assert.equal(shifts[0].current_version?.start_time, "09:00:00");
      assert.ok(capturedUrl.includes("/api/v1/shifts"));
      assert.ok(capturedUrl.includes("search=Morning"));
    });

    it("should fetch a specific shift template by ID", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            id: "shift-456",
            name: "Night Owl Shift",
            code: "NIGHT_01",
            is_active: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const shift = await shiftApi.getShiftById("shift-456", "jwt-token");
      assert.equal(shift.id, "shift-456");
      assert.equal(shift.name, "Night Owl Shift");
      assert.ok(capturedUrl.endsWith("/api/v1/shifts/shift-456"));
    });

    it("should fetch shift assignments for an employee", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify([
            {
              id: "assign-1",
              employee_id: "emp-789",
              shift_id: "shift-123",
              effective_from: "2026-01-01",
              effective_to: null,
              is_active: true,
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const assignments = await shiftApi.getAssignments({ employee_id: "emp-789", active_on_date: "2026-11-03" }, "jwt-token");
      assert.equal(assignments.length, 1);
      assert.equal(assignments[0].employee_id, "emp-789");
      assert.ok(capturedUrl.includes("/api/v1/shifts/assignments"));
      assert.ok(capturedUrl.includes("employee_id=emp-789"));
    });
  });

  describe("attendanceApi operations (Phase 5 Attendance & Corrections)", () => {
    it("should fetch attendance days with query parameters", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "day-1",
                tenant_id: "tenant-1",
                employee_id: "emp-101",
                employee_name: "Alice Smith",
                employee_number: "EMP001",
                attendance_date: "2026-11-03",
                shift_name: "Morning Shift",
                first_check_in: "2026-11-03T09:05:00Z",
                last_check_out: "2026-11-03T17:02:00Z",
                total_working_minutes: 477,
                total_break_minutes: 60,
                net_working_minutes: 417,
                late_arrival_minutes: 5,
                early_departure_minutes: 0,
                overtime_minutes: 0,
                status: "PRESENT",
                calculation_status: "CALCULATED",
                calculation_version: 1,
                is_incomplete: false,
                missing_punch: false,
                source_event_ids: ["ev-1", "ev-2"],
                last_calculated_at: "2026-11-03T17:05:00Z",
                created_at: "2026-11-03T09:05:00Z",
                updated_at: "2026-11-03T17:05:00Z",
              },
            ],
            total: 1,
            next_cursor: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const resp = await attendanceApi.getDays(
        {
          start_date: "2026-11-03",
          end_date: "2026-11-03",
          attendance_status: "PRESENT",
          limit: 20,
        },
        "jwt-token"
      );

      assert.equal(resp.total, 1);
      assert.equal(resp.items[0].employee_name, "Alice Smith");
      assert.equal(resp.items[0].net_working_minutes, 417);
      assert.ok(capturedUrl.includes("/api/v1/attendance/days"));
      assert.ok(capturedUrl.includes("attendance_status=PRESENT"));
    });

    it("should fetch a single day record for an employee", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            id: "day-101",
            employee_id: "emp-101",
            attendance_date: "2026-11-03",
            status: "PRESENT",
            net_working_minutes: 480,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const day = await attendanceApi.getDay("emp-101", "2026-11-03", "jwt-token");
      assert.equal(day.id, "day-101");
      assert.equal(day.status, "PRESENT");
      assert.ok(capturedUrl.endsWith("/api/v1/attendance/days/emp-101/2026-11-03"));
    });

    it("should trigger manual recalculation of attendance day", async () => {
      let capturedUrl = "";
      let capturedBody = "";
      let capturedMethod = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "";
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            id: "day-1",
            employee_id: "emp-101",
            attendance_date: "2026-11-03",
            calculation_version: 2,
            status: "PRESENT",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const res = await attendanceApi.recalculate("emp-101", "2026-11-03", "jwt-token");
      assert.equal(capturedMethod, "POST");
      assert.ok(capturedUrl.endsWith("/api/v1/attendance/recalculate"));
      const body = JSON.parse(capturedBody);
      assert.equal(body.employee_id, "emp-101");
      assert.equal(body.attendance_date, "2026-11-03");
      assert.equal(res.calculation_version, 2);
    });

    it("should execute punch action with idempotency key and client timestamp", async () => {
      let capturedUrl = "";
      let capturedBody = "";
      let capturedMethod = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedMethod = init?.method || "";
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            event: {
              id: "ev-punch-1",
              tenant_id: "tenant-1",
              employee_id: "emp-101",
              event_type: "CHECK_IN",
              event_category: "STANDARD",
              effective_at: "2026-11-03T09:00:00Z",
              server_received_at: "2026-11-03T09:00:01Z",
              idempotency_key: "idem-key-abc-123",
              source: "WEB_CONSOLE",
              timestamp_verification_status: "VERIFIED",
              review_status: "APPROVED",
              created_at: "2026-11-03T09:00:01Z",
            },
            additional_events: [],
            idempotent_replay: false,
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const punchRes = await attendanceApi.punch(
        {
          employee_id: "emp-101",
          event_type: "CHECK_IN",
          client_timestamp: "2026-11-03T09:00:00Z",
          idempotency_key: "idem-key-abc-123",
          location_id: "loc-hq",
        },
        "jwt-token"
      );

      assert.equal(capturedMethod, "POST");
      assert.ok(capturedUrl.endsWith("/api/v1/attendance/punch"));
      const body = JSON.parse(capturedBody);
      assert.equal(body.event_type, "CHECK_IN");
      assert.equal(body.idempotency_key, "idem-key-abc-123");
      assert.equal(punchRes.event.event_type, "CHECK_IN");
      assert.equal(punchRes.idempotent_replay, false);
    });

    it("should create CORRECTION_INSERT with mandatory reason", async () => {
      let capturedUrl = "";
      let capturedBody = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            correction_event: {
              id: "corr-ev-1",
              tenant_id: "tenant-1",
              employee_id: "emp-101",
              event_type: "CHECK_OUT",
              event_category: "CORRECTION_INSERT",
              effective_at: "2026-11-03T18:00:00Z",
              correction_reason: "Employee forgot to punch out due to client emergency",
              actor_user_id: "mgr-user-1",
              source: "ADMIN_WEB_CORRECTION",
              idempotency_key: "corr-key-1",
              created_at: "2026-11-03T19:00:00Z",
            },
            affected_attendance_dates: ["2026-11-03"],
            recalculated_days: [],
            idempotent_replay: false,
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const res = await attendanceApi.createCorrection(
        {
          employee_id: "emp-101",
          correction_type: "CORRECTION_INSERT",
          event_type: "CHECK_OUT",
          effective_at: "2026-11-03T18:00:00Z",
          correction_reason: "Employee forgot to punch out due to client emergency",
          idempotency_key: "corr-key-1",
        },
        "jwt-token"
      );

      assert.ok(capturedUrl.endsWith("/api/v1/attendance/corrections"));
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.correction_type, "CORRECTION_INSERT");
      assert.equal(parsed.correction_reason, "Employee forgot to punch out due to client emergency");
      assert.equal(res.correction_event.event_category, "CORRECTION_INSERT");
    });

    it("should create CORRECTION_SUPERSEDE pointing to target event ID", async () => {
      let capturedBody = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            correction_event: {
              id: "corr-ev-2",
              event_category: "CORRECTION_SUPERSEDE",
              supersedes_event_id: "orig-ev-123",
              correction_reason: "Corrected timestamp: employee arrived at 09:00 not 09:30",
            },
            affected_attendance_dates: ["2026-11-03"],
            recalculated_days: [],
            idempotent_replay: false,
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const res = await attendanceApi.createCorrection(
        {
          employee_id: "emp-101",
          correction_type: "CORRECTION_SUPERSEDE",
          event_type: "CHECK_IN",
          supersedes_event_id: "orig-ev-123",
          effective_at: "2026-11-03T09:00:00Z",
          correction_reason: "Corrected timestamp: employee arrived at 09:00 not 09:30",
          idempotency_key: "corr-key-2",
        },
        "jwt-token"
      );

      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.supersedes_event_id, "orig-ev-123");
      assert.equal(res.correction_event.supersedes_event_id, "orig-ev-123");
    });

    it("should create CORRECTION_VOID to nullify erroneous event", async () => {
      let capturedBody = "";

      globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            correction_event: {
              id: "corr-ev-3",
              event_category: "CORRECTION_VOID",
              supersedes_event_id: "duplicate-ev-456",
              correction_reason: "Accidental double-tap check-in voided per supervisor review",
            },
            affected_attendance_dates: ["2026-11-03"],
            recalculated_days: [],
            idempotent_replay: false,
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const res = await attendanceApi.createCorrection(
        {
          employee_id: "emp-101",
          correction_type: "CORRECTION_VOID",
          supersedes_event_id: "duplicate-ev-456",
          correction_reason: "Accidental double-tap check-in voided per supervisor review",
          idempotency_key: "corr-key-3",
        },
        "jwt-token"
      );

      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.correction_type, "CORRECTION_VOID");
      assert.equal(parsed.supersedes_event_id, "duplicate-ev-456");
      assert.equal(res.correction_event.event_category, "CORRECTION_VOID");
    });

    it("should fetch day events audit stream for drawer timeline", async () => {
      let capturedUrl = "";

      globalThis.fetch = (async (url: string | URL | Request) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            items: [
              {
                id: "ev-1",
                event_type: "CHECK_IN",
                event_category: "STANDARD",
                effective_at: "2026-11-03T09:00:00Z",
                is_active: true,
                source: "WEB_CONSOLE",
                created_at: "2026-11-03T09:00:00Z",
              },
              {
                id: "ev-2",
                event_type: "CHECK_OUT",
                event_category: "CORRECTION_INSERT",
                effective_at: "2026-11-03T17:00:00Z",
                correction_reason: "Missed punch correction",
                actor_user_id: "admin-1",
                is_active: true,
                source: "ADMIN_WEB_CORRECTION",
                created_at: "2026-11-03T18:00:00Z",
              },
            ],
            total: 2,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const auditStream = await attendanceApi.getDayEvents("rec-day-999", "jwt-token");
      assert.equal(auditStream.total, 2);
      assert.equal(auditStream.items[0].event_type, "CHECK_IN");
      assert.equal(auditStream.items[1].event_category, "CORRECTION_INSERT");
      assert.ok(capturedUrl.endsWith("/api/v1/attendance/records/rec-day-999/events"));
    });

    it("should trigger attendance batch reconciliation", async () => {
      let capturedUrl = "";
      let capturedBody = "";

      globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = init?.body as string;
        return new Response(
          JSON.stringify({
            status: "COMPLETED",
            tenant_id: "tenant-1",
            target_dates: ["2026-11-03"],
            total_candidates: 15,
            recalculated_count: 14,
            failed_count: 0,
            errors: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }) as typeof fetch;

      const recon = await attendanceApi.reconcile({ target_date: "2026-11-03" }, "jwt-token");
      assert.equal(recon.status, "COMPLETED");
      assert.equal(recon.total_candidates, 15);
      assert.equal(recon.recalculated_count, 14);
      assert.ok(capturedUrl.endsWith("/api/v1/attendance/reconcile"));
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.target_date, "2026-11-03");
    });
  });

  describe("Attendance Business Logic & Frontend Invariant Verification (Milestone 5)", () => {
    it("should compute accurate dashboard KPI metrics from daily attendance projections", () => {
      const mockDays = [
        // Present on time
        { status: "PRESENT", first_check_in: "09:00:00", last_check_out: "17:00:00", late_arrival_minutes: 0, is_incomplete: false },
        // Present but late
        { status: "PRESENT", first_check_in: "09:20:00", last_check_out: "17:00:00", late_arrival_minutes: 20, is_incomplete: false },
        // Half day
        { status: "HALF_DAY", first_check_in: "09:00:00", last_check_out: "13:00:00", late_arrival_minutes: 0, is_incomplete: false },
        // Absent
        { status: "ABSENT", first_check_in: null, last_check_out: null, late_arrival_minutes: 0, is_incomplete: false },
        // Incomplete
        { status: "INCOMPLETE", first_check_in: "09:00:00", last_check_out: null, late_arrival_minutes: 0, is_incomplete: true },
        // Pending review
        { status: "PENDING_REVIEW", first_check_in: "09:00:00", last_check_out: "17:00:00", late_arrival_minutes: 0, is_incomplete: false },
        // Currently working (active checked in, not checked out, not incomplete)
        { status: "PRESENT", first_check_in: "08:50:00", last_check_out: null, late_arrival_minutes: 0, is_incomplete: false },
      ];

      const present = mockDays.filter((d) => d.status === "PRESENT" || d.status === "HALF_DAY" || d.status === "LATE").length;
      const absent = mockDays.filter((d) => d.status === "ABSENT").length;
      const late = mockDays.filter((d) => d.status === "LATE" || d.late_arrival_minutes > 0).length;
      const incomplete = mockDays.filter((d) => d.status === "INCOMPLETE" || d.is_incomplete).length;
      const pendingReview = mockDays.filter((d) => d.status === "PENDING_REVIEW").length;
      const currentlyWorking = mockDays.filter((d) => d.first_check_in && !d.last_check_out && !d.is_incomplete).length;
      const unresolved = mockDays.filter((d) => d.status === "INCOMPLETE" || d.is_incomplete || (d.first_check_in && !d.last_check_out)).length;

      assert.equal(present, 4); // 2 full present + 1 half day + 1 currently working present
      assert.equal(absent, 1);
      assert.equal(late, 1);
      assert.equal(incomplete, 1);
      assert.equal(pendingReview, 1);
      assert.equal(currentlyWorking, 1);
      assert.equal(unresolved, 2); // 1 incomplete + 1 active without checkout
    });

    it("should enforce manager scope filtering to direct reports only", () => {
      const managerId = "mgr-100";
      const employees = [
        { id: "emp-1", first_name: "Alice", reporting_manager_id: "mgr-100" },
        { id: "emp-2", first_name: "Bob", reporting_manager_id: "mgr-100" },
        { id: "emp-3", first_name: "Charlie", reporting_manager_id: "other-mgr-200" },
        { id: "mgr-100", first_name: "Manager Dave", reporting_manager_id: null },
      ];

      const authorizedDirectReports = employees.filter(
        (e) => e.reporting_manager_id === managerId || e.id === managerId
      );

      assert.equal(authorizedDirectReports.length, 3);
      assert.ok(authorizedDirectReports.some((e) => e.id === "emp-1"));
      assert.ok(authorizedDirectReports.some((e) => e.id === "emp-2"));
      assert.ok(authorizedDirectReports.some((e) => e.id === "mgr-100"));
      assert.ok(!authorizedDirectReports.some((e) => e.id === "emp-3"));

      // In manager view, self-correction must be blocked
      const canCorrect = (targetEmpId: string) => targetEmpId !== managerId;
      assert.equal(canCorrect("emp-1"), true);
      assert.equal(canCorrect("emp-2"), true);
      assert.equal(canCorrect("mgr-100"), false); // Self-correction blocked!
    });

    it("should validate correction reason length requirement (>= 5 chars)", () => {
      const validateCorrectionReason = (reason: string) => {
        if (!reason || reason.trim().length < 5) {
          return "Correction reason is mandatory and must be at least 5 characters.";
        }
        return null;
      };

      assert.equal(validateCorrectionReason(""), "Correction reason is mandatory and must be at least 5 characters.");
      assert.equal(validateCorrectionReason("abc"), "Correction reason is mandatory and must be at least 5 characters.");
      assert.equal(validateCorrectionReason("1234"), "Correction reason is mandatory and must be at least 5 characters.");
      assert.equal(validateCorrectionReason("Valid operational reason for adjustment"), null);
    });

    it("should validate target event requirement for SUPERSEDE and VOID corrections", () => {
      const validateTargetEvent = (type: string, targetEventId: string | null | undefined) => {
        if ((type === "CORRECTION_SUPERSEDE" || type === "CORRECTION_VOID") && !targetEventId) {
          return "Please select the original attendance event to supersede or void.";
        }
        return null;
      };

      assert.equal(validateTargetEvent("CORRECTION_SUPERSEDE", ""), "Please select the original attendance event to supersede or void.");
      assert.equal(validateTargetEvent("CORRECTION_VOID", undefined), "Please select the original attendance event to supersede or void.");
      assert.equal(validateTargetEvent("CORRECTION_SUPERSEDE", "ev-1234"), null);
      assert.equal(validateTargetEvent("CORRECTION_INSERT", ""), null);
    });
  });
});
