import { expect, test } from "@playwright/test";

function mockApi(page) {
  let messageCount = 0;

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();

    if (pathname.endsWith("/api/config/llm") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          current_provider: "openai",
          current_model: "gpt-5.4-mini",
          providers: [
            {
              id: "openai",
              label: "OpenAI",
              enabled: true,
              default_model: "gpt-5.4-mini",
              suggested_models: ["gpt-5.4", "gpt-5.2", "gpt-5.2-chat-latest", "gpt-5.4-mini", "gpt-5.4-nano"],
              models: [
                {
                  id: "gpt-5.4",
                  label: "GPT-5.4",
                  summary: "flagship",
                  tier: "flagship",
                  stage: "stable",
                  notes: "",
                  recommended: true,
                },
                {
                  id: "gpt-5.2",
                  label: "GPT-5.2",
                  summary: "advanced",
                  tier: "advanced",
                  stage: "stable",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gpt-5.2-chat-latest",
                  label: "GPT-5.2 Chat Latest",
                  summary: "chat alias",
                  tier: "chat",
                  stage: "alias",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gpt-5.4-mini",
                  label: "GPT-5.4 Mini",
                  summary: "balanced",
                  tier: "balanced",
                  stage: "stable",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gpt-5.4-nano",
                  label: "GPT-5.4 Nano",
                  summary: "fast",
                  tier: "fast",
                  stage: "stable",
                  notes: "",
                  recommended: false,
                },
              ],
            },
            {
              id: "gemini",
              label: "Google Gemini",
              enabled: true,
              default_model: "gemini-2.5-flash",
              suggested_models: [
                "gemini-3-pro-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
              ],
              models: [
                {
                  id: "gemini-3-pro-preview",
                  label: "Gemini 3 Pro Preview",
                  summary: "flagship",
                  tier: "flagship",
                  stage: "preview",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gemini-3-flash-preview",
                  label: "Gemini 3 Flash Preview",
                  summary: "balanced",
                  tier: "balanced",
                  stage: "preview",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gemini-2.5-pro",
                  label: "Gemini 2.5 Pro",
                  summary: "advanced",
                  tier: "advanced",
                  stage: "stable",
                  notes: "",
                  recommended: false,
                },
                {
                  id: "gemini-2.5-flash",
                  label: "Gemini 2.5 Flash",
                  summary: "balanced",
                  tier: "balanced",
                  stage: "stable",
                  notes: "",
                  recommended: true,
                },
                {
                  id: "gemini-2.5-flash-lite",
                  label: "Gemini 2.5 Flash-Lite",
                  summary: "fast",
                  tier: "fast",
                  stage: "stable",
                  notes: "",
                  recommended: false,
                },
              ],
            },
          ],
        }),
      });
    }

    if (pathname.endsWith("/api/classifications/") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: "main-01", title: "أحوال شخصية" }]),
      });
    }

    if (pathname.endsWith("/api/classifications/main-01/subs") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: "sub-01", title: "التصنيف العام" }]),
      });
    }

    if (pathname.endsWith("/api/classifications/main-01/sub-01/cases") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: "case-01", title: "إقامة حارس قضائي" }]),
      });
    }

    if (pathname.endsWith("/api/sessions/") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session: {
            session_id: "session-1",
            classification: null,
            flags: { missing_fields: [] },
            metadata: {},
          },
        }),
      });
    }

    if (pathname.endsWith("/api/sessions/session-1/classification") && method === "PATCH") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session: {
            session_id: "session-1",
            classification: {
              main_id: "main-01",
              sub_id: "sub-01",
              case_id: "case-01",
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
            },
            flags: { missing_fields: ["بيانات المدعي"] },
            metadata: { pending_prompt: "ما بيانات المدعي؟" },
          },
        }),
      });
    }

    if (pathname.endsWith("/api/agent/message") && method === "POST") {
      messageCount += 1;
      await new Promise((resolve) => setTimeout(resolve, 200));
      if (messageCount === 1) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "هذه أقرب التصنيفات المتاحة.",
            phase: 1,
            session_status: "AWAITING_CLASSIFICATION_CONFIRM",
            completion_percentage: 0,
            extracted_data: {},
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: [],
              guard_issues: [],
            },
            next_action: "confirm_classification",
            metadata: {},
            suggestions: [
              {
                case_id: "case-01",
                case_title: "إقامة حارس قضائي",
                main_id: "main-01",
                main_title: "أحوال شخصية",
                sub_id: "sub-01",
                sub_title: "التصنيف العام",
                confidence: 0.92,
                rationale: "مطابقة الوقائع مع نوع الدعوى.",
                path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
              },
            ],
            classification: null,
          }),
        });
      }

      if (messageCount === 2) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "تم اعتماد التصنيف.\n\nما بيانات المدعي؟",
            phase: 1,
            session_status: "INTERVIEW",
            completion_percentage: 0,
            extracted_data: {},
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: ["بيانات المدعي"],
              guard_issues: [],
            },
            next_action: "ask_field",
            metadata: {},
            suggestions: [],
            classification: {
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
            },
          }),
        });
      }

      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "اكتملت الحقول المطلوبة. أصبحت الجلسة جاهزة للصياغة.",
          phase: 2,
          session_status: "READY_TO_DRAFT",
          completion_percentage: 100,
          extracted_data: { "بيانات المدعي": "نواف" },
          flags: {
            needs_human_review: false,
            critical_issues: [],
            missing_fields: [],
            guard_issues: [],
          },
          next_action: "go_to_phase2",
          metadata: {},
          suggestions: [],
          classification: {
            case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
          },
        }),
      });
    }

    if (pathname.endsWith("/api/petitions/session-1") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          petition_id: "petition-1",
          version: 1,
          facts: { content: "وقائع مولدة عبر البث." },
          evidence: { content: "أسانيد مولدة عبر البث." },
          requests: { content: "طلبات مولدة عبر البث." },
        }),
      });
    }

    if (pathname.endsWith("/api/agent/draft") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "تم إعداد مسودة الصحيفة.",
          phase: 2,
          session_status: "DRAFT_READY",
          petition: {
            petition_id: "petition-1",
            version: 1,
            facts: { content: "وقائع مولدة عبر البث." },
            evidence: { content: "أسانيد مولدة عبر البث." },
            requests: { content: "طلبات مولدة عبر البث." },
          },
        }),
      });
    }

    if (pathname.endsWith("/api/agent/review") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "تم إعداد تقرير المراجعة القانونية.",
          phase: 3,
          session_status: "REVIEW",
          completion_percentage: 100,
          extracted_data: { "بيانات المدعي": "نواف" },
          flags: {
            needs_human_review: false,
            critical_issues: [],
            missing_fields: [],
            guard_issues: [],
          },
          next_action: "review_ready",
          petition: {
            petition_id: "petition-1",
            version: 1,
            facts: { content: "وقائع مولدة عبر البث." },
            evidence: { content: "أسانيد مولدة عبر البث." },
            requests: { content: "طلبات مولدة عبر البث." },
          },
          review_report: {
            completeness_score: 76,
            recommendation: "يحتاج تعديلات",
            summary: "تم رصد ملاحظة قابلة للإصلاح.",
            issues: [
              {
                issue_id: "issue-1",
                severity: "اقتراح",
                category: "شكلي",
                description: "يمكن تحسين الوقائع.",
                suggestion: "أضف تفصيلًا أوضح للوقائع.",
                auto_fixable: true,
              },
            ],
          },
        }),
      });
    }

    if (pathname.endsWith("/api/agent/fix") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "تم تطبيق الإصلاح وإعادة توليد تقرير المراجعة.",
          phase: 3,
          session_status: "REVIEW",
          completion_percentage: 100,
          extracted_data: { "بيانات المدعي": "نواف" },
          flags: {
            needs_human_review: false,
            critical_issues: [],
            missing_fields: [],
            guard_issues: [],
          },
          next_action: "review_ready",
          petition: {
            petition_id: "petition-1",
            version: 2,
            facts: { content: "وقائع محسنة." },
            evidence: { content: "أسانيد مولدة عبر البث." },
            requests: { content: "طلبات مولدة عبر البث." },
          },
          review_report: {
            completeness_score: 92,
            recommendation: "جاهز للرفع",
            summary: "لا توجد ملاحظات جوهرية متبقية.",
            issues: [],
          },
        }),
      });
    }

    return route.continue();
  });
}

async function chooseLLMConfig(page) {
  await expect(page.locator("#llm-config-overlay")).toBeVisible();
  await expect(page.locator("#llm-config-title")).toContainText("اختر مزود الذكاء");
  await expect(page.locator("#llm-model-options")).toContainText("GPT-5.2");
  await page.getByRole("button", { name: "Google Gemini" }).click();
  await expect(page.locator("#llm-model-options")).toContainText("Gemini 3 Pro Preview");
  await page.getByRole("button", { name: "OpenAI" }).click();
  await page.locator("#llm-config-save-btn").evaluate((button) => button.click());
  await expect(page.locator("#llm-config-overlay")).toBeHidden();
  await expect(page.locator("#llm-status-bar")).toBeVisible();
  await expect(page.locator("#main-select option")).toHaveCount(2);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    class FakeEventSource {
      constructor() {
        this.listeners = {};
        setTimeout(() => {
          this.emit("start", { type: "start", section: "facts" });
          this.emit("chunk", { type: "chunk", section: "facts", content: "وقائع مولدة عبر البث." });
          this.emit("start", { type: "start", section: "evidence" });
          this.emit("chunk", { type: "chunk", section: "evidence", content: "أسانيد مولدة عبر البث." });
          this.emit("start", { type: "start", section: "requests" });
          this.emit("chunk", { type: "chunk", section: "requests", content: "طلبات مولدة عبر البث." });
          this.emit("complete", { type: "complete", petition_id: "petition-1", version: 1 });
        }, 50);
      }

      addEventListener(type, callback) {
        this.listeners[type] = this.listeners[type] || [];
        this.listeners[type].push(callback);
      }

      emit(type, payload) {
        (this.listeners[type] || []).forEach((callback) =>
          callback({ data: JSON.stringify(payload) })
        );
      }

      close() {}
    }

    window.__openedUrl = "";
    window.EventSource = FakeEventSource;
    window.open = (url) => {
      window.__openedUrl = url;
      return null;
    };
  });

  await mockApi(page);
});

test("renders RTL flow from classification to review and export", async ({ page }) => {
  await page.goto("/");
  await chooseLLMConfig(page);

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("#messages")).toContainText("مرحبًا");

  await page.locator("#message-input").fill("أريد رفع دعوى على تركة متنازع عليها.");
  await page.locator("#send-btn").click();
  await expect(page.locator("#send-btn")).toBeDisabled();
  await expect(page.locator(".message-card.pending")).toBeVisible();
  await expect(page.locator(".message-card.pending")).toContainText("يجري تحليل الوقائع");
  await expect(page.locator(".suggestion-card")).toContainText("إقامة حارس قضائي");
  await expect(page.locator("#send-btn")).toBeEnabled();

  await page.locator(".suggestion-card .btn").click();
  await expect(page.locator("#progress-label")).toContainText("ما بيانات المدعي");

  await page.locator("#message-input").fill("نواف");
  await page.locator("#send-btn").click();
  await expect(page.locator("#draft-btn")).toBeEnabled();

  await page.locator("#draft-btn").click();
  await expect(page.locator("#phase2-panel")).toBeVisible();
  await expect(page.locator("#petition-content .petition-editor")).toHaveValue("وقائع مولدة عبر البث.");

  await page.locator("#review-btn").click();
  await expect(page.locator("#phase3-panel")).toBeVisible();
  await expect(page.locator("#review-issues-list")).toContainText("يمكن تحسين الوقائع");

  await page.locator("#review-issues-list .btn").click();
  await expect(page.locator("#score-number")).toContainText("92");

  await page.locator("#export-pdf-btn").click();
  await expect(page.evaluate(() => window.__openedUrl)).resolves.toContain("/api/petitions/session-1/export/pdf");
});

test("supports manual cascading classification on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await chooseLLMConfig(page);

  await page.locator("#main-select").selectOption("main-01");
  await page.locator("#sub-select").selectOption("sub-01");
  await page.locator("#case-select").selectOption("case-01");
  await page.locator("#manual-select-btn").click();

  await expect(page.locator("#messages")).toContainText("ما بيانات المدعي");
  await expect(page.locator("#phase-title")).toContainText("التصنيف والاستجواب");
});
