import { agentAPI, classificationsAPI, sessionsAPI } from "../api.js";
import { getState, pushChatMessage, updateState } from "../state.js";

function buildLoadingMessage(state) {
  if (state.currentPhase === 1 && state.currentStep === "welcome") {
    return "يجري تحليل الوقائع واستخراج أقرب تصنيف مناسب...";
  }

  if (state.currentPhase === 1) {
    return "يجري تحليل إجابتك وتجهيز الرد التالي...";
  }

  return "يجري تجهيز الرد الآن...";
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
        applyAgentResponse(response);
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
      updateState((draft) => {
        draft.currentPhase = 1;
        draft.currentStep = "ask_field";
        draft.sessionId = session.session_id;
        draft.classification.selectedPath = session.classification.case_path.join(" > ");
        draft.interview.missingFields = session.flags.missing_fields || [];
        draft.interview.currentPrompt = session.metadata.pending_prompt || "تم اعتماد التصنيف اليدوي.";
        draft.petition.roleSelection = "";
      });
      pushChatMessage("assistant", session.metadata.pending_prompt || "تم اعتماد التصنيف اليدوي.");
    },

    async onSuggestionSelect(rank) {
      await this.sendMessage(String(rank));
    },
  };
}
