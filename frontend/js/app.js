import { configAPI } from "./api.js";
import { createChatComponent } from "./components/chat.js";
import { createClassificationComponent } from "./components/classification.js";
import { createDraftRoleComponent } from "./components/draft-role.js";
import { createInterviewFormComponent } from "./components/interview-form.js";
import { createLLMConfigComponent } from "./components/llm-config.js";
import { createPetitionComponent } from "./components/petition.js";
import { createProgressComponent } from "./components/progress.js";
import { createReviewComponent } from "./components/review.js";
import { createPhase1Controller } from "./phases/phase1.js";
import { createPhase2Controller } from "./phases/phase2.js";
import { createPhase3Controller } from "./phases/phase3.js";
import { getState, resetState, subscribe, updateState } from "./state.js";

const LLM_SELECTION_STORAGE_KEY = "najiz.llm.selection";

const FALLBACK_LLM_CONFIG = {
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
          summary: "نموذج مخصص للاستدلال القانوني العميق وتحليل الوقائع المعقدة.",
          tier: "flagship",
          stage: "stable",
          notes: "مناسب عندما تكون دقة التحليل مقدمة على السرعة.",
          recommended: true,
        },
        {
          id: "gpt-5.2",
          label: "GPT 5.2",
          summary: "خيار احترافي متوازن للصياغة القانونية والتحليل المطول.",
          tier: "advanced",
          stage: "stable",
          notes: "يوفر جودة قوية في التحرير مع تكلفة أقل من GPT 5.4.",
          recommended: false,
        },
        {
          id: "gpt-5.4",
          label: "GPT 5.4",
          summary: "إصدار متقدم للصياغة القانونية المهنية والعمل الذي يحتاج دقة تحرير عالية.",
          tier: "advanced",
          stage: "stable",
          notes: "خيار مناسب للحالات التي تحتاج صياغة نهائية عالية الجودة.",
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
          summary: "خيار Gemini الأساسي للاستدلال القانوني وصياغة المسودات المطولة.",
          tier: "advanced",
          stage: "stable",
          notes: "الاختيار المعتمد من Gemini للمهام القانونية اليومية والمعقدة.",
          recommended: true,
        },
        {
          id: "gemini-3-pro-preview",
          label: "Gemini 3 Pro Preview",
          summary: "معاينة متقدمة من Gemini للمهام التي تحتاج استدلالًا أوسع وتجربة أحدث.",
          tier: "flagship",
          stage: "preview",
          notes: "إصدار معاينة وقد تتغير سلوكياته أو إتاحته مع التحديثات اللاحقة.",
          recommended: false,
        },
      ],
    },
  ],
};

function normalizeProviderModels(provider) {
  if (Array.isArray(provider.models) && provider.models.length > 0) {
    return provider.models;
  }

  return (provider.suggested_models || []).map((modelId) => ({
    id: modelId,
    label: modelId,
    summary: "نموذج معتمد من الإعدادات الحالية.",
    tier: "custom",
    stage: "custom",
    notes: "",
    recommended: modelId === provider.default_model,
  }));
}

function normalizeLLMConfig(config) {
  return {
    ...config,
    providers: (config.providers || []).map((provider) => ({
      ...provider,
      models: normalizeProviderModels(provider),
      suggested_models: provider.suggested_models || normalizeProviderModels(provider).map((model) => model.id),
    })),
  };
}

function readStoredLLMSelection() {
  try {
    const raw = window.localStorage.getItem(LLM_SELECTION_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    if (typeof parsed?.provider !== "string" || typeof parsed?.model !== "string") {
      return null;
    }

    return {
      provider: parsed.provider.trim().toLowerCase(),
      model: parsed.model.trim(),
    };
  } catch {
    return null;
  }
}

function persistLLMSelection(selection) {
  window.localStorage.setItem(LLM_SELECTION_STORAGE_KEY, JSON.stringify(selection));
}

function findPreferredProvider(providers, requestedProvider) {
  return (
    providers.find((provider) => provider.id === requestedProvider && provider.enabled) ||
    providers.find((provider) => provider.enabled) ||
    providers.find((provider) => provider.id === requestedProvider) ||
    providers[0] ||
    null
  );
}

function resolveModel(provider, requestedModel) {
  if (!provider) {
    return "";
  }

  const matched =
    provider.models.find((model) => model.id === requestedModel?.trim()) ||
    provider.models.find((model) => model.id === provider.default_model) ||
    provider.models[0] ||
    null;

  return matched?.id || "";
}

function resolveDraftRoleLabel(role) {
  if (role === "agent") {
    return "وكيل";
  }
  if (role === "principal") {
    return "أصيل";
  }
  return "";
}

function resolvePhaseTitle(state) {
  if (state.currentStep === "fill_form") {
    return "مرحلة استكمال نموذج الدعوى";
  }
  if (state.currentStep === "select_petition_role") {
    return "مرحلة اختيار صيغة الدعوى";
  }
  if (state.currentPhase === 1) {
    return "مرحلة التصنيف";
  }
  if (state.currentPhase === 2) {
    return "مرحلة الصياغة";
  }
  return "مرحلة المراجعة";
}

function seedWelcomeMessage() {
  updateState((draft) => {
    if (draft.chat.length > 0) {
      return;
    }

    draft.chat.push({
      role: "assistant",
      content: "مرحبًا. صف لي وقائع الدعوى أو اختر التصنيف يدويًا لنبدأ.",
      timestamp: new Date().toISOString(),
    });
  });
}

const phase1 = createPhase1Controller();
const phase2 = createPhase2Controller();
const phase3 = createPhase3Controller();

let hasBootstrapped = false;

async function bootstrapClassifications() {
  if (hasBootstrapped) {
    return;
  }

  await phase1.bootstrap();
  hasBootstrapped = true;
}

const llmConfigComponent = createLLMConfigComponent(
  {
    statusBar: document.getElementById("llm-status-bar"),
    statusProvider: document.getElementById("llm-status-provider"),
    statusModel: document.getElementById("llm-status-model"),
    changeButton: document.getElementById("llm-config-change-btn"),
    overlay: document.getElementById("llm-config-overlay"),
    providerOptions: document.getElementById("llm-provider-options"),
    modelInput: document.getElementById("llm-model-input"),
    modelOptions: document.getElementById("llm-model-options"),
    hint: document.getElementById("llm-config-hint"),
    saveButton: document.getElementById("llm-config-save-btn"),
    cancelButton: document.getElementById("llm-config-cancel-btn"),
  },
  {
    onOpen: () => {
      updateState((draft) => {
        draft.llm.chooserOpen = true;
        draft.llm.canDismissChooser = draft.llm.hasSavedSelection;
        draft.llm.draftProvider = draft.llm.selectedProvider || draft.llm.draftProvider;
        draft.llm.draftModel = draft.llm.selectedModel || draft.llm.draftModel;
      });
    },
    onCancel: () => {
      updateState((draft) => {
        if (!draft.llm.canDismissChooser) {
          return;
        }

        draft.llm.chooserOpen = false;
        draft.llm.draftProvider = draft.llm.selectedProvider;
        draft.llm.draftModel = draft.llm.selectedModel;
      });
    },
    onProviderSelect: (providerId) => {
      updateState((draft) => {
        const provider = draft.llm.providers.find((item) => item.id === providerId);
        if (!provider || !provider.enabled) {
          return;
        }

        draft.llm.draftProvider = provider.id;
        draft.llm.draftModel = resolveModel(provider, provider.default_model);
      });
    },
    onModelSelect: (modelId) => {
      updateState((draft) => {
        const provider = draft.llm.providers.find((item) => item.id === draft.llm.draftProvider);
        if (!provider?.models.some((model) => model.id === modelId)) {
          return;
        }
        draft.llm.draftModel = modelId;
      });
    },
    onSave: async () => {
      const state = getState();
      const provider = state.llm.providers.find(
        (item) => item.id === state.llm.draftProvider && item.enabled
      );
      const model = resolveModel(provider, state.llm.draftModel);
      if (!provider || !model) {
        return;
      }

      persistLLMSelection({ provider: provider.id, model });
      updateState((draft) => {
        draft.llm.hasSavedSelection = true;
        draft.llm.chooserOpen = false;
        draft.llm.canDismissChooser = true;
        draft.llm.selectedProvider = provider.id;
        draft.llm.selectedModel = model;
        draft.llm.draftProvider = provider.id;
        draft.llm.draftModel = model;
      });

      await bootstrapClassifications();
    },
  }
);

const chatComponent = createChatComponent({
  container: document.getElementById("messages"),
  form: document.getElementById("message-form"),
  input: document.getElementById("message-input"),
  submitButton: document.getElementById("send-btn"),
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

const draftRoleComponent = createDraftRoleComponent(
  {
    panel: document.getElementById("draft-role-panel"),
    options: document.getElementById("draft-role-options"),
    hint: document.getElementById("draft-role-hint"),
  },
  {
    onSelect: (role) =>
      updateState((draft) => {
        draft.petition.roleSelection = role;
        draft.petition.saveState = "idle";
        draft.petition.saveMessage = "";
      }),
  }
);

const interviewFormComponent = createInterviewFormComponent(
  {
    panel: document.getElementById("interview-form-panel"),
    path: document.getElementById("interview-form-path"),
    title: document.getElementById("interview-form-title"),
    description: document.getElementById("interview-form-description"),
    status: document.getElementById("interview-form-status"),
    groupsContainer: document.getElementById("interview-form-groups"),
    submitButton: document.getElementById("interview-form-submit-btn"),
    supportsPanel: document.getElementById("supports-panel"),
    supportsList: document.getElementById("supports-list"),
    expandAllButton: document.getElementById("supports-expand-all-btn"),
    collapseAllButton: document.getElementById("supports-collapse-all-btn"),
  },
  {
    onFieldInput: (fieldKey, value) => phase1.onFormFieldInput(fieldKey, value),
    onToggleSupport: (supportId, expanded) => phase1.onToggleSupport(supportId, expanded),
    onExpandAllSupports: (expanded) => phase1.onExpandAllSupports(expanded),
    onSubmit: () => phase1.onSubmitForm(),
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
const draftRoleActions = document.getElementById("draft-role-actions");
const phase2Panel = document.getElementById("phase2-panel");
const phase3Panel = document.getElementById("phase3-panel");
const newSessionButton = document.getElementById("new-session-btn");

draftButton.addEventListener("click", () => phase2.startDraft());
newSessionButton.addEventListener("click", async () => {
  resetState();
  seedWelcomeMessage();
  hasBootstrapped = false;
  await bootstrapClassifications();
});

subscribe((state) => {
  llmConfigComponent.render(state);
  chatComponent.render(state);
  classificationComponent.render(state);
  draftRoleComponent.render(state);
  interviewFormComponent.render(state);
  progressComponent.render(state);
  petitionComponent.render(state);
  reviewComponent.render(state);

  phaseTitle.textContent = resolvePhaseTitle(state);

  const showDraftRoleActions = state.currentStep === "select_petition_role";
  draftRoleActions.classList.toggle("hidden", !showDraftRoleActions);
  if (showDraftRoleActions) {
    draftButton.textContent = state.petition.roleSelection
      ? `بدء الصياغة بصيغة ${resolveDraftRoleLabel(state.petition.roleSelection)}`
      : "اختر نوع الصياغة أولًا";
    draftButton.disabled = !state.petition.roleSelection || state.loading;
  } else {
    draftButton.textContent = "بدء الصياغة";
    draftButton.disabled = true;
  }

  phase2Panel.classList.toggle(
    "hidden",
    state.currentPhase < 2 &&
      !state.petition.facts &&
      !state.petition.evidence &&
      !state.petition.requests &&
      !state.petition.isGenerating
  );
  phase3Panel.classList.toggle("hidden", !state.review.isReady && state.currentPhase < 3);
});

seedWelcomeMessage();

async function applyLLMConfig(llmConfig) {
  const storedSelection = readStoredLLMSelection();
  const preferredProvider = findPreferredProvider(
    llmConfig.providers,
    storedSelection?.provider || llmConfig.current_provider
  );
  const selectedProvider = preferredProvider?.id || llmConfig.current_provider;
  const selectedModel = resolveModel(
    preferredProvider,
    storedSelection?.provider === selectedProvider ? storedSelection.model : llmConfig.current_model
  );
  const hasSavedSelection = Boolean(
    storedSelection &&
      storedSelection.provider === selectedProvider &&
      storedSelection.model === selectedModel
  );

  updateState((draft) => {
    draft.llm.ready = true;
    draft.llm.providers = llmConfig.providers;
    draft.llm.hasSavedSelection = hasSavedSelection;
    draft.llm.chooserOpen = !hasSavedSelection;
    draft.llm.canDismissChooser = hasSavedSelection;
    draft.llm.selectedProvider = selectedProvider;
    draft.llm.selectedModel = selectedModel;
    draft.llm.draftProvider = selectedProvider;
    draft.llm.draftModel = selectedModel;
  });

  if (hasSavedSelection) {
    persistLLMSelection({ provider: selectedProvider, model: selectedModel });
    await bootstrapClassifications();
  }
}

async function initializeLLMConfig() {
  try {
    const llmConfig = normalizeLLMConfig(await configAPI.getLLMConfig());
    await applyLLMConfig(llmConfig);
  } catch {
    await applyLLMConfig(normalizeLLMConfig(FALLBACK_LLM_CONFIG));
  }
}

initializeLLMConfig();
