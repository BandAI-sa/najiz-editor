import { agentAPI, classificationsAPI, sessionsAPI } from "../api.js";
import { getState, pushChatMessage, updateState } from "../state.js";

const SUPPORT_STATE_STORAGE_PREFIX = "najiz.support-state";

function createDefaultEnrichmentState() {
  return {
    awaitingDecision: false,
    mode: "none",
    title: "",
    description: "",
    helperText: "",
    canSkip: true,
  };
}

function resolveEnrichmentState(response, interviewForm) {
  const base = createDefaultEnrichmentState();
  const nextAction = response.next_action;
  if (nextAction === "offer_optional_enrichment") {
    return {
      ...base,
      awaitingDecision: true,
      mode: "choice",
      title: "بيانات إضافية اختيارية",
      description:
        "يمكنك إضافة معلومات إضافية لتحسين الصحيفة قبل الصياغة النهائية، أو المتابعة مباشرة.",
      helperText: "هذه الخطوة اختيارية بالكامل وغير مانعة للمتابعة.",
    };
  }

  if (interviewForm?.variant === "supplementary_optional" || nextAction === "fill_supplementary_form") {
    return {
      ...base,
      mode: "form",
      title: "بيانات إضافية اختيارية",
      description: interviewForm?.description || "يمكنك تعبئة ما يتوفر لديك من بيانات إضافية.",
      helperText: interviewForm?.helper_text || "يمكنك ترك أي حقل فارغًا والمتابعة.",
    };
  }

  return base;
}

function buildLoadingMessage(state) {
  if (state.currentPhase === 1 && state.currentStep === "welcome") {
    return "يجري تحليل الوقائع واستخراج أقرب تصنيف مناسب...";
  }

  if (state.currentPhase === 1) {
    return "يجري تحليل إجابتك وتجهيز الرد التالي...";
  }

  return "يجري تجهيز الرد الآن...";
}

function pushAssistantMessage(content) {
  const text = String(content || "").trim();
  if (!text) return;
  const state = getState();
  const last = state.chat[state.chat.length - 1];
  if (last?.role === "assistant" && last.content === text) {
    return;
  }
  pushChatMessage("assistant", text);
}

// ── Structured form helpers (restored from original) ────────────────

function readStoredSupportState(sessionId, form) {
  if (!sessionId || !form) {
    return { expandAll: false, expandedById: {} };
  }

  try {
    const raw = window.sessionStorage.getItem(`${SUPPORT_STATE_STORAGE_PREFIX}:${sessionId}`);
    const parsed = raw ? JSON.parse(raw) : {};
    const expandedById = {};
    (form.support_items || []).forEach((item) => {
      expandedById[item.support_id] = Boolean(parsed.expandedById?.[item.support_id] ?? item.default_expanded);
    });
    const expandAll =
      Object.keys(expandedById).length > 0 && Object.values(expandedById).every((value) => Boolean(value));
    return { expandAll, expandedById };
  } catch {
    return { expandAll: false, expandedById: {} };
  }
}

function persistSupportState(sessionId, supportState) {
  if (!sessionId) {
    return;
  }

  window.sessionStorage.setItem(
    `${SUPPORT_STATE_STORAGE_PREFIX}:${sessionId}`,
    JSON.stringify(supportState)
  );
}

function buildFormValues(form, extractedData, existingValues = {}) {
  if (!form) {
    return {};
  }

  const values = {};
  (form.fields || []).forEach((field) => {
    values[field.key] =
      existingValues[field.key] ??
      extractedData?.[field.label] ??
      "";
  });
  return values;
}

function computeMissingFields(form, values) {
  if (!form) {
    return [];
  }

  return (form.fields || [])
    .filter((field) => field.required && !String(values[field.key] || "").trim())
    .map((field) => field.label);
}

function computeCompletion(form, values) {
  if (!form || !Array.isArray(form.fields)) {
    return 0;
  }

  const requiredFields = form.fields.filter((field) => field.required);
  if (requiredFields.length === 0) {
    return 100;
  }

  const completed = requiredFields.filter((field) => String(values[field.key] || "").trim()).length;
  return Math.round((completed / requiredFields.length) * 100);
}

function validateForm(form, values) {
  const errors = {};
  if (!form) {
    return errors;
  }

  (form.fields || []).forEach((field) => {
    const value = String(values[field.key] || "").trim();
    if (field.required && !value) {
      errors[field.key] = "يرجى إكمال هذا الحقل.";
      return;
    }

    if (field.input_type === "date" && value && !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      errors[field.key] = "يرجى إدخال التاريخ بصيغة صحيحة.";
      return;
    }

    if (field.input_type === "radio" && value) {
      const allowedValues = new Set((field.options || []).map((option) => option.value));
      if (!allowedValues.has(value)) {
        errors[field.key] = "يرجى اختيار إجابة صحيحة.";
      }
    }
  });

  return errors;
}

// ── Response handlers ───────────────────────────────────────────────

function applyFormResponse(response) {
  const awaitingDraftRole = response.next_action === "go_to_phase2" && !response.petition;
  const responseForm = response.interview_form || null;
  const enrichmentState = resolveEnrichmentState(response, responseForm);

  updateState((draft) => {
    draft.sessionId = response.session_id;
    draft.currentPhase = awaitingDraftRole ? 1 : response.phase;
    draft.currentStep = awaitingDraftRole ? "select_petition_role" : response.next_action;
    draft.classification.suggestions = response.suggestions || [];
    draft.classification.warning = response.inline_notice || null;

    if (response.classification) {
      draft.classification.selectedPath = response.classification.case_path.join(" > ");
    }

    draft.interview.extractedData = response.extracted_data || {};
    draft.interview.currentPrompt = awaitingDraftRole
      ? "اكتملت البيانات المطلوبة. اختر صيغة صحيفة الدعوى للمتابعة."
      : response.reply;
    draft.flags.needsHumanReview = response.flags?.needs_human_review || false;
    draft.flags.criticalIssues = response.flags?.critical_issues || [];
    draft.flags.guardIssues = response.flags?.guard_issues || [];
    draft.interview.enrichment = awaitingDraftRole ? createDefaultEnrichmentState() : enrichmentState;

    if (responseForm) {
      draft.interview.form = responseForm;
      draft.interview.formValues = buildFormValues(
        responseForm,
        response.extracted_data || {},
        draft.interview.formValues
      );
      draft.interview.supportState = readStoredSupportState(response.session_id, responseForm);
      draft.interview.completion = computeCompletion(responseForm, draft.interview.formValues);
      draft.interview.missingFields = computeMissingFields(responseForm, draft.interview.formValues);
    } else {
      if (response.next_action === "offer_optional_enrichment") {
        draft.interview.form = null;
      }
      draft.interview.completion = response.completion_percentage ?? draft.interview.completion;
      draft.interview.missingFields = response.flags?.missing_fields || [];
    }

    if (response.next_action === "fill_form" || response.next_action === "fill_supplementary_form") {
      draft.interview.formErrors = response.metadata?.form_errors || {};
      draft.interview.submitState = response.inline_notice ? "error" : "idle";
      draft.interview.submitMessage =
        response.inline_notice?.message ||
        (response.next_action === "fill_supplementary_form"
          ? "هذه البيانات اختيارية. يمكنك تعبئة ما يتوفر لديك ثم المتابعة."
          : "أكمل الحقول الأساسية المطلوبة، ثم تابع إلى الصياغة.");
    } else if (response.next_action === "offer_optional_enrichment") {
      draft.interview.formErrors = {};
      draft.interview.submitState = "idle";
      draft.interview.submitMessage = response.inline_notice?.message || response.reply;
    } else if (awaitingDraftRole) {
      draft.interview.formErrors = {};
      draft.interview.submitState = "success";
      draft.interview.submitMessage = response.reply;
      draft.petition.roleSelection = "";
    } else if (response.phase < 2) {
      draft.petition.roleSelection = "";
    }

    if (!awaitingDraftRole && response.phase >= 2) {
      draft.currentPhase = 2;
    }
  });

  pushAssistantMessage(response.reply);
}

function applyAgentResponse(response) {
  const awaitingDraftRole = response.next_action === "go_to_phase2" && !response.petition;
  const enrichmentState = resolveEnrichmentState(response, response.interview_form || null);
  updateState((draft) => {
    draft.sessionId = response.session_id;
    draft.currentPhase = awaitingDraftRole ? 1 : response.phase;
    draft.currentStep = awaitingDraftRole ? "select_petition_role" : response.next_action;
    draft.classification.suggestions = response.suggestions || [];
    if (response.classification) {
      draft.classification.selectedPath = response.classification.case_path.join(" > ");
    }
    draft.interview.extractedData = response.extracted_data || {};
    draft.interview.missingFields = response.flags?.missing_fields || [];
    draft.interview.completion = response.completion_percentage ?? 0;
    draft.interview.currentPrompt = awaitingDraftRole
      ? "هل تريد صياغة الدعوى أصيل أم وكيل؟"
      : response.reply;
    draft.interview.enrichment = awaitingDraftRole ? createDefaultEnrichmentState() : enrichmentState;
    draft.flags.needsHumanReview = response.flags?.needs_human_review || false;
    draft.flags.criticalIssues = response.flags?.critical_issues || [];
    draft.flags.guardIssues = response.flags?.guard_issues || [];
    if (awaitingDraftRole) {
      draft.petition.roleSelection = "";
    } else if (response.phase < 2) {
      draft.petition.roleSelection = "";
    }
    if (!awaitingDraftRole && response.phase >= 2) {
      draft.currentPhase = 2;
    }
  });
  pushAssistantMessage(response.reply);
}

function applyResponse(response) {
  if (
    response.intake_mode === "structured" &&
    (response.interview_form ||
      response.next_action === "offer_optional_enrichment" ||
      response.next_action === "fill_supplementary_form")
  ) {
    applyFormResponse(response);
  } else {
    applyAgentResponse(response);
  }
}

// ── Exported helpers for app.js ─────────────────────────────────────

export {
  applyResponse,
  buildFormValues,
  computeCompletion,
  computeMissingFields,
  persistSupportState,
  readStoredSupportState,
  validateForm,
};

// ── Chat intent bridging ────────────────────────────────────────────

const _ENRICHMENT_ADD_WORDS = new Set([
  "نعم", "أيوه", "ايوه", "اكمل", "أكمل", "إضافة", "اضافة", "add", "yes",
]);
const _ENRICHMENT_SKIP_WORDS = new Set([
  "تخطي", "تخطى", "تجاوز", "لا", "skip", "no",
]);
const _ROLE_PRINCIPAL_WORDS = new Set([
  "أصيل", "اصيل", "principal",
]);
const _ROLE_AGENT_WORDS = new Set([
  "وكيل", "agent",
]);
const _MODE_CHAT_WORDS = new Set([
  "محادثة", "محادثه", "chat", "conversational",
]);
const _MODE_FORM_WORDS = new Set([
  "نموذج", "form", "structured",
]);
let enrichmentDecisionInFlightKey = null;

function matchChatIntent(message, step) {
  const token = message.trim().replace(/[.!؟?،,]+$/g, "").trim();
  const lower = token.toLowerCase();

  if (step === "offer_optional_enrichment") {
    if (lower.includes("إضافة بيانات إضافية") || lower.includes("اضافة بيانات اضافية")) {
      return { action: "enrichment", value: "add" };
    }
    if (_ENRICHMENT_ADD_WORDS.has(lower)) return { action: "enrichment", value: "add" };
    if (_ENRICHMENT_SKIP_WORDS.has(lower)) return { action: "enrichment", value: "skip" };
  }

  if (step === "select_petition_role") {
    if (_ROLE_PRINCIPAL_WORDS.has(lower)) return { action: "role", value: "principal" };
    if (_ROLE_AGENT_WORDS.has(lower)) return { action: "role", value: "agent" };
  }

  if (step === "select_intake_mode") {
    if (_MODE_CHAT_WORDS.has(lower)) return { action: "mode", value: "conversational" };
    if (_MODE_FORM_WORDS.has(lower)) return { action: "mode", value: "structured" };
  }

  return null;
}

// ── Controller ──────────────────────────────────────────────────────

export function createPhase1Controller() {
  return {
    async bootstrap() {
      const mains = await classificationsAPI.getMainClassifications();
      updateState((draft) => {
        draft.classification.mains = mains;
      });
    },

    async sendMessage(message) {
      const state = getState();
      if (state.loading) {
        return;
      }
      let userMessageAlreadyPushed = false;

      const intent = matchChatIntent(message, state.currentStep);
      if (intent) {
        pushChatMessage("user", message);
        userMessageAlreadyPushed = true;
        if (intent.action === "enrichment") {
          const handled = await this.onOptionalEnrichmentDecision(intent.value);
          if (handled) return;
        }
        if (intent.action === "role") {
          updateState((draft) => {
            draft.petition.roleSelection = intent.value;
            draft.petition.saveState = "idle";
            draft.petition.saveMessage = "";
          });
          pushAssistantMessage(
            intent.value === "agent"
              ? "تم اختيار صيغة «وكيل». يمكنك الآن بدء الصياغة."
              : "تم اختيار صيغة «أصيل». يمكنك الآن بدء الصياغة.",
          );
          return;
        }
        if (intent.action === "mode") {
          return this.onIntakeModeSelect(intent.value);
        }
      }

      if (!userMessageAlreadyPushed) {
        pushChatMessage("user", message);
      }
      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage = buildLoadingMessage(state);
      });

      try {
        const response = await agentAPI.message(state.sessionId, message, state.currentPhase);
        applyResponse(response);
      } catch (error) {
        pushAssistantMessage(
          error instanceof Error ? error.message : "تعذر إتمام الطلب حاليًا. حاول مرة أخرى."
        );
      } finally {
        updateState((draft) => {
          draft.loading = false;
          draft.loadingMessage = "";
        });
      }
    },

    async onMainChange(mainId) {
      updateState((draft) => {
        draft.classification.mainId = mainId;
        draft.classification.subId = "";
        draft.classification.caseId = "";
        draft.classification.subs = [];
        draft.classification.cases = [];
      });
      if (!mainId) {
        return;
      }
      const subs = await classificationsAPI.getSubs(mainId);
      updateState((draft) => {
        draft.classification.subs = subs;
      });
    },

    async onSubChange(subId) {
      const state = getState();
      updateState((draft) => {
        draft.classification.subId = subId;
        draft.classification.caseId = "";
        draft.classification.cases = [];
      });
      if (!subId) {
        return;
      }
      const cases = await classificationsAPI.getCases(state.classification.mainId, subId);
      updateState((draft) => {
        draft.classification.cases = cases;
      });
    },

    onCaseChange(caseId) {
      updateState((draft) => {
        draft.classification.caseId = caseId;
      });
    },

    async onManualSubmit() {
      let state = getState();
      let sessionId = state.sessionId;
      if (!sessionId) {
        const created = await sessionsAPI.create();
        sessionId = created.session.session_id;
        updateState((draft) => {
          draft.sessionId = sessionId;
        });
      }

      const sessionPayload = await sessionsAPI.updateClassification(sessionId, {
        main_id: state.classification.mainId,
        sub_id: state.classification.subId,
        case_id: state.classification.caseId,
      });
      const session = sessionPayload.session;
      updateState((draft) => {
        draft.currentPhase = 1;
        draft.currentStep = session.metadata?.pending_next_action || "select_intake_mode";
        draft.sessionId = session.session_id;
        draft.classification.selectedPath = session.classification.case_path.join(" > ");
        draft.interview.missingFields = session.flags.missing_fields || [];
        draft.interview.currentPrompt =
          session.metadata.pending_prompt || "تم اعتماد التصنيف. اختر طريقة إدخال البيانات المناسبة لك.";
        draft.interview.enrichment = createDefaultEnrichmentState();
        draft.petition.roleSelection = "";
      });
      pushAssistantMessage(
        session.metadata.pending_prompt || "تم اعتماد التصنيف. اختر طريقة إدخال البيانات المناسبة لك."
      );
    },

    async onIntakeModeSelect(mode) {
      const state = getState();
      const sessionId = state.sessionId;
      if (!sessionId) return;

      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage = "جاري تفعيل طريقة الإدخال المختارة...";
      });

      try {
        const result = await sessionsAPI.updateIntakeMode(sessionId, mode);
        const session = result.session;
        const pendingNextAction = session.metadata?.pending_next_action || "";
        updateState((draft) => {
          draft.interview.mode = mode;
          draft.interview.enrichment = createDefaultEnrichmentState();
          draft.interview.currentPrompt = session.metadata?.pending_prompt || draft.interview.currentPrompt;
          if (mode === "structured") {
            draft.currentStep = pendingNextAction || "fill_form";
            const shouldShowOffer = pendingNextAction === "offer_optional_enrichment";
            draft.interview.form = shouldShowOffer ? null : session.interview_form || null;
            if (draft.interview.form) {
              draft.interview.formValues = buildFormValues(
                draft.interview.form,
                session.extracted_data || {},
                draft.interview.formValues
              );
              draft.interview.supportState = readStoredSupportState(sessionId, draft.interview.form);
              draft.interview.completion = computeCompletion(draft.interview.form, draft.interview.formValues);
              draft.interview.missingFields = computeMissingFields(draft.interview.form, draft.interview.formValues);
            }
            if (shouldShowOffer) {
              draft.interview.enrichment = {
                awaitingDecision: true,
                mode: "choice",
                title: "بيانات إضافية اختيارية",
                description:
                  "يمكنك إضافة معلومات إضافية لتحسين الصحيفة قبل الصياغة النهائية، أو المتابعة مباشرة.",
                helperText: "هذه الخطوة اختيارية بالكامل وغير مانعة للمتابعة.",
                canSkip: true,
              };
            } else if (pendingNextAction === "go_to_phase2") {
              draft.currentStep = "select_petition_role";
              draft.petition.roleSelection = "";
            }
          } else {
            if (pendingNextAction === "offer_optional_enrichment") {
              draft.currentStep = "offer_optional_enrichment";
              draft.interview.enrichment = {
                awaitingDecision: true,
                mode: "choice",
                title: "بيانات إضافية اختيارية",
                description:
                  "يمكنك إضافة معلومات إضافية لتحسين الصحيفة قبل الصياغة النهائية، أو المتابعة مباشرة.",
                helperText: "هذه الخطوة اختيارية بالكامل وغير مانعة للمتابعة.",
                canSkip: true,
              };
            } else if (pendingNextAction === "go_to_phase2") {
              draft.currentStep = "select_petition_role";
              draft.petition.roleSelection = "";
            } else {
              draft.currentStep = pendingNextAction || "ask_field";
            }
            draft.interview.form = null;
          }
        });
        if (session.metadata?.pending_prompt) {
          pushAssistantMessage(session.metadata.pending_prompt);
        }
      } catch (error) {
        pushAssistantMessage(
          error instanceof Error ? error.message : "تعذر تغيير طريقة الإدخال."
        );
      } finally {
        updateState((draft) => {
          draft.loading = false;
          draft.loadingMessage = "";
        });
      }
    },

    async onSuggestionSelect(rank) {
      await this.sendMessage(String(rank));
    },

    async onOptionalEnrichmentDecision(action) {
      const state = getState();
      if (!state.sessionId || state.loading) {
        return false;
      }
      if (state.currentStep !== "offer_optional_enrichment" || !state.interview.enrichment.awaitingDecision) {
        return false;
      }
      const normalizedAction = action === "add" ? "add" : "skip";
      const decisionKey = `${state.sessionId}:${state.currentStep}:${normalizedAction}`;
      if (enrichmentDecisionInFlightKey === decisionKey) {
        return false;
      }
      enrichmentDecisionInFlightKey = decisionKey;
      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage =
          normalizedAction === "add"
            ? "جاري تجهيز خطوة البيانات الإضافية..."
            : "جاري المتابعة إلى اختيار صيغة الصحيفة...";
        // Hide the decision panel immediately to prevent duplicate clicks/transitions.
        draft.interview.enrichment.awaitingDecision = false;
      });
      try {
        const response = await sessionsAPI.decideOptionalEnrichment(state.sessionId, normalizedAction);
        applyResponse(response);
        return true;
      } catch (error) {
        pushAssistantMessage(
          error instanceof Error ? error.message : "تعذر تحديث خطوة البيانات الإضافية."
        );
        updateState((draft) => {
          if (draft.currentStep === "offer_optional_enrichment") {
            draft.interview.enrichment.awaitingDecision = true;
          }
        });
      } finally {
        enrichmentDecisionInFlightKey = null;
        updateState((draft) => {
          draft.loading = false;
          draft.loadingMessage = "";
        });
      }
      return false;
    },
  };
}
