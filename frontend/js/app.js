import { createChatComponent } from "./components/chat.js";
import { createClassificationComponent } from "./components/classification.js";
import { createPetitionComponent } from "./components/petition.js";
import { createProgressComponent } from "./components/progress.js";
import { createReviewComponent } from "./components/review.js";
import { createPhase1Controller } from "./phases/phase1.js";
import { createPhase2Controller } from "./phases/phase2.js";
import { createPhase3Controller } from "./phases/phase3.js";
import { resetState, subscribe, updateState } from "./state.js";

const phase1 = createPhase1Controller();
const phase2 = createPhase2Controller();
const phase3 = createPhase3Controller();

const chatComponent = createChatComponent({
  container: document.getElementById("messages"),
  form: document.getElementById("message-form"),
  input: document.getElementById("message-input"),
  onSubmit: (value) => phase1.sendMessage(value),
});

const classificationComponent = createClassificationComponent(
  {
    mainSelect: document.getElementById("main-select"),
    subSelect: document.getElementById("sub-select"),
    caseSelect: document.getElementById("case-select"),
    manualButton: document.getElementById("manual-select-btn"),
    suggestionsPanel: document.getElementById("suggestions-panel"),
  },
  {
    onMainChange: (mainId) => phase1.onMainChange(mainId),
    onSubChange: (subId) => phase1.onSubChange(subId),
    onCaseChange: (caseId) => phase1.onCaseChange(caseId),
    onManualSubmit: () => phase1.onManualSubmit(),
    onSuggestionSelect: (rank) => phase1.onSuggestionSelect(rank),
  }
);

const progressComponent = createProgressComponent({
  label: document.getElementById("progress-label"),
  bar: document.getElementById("progress-bar"),
  value: document.getElementById("progress-value"),
  count: document.getElementById("missing-fields-count"),
  extractedFields: document.getElementById("extracted-fields"),
  guardAlerts: document.getElementById("guard-alerts"),
});

const petitionComponent = createPetitionComponent(
  {
    panel: document.getElementById("phase2-panel"),
    content: document.getElementById("petition-content"),
    reviewButton: document.getElementById("review-btn"),
    editButton: document.getElementById("edit-petition-btn"),
    saveButton: document.getElementById("save-petition-btn"),
    statusLabel: document.getElementById("petition-status"),
    tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
  },
  {
    onTabChange: (tab) => phase2.onTabChange(tab),
    onReview: () => phase2.onReview(),
    onContentInput: (section, value) => phase2.onContentInput(section, value),
    onEditActive: () => phase2.onEditActive(),
    onSaveActive: () => phase2.onSaveActive(),
  }
);

const reviewComponent = createReviewComponent(
  {
    panel: document.getElementById("phase3-panel"),
    scoreCircle: document.getElementById("review-score-circle"),
    scoreNumber: document.getElementById("score-number"),
    recommendation: document.getElementById("review-recommendation"),
    summary: document.getElementById("review-summary-text"),
    issuesList: document.getElementById("review-issues-list"),
    exportMdButton: document.getElementById("export-md-btn"),
    exportPdfButton: document.getElementById("export-pdf-btn"),
  },
  {
    onAutoFix: (issue) => phase3.onAutoFix(issue),
    onExport: (format) => phase3.onExport(format),
  }
);

const phaseTitle = document.getElementById("phase-title");
const draftButton = document.getElementById("draft-btn");
const newSessionButton = document.getElementById("new-session-btn");

draftButton.addEventListener("click", () => phase2.startDraft());
newSessionButton.addEventListener("click", async () => {
  resetState();
  await phase1.bootstrap();
});

subscribe((state) => {
  chatComponent.render(state);
  classificationComponent.render(state);
  progressComponent.render(state);
  petitionComponent.render(state);
  reviewComponent.render(state);

  phaseTitle.textContent =
    state.currentPhase === 1
      ? "مرحلة التصنيف والاستجواب"
      : state.currentPhase === 2
        ? "مرحلة الصياغة"
        : "مرحلة المراجعة";

  draftButton.disabled = state.currentStep !== "go_to_phase2" && state.currentPhase < 2;
  document.getElementById("phase2-panel").classList.toggle(
    "hidden",
    state.currentPhase < 2 &&
      !state.petition.facts &&
      !state.petition.evidence &&
      !state.petition.requests &&
      !state.petition.isGenerating
  );
  document.getElementById("phase3-panel").classList.toggle("hidden", !state.review.isReady && state.currentPhase < 3);
});

updateState((draft) => {
  draft.chat.push({
    role: "assistant",
    content: "مرحبًا. صف لي وقائع الدعوى أو اختر التصنيف يدويًا لنبدأ.",
    timestamp: new Date().toISOString(),
  });
});

phase1.bootstrap();
