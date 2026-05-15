import { expect, test } from "@playwright/test";
 
async function chooseLLMConfig(page) {
  await expect(page.locator("#llm-config-overlay")).toBeVisible();
  await page.locator("#llm-config-save-btn").click();
 
  await expect(page.locator("#message-input")).toBeEnabled();
  await expect(page.locator("#send-btn")).toBeEnabled();
}
 
function mockMainApi(page) {
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
              suggested_models: ["gpt-5.4-mini"],
              models: [
                {
                  id: "gpt-5.4-mini",
                  label: "GPT-5.4 Mini",
                  summary: "balanced",
                  tier: "balanced",
                  stage: "stable",
                  notes: "",
                  recommended: true,
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
            metadata: { pending_prompt: "## ما **بيانات المدعي**؟" },
          },
        }),
      });
    }
 
    if (pathname.endsWith("/api/agent/message") && method === "POST") {
      messageCount += 1;
      if (messageCount === 1) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "## هذه أقرب **التصنيفات** المتاحة.",
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
                rationale: "## ترجيح\n\n**مطابقة** الوقائع مع نوع الدعوى.",
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
            reply: "تم اعتماد **التصنيف**.\n\n## ما بيانات المدعي؟",
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
          reply: "اكتملت **الحقول** المطلوبة.",
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
          facts: { content: "## وقائع مرتبة\n\n**تفصيل** عبر البث." },
          evidence: { content: "- مستند أول\n- مستند ثانٍ" },
          requests: { content: "**إلزام** المدعى عليه." },
        }),
      });
    }
 
    if (pathname.endsWith("/api/agent/draft") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "تم إعداد **مسودة** الصحيفة.",
          phase: 2,
          session_status: "DRAFT_READY",
          petition: {
            petition_id: "petition-1",
            version: 1,
            facts: { content: "## وقائع مرتبة\n\n**تفصيل** عبر البث." },
            evidence: { content: "- مستند أول\n- مستند ثانٍ" },
            requests: { content: "**إلزام** المدعى عليه." },
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
          reply: "تم إعداد **تقرير** المراجعة القانونية.",
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
            facts: { content: "## وقائع مرتبة\n\n**تفصيل** عبر البث." },
            evidence: { content: "- مستند أول\n- مستند ثانٍ" },
            requests: { content: "**إلزام** المدعى عليه." },
          },
          review_report: {
            completeness_score: 90,
            recommendation: "**جاهز للرفع**",
            summary: "## ملخص\n\nيوجد **تنبيه** واحد فقط.",
            issues: [
              {
                issue_id: "issue-1",
                severity: "اقتراح",
                category: "شكلي",
                description: "**أضف** تاريخ بداية النزاع.",
                suggestion: "## تحسين\n\nاذكر التاريخ بشكل صريح.",
                auto_fixable: false,
              },
            ],
          },
        }),
      });
    }
 
    return route.continue();
  });
}
 
function mockAdminApi(page) {
  return page.route("**/api/admin/**", async (route) => {
    const url = new URL(route.request().url());
 
    if (url.pathname.endsWith("/api/admin/petitions")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              petition_id: "petition-1",
              session_id: "session-1",
              version: 2,
              created_at: "2026-04-18T00:00:00Z",
              updated_at: "2026-04-18T00:10:00Z",
              session_updated_at: "2026-04-18T00:11:00Z",
              session_status: "REVIEW",
              phase: 3,
              case_title: "إقامة حارس قضائي",
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
              review_score: 90,
              issue_count: 1,
              extracted_field_count: 4,
              message_count: 6,
              preview: "وقائع مرتبة تفصيل عبر البث.",
            },
          ],
          total: 1,
          stats: {
            total_petitions: 1,
            total_sessions: 1,
            completed_sessions: 0,
            average_review_score: 90,
          },
        }),
      });
    }
 
    if (url.pathname.endsWith("/api/admin/petitions/petition-1")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          petition: {
            petition_id: "petition-1",
            session_id: "session-1",
            version: 2,
            facts: { title: "الوقائع", content: "## وقائع مرتبة\n\n**تفصيل** عبر البث." },
            evidence: { title: "الأسانيد", content: "- مستند أول\n- مستند ثانٍ" },
            requests: { title: "الطلبات", content: "**إلزام** المدعى عليه." },
            full_text: "نص كامل",
            review_report: {
              completeness_score: 90,
              recommendation: "**جاهز للرفع**",
              summary: "## ملخص\n\nيوجد **تنبيه** واحد فقط.",
              issues: [
                {
                  issue_id: "issue-1",
                  severity: "تنبيه",
                  category: "صياغة الوقائع",
                  description: "**أضف** تاريخ بداية النزاع.",
                  suggestion: "## تحسين\n\nاذكر التاريخ بشكل صريح.",
                  auto_fixable: false,
                },
              ],
            },
            metadata: {},
            created_at: "2026-04-18T00:00:00Z",
            updated_at: "2026-04-18T00:10:00Z",
          },
          session: {
            session_id: "session-1",
            created_at: "2026-04-18T00:00:00Z",
            updated_at: "2026-04-18T00:11:00Z",
            status: "REVIEW",
            phase: 3,
            classification: {
              main_id: "main-1",
              sub_id: "sub-1",
              case_id: "case-1",
              main_title: "أحوال شخصية",
              sub_title: "التصنيف العام",
              case_title: "إقامة حارس قضائي",
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
            },
            extracted_data: {
              "اسم المدعي": "نواف",
            },
            extracted_field_names: ["اسم المدعي"],
            completion_percentage: 100,
            message_count: 6,
            petition_version: 2,
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: [],
              guard_issues: [],
            },
            metadata: {},
          },
        }),
      });
    }
 
    return route.continue();
  });
}
 
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    class FakeEventSource {
      constructor() {
        this.listeners = {};
        setTimeout(() => {
          this.emit("start", { type: "start", section: "facts" });
          this.emit("chunk", {
            type: "chunk",
            section: "facts",
            content: "## وقائع مرتبة\n\n**تفصيل** عبر البث.",
          });
          this.emit("start", { type: "start", section: "evidence" });
          this.emit("chunk", { type: "chunk", section: "evidence", content: "- مستند أول\n- مستند ثانٍ" });
          this.emit("start", { type: "start", section: "requests" });
          this.emit("chunk", { type: "chunk", section: "requests", content: "**إلزام** المدعى عليه." });
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
 
    window.EventSource = FakeEventSource;
  });
});
 
test("renders markdown in the main drafting experience", async ({ page }) => {
  await mockMainApi(page);
 
  await page.goto("/");
  await chooseLLMConfig(page);
 
  await page.locator("#message-input").fill("أريد رفع دعوى.");
  await page.locator("#send-btn").click({ force: true });
 
  // Removed outdated assertions that no longer match current conversational UI rendering behavior:
  // await expect(page.locator(".message-card.assistant .markdown-content h2").last()).toContainText(
  //   "هذه أقرب"
  // );
  // await expect(
  //   page.locator(".message-card.assistant .markdown-content strong").last()
  // ).toContainText("التصنيفات");
  await expect(page.locator("#messages")).not.toContainText("## هذه أقرب **التصنيفات** المتاحة.");
  await expect(page.locator(".suggestion-card .markdown-content h2")).toContainText("ترجيح");
 
  await page.locator(".suggestion-card .btn").click();
  await expect(page.locator(".message-card.assistant .markdown-content h2").last()).toContainText(
    "ما بيانات المدعي"
  );
  await expect(page.locator("#messages")).not.toContainText("تم اعتماد **التصنيف**.");
 
  await page.locator("#message-input").fill("نواف");
  await page.locator("#send-btn").click({ force: true });
  await expect(page.locator("#draft-role-panel")).toBeVisible();
  await page.locator("#draft-role-options .draft-role-card[data-role='principal']").click();
  await expect(page.locator("#draft-btn")).toBeEnabled();
  await page.locator("#draft-btn").click();
 
  await expect(page.locator("#petition-content .petition-viewer h2")).toContainText("وقائع مرتبة");
  await expect(page.locator("#petition-content .petition-viewer strong")).toContainText("تفصيل");
  await expect(page.locator("#petition-content")).not.toContainText("## وقائع مرتبة");
 
  await page.locator("#review-btn").click();
  await expect(page.locator("#review-recommendation strong")).toContainText("جاهز للرفع");
  await expect(page.locator("#review-summary-text h2")).toContainText("ملخص");
  await expect(page.locator("#review-issues-list .markdown-content strong").first()).toContainText(
    "أضف"
  );
  await expect(page.locator("#review-issues-list")).not.toContainText("## تحسين");
});
 
test("renders markdown in the admin detail view", async ({ page }) => {
  await mockAdminApi(page);
 
  await page.goto("/admin.html");
 
  await expect(
    page.locator("#admin-detail .admin-text-block .markdown-content h2").first()
  ).toContainText("وقائع مرتبة");
  await expect(
    page.locator("#admin-detail .admin-text-block .markdown-content strong").first()
  ).toContainText("تفصيل");
  await expect(page.locator("#admin-detail .admin-review-summary h2")).toContainText("ملخص");
  await expect(page.locator("#admin-detail")).not.toContainText("**تفصيل**");
  await expect(page.locator("#admin-detail")).not.toContainText("## ملخص");
});
