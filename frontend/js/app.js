import { configAPI } from "./api.js";
import { createChatComponent } from "./components/chat.js";
import { createClassificationComponent } from "./components/classification.js";
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
  current_model: "gpt-5.4-mini",
  providers: [
    {
      id: "openai",
      label: "OpenAI",
      enabled: true,
      default_model: "gpt-5.4-mini",
      suggested_models: ["gpt-5.4-mini", "gpt-5.4", "gpt-5.2"],
    },
    {
      id: "gemini",
      label: "Google Gemini",
      enabled: true,
      default_model: "gemini-2.5-flash",
      suggested_models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
    },
  ],
};

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
  return requestedModel?.trim() || provider?.default_model || "";
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
    modelSuggestions: document.getElementById("llm-model-suggestions"),
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
        draft.llm.draftModel = provider.default_model;
      });
    },
    onModelInput: (value) => {
      updateState((draft) => {
        draft.llm.draftModel = value;
      });
    },
    onSave: async (value) => {
      const state = getState();
      const provider = state.llm.providers.find(
        (item) => item.id === state.llm.draftProvider && item.enabled
      );
      const model = value.trim() || resolveModel(provider, state.llm.draftModel);
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
  seedWelcomeMessage();
  hasBootstrapped = false;
  await bootstrapClassifications();
});

subscribe((state) => {
  llmConfigComponent.render(state);
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
  document.getElementById("phase3-panel").classList.toggle(
    "hidden",
    !state.review.isReady && state.currentPhase < 3
  );
});

seedWelcomeMessage();

async function initializeLLMConfig() {
  const llmConfig = await configAPI.getLLMConfig().catch(() => FALLBACK_LLM_CONFIG);
  const storedSelection = readStoredLLMSelection();
  const preferredProvider = findPreferredProvider(
    llmConfig.providers,
    storedSelection?.provider || llmConfig.current_provider
  );
  const selectedProvider = preferredProvider?.id || llmConfig.current_provider;
  const selectedModel = resolveModel(
    preferredProvider,
    storedSelection?.provider === selectedProvider ? storedSelection.model : ""
  );
  const hasSavedSelection = Boolean(
    storedSelection &&
      storedSelection.provider === selectedProvider &&
      storedSelection.model &&
      selectedModel
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

initializeLLMConfig().catch(() => {
  updateState((draft) => {
    draft.llm.ready = true;
    draft.llm.providers = FALLBACK_LLM_CONFIG.providers;
    draft.llm.hasSavedSelection = true;
    draft.llm.chooserOpen = false;
    draft.llm.canDismissChooser = true;
    draft.llm.selectedProvider = FALLBACK_LLM_CONFIG.current_provider;
    draft.llm.selectedModel = FALLBACK_LLM_CONFIG.current_model;
    draft.llm.draftProvider = FALLBACK_LLM_CONFIG.current_provider;
    draft.llm.draftModel = FALLBACK_LLM_CONFIG.current_model;
  });
  persistLLMSelection({
    provider: FALLBACK_LLM_CONFIG.current_provider,
    model: FALLBACK_LLM_CONFIG.current_model,
  });
  return bootstrapClassifications();
});
