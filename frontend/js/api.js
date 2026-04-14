const DEFAULT_BASE_URL = `${window.location.origin}/api`;
const BASE_URL = (window.NAJIZ_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");

async function apiCall(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
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
  draft: (sessionId) =>
    apiCall("/agent/draft", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
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
    const eventSource = new EventSource(
      `${BASE_URL}/agent/draft/stream?session_id=${encodeURIComponent(sessionId)}`
    );
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
