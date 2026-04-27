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

function applyResponseState(response, { pushToChat = true } = {}) {
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
      draft.interview.form = draft.interview.form;
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

  if (pushToChat) {
    pushChatMessage("assistant", response.reply);
  }
}

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
        applyResponseState(response);
      } catch (error) {
        pushChatMessage(
          "assistant",
          error instanceof Error ? error.message : "تعذر إتمام الطلب حالياً. حاول مرة أخرى."
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
      const interviewForm = session.interview_form || null;
      const formValues = buildFormValues(interviewForm, session.extracted_data || {});
      const supportState = readStoredSupportState(session.session_id, interviewForm);

      updateState((draft) => {
        draft.currentPhase = 1;
        draft.currentStep = interviewForm ? "fill_form" : "ask_field";
        draft.sessionId = session.session_id;
        draft.classification.selectedPath = session.classification.case_path.join(" > ");
        draft.classification.warning = session.inline_notice || null;
        draft.interview.extractedData = session.extracted_data || {};
        draft.interview.form = interviewForm;
        draft.interview.formValues = formValues;
        draft.interview.formErrors = {};
        draft.interview.submitState = "idle";
        draft.interview.submitMessage = interviewForm
          ? "أكمل جميع الحقول الإلزامية ثم اعتمد البيانات للمتابعة."
          : "تم اعتماد التصنيف اليدوي.";
        draft.interview.supportState = supportState;
        draft.interview.missingFields = computeMissingFields(interviewForm, formValues);
        draft.interview.completion = computeCompletion(interviewForm, formValues);
        draft.interview.currentPrompt = interviewForm
          ? interviewForm.description
          : "تم اعتماد التصنيف اليدوي.";
        draft.petition.roleSelection = "";
      });

      persistSupportState(session.session_id, supportState);
    },

    async onSuggestionSelect(rank) {
      await this.sendMessage(String(rank));
    },

    onFormFieldInput(fieldKey, value) {
      updateState((draft) => {
        draft.interview.formValues[fieldKey] = value;
        delete draft.interview.formErrors[fieldKey];
        draft.classification.warning = null;
        draft.interview.submitState = "idle";
        draft.interview.submitMessage = "";
        draft.interview.completion = computeCompletion(draft.interview.form, draft.interview.formValues);
        draft.interview.missingFields = computeMissingFields(draft.interview.form, draft.interview.formValues);
      });
    },

    onToggleSupport(supportId, expanded) {
      const state = getState();
      updateState((draft) => {
        draft.interview.supportState.expandedById[supportId] = expanded;
        draft.interview.supportState.expandAll = Object.values(
          draft.interview.supportState.expandedById
        ).every(Boolean);
      });
      persistSupportState(state.sessionId, getState().interview.supportState);
    },

    onExpandAllSupports(expanded) {
      const state = getState();
      updateState((draft) => {
        const nextMap = {};
        (draft.interview.form?.support_items || []).forEach((item) => {
          nextMap[item.support_id] = expanded;
        });
        draft.interview.supportState.expandedById = nextMap;
        draft.interview.supportState.expandAll = expanded;
      });
      persistSupportState(state.sessionId, getState().interview.supportState);
    },

    async onSubmitForm() {
      const state = getState();
      if (!state.sessionId || !state.interview.form) {
        return;
      }

      const errors = validateForm(state.interview.form, state.interview.formValues);
      if (Object.keys(errors).length > 0) {
        updateState((draft) => {
          draft.interview.formErrors = errors;
          draft.interview.submitState = "error";
          draft.interview.submitMessage = "يرجى استكمال الحقول الإلزامية الموضحة أدناه.";
          draft.interview.completion = computeCompletion(draft.interview.form, draft.interview.formValues);
          draft.interview.missingFields = computeMissingFields(draft.interview.form, draft.interview.formValues);
        });
        return;
      }

      updateState((draft) => {
        draft.loading = true;
        draft.loadingMessage = "يجري اعتماد بيانات الدعوى والتحقق منها...";
      });

      try {
        const response = await sessionsAPI.submitInterviewForm(state.sessionId, state.interview.formValues);
        applyResponseState(response, { pushToChat: false });
      } finally {
        updateState((draft) => {
          draft.loading = false;
          draft.loadingMessage = "";
        });
      }
    },
  };
}
