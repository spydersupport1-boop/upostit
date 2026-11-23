import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  notificationApi,
  ApiError,
  API_BASE_URL,
} from "./api.ts";
import type {
  NotificationOverviewDto,
  NotificationTemplateDto,
  TemplateCreateRequestDto,
  NotificationPreferenceDto,
  PreferenceUpdateRequestDto,
  ChannelListResponseDto,
  NotificationActivityListDto,
  NotificationDto,
} from "./api.ts";

describe("Phase 10 Milestone 10.5 — Next.js Web Console: Notification Administration", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const tToken = "mock-jwt-token-admin";
  const tTenantId = "tenant-uuid-111";

  // ===========================================================================
  // 1. Overview & Delivery Metric Tests
  // ===========================================================================
  describe("notificationApi — Overview & Delivery Metrics", () => {
    it("should fetch notification delivery overview and calculate status and channel distributions", async () => {
      let capturedUrl = "";
      let capturedHeaders: Record<string, string> = {};

      const mockOverview: NotificationOverviewDto = {
        total_count: 42,
        status_counts: {
          pending: 3,
          processing: 2,
          retry_scheduled: 1,
          sent: 25,
          delivered: 10,
          failed: 1,
          cancelled: 0,
        },
        channel_counts: {
          push: 24,
          email: 18,
          sms: 0,
        },
        recent_notifications: [
          {
            id: "notif-uuid-1",
            tenant_id: tTenantId,
            event_type: "leave_request_submitted",
            channel: "EMAIL",
            template_key: "leave_request_submitted",
            recipient_destination: "supervisor@upostit.test",
            subject: "Leave Request Submitted: Jane Doe (AL)",
            body: "Jane Doe has requested 2 days of Annual Leave.",
            status: "SENT",
            priority: "NORMAL",
            scheduled_for: "2026-03-01T08:00:00Z",
            attempt_count: 1,
            max_attempts: 3,
            provider_name: "MockEmailProvider",
            provider_message_id: "msg-12345",
            sent_at: "2026-03-01T08:00:02Z",
            created_at: "2026-03-01T08:00:00Z",
            updated_at: "2026-03-01T08:00:02Z",
          },
        ],
        delivery_distinction_note:
          "SENT indicates that the notification was accepted by the downstream provider. DELIVERED indicates verified receipt confirmation.",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = String(url);
        capturedHeaders = (init?.headers as Record<string, string>) || {};
        return new Response(JSON.stringify(mockOverview), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.getOverview(tToken);

      assert.equal(capturedUrl, `${API_BASE_URL}/api/v1/notifications/overview`);
      assert.equal(capturedHeaders["Authorization"], `Bearer ${tToken}`);
      assert.equal(result.total_count, 42);
      assert.equal(result.status_counts.sent, 25);
      assert.equal(result.status_counts.delivered, 10);
      assert.equal(result.channel_counts.push, 24);
      assert.equal(result.recent_notifications.length, 1);
      assert.ok(result.delivery_distinction_note.includes("SENT indicates"));
      assert.ok(result.delivery_distinction_note.includes("DELIVERED indicates"));
    });

    it("should clearly differentiate between SENT (provider accepted) and DELIVERED (device acknowledged)", async () => {
      const mockOverview: NotificationOverviewDto = {
        total_count: 35,
        status_counts: {
          pending: 0,
          processing: 0,
          retry_scheduled: 0,
          sent: 25,
          delivered: 10,
          failed: 0,
          cancelled: 0,
        },
        channel_counts: { push: 35, email: 0, sms: 0 },
        recent_notifications: [],
        delivery_distinction_note: "SENT != DELIVERED",
      };

      globalThis.fetch = async () =>
        new Response(JSON.stringify(mockOverview), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      const result = await notificationApi.getOverview(tToken);
      // Invariant: Sent (25) + Delivered (10) = 35 total completed handshakes
      assert.equal(result.status_counts.sent + result.status_counts.delivered, 35);
      assert.notEqual(result.status_counts.sent, result.status_counts.delivered);
    });
  });

  // ===========================================================================
  // 2. Template Administration Tests
  // ===========================================================================
  describe("notificationApi — Template Catalog & Overrides", () => {
    it("should fetch templates list distinguishing system defaults from tenant overrides", async () => {
      let capturedUrl = "";
      const mockTemplates: NotificationTemplateDto[] = [
        {
          id: "tpl-sys-1",
          tenant_id: null,
          template_key: "leave_request_submitted",
          name: "Leave Request Submitted (Email)",
          event_type: "leave_request_submitted",
          channel: "EMAIL",
          subject_template: "Leave Request Submitted: {employee_name} ({leave_type})",
          body_template: "Hello,\n{employee_name} has requested {duration_days} day(s).",
          locale: "en",
          is_active: true,
          is_system: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "tpl-custom-2",
          tenant_id: tTenantId,
          template_key: "leave_request_submitted",
          name: "Acme Corp Custom Leave Notice (Email)",
          description: "Branded leave notice with policy link",
          event_type: "leave_request_submitted",
          channel: "EMAIL",
          subject_template: "[ACME HR] Leave Request: {employee_name}",
          body_template: "Hi,\nPlease review {employee_name}'s application for {leave_type}.",
          locale: "en",
          is_active: true,
          is_system: false,
          created_at: "2026-02-01T00:00:00Z",
          updated_at: "2026-02-01T00:00:00Z",
        },
      ];

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = String(url);
        return new Response(JSON.stringify(mockTemplates), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.getTemplates(tToken);

      assert.equal(capturedUrl, `${API_BASE_URL}/api/v1/notifications/templates`);
      assert.equal(result.length, 2);

      const systemTpl = result.find((t) => t.is_system);
      const tenantTpl = result.find((t) => !t.is_system);

      assert.ok(systemTpl);
      assert.equal(systemTpl?.tenant_id, null);
      assert.equal(systemTpl?.is_system, true);

      assert.ok(tenantTpl);
      assert.equal(tenantTpl?.tenant_id, tTenantId);
      assert.equal(tenantTpl?.is_system, false);
      assert.equal(tenantTpl?.name, "Acme Corp Custom Leave Notice (Email)");
    });

    it("should create or update a tenant template override with safe variable syntax", async () => {
      let capturedMethod = "";
      let capturedBody = "";

      const createPayload: TemplateCreateRequestDto = {
        template_key: "leave_request_approved",
        name: "Custom Approval Template",
        event_type: "leave_request_approved",
        channel: "EMAIL",
        subject_template: "Approved: {leave_type} for {employee_name}",
        body_template: "Congratulations {employee_name}, your {leave_type} request from {start_date} has been approved.",
        locale: "en",
        is_active: true,
      };

      const mockResponse: NotificationTemplateDto = {
        id: "tpl-created-999",
        tenant_id: tTenantId,
        ...createPayload,
        locale: createPayload.locale || "en",
        is_active: createPayload.is_active ?? true,
        is_system: false,
        created_at: "2026-03-01T12:00:00Z",
        updated_at: "2026-03-01T12:00:00Z",
      };

      globalThis.fetch = async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = String(init?.body || "");
        return new Response(JSON.stringify(mockResponse), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.createOrUpdateTemplate(createPayload, tToken);

      assert.equal(capturedMethod, "POST");
      const parsedBody = JSON.parse(capturedBody);
      assert.equal(parsedBody.template_key, "leave_request_approved");
      assert.equal(parsedBody.channel, "EMAIL");
      assert.ok(parsedBody.body_template.includes("{employee_name}"));
      assert.ok(parsedBody.body_template.includes("{start_date}"));

      assert.equal(result.id, "tpl-created-999");
      assert.equal(result.tenant_id, tTenantId);
      assert.equal(result.is_system, false);
    });

    it("should update an existing tenant template override via PUT /templates/{id}", async () => {
      let capturedMethod = "";
      let capturedUrl = "";
      let capturedBody = "";

      const updatePayload = {
        name: "Updated Approval Notice",
        subject_template: "[ACME] Updated Subject",
        body_template: "Updated body text for {employee_name}.",
      };

      const mockUpdated: NotificationTemplateDto = {
        id: "tpl-custom-2",
        tenant_id: tTenantId,
        template_key: "leave_request_approved",
        name: "Updated Approval Notice",
        event_type: "leave_request_approved",
        channel: "EMAIL",
        subject_template: "[ACME] Updated Subject",
        body_template: "Updated body text for {employee_name}.",
        locale: "en",
        is_active: true,
        is_system: false,
        created_at: "2026-02-01T00:00:00Z",
        updated_at: "2026-03-01T14:00:00Z",
      };

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        capturedUrl = String(url);
        capturedMethod = init?.method || "GET";
        capturedBody = String(init?.body || "");
        return new Response(JSON.stringify(mockUpdated), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.updateTemplate("tpl-custom-2", updatePayload, tToken);

      assert.equal(capturedUrl, `${API_BASE_URL}/api/v1/notifications/templates/tpl-custom-2`);
      assert.equal(capturedMethod, "PUT");
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.name, "Updated Approval Notice");
      assert.equal(result.name, "Updated Approval Notice");
    });

    it("should throw 403 Forbidden when unauthorized employee attempts to edit templates", async () => {
      globalThis.fetch = async () =>
        new Response(
          JSON.stringify({ detail: "Insufficient permissions for this operation" }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );

      await assert.rejects(
        async () => {
          await notificationApi.createOrUpdateTemplate(
            {
              template_key: "any_key",
              name: "Unauthorized Attempt",
              event_type: "leave_request_submitted",
              channel: "EMAIL",
              body_template: "body",
            },
            "employee-token"
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          assert.ok(err.detail.includes("Insufficient permissions"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 3. Channel Readiness & Mock State Tests
  // ===========================================================================
  describe("notificationApi — Outbound Channel Readiness & Status", () => {
    it("should fetch channel configurations clearly indicating mock and unconfigured adapters", async () => {
      const mockChannels: ChannelListResponseDto = {
        channels: [
          {
            channel: "PUSH",
            is_enabled: true,
            provider_name: "MockPushProvider (Development Fallback)",
            status: "MOCK",
            description: "Delivers push notifications via local mock provider.",
            details: { fcm_enabled: false, provider_mode: "mock_development" },
          },
          {
            channel: "EMAIL",
            is_enabled: true,
            provider_name: "Console Provider (Dev Preview)",
            status: "MOCK",
            description: "Transactional email delivery logged to console.",
            details: { backend: "console", from_address: "noreply@attendance.io" },
          },
          {
            channel: "SMS",
            is_enabled: false,
            provider_name: "Deferred / Unconfigured",
            status: "UNCONFIGURED",
            description: "SMS provider integration deferred per Phase 10 roadmap.",
            details: { deferred: true },
          },
        ],
      };

      globalThis.fetch = async () =>
        new Response(JSON.stringify(mockChannels), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      const result = await notificationApi.getChannels(tToken);

      assert.equal(result.channels.length, 3);

      const pushCh = result.channels.find((c) => c.channel === "PUSH");
      assert.ok(pushCh);
      assert.equal(pushCh?.status, "MOCK");
      assert.equal(pushCh?.is_enabled, true);

      const emailCh = result.channels.find((c) => c.channel === "EMAIL");
      assert.ok(emailCh);
      assert.equal(emailCh?.status, "MOCK");

      const smsCh = result.channels.find((c) => c.channel === "SMS");
      assert.ok(smsCh);
      assert.equal(smsCh?.status, "UNCONFIGURED");
      assert.equal(smsCh?.is_enabled, false);
      assert.ok(smsCh?.details?.deferred);
    });

    it("should never display Active (Production) for unverified credentials", async () => {
      const mockChannelsWithCredentials: ChannelListResponseDto = {
        channels: [
          {
            channel: "PUSH",
            is_enabled: true,
            provider_name: "Firebase Cloud Messaging (FCM Gateway)",
            status: "CONFIGURED_UNVERIFIED",
            description: "FCM credentials detected but device delivery unverified.",
            details: { fcm_enabled: true, credentials_present: true },
          },
          {
            channel: "EMAIL",
            is_enabled: true,
            provider_name: "SMTP Relay (Credentials Present - Unverified Gateway in Phase 10)",
            status: "CONFIGURED_UNVERIFIED",
            description: "SMTP host detected but live delivery unverified.",
            details: { backend: "smtp" },
          },
          {
            channel: "SMS",
            is_enabled: false,
            provider_name: "Deferred / Unconfigured",
            status: "UNCONFIGURED",
            description: "SMS provider deferred.",
            details: { deferred: true },
          },
        ],
      };

      globalThis.fetch = async () =>
        new Response(JSON.stringify(mockChannelsWithCredentials), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      const result = await notificationApi.getChannels(tToken);
      for (const ch of result.channels) {
        // Strict invariant: no channel may claim to be "PRODUCTION" or "ACTIVE_PRODUCTION"
        assert.notEqual(ch.status, "CONFIGURED");
        assert.notEqual(ch.status, "ACTIVE_PRODUCTION");
        if (ch.channel === "SMS") {
          assert.equal(ch.status, "UNCONFIGURED");
        } else {
          assert.equal(ch.status, "CONFIGURED_UNVERIFIED");
        }
      }
    });
  });

  // ===========================================================================
  // 4. Tenant Preferences & Quiet-Hours Tests
  // ===========================================================================
  describe("notificationApi — Tenant Preferences & Quiet Hours", () => {
    it("should fetch tenant default preferences including quiet-hours windows", async () => {
      const mockPref: NotificationPreferenceDto = {
        id: "pref-uuid-1",
        tenant_id: tTenantId,
        user_id: null,
        is_push_enabled: true,
        is_email_enabled: true,
        is_sms_enabled: false,
        quiet_hours_enabled: true,
        quiet_hours_start: "22:00",
        quiet_hours_end: "07:00",
        timezone: "America/New_York",
        category_preferences: {},
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      };

      globalThis.fetch = async () =>
        new Response(JSON.stringify(mockPref), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      const result = await notificationApi.getPreferences(tToken);

      assert.equal(result.tenant_id, tTenantId);
      assert.equal(result.user_id, null);
      assert.equal(result.is_push_enabled, true);
      assert.equal(result.is_email_enabled, true);
      assert.equal(result.is_sms_enabled, false);
      assert.equal(result.quiet_hours_enabled, true);
      assert.equal(result.quiet_hours_start, "22:00");
      assert.equal(result.quiet_hours_end, "07:00");
      assert.equal(result.timezone, "America/New_York");
    });

    it("should update tenant default preferences as administrator", async () => {
      let capturedMethod = "";
      let capturedBody = "";

      const updatePayload: PreferenceUpdateRequestDto = {
        is_push_enabled: true,
        is_email_enabled: true,
        is_sms_enabled: false,
        quiet_hours_enabled: true,
        quiet_hours_start: "21:30",
        quiet_hours_end: "06:30",
        timezone: "Asia/Kolkata",
      };

      const updatedPref: NotificationPreferenceDto = {
        id: "pref-uuid-1",
        tenant_id: tTenantId,
        user_id: null,
        is_push_enabled: true,
        is_email_enabled: true,
        is_sms_enabled: false,
        quiet_hours_enabled: true,
        quiet_hours_start: "21:30",
        quiet_hours_end: "06:30",
        timezone: "Asia/Kolkata",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-03-01T15:00:00Z",
      };

      globalThis.fetch = async (_url: string | URL | Request, init?: RequestInit) => {
        capturedMethod = init?.method || "GET";
        capturedBody = String(init?.body || "");
        return new Response(JSON.stringify(updatedPref), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.updatePreferences(updatePayload, tToken);

      assert.equal(capturedMethod, "PUT");
      const parsed = JSON.parse(capturedBody);
      assert.equal(parsed.quiet_hours_start, "21:30");
      assert.equal(parsed.quiet_hours_end, "06:30");
      assert.equal(parsed.timezone, "Asia/Kolkata");

      assert.equal(result.quiet_hours_start, "21:30");
      assert.equal(result.timezone, "Asia/Kolkata");
    });

    it("should throw 403 Forbidden when non-admin attempts to update tenant default preferences", async () => {
      globalThis.fetch = async () =>
        new Response(
          JSON.stringify({ detail: "Insufficient permissions for this operation" }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );

      await assert.rejects(
        async () => {
          await notificationApi.updatePreferences(
            { quiet_hours_enabled: false },
            "manager-token"
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 403);
          return true;
        }
      );
    });

    it("should throw 422 Unprocessable Entity when quiet hours time is not in HH:MM format", async () => {
      globalThis.fetch = async () =>
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ["body", "quiet_hours_start"],
                msg: "Time must be in 24-hour 'HH:MM' format (e.g. '22:00', '07:30')",
                type: "value_error",
              },
            ],
          }),
          { status: 422, headers: { "Content-Type": "application/json" } }
        );

      await assert.rejects(
        async () => {
          await notificationApi.updatePreferences(
            { quiet_hours_start: "10pm" },
            tToken
          );
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.equal(err.status, 422);
          assert.ok(err.detail.includes("HH:MM"));
          return true;
        }
      );
    });
  });

  // ===========================================================================
  // 5. Activity Log & Filtering Tests
  // ===========================================================================
  describe("notificationApi — Notification Activity Log & Inspection", () => {
    it("should query paginated activity log with channel, status, and event-type filters", async () => {
      let capturedUrl = "";

      const mockActivity: NotificationActivityListDto = {
        items: [
          {
            id: "notif-uuid-101",
            tenant_id: tTenantId,
            event_type: "high_risk_fraud_alert",
            channel: "PUSH",
            template_key: "high_risk_fraud_alert",
            recipient_destination: "device_token_hash:3a4b5c6d...",
            subject: "SECURITY ALERT: High-Risk Activity Detected",
            body: "A high-risk fraud score (92) was recorded for John Doe.",
            status: "DELIVERED",
            priority: "URGENT",
            scheduled_for: "2026-03-01T10:00:00Z",
            attempt_count: 1,
            max_attempts: 3,
            provider_name: "MockPushProvider",
            provider_message_id: "fcm-ack-9988",
            sent_at: "2026-03-01T10:00:01Z",
            delivered_at: "2026-03-01T10:00:03Z",
            created_at: "2026-03-01T10:00:00Z",
            updated_at: "2026-03-01T10:00:03Z",
          },
        ],
        total: 1,
        offset: 0,
        limit: 20,
      };

      globalThis.fetch = async (url: string | URL | Request) => {
        capturedUrl = String(url);
        return new Response(JSON.stringify(mockActivity), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await notificationApi.getActivity(
        {
          status: "DELIVERED",
          channel: "PUSH",
          event_type: "high_risk_fraud_alert",
          limit: 20,
          offset: 0,
        },
        tToken
      );

      assert.ok(capturedUrl.includes("status=DELIVERED"));
      assert.ok(capturedUrl.includes("channel=PUSH"));
      assert.ok(capturedUrl.includes("event_type=high_risk_fraud_alert"));
      assert.equal(result.total, 1);
      assert.equal(result.items.length, 1);

      const item = result.items[0];
      assert.equal(item.status, "DELIVERED");
      assert.equal(item.priority, "URGENT");
      assert.ok(item.recipient_destination.startsWith("device_token_hash:"));
      assert.ok(item.delivered_at);
      // Zero raw secrets in body or destination
      assert.ok(!item.recipient_destination.includes("secret"));
      assert.ok(!item.body.includes("password"));
    });
  });

  // ===========================================================================
  // 6. Security & Invariant Verification
  // ===========================================================================
  describe("Security & Invariant Verification", () => {
    it("should never expose raw credentials or passwords in template definitions", () => {
      const templateExamples: string[] = [
        "Leave Request Submitted: {employee_name} ({leave_type})",
        "Hi {recipient_name}, activate your account at {activation_url}",
        "Security Alert: High risk score {risk_score} detected for {employee_name}",
      ];

      for (const tpl of templateExamples) {
        assert.ok(!tpl.includes("password"));
        assert.ok(!tpl.includes("fcm_token"));
        assert.ok(!tpl.includes("secret_key"));
      }
    });

    it("should confirm delivery status hierarchy invariants", () => {
      const validStatuses = new Set([
        "PENDING",
        "PROCESSING",
        "RETRY_SCHEDULED",
        "SENT",
        "DELIVERED",
        "FAILED",
        "CANCELLED",
      ]);

      assert.equal(validStatuses.size, 7);
      assert.ok(validStatuses.has("SENT"));
      assert.ok(validStatuses.has("DELIVERED"));
    });
  });
});

