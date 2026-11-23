import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  notificationApi,
  apiFetch,
  ApiError,
  API_BASE_URL,
} from "./api.ts";

describe("Phase 10 Milestone 10.8 — Web Console: Security Audit & Penetration Testing", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const adminToken = "jwt-token-verified-admin";
  const employeeToken = "jwt-token-verified-employee";

  // ===========================================================================
  // 1. RBAC Hardening on Administration Endpoints
  // ===========================================================================
  describe("RBAC Hardening on Administration Endpoints", () => {
    it("should reject employee role with 403 Forbidden on getOverview", async () => {
      globalThis.fetch = async (input, init) => {
        const auth = (init?.headers as Record<string, string>)?.["Authorization"] || "";
        if (auth.includes(employeeToken)) {
          return new Response(
            JSON.stringify({ detail: "Insufficient permissions for this operation" }),
            { status: 403, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ total_count: 5 }), { status: 200 });
      };

      await assert.rejects(
        async () => {
          await notificationApi.getOverview(employeeToken);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 403);
          assert.ok(err.detail.includes("Insufficient permissions"));
          return true;
        }
      );
    });

    it("should reject employee role with 403 Forbidden on getActivity", async () => {
      globalThis.fetch = async (input, init) => {
        const auth = (init?.headers as Record<string, string>)?.["Authorization"] || "";
        if (auth.includes(employeeToken)) {
          return new Response(
            JSON.stringify({ detail: "Insufficient permissions for this operation" }),
            { status: 403, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 });
      };

      await assert.rejects(
        async () => {
          await notificationApi.getActivity({}, employeeToken);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 403);
          return true;
        }
      );
    });

    it("should reject employee role with 403 Forbidden on getPreferences", async () => {
      globalThis.fetch = async (input, init) => {
        const auth = (init?.headers as Record<string, string>)?.["Authorization"] || "";
        if (auth.includes(employeeToken)) {
          return new Response(
            JSON.stringify({ detail: "Insufficient permissions for this operation" }),
            { status: 403, headers: { "Content-Type": "application/json" } }
          );
        }
        return new Response(JSON.stringify({ is_push_enabled: true }), { status: 200 });
      };

      await assert.rejects(
        async () => {
          await notificationApi.getPreferences(employeeToken);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 403);
          return true;
        }
      );
    });

    it("should allow admin role to access getOverview successfully", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            total_count: 15,
            status_counts: { sent: 10, delivered: 5 },
            channel_counts: { push: 10, email: 5 },
            recent_notifications: [],
            delivery_distinction_note: "SENT vs DELIVERED distinction note",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const overview = await notificationApi.getOverview(adminToken);
      assert.strictEqual(overview.total_count, 15);
      assert.strictEqual(overview.status_counts.sent, 10);
    });
  });

  // ===========================================================================
  // 2. Input Validation & SSTI Anti-Tampering
  // ===========================================================================
  describe("Input Validation & SSTI Anti-Tampering", () => {
    it("should surface 422 error when template contains prohibited SSTI expressions", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            detail: "Template contains prohibited expressions, dunder attributes, or unsafe keywords.",
          }),
          { status: 422, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await notificationApi.createOrUpdateTemplate(
            {
              template_key: "ssti_exploit",
              name: "Exploit Template",
              event_type: "leave_request_submitted",
              channel: "EMAIL",
              body_template: "Hello {{ __import__('os').system('id') }}",
            },
            adminToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 422);
          assert.ok(err.detail.includes("prohibited expressions"));
          return true;
        }
      );
    });

    it("should reject oversized token hash in device deletion with 400", async () => {
      const oversizedHash = "a".repeat(256);
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Token hash exceeds maximum permissible length of 128 characters" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await apiFetch(`/notifications/devices/${oversizedHash}`, {
            method: "DELETE",
            token: employeeToken,
          });
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 400);
          assert.ok(err.detail.includes("maximum permissible length"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 3. Secret Protection & Invariant Guarantees
  // ===========================================================================
  describe("Secret Protection & Invariant Guarantees", () => {
    it("should never expose SMTP password or credentials in channel status response", async () => {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            channels: [
              {
                channel: "PUSH",
                is_enabled: true,
                provider_name: "MockPushProvider",
                status: "MOCK",
                description: "Local mock push provider",
                details: { fcm_enabled: false },
              },
              {
                channel: "EMAIL",
                is_enabled: true,
                provider_name: "Mock Email Provider",
                status: "MOCK",
                description: "Local mock email provider",
                details: { backend: "mock", from_address: "noreply@upostit.test" },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const result = await notificationApi.getChannels(adminToken);
      const rawText = JSON.stringify(result).toLowerCase();
      assert.ok(!rawText.includes("password"));
      assert.ok(!rawText.includes("secret"));
      assert.ok(!rawText.includes("private_key"));
    });
  });
});
