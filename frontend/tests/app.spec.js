import { expect, test } from "@playwright/test";

let lastDraftPayload = null;

const interviewForm = {
  title: "نموذج بيانات الدعوى",
  description: "أكمل جميع الحقول الإلزامية الخاصة بالدعوى قبل الانتقال إلى الصياغة.",
  submit_label: "اعتماد البيانات والمتابعة",
  fields: [
    {
      key: "auth_01",
      label: "بيانات المدعي",
      hint: "اكتب اسم المدعي وصفته وبيانات التواصل المتاحة.",
      placeholder: "أدخل بيانات المدعي",
      aria_label: "حقل إلزامي: بيانات المدعي",
      input_type: "text",
      group_id: "parties",
      group_label: "بيانات الأطراف",
      required: true,
      source: "authentic",
      badge_label: null,
      options: [],
    },
    {
      key: "auth_02",
      label: "تفاصيل النزاع",
      hint: "اشرح طبيعة النزاع والوقائع الجوهرية المرتبطة به.",
      placeholder: "اكتب تفاصيل النزاع",
      aria_label: "حقل إلزامي: تفاصيل النزاع",
      input_type: "textarea",
      group_id: "case_details",
      group_label: "تفاصيل الدعوى",
      required: true,
      source: "authentic",
      badge_label: null,
      options: [],
    },
    {
      key: "agent_attachment_01",
      label: "هل المرفق التالي متوفر: صك حصر ورثة؟",
      hint: "هذا سؤال إضافي أضافه النظام استنادًا إلى متطلبات نوع الدعوى.",
      placeholder: "",
      aria_label: "سؤال إضافي حول توفر المرفق صك حصر ورثة",
      input_type: "radio",
      group_id: "evidence",
      group_label: "المرفقات والأسانيد",
      required: true,
      source: "agent",
      badge_label: "سؤال إضافي",
      options: [
        { label: "نعم", value: "نعم" },
        { label: "لا", value: "لا" },
      ],
    },
  ],
  support_items: [
    {
      support_id: "field_01",
      title: "بيانات المدعي",
      summary: "حقل إلزامي يجب تعبئته قبل الانتقال إلى الصياغة.",
      details: "اكتب اسم المدعي وصفته ووسيلة التواصل أو أي وسيلة تبليغ متاحة.",
      aria_label: "تفاصيل الدعم للحقل بيانات المدعي",
      default_expanded: false,
    },
    {
      support_id: "attachment_01",
      title: "صك حصر ورثة",
      summary: "مرفق إلزامي لهذا النوع من الدعاوى.",
      details: "يوضح هذا المرفق صفة الورثة ويمكن أن يؤثر على اكتمال الصحيفة النهائية.",
      aria_label: "تفاصيل الدعم للمرفق صك حصر ورثة",
      default_expanded: false,
    },
  ],
};

function cloneInterviewForm(form = interviewForm) {
  return JSON.parse(JSON.stringify(form));
}

function mockApi(page, formFixture = interviewForm) {
  lastDraftPayload = null;
  const form = cloneInterviewForm(formFixture);

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;
    const method = route.request().method();
    let body = null;
    try {
      body = route.request().postDataJSON();
    } catch {
      body = null;
    }

    if (pathname.endsWith("/api/config/llm") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          current_provider: "openai",
          current_model: "o3",
          providers: [
            {
              id: "openai",
              label: "OpenAI",
              enabled: true,
              default_model: "o3",
              suggested_models: ["o3", "gpt-5.2", "gpt-5.4"],
              models: [
                {
                  id: "o3",
                  label: "GPT O3",
                  summary: "استدلال عميق",
                  tier: "flagship",
                  stage: "stable",
                  notes: "مناسب للتحليل القانوني المعقد.",
                  recommended: true,
                },
                {
                  id: "gpt-5.2",
                  label: "GPT 5.2",
                  summary: "صياغة متقدمة",
                  tier: "advanced",
                  stage: "stable",
                  notes: "خيار احترافي متوازن.",
                  recommended: false,
                },
                {
                  id: "gpt-5.4",
                  label: "GPT 5.4",
                  summary: "تحرير احترافي",
                  tier: "advanced",
                  stage: "stable",
                  notes: "ملائم للصياغة النهائية عالية الدقة.",
                  recommended: false,
                },
              ],
            },
            {
              id: "gemini",
              label: "Google Gemini",
              enabled: true,
              default_model: "gemini-2.5-pro",
              suggested_models: ["gemini-2.5-pro", "gemini-3-pro-preview"],
              models: [
                {
                  id: "gemini-2.5-pro",
                  label: "Gemini 2.5 Pro",
                  summary: "استدلال قانوني",
                  tier: "advanced",
                  stage: "stable",
                  notes: "الخيار المعتمد من Gemini.",
                  recommended: true,
                },
                {
                  id: "gemini-3-pro-preview",
                  label: "Gemini 3 Pro Preview",
                  summary: "معاينة متقدمة",
                  tier: "flagship",
                  stage: "preview",
                  notes: "إصدار معاينة قابل للتغير.",
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
            extracted_data: {},
            interview_form: null,
            inline_notice: null,
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
              main_title: "أحوال شخصية",
              sub_title: "التصنيف العام",
              case_title: "إقامة حارس قضائي",
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
            },
            flags: { missing_fields: ["بيانات المدعي", "تفاصيل النزاع"] },
            metadata: {},
            extracted_data: {},
            interview_form: form,
            inline_notice: null,
          },
        }),
      });
    }

    if (pathname.endsWith("/api/sessions/session-1/interview-form") && method === "PATCH") {
      const values = body?.values || {};
      const missingKeys = form.fields
        .filter((field) => field.required && !String(values[field.key] || "").trim())
        .map((field) => field.key);

      if (missingKeys.length > 0) {
        const formErrors = Object.fromEntries(
          missingKeys.map((key) => [key, "هذا الحقل إلزامي."])
        );
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "لا يمكن المتابعة قبل استكمال جميع الحقول الإلزامية الظاهرة في النموذج.",
            phase: 1,
            session_status: "INTERVIEW",
            completion_percentage: 33,
            extracted_data: {},
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: missingKeys,
              guard_issues: [],
            },
            next_action: "fill_form",
            metadata: { form_errors: formErrors },
            suggestions: [],
            classification: {
              case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
            },
            interview_form: form,
            inline_notice: {
              tone: "warning",
              icon: "⚠️",
              title: "أكمل الحقول الإلزامية",
              message: "لا يمكن المتابعة قبل استكمال جميع الحقول الإلزامية الظاهرة في النموذج.",
              aria_label: "تنبيه: توجد حقول إلزامية ناقصة في نموذج الدعوى.",
            },
          }),
        });
      }

      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "session-1",
          reply: "اكتملت البيانات المطلوبة. يمكنك الآن اختيار صيغة صحيفة الدعوى ثم بدء الصياغة.",
          phase: 2,
          session_status: "READY_TO_DRAFT",
          completion_percentage: 100,
          extracted_data: {
            "بيانات المدعي": values.auth_01,
            "تفاصيل النزاع": values.auth_02,
            "هل المرفق التالي متوفر: صك حصر ورثة؟": values.agent_attachment_01,
          },
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
          interview_form: form,
          inline_notice: null,
        }),
      });
    }

    if (pathname.endsWith("/api/agent/message") && method === "POST") {
      if ((body?.message || "").includes("غامض")) {
        await new Promise((resolve) => setTimeout(resolve, 120));
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "لم نتمكن من تحديد نوع ورقة الدعوى بناءً على المعلومات المدخلة. يرجى تقديم مزيد من التفاصيل حول ط�[...]
            phase: 1,
            session_status: "NEW",
            completion_percentage: 0,
            extracted_data: {},
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: [],
              guard_issues: [],
            },
            next_action: "clarify_classification",
            metadata: {},
            suggestions: [],
            classification: null,
            interview_form: null,
            inline_notice: {
              tone: "warning",
              icon: "⚠️",
              title: "البيانات الحالية غير كافية لتحديد نوع الدعوى",
              message:
                "لم نتمكن من تحديد نوع ورقة الدعوى بناءً على المعلومات المدخلة. يرجى تقديم مزيد من التفاصيل حول طبي[...]
              aria_label: "تنبيه: تعذر تصنيف نوع الدعوى لعدم كفاية التفاصيل.",
            },
          }),
        });
      }

      if (body?.session_id && body?.message === "1") {
        await new Promise((resolve) => setTimeout(resolve, 120));
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: "session-1",
            reply: "تم اعتماد نوع الدعوى. يرجى استكمال نموذج البيانات الإلزامية قبل الانتقال إلى الصياغة.",
            phase: 1,
            session_status: "INTERVIEW",
            completion_percentage: 0,
            extracted_data: {},
            flags: {
              needs_human_review: false,
              critical_issues: [],
              missing_fields: ["بيانات المدعي", "تفاصيل النزاع"],
              guard_issues: [],
            },
            next_action: "fill_form",
            metadata: {},
            suggestions: [],
            classification: {
              case_path: ["أحوال شخصية", "التصني�� العام", "إقامة حارس قضائي"],
            },
            interview_form: form,
            inline_notice: null,
          }),
        });
      }

      await new Promise((resolve) => setTimeout(resolve, 120));
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
          interview_form: null,
          inline_notice: null,
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
      lastDraftPayload = body;
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
            model: "o3",
            metadata: {
              petition_role: body?.petition_role || "agent",
            },
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
                title: "يمكن تحسين الوقائع",
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

async function waitForLLMOverlayToClose(page) {
  const overlay = page.locator("#llm-config-overlay");

  // Ensure the overlay is no longer visible.
  await overlay.waitFor({ state: "hidden" });
  await expect(overlay).toBeHidden();

  // If the overlay stays mounted, it should be aria-hidden.
  await expect(overlay).toHaveAttribute("aria-hidden", "true");

  // And it must not be able to intercept pointer events.
  await expect.poll(async () => {
    return overlay.evaluate((el) => getComputedStyle(el).pointerEvents);
  }).toBe("none");
}

async function chooseLLMConfig(page) {
  await expect(page.locator("#llm-config-overlay")).toBeVisible();
  await expect(page.locator("#llm-config-title")).toContainText("اختر مزود الذكاء");
  await expect(page.locator("#llm-model-options")).toContainText("GPT O3");
  await expect(page.locator("#llm-model-options")).toContainText("GPT 5.2");
  await expect(page.locator("#llm-model-options")).toContainText("GPT 5.4");
  await expect(page.locator("#llm-model-options")).not.toContainText("GPT-5.4 Mini");

  await page.getByRole("button", { name: "Google Gemini" }).click();
  await expect(page.locator("#llm-model-options")).toContainText("Gemini 2.5 Pro");
  await expect(page.locator("#llm-model-options")).toContainText("Gemini 3 Pro Preview");
  await expect(page.locator("#llm-model-options")).not.toContainText("Gemini 2.5 Flash");

  await page.getByRole("button", { name: "OpenAI" }).click();
  await page.locator("#llm-config-save-btn").click();

  await expect(page.locator("#message-input")).toBeEnabled();
  await expect(page.locator("#send-btn")).toBeEnabled();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__openedUrl = "";
    window.open = (url) => {
      window.__openedUrl = url;
      return null;
    };
  });

  await mockApi(page);
});

test("renders the curated model list and form-first lawsuit flow", async ({ page }) => {
  await page.goto("/");
  await chooseLLMConfig(page);

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("#messages")).toContainText("مرحبًا");

  await page.locator("#message-input").fill("أريد رفع دعوى على تركة متنازع عليها.");
  await page.locator("#send-btn").click({ force: true });
  await expect(page.locator(".message-card.pending")).toBeVisible();
  await expect(page.locator(".suggestion-card")).toContainText("إقامة حارس قضائي");

  await page.locator(".suggestion-card .btn").click();
  await expect(page.locator("#interview-form-panel")).toBeVisible();
  await expect(page.locator("#supports-panel")).toBeVisible();
  await expect(page.locator("#message-form")).toBeHidden();
  await expect(page.locator("#phase-title")).toContainText("استكمال نموذج الدعوى");
  await expect(page.locator("#interview-form-panel")).toContainText("سؤال إضافي");

  const firstSupportDetails = page.locator(".support-item-details").first();
  await expect(firstSupportDetails).toHaveAttribute("aria-hidden", "true");

  await page.locator("#supports-expand-all-btn").click();
  await expect(page.locator(".support-item-details.is-open")).toHaveCount(2);

  await page.locator("#supports-collapse-all-btn").click();
  await expect(page.locator(".support-item-details.is-open")).toHaveCount(0);

  await page.locator(".support-toggle-btn").first().click();
  await expect(firstSupportDetails).toHaveAttribute("aria-hidden", "false");

  const partyField = page.locator("#interview-field-auth_01");
  await partyField.click();
  await page.keyboard.type("Nawaf");
  await expect(partyField).toHaveValue("Nawaf");
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.id || ""))
    .toBe("interview-field-auth_01");
  await page
    .locator("#interview-field-auth_02")
    .fill("يوجد نزاع على إدارة التركة وطلب تعيين حارس قضائي.");
  await page.getByLabel("نعم").check();
  await page.locator("#interview-form-submit-btn").click();

  await expect(page.locator("#draft-role-panel")).toBeVisible();
  await expect(page.locator("#draft-role-actions")).toBeVisible();
  await expect(page.locator("#draft-btn")).toBeDisabled();

  await page.getByRole("button", { name: "وكيل" }).click();
  await expect(page.locator("#draft-btn")).toBeEnabled();

  await page.locator("#draft-btn").click();
  await expect(page.locator("#phase2-panel")).toBeVisible();
  expect(lastDraftPayload?.petition_role).toBe("agent");
  await expect(page.locator("#petition-content .petition-viewer")).toContainText(
    "وقائع مولدة عبر البث."
  );

  await page.locator("#review-btn").click();
  await expect(page.locator("#phase3-panel")).toBeVisible();
  await expect(page.locator("#review-issues-list")).toContainText("يمكن تحسين الوقائع");

  await page.locator("#review-issues-list .btn").click();
  await expect(page.locator("#score-number")).toContainText("92");

  await page.locator("#export-pdf-btn").click();
  await expect
    .poll(() => page.evaluate(() => window.__openedUrl))
    .toContain("/api/petitions/session-1/export/pdf");
});

test("shows an inline ambiguity warning and keeps discovery chat active", async ({ page }) => {
  await page.goto("/");
  await chooseLLMConfig(page);

  await page.locator("#message-input").fill("وصف غامض");
  await page.locator("#send-btn").click({ force: true });

  await expect(page.locator(".classification-warning-card")).toBeVisible();
  await expect(page.locator(".classification-warning-card")).toContainText(
    "لم نتمكن من تحديد نوع ورقة الدعوى"
  );
  await expect(page.locator(".suggestion-card")).toHaveCount(0);
  await expect(page.locator("#message-input")).toBeEnabled();
  await expect(page.locator("#interview-form-panel")).toBeHidden();
});

test("supports manual classification on mobile and switches directly to form mode", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await chooseLLMConfig(page);

  const mainSelect = page.locator("#main-select");
  await mainSelect.scrollIntoViewIfNeeded();
  await mainSelect.selectOption("main-01");

  const subSelect = page.locator("#sub-select");
  await subSelect.scrollIntoViewIfNeeded();
  await subSelect.selectOption("sub-01");

  const caseSelect = page.locator("#case-select");
  await caseSelect.scrollIntoViewIfNeeded();
  await caseSelect.selectOption("case-01");
  await page.locator("#manual-select-btn").click();

  await expect(page.locator("#interview-form-panel")).toBeVisible();
  await expect(page.locator("#supports-panel")).toBeVisible();
  await expect(page.locator("#messages")).toBeHidden();
  await expect(page.locator("#phase-title")).toContainText("استكمال نموذج الدعوى");
});

test("renders yes-no controls even when a boolean field arrives without options", async ({ page }) => {
  const malformedForm = cloneInterviewForm();
  malformedForm.fields.splice(2, 0, {
    key: "auth_03",
    label: "هل قدم المدعى عليه ورقة تجارية للمدعي ومتعلقة بالدعوى؟- في حال كان المدعي مقرض -.",
    hint: "اختر الإجابة الأقرب لما ورد في المستندات أو الوقائع المتاحة.",
    placeholder: "",
    aria_label:
      "حقل إلزامي: هل قدم المدعى عليه ورقة تجارية للمدعي ومتعلقة بالدعوى؟- في حال كان المدعي مقرض -.",
    input_type: "radio",
    group_id: "case_details",
    group_label: "تفاصيل الدعوى",
    required: true,
    source: "authentic",
    badge_label: null,
    options: [],
  });

  await page.unroute("**/api/**");
  await mockApi(page, malformedForm);

  await page.goto("/");
  await chooseLLMConfig(page);

  await page.locator("#message-input").fill("أريد رفع دعوى على تركة متنازع عليها.");
  await page.locator("#send-btn").click({ force: true });
  await page.locator(".suggestion-card .btn").click();

  const loanQuestion = page.locator(".interview-form-field").filter({
    hasText: "هل قدم المدعى عليه ورقة تجارية للمدعي ومتعلقة بالدعوى؟- في حال كان المدعي مقرض -.",
  });

  await expect(loanQuestion).toBeVisible();
  await expect(loanQuestion.locator('input[type="radio"]')).toHaveCount(2);
  await expect(loanQuestion).toContainText("نعم");
  await expect(loanQuestion).toContainText("لا");
});
