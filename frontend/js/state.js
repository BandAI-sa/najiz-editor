const initialState = () => ({
  sessionId: null,
  currentPhase: 1,
  currentStep: "welcome",
  loading: false,
  loadingMessage: "",
  llm: {
    ready: false,
    providers: [],
    hasSavedSelection: false,
    chooserOpen: false,
    canDismissChooser: false,
    selectedProvider: "",
    selectedModel: "",
    draftProvider: "",
    draftModel: "",
  },
  classification: {
    mainId: "",
    subId: "",
    caseId: "",
    mains: [],
    subs: [],
    cases: [],
    suggestions: [],
    selectedPath: "",
  },
  interview: {
    extractedData: {},
    completion: 0,
    missingFields: [],
    currentPrompt: "",
  },
  petition: {
    petitionId: null,
    facts: "",
    evidence: "",
    requests: "",
    roleSelection: "",
    activeTab: "facts",
    version: 0,
    isGenerating: false,
    saveState: "idle",
    saveMessage: "",
    editMode: false,
    loadingSections: {
      facts: false,
      evidence: false,
      requests: false,
    },
    dirtySections: {
      facts: false,
      evidence: false,
      requests: false,
    },
  },
  review: {
    score: null,
    issues: [],
    recommendation: "",
    summary: "",
    isReady: false,
  },
  flags: {
    needsHumanReview: false,
    criticalIssues: [],
    guardIssues: [],
  },
  chat: [],
});

const state = initialState();
const listeners = new Set();

function clone(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function emit() {
  const snapshot = clone(state);
  listeners.forEach((listener) => listener(snapshot));
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(clone(state));
  return () => listeners.delete(listener);
}

export function getState() {
  return clone(state);
}

export function updateState(mutator) {
  const draft = clone(state);
  mutator(draft);
  Object.keys(state).forEach((key) => {
    delete state[key];
  });
  Object.assign(state, draft);
  emit();
}

export function resetState(options = {}) {
  const fresh = initialState();
  if (options.preserveLLM !== false) {
    fresh.llm = clone(state.llm);
  }
  Object.keys(state).forEach((key) => {
    delete state[key];
  });
  Object.assign(state, fresh);
  emit();
}

export function pushChatMessage(role, content) {
  updateState((draft) => {
    draft.chat.push({
      role,
      content,
      timestamp: new Date().toISOString(),
    });
  });
}
