import { agentAPI, petitionsAPI } from "../api.js";
import { getState, pushChatMessage, updateState } from "../state.js";

function applyReviewPayload(response) {
  updateState((draft) => {
    if (response.petition) {
      draft.petition.petitionId = response.petition.petition_id;
      draft.petition.version = response.petition.version;
      draft.petition.facts = response.petition.facts?.content || draft.petition.facts;
      draft.petition.evidence = response.petition.evidence?.content || draft.petition.evidence;
      draft.petition.requests = response.petition.requests?.content || draft.petition.requests;
    }
    if (response.review_report) {
      draft.review.score = response.review_report.completeness_score;
      draft.review.issues = response.review_report.issues;
      draft.review.recommendation = response.review_report.recommendation;
      draft.review.summary = response.review_report.summary;
      draft.review.isReady = true;
    }
  });
}

export function createPhase3Controller() {
  return {
    async onAutoFix(issue) {
      const state = getState();
      const response = await agentAPI.fix(state.sessionId, issue.issue_id, issue.suggestion);
      applyReviewPayload(response);
      pushChatMessage("assistant", response.reply);
    },

    onExport(format) {
      const state = getState();
      if (!state.sessionId) {
        return;
      }
      if (format === "md") {
        window.open(petitionsAPI.exportMdUrl(state.sessionId), "_blank", "noopener");
      } else if (format === "pdf") {
        window.open(petitionsAPI.exportPdfUrl(state.sessionId), "_blank", "noopener");
      } else {
        window.open(petitionsAPI.exportUrl(state.sessionId), "_blank", "noopener");
      }
    },
  };
}
