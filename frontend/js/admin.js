import { adminAPI, petitionsAPI } from "./api.js";

const SEARCH_DEBOUNCE_MS = 250;

const elements = {
  refreshButton: document.getElementById("admin-refresh-btn"),
  filterForm: document.getElementById("admin-filter-form"),
  searchInput: document.getElementById("admin-search-input"),
  statusSelect: document.getElementById("admin-status-select"),
  listMeta: document.getElementById("admin-list-meta"),
  listStatus: document.getElementById("admin-list-status"),
  list: document.getElementById("admin-petition-list"),
  detail: document.getElementById("admin-detail"),
  metricTotalPetitions: document.getElementById("metric-total-petitions"),
  metricTotalSessions: document.getElementById("metric-total-sessions"),
  metricCompletedSessions: document.getElementById("metric-completed-sessions"),
  metricAverageScore: document.getElementById("metric-average-score"),
};

const state = {
  items: [],
  stats: null,
  selectedId: "",
  detail: null,
  listError: "",
  detailError: "",
  loadingList: false,
  loadingDetail: false,
  filters: {
    q: "",
    status: "",
  },
};

let searchTimer = null;

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] || character;
  });
}

function formatDate(value) {
  if (!value) {
    return "غير متاح";
  }

  try {
    return new Intl.DateTimeFormat("ar-SA", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatScore(value) {
  if (value === null || value === undefined) {
    return "بدون تقييم";
  }
  return `${value}%`;
}

function formatPhase(value) {
  if (!value) {
    return "غير محددة";
  }

  const labels = {
    1: "المرحلة الأولى",
    2: "المرحلة الثانية",
    3: "المرحلة الثالثة",
  };
  return labels[value] || `المرحلة ${value}`;
}

function renderMetrics() {
  const stats = state.stats || {
    total_petitions: 0,
    total_sessions: 0,
    completed_sessions: 0,
    average_review_score: null,
  };

  elements.metricTotalPetitions.textContent = stats.total_petitions ?? 0;
  elements.metricTotalSessions.textContent = stats.total_sessions ?? 0;
  elements.metricCompletedSessions.textContent = stats.completed_sessions ?? 0;
  elements.metricAverageScore.textContent =
    stats.average_review_score === null || stats.average_review_score === undefined
      ? "--"
      : `${stats.average_review_score}%`;
}

function renderListMeta() {
  if (state.loadingList) {
    elements.listMeta.textContent = "جاري تحميل الصحف المحفوظة...";
    return;
  }

  if (state.listError) {
    elements.listMeta.textContent = "تعذر تحميل الفهرس.";
    return;
  }

  elements.listMeta.textContent = `تم العثور على ${state.items.length} صحيفة في النطاق الحالي.`;
}

function renderListStatus() {
  if (state.listError) {
    elements.listStatus.innerHTML = `<div class="admin-inline-message error">${escapeHtml(state.listError)}</div>`;
    return;
  }

  if (!state.loadingList && state.items.length === 0) {
    elements.listStatus.innerHTML =
      '<div class="admin-inline-message">لا توجد صحف مطابقة للبحث الحالي. جرّب توسيع نطاق البحث أو إزالة الفلاتر.</div>';
    return;
  }

  elements.listStatus.innerHTML = "";
}

function buildTag(label, tone = "") {
  const toneClass = tone ? ` ${tone}` : "";
  return `<span class="admin-tag${toneClass}">${escapeHtml(label)}</span>`;
}

function renderList() {
  renderListMeta();
  renderListStatus();

  if (state.loadingList) {
    elements.list.innerHTML = Array.from({ length: 3 })
      .map(
        () => `
          <div class="admin-record admin-record-skeleton">
            <div class="skeleton-line short"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
          </div>
        `
      )
      .join("");
    return;
  }

  if (state.listError || state.items.length === 0) {
    elements.list.innerHTML = "";
    return;
  }

  elements.list.innerHTML = state.items
    .map((item) => {
      const tags = [
        item.session_status ? buildTag(item.session_status) : "",
        buildTag(`الإصدار ${item.version}`),
        item.review_score !== null ? buildTag(`التقييم ${item.review_score}%`, "success") : "",
        item.issue_count ? buildTag(`${item.issue_count} ملاحظات`, "warning") : "",
      ]
        .filter(Boolean)
        .join("");

      const activeClass = item.petition_id === state.selectedId ? " is-active" : "";
      return `
        <button type="button" class="admin-record${activeClass}" data-petition-id="${escapeHtml(item.petition_id)}">
          <div class="admin-record-top">
            <div>
              <strong class="admin-record-title">${escapeHtml(item.case_title || "صحيفة بدون تصنيف")}</strong>
              <div class="admin-record-subtitle">${escapeHtml(item.session_id)}</div>
            </div>
            <span class="admin-record-date">${escapeHtml(formatDate(item.updated_at))}</span>
          </div>
          <p class="admin-record-path">${escapeHtml((item.case_path || []).join(" / ") || "لم يتم اعتماد مسار تصنيف بعد.")}</p>
          <p class="admin-record-preview">${escapeHtml(item.preview || "لا يوجد نص معاينة متاح لهذه الصحيفة.")}</p>
          <div class="admin-record-tags">${tags}</div>
        </button>
      `;
    })
    .join("");
}

function buildDefinitionList(entries) {
  if (!entries.length) {
    return '<p class="admin-section-empty">لا توجد بيانات متاحة في هذا القسم.</p>';
  }

  return `
    <div class="admin-keyvals">
      ${entries
        .map(
          ([label, value]) => `
            <div class="admin-keyval">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderReviewIssues(issues = []) {
  if (!issues.length) {
    return '<p class="admin-section-empty">لا توجد ملاحظات قانونية مسجلة على هذه الصحيفة.</p>';
  }

  return `
    <div class="admin-review-list">
      ${issues
        .map(
          (issue) => `
            <article class="review-issue ${escapeHtml(issue.severity === "حرج" ? "critical" : issue.severity === "تنبيه" ? "warning" : "suggestion")}">
              <strong class="review-issue-title">${escapeHtml(issue.category || issue.severity || "ملاحظة")}</strong>
              <p>${escapeHtml(issue.description || "")}</p>
              <p><strong>المعالجة المقترحة:</strong> ${escapeHtml(issue.suggestion || "لا توجد توصية إضافية.")}</p>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderDetail() {
  if (state.loadingDetail) {
    elements.detail.innerHTML = `
      <div class="admin-detail-loading">
        <div class="spinner"></div>
        <p class="petition-loading-label">جاري تحميل تفاصيل الصحيفة...</p>
      </div>
    `;
    return;
  }

  if (state.detailError) {
    elements.detail.innerHTML = `<div class="admin-empty-state error">${escapeHtml(state.detailError)}</div>`;
    return;
  }

  if (!state.detail) {
    elements.detail.innerHTML = `
      <div class="admin-empty-state">
        اختر صحيفة من القائمة لعرض نص الدعوى، البيانات المستخرجة، وسجل المراجعة القانونية.
      </div>
    `;
    return;
  }

  const { petition, session } = state.detail;
  const classificationPath = session?.classification?.case_path?.join(" / ") || "لم يتم اعتماد التصنيف بعد.";
  const sessionFacts = [
    ["رقم الجلسة", session?.session_id || petition.session_id],
    ["حالة الجلسة", session?.status || "غير متاحة"],
    ["المرحلة الحالية", formatPhase(session?.phase)],
    ["عدد الرسائل", String(session?.message_count ?? 0)],
    ["الحقول المستخرجة", String(session?.extracted_field_names?.length ?? 0)],
    ["آخر تحديث للجلسة", formatDate(session?.updated_at)],
  ];
  const petitionFacts = [
    ["معرّف الصحيفة", petition.petition_id],
    ["الإصدار", String(petition.version)],
    ["تاريخ الإنشاء", formatDate(petition.created_at)],
    ["آخر تحديث", formatDate(petition.updated_at)],
    ["درجة المراجعة", formatScore(petition.review_report?.completeness_score)],
    ["عدد الملاحظات", String(petition.review_report?.issues?.length ?? 0)],
  ];
  const extractedDataEntries = Object.entries(session?.extracted_data || {}).map(([label, value]) => [
    label,
    typeof value === "string" ? value : JSON.stringify(value),
  ]);

  elements.detail.innerHTML = `
    <div class="admin-detail-header">
      <div>
        <p class="eyebrow">تفاصيل السجل</p>
        <h2>${escapeHtml(session?.classification?.case_title || "صحيفة محفوظة")}</h2>
        <p class="admin-detail-path">${escapeHtml(classificationPath)}</p>
      </div>
      <div class="admin-detail-actions">
        <a class="btn btn-secondary" href="${escapeHtml(
          petitionsAPI.exportUrl(petition.session_id)
        )}" target="_blank" rel="noopener noreferrer">عرض HTML</a>
        <a class="btn btn-primary" href="${escapeHtml(
          petitionsAPI.exportPdfUrl(petition.session_id)
        )}" target="_blank" rel="noopener noreferrer">فتح PDF</a>
      </div>
    </div>

    <section class="admin-section">
      <h3>ملخص تشغيلي</h3>
      <div class="admin-info-grid">
        <div class="admin-info-block">
          <h4>بيانات الجلسة</h4>
          ${buildDefinitionList(sessionFacts)}
        </div>
        <div class="admin-info-block">
          <h4>بيانات الصحيفة</h4>
          ${buildDefinitionList(petitionFacts)}
        </div>
      </div>
    </section>

    <section class="admin-section">
      <h3>البيانات المستخرجة</h3>
      ${buildDefinitionList(extractedDataEntries)}
    </section>

    <section class="admin-section">
      <h3>النص الكامل</h3>
      <div class="admin-text-grid">
        <article class="admin-text-block">
          <h4>${escapeHtml(petition.facts.title || "الوقائع")}</h4>
          <p class="petition-text">${escapeHtml(petition.facts.content || "لا توجد وقائع معروضة.")}</p>
        </article>
        <article class="admin-text-block">
          <h4>${escapeHtml(petition.evidence.title || "الأسانيد")}</h4>
          <p class="petition-text">${escapeHtml(petition.evidence.content || "لا توجد أسانيد معروضة.")}</p>
        </article>
        <article class="admin-text-block">
          <h4>${escapeHtml(petition.requests.title || "الطلبات")}</h4>
          <p class="petition-text">${escapeHtml(petition.requests.content || "لا توجد طلبات معروضة.")}</p>
        </article>
      </div>
    </section>

    <section class="admin-section">
      <h3>المراجعة القانونية</h3>
      <p class="admin-review-summary">${escapeHtml(
        petition.review_report?.summary || "لم يتم تسجيل ملخص مراجعة لهذه الصحيفة بعد."
      )}</p>
      ${renderReviewIssues(petition.review_report?.issues || [])}
    </section>
  `;
}

function syncUrl() {
  const url = new URL(window.location.href);
  if (state.selectedId) {
    url.searchParams.set("petition", state.selectedId);
  } else {
    url.searchParams.delete("petition");
  }
  history.replaceState({}, "", url);
}

async function loadDetail(petitionId) {
  state.selectedId = petitionId || "";
  state.detailError = "";
  state.loadingDetail = Boolean(petitionId);
  if (!petitionId) {
    state.detail = null;
    renderList();
    renderDetail();
    syncUrl();
    return;
  }

  renderList();
  renderDetail();
  syncUrl();

  try {
    state.detail = await adminAPI.getPetition(petitionId);
  } catch (error) {
    state.detail = null;
    state.detailError = error.message || "تعذر تحميل تفاصيل الصحيفة.";
  } finally {
    state.loadingDetail = false;
    renderList();
    renderDetail();
  }
}

async function loadList() {
  state.loadingList = true;
  state.listError = "";
  renderMetrics();
  renderList();
  renderDetail();

  try {
    const payload = await adminAPI.listPetitions({
      q: state.filters.q,
      status: state.filters.status,
    });
    state.items = payload.items || [];
    state.stats = payload.stats || null;

    const hasSelection = state.items.some((item) => item.petition_id === state.selectedId);
    const nextId = hasSelection ? state.selectedId : state.items[0]?.petition_id || "";

    state.loadingList = false;
    renderMetrics();
    renderList();
    await loadDetail(nextId);
    return;
  } catch (error) {
    state.items = [];
    state.stats = null;
    state.detail = null;
    state.selectedId = "";
    state.loadingList = false;
    state.listError = error.message || "تعذر تحميل قائمة الصحف.";
  }

  renderMetrics();
  renderList();
  renderDetail();
}

function scheduleSearch() {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    loadList().catch(() => {});
  }, SEARCH_DEBOUNCE_MS);
}

function initializeFromUrl() {
  const url = new URL(window.location.href);
  state.selectedId = url.searchParams.get("petition") || "";
}

function attachEvents() {
  elements.refreshButton.addEventListener("click", () => {
    loadList().catch(() => {});
  });

  elements.filterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    state.filters.q = elements.searchInput.value.trim();
    state.filters.status = elements.statusSelect.value;
    loadList().catch(() => {});
  });

  elements.searchInput.addEventListener("input", () => {
    state.filters.q = elements.searchInput.value.trim();
    scheduleSearch();
  });

  elements.statusSelect.addEventListener("change", () => {
    state.filters.status = elements.statusSelect.value;
    loadList().catch(() => {});
  });

  elements.list.addEventListener("click", (event) => {
    const target = event.target.closest("[data-petition-id]");
    if (!target) {
      return;
    }

    const petitionId = target.getAttribute("data-petition-id");
    loadDetail(petitionId).catch(() => {});
  });
}

initializeFromUrl();
attachEvents();
renderMetrics();
renderList();
renderDetail();
loadList().catch(() => {
  renderMetrics();
  renderList();
  renderDetail();
});
