import { configAPI } from "./api.js";
import { createChatComponent } from "./components/chat.js";
import { createClassificationComponent } from "./components/classification.js";
import { createDraftRoleComponent } from "./components/draft-role.js";
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
      suggested_models: ["gpt-5.4", "gpt-5.2", "gpt-5.2-chat-latest", "gpt-5.4-mini", "gpt-5.4-nano"],
      models: [
        {
          id: "gpt-5.4",
          label: "GPT-5.4",
          summary: "Flagship OpenAI preset for the strongest reasoning and legal drafting quality.",
          tier: "flagship",
          stage: "stable",
          notes: "Best fit when quality matters more than latency or cost.",
          recommended: true,
        },
        {
          id: "gpt-5.2",
          label: "GPT-5.2",
          summary: "High-end GPT-5 family model for professional writing and complex analysis.",
          tier: "advanced",
          stage: "stable",
          notes: "A strong heavier option below GPT-5.4 for demanding tasks.",
          recommended: false,
        },
        {
          id: "gpt-5.2-chat-latest",
          label: "GPT-5.2 Chat Latest",
          summary: "ChatGPT-tuned GPT-5.2 alias for more conversational behavior.",
          tier: "chat",
          stage: "alias",
          notes: "Alias model that may move with newer GPT-5.2 chat snapshots.",
          recommended: false,
        },
        {
          id: "gpt-5.4-mini",
          label: "GPT-5.4 Mini",
          summary: "Balanced lower-latency option that still handles strong reasoning well.",
          tier: "balanced",
          stage: "stable",
          notes: "Good default when you want speed without dropping too much quality.",
          recommended: false,
        },
        {
          id: "gpt-5.4-nano",
          label: "GPT-5.4 Nano",
          summary: "Fastest and cheapest GPT-5.4-family preset for lighter, high-volume requests.",
          tier: "fast",
          stage: "stable",
          notes: "Best for quick iterations and lower-cost workloads.",
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
          summary: "Most capable Gemini preset here for deeper reasoning and harder drafting tasks.",
          tier: "flagship",
          stage: "preview",
          notes: "Preview model; quality is high, but behavior and availability can change.",
          recommended: false,
        },
        {
          id: "gemini-3-flash-preview",
          label: "Gemini 3 Flash Preview",
          summary: "Newer Gemini preview with a strong speed-to-quality balance.",
          tier: "balanced",
          stage: "preview",
          notes: "Preview model tuned for fast, capable general work.",
          recommended: false,
        },
        {
          id: "gemini-2.5-pro",
          label: "Gemini 2.5 Pro",
          summary: "Stable advanced Gemini model for complex legal reasoning and long-form drafting.",
          tier: "advanced",
          stage: "stable",
          notes: "The strongest stable Gemini preset in this app.",
          recommended: false,
        },
        {
          id: "gemini-2.5-flash",
          label: "Gemini 2.5 Flash",
          summary: "Stable default with strong price-performance for general legal workflows.",
          tier: "balanced",
          stage: "stable",
          notes: "Best balance for everyday use if you prefer Gemini.",
          recommended: true,
        },
        {
          id: "gemini-2.5-flash-lite",
          label: "Gemini 2.5 Flash-Lite",
          summary: "Fastest budget-friendly Gemini preset for lower-latency tasks.",
          tier: "fast",
          stage: "stable",
          notes: "Useful when responsiveness matters more than maximum depth.",
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
    summary: "Model option discovered from backend suggestions.",
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
  return requestedModel?.trim() || provider?.default_model || "";
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
        draft.llm.draftModel = provider.default_model;
      });
    },
    onModelSelect: (modelId) => {
      updateState((draft) => {
        draft.llm.draftModel = modelId;
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
  draftRoleComponent.render(state);
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
  if (state.currentStep === "select_petition_role") {
    phaseTitle.textContent = "مرحلة اختيار صيغة الدعوى";
    draftButton.textContent = state.petition.roleSelection
      ? `بدء الصياغة بصيغة ${resolveDraftRoleLabel(state.petition.roleSelection)}`
      : "اختر نوع الصياغة أولًا";
    draftButton.disabled = !state.petition.roleSelection;
  } else {
    draftButton.textContent = "بدء الصياغة";
  }
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
  const llmConfig = normalizeLLMConfig(await configAPI.getLLMConfig().catch(() => FALLBACK_LLM_CONFIG));
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
  const fallbackConfig = normalizeLLMConfig(FALLBACK_LLM_CONFIG);
  updateState((draft) => {
    draft.llm.ready = true;
    draft.llm.providers = fallbackConfig.providers;
    draft.llm.hasSavedSelection = true;
    draft.llm.chooserOpen = false;
    draft.llm.canDismissChooser = true;
    draft.llm.selectedProvider = fallbackConfig.current_provider;
    draft.llm.selectedModel = fallbackConfig.current_model;
    draft.llm.draftProvider = fallbackConfig.current_provider;
    draft.llm.draftModel = fallbackConfig.current_model;
  });
  persistLLMSelection({
    provider: fallbackConfig.current_provider,
    model: fallbackConfig.current_model,
  });
  return bootstrapClassifications();
});
