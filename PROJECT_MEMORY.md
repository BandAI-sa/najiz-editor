# Najiz Legal AI — Project Memory & Architecture State

> **Purpose**: This is a living engineering memory file. It preserves full architectural context, implementation history, integration decisions, and current system state so that any future engineer or AI session can resume work with minimal ramp-up. **Keep this file updated as the system evolves.**

> **Last Updated**: 2026-05-14
> **Branch**: `hybrid-integration`
> **Base Commit**: `2872daa` (conversational branch)
> **Latest Commit**: `3930915`

---

## 1. System Overview

Najiz is an **AI-powered Saudi legal case petition generator**. Users describe their legal dispute, the system classifies it against Saudi court taxonomy, interviews the user for required data fields, drafts a formal Arabic legal petition (صحيفة دعوى), and offers quality review.

### Core Pipeline

```
User Input → Classification → Interview (Data Collection) → Drafting → Review → Export
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Database | MongoDB 5 (via Motor async driver) |
| LLM | Pluggable: OpenAI / Google Gemini (configurable per session) |
| Frontend | Vanilla JS (ES modules), CSS, no framework |
| Serving | Docker Compose: backend (uvicorn), frontend (nginx), MongoDB |
| Security | AES encryption for `extracted_data` at rest |

### Runtime Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌───────────┐
│  nginx:3000 │──────▶│  uvicorn:8000    │──────▶│  mongo:27017│
│  (frontend) │  /api │  (FastAPI)       │       │  (sessions) │
└─────────────┘       └──────────────────┘       └───────────┘
      │                        │
   static files        app.state.catalog
   from volume          (classification tree)
```

---

## 2. Original System Architecture (main branch)

The original system was a **structured, form-driven** legal intake workflow.

### Session Lifecycle

```
NEW → AWAITING_CLASSIFICATION_CONFIRM → INTERVIEW → READY_TO_DRAFT → DRAFTING → DRAFT_READY → REVIEW → COMPLETE
```

### Phase Model

| Phase | Purpose | Key Service |
|-------|---------|------------|
| Phase 1 | Classification + Interview (data collection) | `Phase1ClassifierService`, `Phase1InterviewerService` |
| Phase 2 | Petition drafting + evidence mapping | `Phase2DrafterService`, `Phase2EvidenceService` |
| Phase 3 | Quality review | `Phase3ReviewerService` |

### Frontend `currentStep` Values

| Step | Meaning |
|------|---------|
| `welcome` | Initial state, no session yet |
| `classify` | User describing facts for AI classification |
| `confirm_classification` | User confirming AI's classification suggestion |
| `select_intake_mode` | **[HYBRID]** User choosing between structured/conversational |
| `fill_form` | Structured form interview (Phase 1) |
| `ask_field` | Conversational interview (Phase 1) |
| `select_petition_role` | Choosing أصيل (principal) vs وكيل (attorney) |
| `go_to_phase2` | Ready to draft |

### Classification Catalog

- Source: `/data/classification_data.json` — Saudi court taxonomy
- 3-level hierarchy: Main Category → Sub Category → Case Type
- Each Case Type has `requirements`: `data_fields[]`, `attachments[]`, `notes[]`
- Loaded at startup, seeded to MongoDB, and cached in `app.state.catalog`

### `extracted_data` — The Universal Contract

**This is the single most important data structure in the system.**

Both intake modes (structured and conversational) populate the same `session.extracted_data: dict[str, Any]` dictionary. This dictionary is the source of truth for the drafting pipeline. Keys are Arabic field labels (e.g., `"اسم المدعي"`, `"تاريخ العقد"`).

```
          ┌──────────────────┐
          │ session.extracted │
          │     _data        │
          └────────┬─────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   Phase2      Phase2     Phase3
   Drafter    Evidence    Reviewer
```

> **WARNING**: Never change how `extracted_data` keys are named without updating the drafter prompts. The drafting LLM receives these keys directly.

---

## 3. Conversational System Additions (feature/test branch)

Commit `2872daa` introduced a comprehensive conversational AI orchestration layer that replaces the simple field-by-field interviewer with an intelligent, context-aware conversation engine.

### New Services (all in `backend/app/services/agent/`)

| Service | File | Purpose |
|---------|------|---------|
| `SmartInterviewerService` | `smart_interviewer.py` (30KB) | Main conversational engine. Extends `Phase1InterviewerService`. Multi-field extraction per turn, adaptive follow-ups. |
| `SemanticAnswerExtractor` | `semantic_extractor.py` | LLM-based extraction of structured data from free-form Arabic text. Returns confidence scores per field. |
| `AnswerValidationLayer` | `answer_validator.py` | Validates extracted answers (format, completeness, plausibility). |
| `ContradictionChecker` | `contradiction_checker.py` | Detects contradictions between new and existing extracted data. |
| `RepetitionGuard` | `repetition_guard.py` | Prevents asking the same question twice. Tracks question history. |
| `ConversationMemoryInjector` | `memory_injector.py` | Injects recent conversation history into LLM context for coherence. |
| `QuestionHumanizer` | `question_humanizer.py` | Rewrites robotic questions into natural Saudi Arabic conversational tone. |
| `CompletenessPolicy` | `completeness_policy.py` | Determines when enough data has been collected to proceed to drafting. |

### Smart Features Toggle

All smart features are individually toggleable via environment variables / settings:

```python
smart_extractor_enabled: bool
answer_validation_enabled: bool
repetition_guard_enabled: bool
memory_injection_enabled: bool
humanized_questions_enabled: bool
completeness_check_enabled: bool
contradiction_check_enabled: bool
```

When ALL are disabled, `SmartInterviewerService` falls back to the base `Phase1InterviewerService` (simple one-field-at-a-time).

### Inheritance Chain

```
Phase1InterviewerService      ← base class (86 lines, simple field extraction)
    └── SmartInterviewerService   ← conversational engine (overrides start/process_turn)
```

> **WARNING**: `phase1_interviewer.py` is NOT dead code. It is the base class for `SmartInterviewerService` and is imported in 3 files. Do NOT delete it.

---

## 4. Hybrid Integration Architecture

### Goal

Users can choose between:
1. **Structured Mode** — dynamic form UI, field-by-field validation
2. **Conversational Mode** — AI-driven Arabic dialogue, multi-field extraction

Both modes populate the same `session.extracted_data`, feeding the identical drafting pipeline.

### Architecture Diagram

```
                    ┌─────────────────────────┐
                    │   AgentOrchestrator      │
                    │                         │
                    │  interviewer: Hybrid     │
                    │   ┌───────────────────┐  │
                    │   │ HybridInterviewer │  │
                    │   │  ┌─────────────┐  │  │
                    │   │  │ .structured  │──┼──┼──▶ StructuredInterviewerService
                    │   │  │ .smart       │──┼──┼──▶ SmartInterviewerService
                    │   │  └─────────────┘  │  │
                    │   └───────────────────┘  │
                    └─────────────────────────┘
                                │
                    session.intake_mode
                    ┌──────┬────────────┐
                    │struct│ conversat. │
                    └──┬───┴─────┬──────┘
                       ▼         ▼
               InterviewForm   Chat turns
               (dynamic form)  (LLM dialogue)
                       │         │
                       ▼         ▼
                session.extracted_data
                       │
                       ▼
                  Phase2Drafter
```

### Key Model: `IntakeMode`

```python
class IntakeMode(StrEnum):
    STRUCTURED = "structured"
    CONVERSATIONAL = "conversational"
```

Default: `CONVERSATIONAL` — backward compatible with existing sessions.

### `HybridInterviewerService` (dispatch proxy)

File: `backend/app/services/agent/hybrid_interviewer.py` (55 lines)

The orchestrator is unaware of modes. It calls `start()`/`process_turn()` on the `HybridInterviewerService`, which checks `session.intake_mode` and dispatches to the correct backend.

```python
async def start(self, session):
    if session.intake_mode == IntakeMode.STRUCTURED:
        return await self.structured.start(session)
    return await self.smart.start(session)
```

### `StructuredInterviewerService`

File: `backend/app/services/agent/structured_interviewer.py` (645 lines)

Restored from the original `main` branch. Builds dynamic `InterviewForm` objects from `case.requirements.data_fields`, validates submissions, and manages completion tracking.

### Dependency Injection (`deps.py`)

Both interviewers are always built. The `HybridInterviewerService` wraps them:

```python
def _build_interviewer(settings, classification_repo, llm, message_repo):
    structured = StructuredInterviewerService(classification_repo)
    smart = SmartInterviewerService(...) if any_smart_feature else Phase1InterviewerService(...)
    return HybridInterviewerService(structured, smart)
```

---

## 5. User Flow (Hybrid)

```
1. User opens app
2. LLM config modal (select provider/model)
3. User describes legal facts (Arabic free text)
4. AI classifies case type (3 suggestions)
5. User confirms classification (click suggestion or type confirmation)
6. ▶ INTAKE MODE SELECTOR appears:
   ┌─────────────────────┬─────────────────────┐
   │   💬 محادثة ذكية    │   📋 نموذج تقليدي    │
   │  (Conversational)   │   (Structured Form)  │
   └─────────────────────┴─────────────────────┘
7a. CONVERSATIONAL: AI-driven Q&A, multi-field extraction per turn
7b. STRUCTURED: Dynamic form with validation, field groups, supports panel
8. Both populate session.extracted_data
9. Petition role selection (أصيل / وكيل)
10. AI drafts petition (facts, evidence, requests sections)
11. User edits draft
12. Quality review (score, issues, auto-fix suggestions)
13. Export (Markdown / PDF)
```

---

## 6. API Endpoints (Hybrid-Relevant)

| Method | Path | Purpose | Returns |
|--------|------|---------|---------|
| `POST` | `/api/sessions/` | Create new session | `SessionResponse` |
| `GET` | `/api/sessions/{id}` | Get session state | `SessionResponse` |
| `PATCH` | `/api/sessions/{id}/classification` | Manual classification | `SessionResponse` |
| `PATCH` | `/api/sessions/{id}/intake-mode` | **Switch intake mode** | `SessionResponse` |
| `PATCH` | `/api/sessions/{id}/interview-form` | **Submit structured form** | `AgentResponse` |
| `POST` | `/api/agent/message` | Send message (all phases) | `AgentResponse` |

### Key Fields in `AgentResponse`

```json
{
  "session_id": "...",
  "reply": "...",
  "phase": 1,
  "session_status": "INTERVIEW",
  "next_action": "select_intake_mode | fill_form | ask_field | go_to_phase2",
  "intake_mode": "structured | conversational",
  "interview_form": { "title": "...", "fields": [...], "support_items": [...] },
  "inline_notice": { "tone": "warning", "message": "..." },
  "extracted_data": { ... },
  "completion_percentage": 45,
  "flags": { "missing_fields": [...] }
}
```

---

## 7. Critical Files Reference

### Backend — Models

| File | Key Contents |
|------|-------------|
| `models/session.py` | `Session`, `IntakeMode`, `SessionStatus`, `Phase`, `SessionFlags` |
| `models/classification.py` | `ClassificationNode`, `InterviewForm`, `InterviewField`, `InterviewFieldOption`, `InterviewSupportItem`, `ClassificationSelection` |
| `models/common.py` | `BaseSchema`, `InlineNotice`, `GuardIssue` |
| `models/api.py` | `AgentResponse`, `SessionResponse`, `InterviewFormSubmissionRequest`, `UpdateIntakeModeRequest` |

### Backend — Services

| File | Key Contents |
|------|-------------|
| `services/agent/agent_orchestrator.py` | Main dispatch: status → service routing. Handles `select_intake_mode` transition. |
| `services/agent/hybrid_interviewer.py` | Mode-based dispatch proxy (55 lines) |
| `services/agent/structured_interviewer.py` | Form builder + validator (645 lines) |
| `services/agent/smart_interviewer.py` | Conversational engine (638 lines) |
| `services/agent/phase1_interviewer.py` | Base class for SmartInterviewer (86 lines). **DO NOT DELETE.** |
| `services/agent/phase1_classifier.py` | LLM classification + confirmation (567 lines) |
| `services/agent/semantic_extractor.py` | Free-text → structured field extraction |
| `services/agent/models.py` | `AgentTurnResult` (interview_form, inline_notice fields) |

### Backend — Routes

| File | Key Endpoints |
|------|--------------|
| `routers/sessions.py` | CRUD + classification + intake-mode + form submit |
| `routers/agent.py` | `/agent/message` — main conversation endpoint |
| `routers/deps.py` | Dependency factory. Builds `HybridInterviewerService`. |

### Frontend

| File | Purpose |
|------|---------|
| `js/app.js` (26KB) | Main application: component wiring, render loop, event handlers, visibility logic |
| `js/state.js` | Centralized state with Immer-like `updateState`/`subscribe` |
| `js/api.js` | API client (`apiCall`, `sessionsAPI`, `agentAPI`) |
| `js/phases/phase1.js` | Phase 1 controller: classification, mode select, structured form helpers |
| `js/components/interview-form.js` | Structured form renderer (groups, fields, validation, supports) |
| `js/components/chat.js` | Chat message renderer |
| `js/components/classification.js` | Classification dropdown renderer |
| `js/components/petition.js` | Phase 2 petition editor |
| `js/components/review.js` | Phase 3 review panel |
| `css/styles.css` | All styles including interview form + intake mode selector |
| `index.html` | Single-page app shell |

---

## 8. Frontend State Shape

```javascript
{
  sessionId: null,
  currentPhase: 1,               // 1=intake, 2=draft, 3=review
  currentStep: "welcome",        // controls what's visible
  loading: false,
  interview: {
    mode: "conversational",       // "structured" | "conversational"
    extractedData: {},
    completion: 0,
    missingFields: [],
    form: null,                   // InterviewForm object (structured mode)
    formValues: {},               // { field_key: user_value }
    formErrors: {},               // { field_key: error_message }
    submitState: "idle",          // "idle" | "loading" | "error" | "success"
    submitMessage: "",
    supportState: { expandAll: false, expandedById: {} },
  },
  classification: { mainId, subId, caseId, suggestions, selectedPath },
  petition: { facts, evidence, requests, roleSelection },
  review: { isReady, score, issues },
  flags: { needsHumanReview, criticalIssues, guardIssues },
}
```

### Visibility Logic (app.js render loop)

```
Intake Mode Panel:  currentPhase===1 && currentStep==="select_intake_mode" && !loading
Interview Form:     interview.mode==="structured" && interview.form && currentPhase===1 && step!=="select_intake_mode"
Messages Area:      interview.mode!=="structured" || !interview.form || currentPhase>=2
```

---

## 9. Bugs Fixed (Integration History)

### Bug 1: Mode Selector Bypass
**Commit**: `5272103`
**Problem**: After classification confirmation, the orchestrator immediately called `interviewer.start()`, skipping the mode selection step entirely.
**Root Cause**: `agent_orchestrator.py` line 82-86 called `interviewer.start()` when `next_action == "start_interview"`. Same issue in `sessions.py:update_classification()`.
**Fix**: Orchestrator now returns `next_action="select_intake_mode"` instead of auto-starting. `update_intake_mode()` endpoint starts the correct interviewer for both modes.

### Bug 2: Form Fields Not Rendering (`groupsContainer`)
**Commit**: `5272103`
**Problem**: Structured form container appeared but no fields rendered.
**Root Cause**: `app.js` passed `{ groups: document.getElementById("interview-form-groups") }` but `interview-form.js` destructured it as `groupsContainer`. Undefined reference caused silent render failure.
**Fix**: Renamed `groups` → `groupsContainer` in app.js.

### Bug 3: Field Input Handler Name Mismatch
**Commit**: `3930915`
**Problem**: After validation failure, editing fields didn't clear errors or re-enable submit button.
**Root Cause**: `interview-form.js` calls `handlers.onFieldInput()` on input events, but `app.js` registered the handler as `onFieldChange`. Name mismatch meant field edits were silently ignored.
**Fix**: Renamed `onFieldChange` → `onFieldInput` in app.js.

### Bug 4: Submit State Stuck After Validation Retry
**Commit**: `3930915`
**Problem**: After correcting all fields, the status bar continued showing the error warning.
**Root Cause**: `submitState` was set to `"error"` on failed validation but never reset when the user corrected all fields.
**Fix**: Added logic in `onFieldInput` to reset `submitState` to `"idle"` when all `formErrors` are cleared.

---

## 10. Technical Debt & Known Limitations

### Code Quality
- **Flake8 line-length warnings**: Pre-existing throughout codebase (79-char limit). Cosmetic only.
- **Unused import**: `typing.Literal` in `classification.py` — harmless, can be cleaned up.
- **Orchestrator type hint**: `interviewer: Phase1InterviewerService` but receives `HybridInterviewerService`. Works via duck typing. Could add a Protocol/ABC.

### Testing
- **No unit tests for `StructuredInterviewerService`**: Original tests were deleted in the conversational branch. Should be re-written.
- **No unit tests for `HybridInterviewerService`**: Needs mode dispatch tests.
- **Integration tests outdated**: `test_api_flow.py` was modified but may not cover hybrid paths.

### Architecture
- **Mode persistence per user**: `intake_mode` is per-session. No user-level preference memory across sessions.
- **No mid-interview mode switch**: Once the user starts in one mode, switching modes mid-interview would lose conversational context (for chat) or form state (for structured). Not currently blocked in UI but behavior is undefined.
- **Session repository round-trip**: `_from_document()` uses `Session.model_validate(payload)` which recreates the session from MongoDB. Ensure `InterviewForm` with nested fields survives this round-trip (currently works but fragile with schema changes).

### Frontend
- **No build step**: Raw ES modules served by nginx. Works for development but no minification/bundling for production.
- **No error boundary**: JS errors in component renders can silently break the entire render loop.
- **No i18n framework**: All Arabic strings are hardcoded. Acceptable for Saudi-only product.

---

## 11. Important Warnings

> **DO NOT** delete `phase1_interviewer.py`. It is the base class for `SmartInterviewerService` and is imported in `smart_interviewer.py`, `agent_orchestrator.py`, and `deps.py`.

> **DO NOT** change `extracted_data` key names without updating `phase2_drafter.py` prompts. The drafter uses these Arabic labels directly in LLM context.

> **DO NOT** remove the `interview_form` and `inline_notice` fields from `Session`, `AgentTurnResult`, or `AgentResponse`. They are the data bridge for structured mode.

> **DO NOT** change `HybridInterviewerService.start()`/`process_turn()` signatures. The `AgentOrchestrator` calls these as a drop-in for `Phase1InterviewerService`.

> The frontend uses `handlers.onFieldInput` (not `onFieldChange`) in `interview-form.js`. Any new handler names must match exactly between `app.js` and the component.

---

## 12. Environment Variables (Key Ones)

```env
# LLM
LLM_PROVIDER=gemini              # or openai
GEMINI_API_KEY=...
OPENAI_API_KEY=...

# Smart Features (all default to True when LLM is available)
SMART_EXTRACTOR_ENABLED=True
ANSWER_VALIDATION_ENABLED=True
REPETITION_GUARD_ENABLED=True
MEMORY_INJECTION_ENABLED=True
HUMANIZED_QUESTIONS_ENABLED=True
COMPLETENESS_CHECK_ENABLED=True
CONTRADICTION_CHECK_ENABLED=True

# Mongo
MONGO_URL=mongodb://mongo:27017
MONGO_DB_NAME=najiz

# Security
APP_ENCRYPTION_KEY=...           # AES key for extracted_data encryption

# Ports
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

---

## 13. Running the System

```bash
# Start everything
docker compose up --build

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/api
# Health check: http://localhost:8000/api/health
```

Frontend files are volume-mounted (`./frontend:/usr/share/nginx/html:ro`), so JS/CSS/HTML changes are live without rebuild. Backend changes require container restart.

---

## 14. Git History (Hybrid Integration)

| Commit | Description |
|--------|-------------|
| `3cee097` | Merge: fix admin history persistence (pre-hybrid baseline) |
| `2872daa` | **feat**: Smart conversational intake orchestration (7 new services) |
| `a636f9c` | **feat**: Hybrid intake architecture (18 files, +2092 lines) |
| `5272103` | **fix**: Intake mode selector + form field rendering (4 files) |
| `3930915` | **fix**: Field input handler + validation retry state (1 file) |

---

## 15. Future Roadmap

### Short Term
- [ ] Write unit tests for `StructuredInterviewerService` and `HybridInterviewerService`
- [ ] Update integration tests to cover both intake modes
- [ ] Add console error boundary in frontend render loop
- [ ] Clean up Flake8 line-length warnings

### Medium Term
- [ ] Add user preference persistence for intake mode (localStorage or user profile)
- [ ] Implement mid-interview mode switching with state preservation
- [ ] Add structured form auto-save (debounced to sessionStorage)
- [ ] Add field-level validation on blur (not just on submit)
- [ ] Add conversational mode progress indicators

### Long Term
- [ ] Supplementary enrichment flow (post-intake AI follow-up for optional data)
- [ ] Privacy-friendly optional data collection layer
- [ ] Document template system for different petition styles
- [ ] Multi-language support (Arabic + English)
- [ ] Production build pipeline (bundling, minification, source maps)

---

## 16. Continuation Checklist for Future Sessions

When resuming work on this project:

1. **Read this file first** — it contains all context needed to understand the system
2. **Check `git log --oneline -5`** — see latest changes since this file was written
3. **Check `git status`** — see if there are uncommitted changes
4. **Run `docker compose up --build`** — ensure the system starts cleanly
5. **Test both modes** — structured form + conversational chat
6. **Key files to review if making changes**:
   - `agent_orchestrator.py` — dispatch logic
   - `hybrid_interviewer.py` — mode routing
   - `deps.py` — dependency wiring
   - `app.js` — frontend render loop + handlers
   - `phase1.js` — intake flow controller
   - `state.js` — state shape
7. **Run import smoke test** (Docker):
   ```bash
   docker compose exec backend python -c "
   from app.models.session import Session, IntakeMode
   from app.services.agent.hybrid_interviewer import HybridInterviewerService
   print('OK')
   "
   ```

---

*This file should be updated whenever significant architectural changes, bug fixes, or design decisions are made. It serves as the project's institutional memory.*
