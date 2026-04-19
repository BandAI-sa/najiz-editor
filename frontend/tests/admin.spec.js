import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/admin/petitions*", async (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get("q") || "";
    const status = url.searchParams.get("status") || "";

    const records = [
      {
        petition_id: "petition-1",
        session_id: "session-1",
        version: 2,
        model: "gpt-5.4-mini",
        created_at: "2026-04-18T00:00:00Z",
        updated_at: "2026-04-18T00:10:00Z",
        session_updated_at: "2026-04-18T00:11:00Z",
        session_status: "REVIEW",
        phase: 3,
        case_title: "إقامة حارس قضائي",
        case_path: ["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
        review_score: 88,
        issue_count: 1,
        extracted_field_count: 4,
        message_count: 6,
        preview: "وقائع الدعوى الأولى مع تفاصيل موجزة عن النزاع.",
      },
      {
        petition_id: "petition-2",
        session_id: "session-2",
        version: 1,
        model: null,
        created_at: "2026-04-17T18:00:00Z",
        updated_at: "2026-04-17T18:15:00Z",
        session_updated_at: "2026-04-17T18:16:00Z",
        session_status: "DRAFT_READY",
        phase: 2,
        case_title: "مطالبة مالية",
        case_path: ["تجاري", "عقود", "مطالبة مالية"],
        review_score: null,
        issue_count: 0,
        extracted_field_count: 2,
        message_count: 3,
        preview: "صحيفة مطالبة مالية جاهزة للمراجعة النهائية.",
      },
    ].filter((item) => {
      const queryMatch =
        !query ||
        `${item.case_title} ${item.session_id} ${item.preview}`.toLowerCase().includes(query.toLowerCase());
      const statusMatch = !status || item.session_status === status;
      return queryMatch && statusMatch;
    });

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: records,
        total: records.length,
        stats: {
          total_petitions: records.length,
          total_sessions: records.length,
          completed_sessions: 0,
          average_review_score: records.some((item) => item.review_score !== null) ? 88 : null,
        },
      }),
    });
  });

  await page.route("**/api/admin/petitions/petition-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        petition: {
          petition_id: "petition-1",
          session_id: "session-1",
          version: 2,
          model: "gpt-5.4-mini",
          facts: { title: "الوقائع", content: "وقائع مفصلة عن النزاع بين الأطراف." },
          evidence: { title: "الأسانيد", content: "نصوص نظامية ومرفقات داعمة." },
          requests: { title: "الطلبات", content: "تعيين حارس قضائي وإلزام الخصوم بالتسليم." },
          full_text: "نص كامل للصحيفة",
          review_report: {
            completeness_score: 88,
            recommendation: "جاهزة بعد التعديل",
            summary: "يوجد تنبيه واحد متعلق بصياغة الوقائع.",
            issues: [
              {
                issue_id: "issue-1",
                severity: "تنبيه",
                category: "صياغة الوقائع",
                description: "يلزم توضيح تاريخ بدء النزاع.",
                suggestion: "أضف التاريخ بشكل صريح داخل قسم الوقائع.",
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
            "اسم المدعى عليه": "شركة مثال",
          },
          extracted_field_names: ["اسم المدعي", "اسم المدعى عليه"],
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
  });

  await page.route("**/api/admin/petitions/petition-2", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        petition: {
          petition_id: "petition-2",
          session_id: "session-2",
          version: 1,
          model: null,
          facts: { title: "الوقائع", content: "وقائع مطالبة مالية." },
          evidence: { title: "الأسانيد", content: "عقد وفواتير." },
          requests: { title: "الطلبات", content: "إلزام بالسداد." },
          full_text: "نص كامل",
          review_report: null,
          metadata: {},
          created_at: "2026-04-17T18:00:00Z",
          updated_at: "2026-04-17T18:15:00Z",
        },
        session: {
          session_id: "session-2",
          created_at: "2026-04-17T18:00:00Z",
          updated_at: "2026-04-17T18:16:00Z",
          status: "DRAFT_READY",
          phase: 2,
          classification: {
            main_id: "main-2",
            sub_id: "sub-2",
            case_id: "case-2",
            main_title: "تجاري",
            sub_title: "عقود",
            case_title: "مطالبة مالية",
            case_path: ["تجاري", "عقود", "مطالبة مالية"],
          },
          extracted_data: {
            "رقم العقد": "44",
          },
          extracted_field_names: ["رقم العقد"],
          completion_percentage: 80,
          message_count: 3,
          petition_version: 1,
          flags: {
            needs_human_review: false,
            critical_issues: [],
            missing_fields: ["قيمة المطالبة"],
            guard_issues: [],
          },
          metadata: {},
        },
      }),
    });
  });
});

test("renders admin dashboard, filters results, and opens petition details", async ({ page }) => {
  await page.goto("/admin.html");

  await expect(page.locator("h1")).toContainText("لوحة إدارة الصحف المحفوظة");
  await expect(page.locator("#metric-total-petitions")).toContainText("2");
  await expect(page.locator("#admin-petition-list")).toContainText("إقامة حارس قضائي");
  await expect(page.locator('[data-petition-id="petition-1"] .admin-model-row')).toContainText("Generated by");
  await expect(page.locator('[data-petition-id="petition-1"] .admin-tag-model')).toContainText("gpt-5.4-mini");
  await expect(page.locator('[data-petition-id="petition-1"] .admin-tag-model')).toHaveCSS(
    "background-color",
    "rgb(250, 238, 218)"
  );
  await expect(page.locator('[data-petition-id="petition-2"] .admin-tag-model')).toContainText("Unknown model");
  await expect(page.locator('[data-petition-id="petition-2"] .admin-tag-model')).toHaveCSS(
    "background-color",
    "rgb(241, 239, 232)"
  );
  await expect(page.locator("#admin-detail")).toContainText("صياغة الوقائع");
  await expect(page.locator("#admin-detail .admin-tag-model")).toContainText("gpt-5.4-mini");

  await page.locator("#admin-status-select").selectOption("DRAFT_READY");
  await expect(page.locator("#admin-petition-list")).toContainText("مطالبة مالية");
  await expect(page.locator("#admin-petition-list")).not.toContainText("إقامة حارس قضائي");
  await expect(page.locator("#admin-detail .admin-tag-model")).toContainText("Unknown model");

  await page.locator("#admin-search-input").fill("session-1");
  await page.locator("#admin-status-select").selectOption("");
  await expect(page.locator("#admin-petition-list")).toContainText("إقامة حارس قضائي");

  await page.locator('[data-petition-id="petition-1"]').click();
  await expect(page.locator("#admin-detail")).toContainText("اسم المدعي");
  await expect(page.locator("#admin-detail")).toContainText("فتح PDF");
});
