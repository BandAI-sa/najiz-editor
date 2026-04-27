import { getState } from "./state.js";

const DEFAULT_BASE_URL = `${window.location.origin}/api`;
const BASE_URL = (window.NAJIZ_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");

function getLLMSelection() {
  const { llm } = getState();
  if (!llm.selectedProvider || !llm.selectedModel) {
    return null;
  }

  return {
    provider: llm.selectedProvider,
    model: llm.selectedModel,
  };
}

function buildLLMHeaders() {
  const selection = getLLMSelection();
  if (!selection) {
    return {};
  }

  return {
    "X-LLM-Provider": selection.provider,
    "X-LLM-Model": selection.model,
  };
}

function buildLLMQuery() {
  const selection = getLLMSelection();
  const params = new URLSearchParams();
  if (!selection) {
    return params;
  }

  params.set("llm_provider", selection.provider);
  params.set("llm_model", selection.model);
  return params;
}

async function apiCall(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...buildLLMHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload.message || "حدث خطأ في الطلب.";
    throw new Error(message);
  }

  return payload;
}

export const configAPI = {
  getLLMConfig: () => apiCall("/config/llm"),
};

export const healthAPI = {
  get: () => apiCall("/health"),
};

export const classificationsAPI = {
  getMainClassifications: () => apiCall("/classifications/"),
  getSubs: (mainId) => apiCall(`/classifications/${mainId}/subs`),
  getCases: (mainId, subId) => apiCall(`/classifications/${mainId}/${subId}/cases`),
  getCaseDetails: (caseId) => apiCall(`/classifications/case/${caseId}`),
};

export const sessionsAPI = {
  create: () => apiCall("/sessions/", { method: "POST" }),
  get: (id) => apiCall(`/sessions/${id}`),
  updateClassification: (id, payload) =>
    apiCall(`/sessions/${id}/classification`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  submitInterviewForm: (id, values) =>
    apiCall(`/sessions/${id}/interview-form`, {
      method: "PATCH",
      body: JSON.stringify({ values }),
    }),
};

export const agentAPI = {
  message: (sessionId, message, phase) =>
    apiCall("/agent/message", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        message,
        phase,
      }),
    }),
  classify: (sessionId, message) =>
    apiCall("/agent/classify", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message, phase: 1 }),
    }),
  draft: (sessionId, petitionRole) =>
    apiCall("/agent/draft", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, petition_role: petitionRole || undefined }),
    }),
  review: (sessionId) =>
    apiCall("/agent/review", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    }),
  fix: (sessionId, issueId, instruction) =>
    apiCall("/agent/fix", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, issue_id: issueId, instruction }),
    }),
  streamDraft(sessionId, handlers) {
    const params = buildLLMQuery();
    params.set("session_id", sessionId);
    const eventSource = new EventSource(`${BASE_URL}/agent/draft/stream?${params.toString()}`);
    let completed = false;
    let handledError = false;
    const types = ["start", "chunk", "end", "complete", "error"];

    types.forEach((type) => {
      eventSource.addEventListener(type, (event) => {
        const payload = JSON.parse(event.data);
        handlers?.onEvent?.(payload);

        if (type === "error") {
          handledError = true;
          handlers?.onError?.(payload);
          eventSource.close();
          return;
        }

        if (type === "complete") {
          completed = true;
          handlers?.onDone?.(payload);
          eventSource.close();
        }
      });
    });

    eventSource.onerror = () => {
      if (completed || handledError || eventSource.readyState === EventSource.CLOSED) {
        return;
      }
      handledError = true;
      handlers?.onError?.(new Error("تعذر متابعة البث."));
      eventSource.close();
    };

    return eventSource;
  },
};

export const petitionsAPI = {
  getLatest: (sessionId) => apiCall(`/petitions/${sessionId}`),
  updateSection: (sessionId, section, content) =>
    apiCall(`/petitions/${sessionId}/sections`, {
      method: "PATCH",
      body: JSON.stringify({ section, content }),
    }),
  exportUrl: (sessionId) => `${BASE_URL}/petitions/${sessionId}/export`,
  exportMdUrl: (sessionId) => `${BASE_URL}/petitions/${sessionId}/export/md`,
  exportPdfUrl: (sessionId) => `${BASE_URL}/petitions/${sessionId}/export/pdf`,
};

export const adminAPI = {
  listPetitions: ({ q = "", status = "", limit } = {}) => {
    const params = new URLSearchParams();
    if (q.trim()) {
      params.set("q", q.trim());
    }
    if (status) {
      params.set("status", status);
    }
    if (Number.isInteger(limit)) {
      params.set("limit", String(limit));
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiCall(`/admin/petitions${suffix}`);
  },
  getPetition: (petitionId) => apiCall(`/admin/petitions/${petitionId}`),
  deletePetition: (petitionId) =>
    apiCall(`/admin/petitions/${petitionId}`, {
      method: "DELETE",
    }),
};
