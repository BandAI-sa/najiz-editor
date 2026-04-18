import { expect, test } from "@playwright/test";

test("deletes a petition from the admin dashboard and refreshes the active detail", async ({ page }) => {
  const records = [
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
  ];

  const details = {
    "petition-1": {
      petition: {
        petition_id: "petition-1",
        session_id: "session-1",
        version: 2,
        facts: { title: "الوقائع", content: "وقائع مفصلة عن النزاع بين الأطراف." },
        evidence: { title: "الأسانيد", content: "نصوص نظامية ومرفقات داعمة." },
        requests: { title: "الطلبات", content: "تعيين حارس قضائي وإلزام الخصوم بالتسليم." },
        full_text: "نص كامل للصحيفة",
        review_report: {
          completeness_score: 88,
          recommendation: "جاهزة بعد التعديل",
          summary: "يوجد تنبيه واحد متعلق بصياغة الوقائع.",
          issues: [],
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
    },
    "petition-2": {
      petition: {
        petition_id: "petition-2",
        session_id: "session-2",
        version: 1,
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
    },
  };

  await page.route("**/api/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname.endsWith("/api/admin/petitions")) {
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
    }

    const petitionId = url.pathname.split("/").pop();
    if (method === "GET" && petitionId && details[petitionId]) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(details[petitionId]),
      });
    }

    if (method === "DELETE" && petitionId === "petition-1") {
      records.splice(
        0,
        records.length,
        ...records.filter((item) => item.petition_id !== "petition-1")
      );
      delete details["petition-1"];

      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          petition_id: "petition-1",
          session_id: "session-1",
          remaining_petitions_in_session: 0,
          deleted_session: true,
          deleted_message_count: 6,
        }),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        message: "not found",
      }),
    });
  });

  page.on("dialog", (dialog) => dialog.accept());

  await page.goto("/admin.html");

  await expect(page.locator("#admin-petition-list")).toContainText("إقامة حارس قضائي");
  await page.locator('[data-petition-id="petition-1"]').click();
  await expect(page.locator("#admin-detail")).toContainText("إقامة حارس قضائي");

  await page.locator('[data-delete-petition-id="petition-1"]').click();

  await expect(page.locator("#admin-list-status")).toContainText("تم حذف الصحيفة بنجاح");
  await expect(page.locator("#admin-petition-list")).not.toContainText("إقامة حارس قضائي");
  await expect(page.locator("#admin-petition-list")).toContainText("مطالبة مالية");
  await expect(page.locator("#admin-detail")).toContainText("مطالبة مالية");
});
