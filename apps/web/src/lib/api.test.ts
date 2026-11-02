import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  apiFetch,
  ApiError,
  organizationApi,
  authApi,
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
});
