import { agentAPI, classificationsAPI, sessionsAPI } from "../api.js";
import { getState, pushChatMessage, updateState } from "../state.js";

const SUPPORT_STATE_STORAGE_PREFIX = "najiz.support-state";

function buildLoadingMessage(state) {
  if (state.currentPhase === 1 && state.currentStep === "welcome") {
    return "يجري تحليل الوقائع واستخراج أقرب تصنيف مناسب...";
  }

  if (state.currentPhase === 1) {
    return "يجري تحليل إجابتك وتجهيز الرد التالي...";
  }

  return "يجري تجهيز الرد الآن...";
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
      errors[field.key] = "هذا الحقل إلزامي.";
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
      draft.interview.completion = response.completion_percentage ?? draft.interview.completion;
      draft.interview.missingFields = response.flags?.missing_fields || [];
    }

    if (response.next_action === "fill_form") {
      draft.interview.formErrors = response.metadata?.form_errors || {};
      draft.interview.submitState = response.inline_notice ? "error" : "idle";
      draft.interview.submitMessage =
        response.inline_notice?.message || "أكمل جميع الحقول الإلزامية ثم اعتمد البيانات للمتابعة.";
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

  pushChatMessage("assistant", response.reply);
}

function applyAgentResponse(response) {
  const awaitingDraftRole = response.next_action === "go_to_phase2" && !response.petition;
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
  pushChatMessage("assistant", response.reply);
}

function applyResponse(response) {
  if (response.intake_mode === "structured" && response.interview_form) {
    applyFormResponse(response);
  } else {
    applyAgentResponse(response);
  }
}

// ── Exported helpers for app.js ─────────────────────────────────────

export {
  buildFormValues,
  computeCompletion,
  computeMissingFields,
  persistSupportState,
  readStoredSupportState,
  validateForm,
};

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

      pushChatMessage("user", message);
      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage = buildLoadingMessage(state);
      });

      try {
        const response = await agentAPI.message(state.sessionId, message, state.currentPhase);
        applyResponse(response);
      } catch (error) {
        pushChatMessage(
          "assistant",
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
      const mode = session.intake_mode || "conversational";
      const nextStep = mode === "structured" ? "fill_form" : "select_intake_mode";
      updateState((draft) => {
        draft.currentPhase = 1;
        draft.currentStep = nextStep;
        draft.sessionId = session.session_id;
        draft.classification.selectedPath = session.classification.case_path.join(" > ");
        draft.interview.mode = mode;
        draft.interview.missingFields = session.flags.missing_fields || [];
        draft.interview.currentPrompt = session.metadata.pending_prompt || "تم اعتماد التصنيف اليدوي.";
        draft.interview.form = session.interview_form || null;
        draft.petition.roleSelection = "";
      });
      pushChatMessage("assistant", session.metadata.pending_prompt || "تم اعتماد التصنيف اليدوي.");
    },

    async onIntakeModeSelect(mode) {
      const state = getState();
      const sessionId = state.sessionId;
      if (!sessionId) return;

      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage = "جاري تحديث طريقة الإدخال...";
      });

      try {
        const result = await sessionsAPI.updateIntakeMode(sessionId, mode);
        const session = result.session;
        updateState((draft) => {
          draft.interview.mode = mode;
          if (mode === "structured") {
            draft.currentStep = "fill_form";
            draft.interview.form = session.interview_form || null;
            if (session.interview_form) {
              draft.interview.formValues = buildFormValues(
                session.interview_form,
                session.extracted_data || {},
                draft.interview.formValues
              );
              draft.interview.supportState = readStoredSupportState(sessionId, session.interview_form);
              draft.interview.completion = computeCompletion(session.interview_form, draft.interview.formValues);
              draft.interview.missingFields = computeMissingFields(session.interview_form, draft.interview.formValues);
            }
          } else {
            draft.currentStep = "ask_field";
          }
        });
        if (mode === "conversational" && session.metadata?.pending_prompt) {
          pushChatMessage("assistant", session.metadata.pending_prompt);
        }
      } catch (error) {
        pushChatMessage(
          "assistant",
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
  };
}
