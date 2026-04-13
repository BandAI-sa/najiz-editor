import { agentAPI, petitionsAPI } from "../api.js";
import { getState, pushChatMessage, updateState } from "../state.js";

function setPetitionFromDraft(petition) {
  updateState((draft) => {
    draft.currentPhase = 2;
    draft.petition.petitionId = petition.petition_id;
    draft.petition.version = petition.version;
    draft.petition.facts = petition.facts?.content || "";
    draft.petition.evidence = petition.evidence?.content || "";
    draft.petition.requests = petition.requests?.content || "";
    draft.petition.isGenerating = false;
    draft.petition.saveState = "idle";
    draft.petition.saveMessage = "";
    draft.petition.editMode = false;
    draft.petition.loadingSections = {
      facts: false,
      evidence: false,
      requests: false,
    };
    draft.petition.dirtySections = {
      facts: false,
      evidence: false,
      requests: false,
    };
  });
}

function stopGenerationState(message = "") {
  updateState((draft) => {
    draft.petition.isGenerating = false;
    draft.petition.loadingSections = {
      facts: false,
      evidence: false,
      requests: false,
    };
    draft.petition.saveState = message ? "error" : "idle";
    draft.petition.saveMessage = message;
  });
}

async function saveSection(section) {
  const state = getState();
  if (!state.sessionId || !state.petition.dirtySections[section]) {
    return true;
  }

  updateState((draft) => {
    draft.petition.saveState = "saving";
    draft.petition.saveMessage = "جارٍ حفظ التعديل...";
  });

  try {
    const response = await petitionsAPI.updateSection(state.sessionId, section, state.petition[section]);
    setPetitionFromDraft(response.petition);
    updateState((draft) => {
      draft.petition.activeTab = section;
      draft.petition.editMode = false;
      draft.petition.saveState = "saved";
      draft.petition.saveMessage = "تم حفظ التعديل وإصدار نسخة جديدة.";
      draft.review.isReady = false;
      draft.review.issues = [];
      draft.review.score = null;
      draft.review.recommendation = "";
      draft.review.summary = "";
    });
    return true;
  } catch (error) {
    updateState((draft) => {
      draft.petition.saveState = "error";
      draft.petition.saveMessage = error.message || "تعذر حفظ التعديل.";
    });
    return false;
  }
}

async function tryLoadLatestPetition(sessionId) {
  try {
    const petition = await petitionsAPI.getLatest(sessionId);
    if (petition?.petition_id) {
      setPetitionFromDraft(petition);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

export function createPhase2Controller() {
  return {
    onTabChange(tab) {
      updateState((draft) => {
        draft.petition.activeTab = tab;
        draft.petition.editMode = false;
      });
    },

    onContentInput(section, value) {
      updateState((draft) => {
        draft.petition[section] = value;
        draft.petition.dirtySections[section] = true;
        draft.petition.saveState = "idle";
        draft.petition.saveMessage = "";
        draft.review.isReady = false;
        draft.review.issues = [];
        draft.review.score = null;
        draft.review.recommendation = "";
        draft.review.summary = "";
      });
    },

    onEditActive() {
      updateState((draft) => {
        draft.petition.editMode = true;
      });
    },

    async onSaveActive() {
      const state = getState();
      await saveSection(state.petition.activeTab);
    },

    async startDraft() {
      const state = getState();
      if (!state.sessionId) {
        return;
      }

      updateState((draft) => {
        draft.currentPhase = 2;
        draft.petition.facts = "";
        draft.petition.evidence = "";
        draft.petition.requests = "";
        draft.petition.activeTab = "facts";
        draft.petition.isGenerating = true;
        draft.petition.saveState = "idle";
        draft.petition.saveMessage = "";
        draft.petition.editMode = false;
        draft.petition.loadingSections = {
          facts: true,
          evidence: true,
          requests: true,
        };
        draft.petition.dirtySections = {
          facts: false,
          evidence: false,
          requests: false,
        };
      });
      pushChatMessage("assistant", "جارٍ إعداد مسودة الصحيفة... قد يستغرق هذا بضع ثوانٍ.");

      try {
        const response = await agentAPI.draft(state.sessionId);
        if (response.petition) {
          setPetitionFromDraft(response.petition);
          pushChatMessage("assistant", response.reply);
        } else {
          stopGenerationState("تعذر تحميل النسخة النهائية من الصحيفة.");
        }
      } catch (error) {
        updateState((draft) => {
          draft.petition.saveState = "error";
          draft.petition.saveMessage = error.message || "تعذر توليد الصحيفة.";
        });
        stopGenerationState("حدث خطأ أثناء إعداد المسودة.");
      }
    },

    async onReview() {
      const stateBeforeReview = getState();
      for (const section of ["facts", "evidence", "requests"]) {
        if (stateBeforeReview.petition.dirtySections[section]) {
          const saved = await saveSection(section);
          if (!saved) {
            return;
          }
        }
      }

      const state = getState();
      const response = await agentAPI.review(state.sessionId);
      if (response.review_report) {
        updateState((draft) => {
          draft.currentPhase = 3;
          draft.review.score = response.review_report.completeness_score;
          draft.review.issues = response.review_report.issues;
          draft.review.recommendation = response.review_report.recommendation;
          draft.review.summary = response.review_report.summary;
          draft.review.isReady = true;
        });
        pushChatMessage("assistant", response.reply);
      }
    },
  };
}
