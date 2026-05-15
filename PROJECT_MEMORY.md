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

## UI/UX Refinement Pass — 2026-05-14

**Scope:** Strictly visual + UX polish. No backend, orchestration, API, or flow logic changes.

### Text Fixes Applied
- Chat mode subtitle changed from `"حاور المساعد القانوني وأجب بطريقتك"` → `"حاور المساعد الذكي واجب بكلامك"` (واجب without hamza, per spec).
- Removed `"إلزامي"` badge entirely from the structured interview form field cards (`interview-form.js`). Required fields now show no badge — only optional fields show `"اختياري"`.
- Inline validation error softened: `"هذا الحقل إلزامي."` → `"يرجى إكمال هذا الحقل."` in `phase1.js`.
- Role selector descriptions shortened for compact row layout.

### Visual & Layout Changes (`styles.css`)
- **Intake mode cards** — converted from centered grid cards (2.4rem icon, stacked layout) to compact horizontal rows with 1.5rem icon + `.intake-mode-text` label block. Tighter padding (`12px 16px`), `border-radius: 16px`, lighter border, subtle hover shadow, `.is-active` teal state.
- **Role selector** — `.draft-role-card` converted from tall grid cards to compact `flex` pill-rows (`24px border-radius`, `10px 16px` padding). Selected state uses teal border + faint teal background. Description shown inline as muted small text.
- **Optional enrichment panel** — refactored from stacked grid to a single horizontal `flex` row (`.optional-enrichment-inner`) with copy on the right and action buttons on the left. Compact background, no large empty space. Skip button demoted to `.btn-ghost`.
- **Interview form panel** — reduced padding to `16px`, `border-radius: 18px`, softer background.
- **Form field cards** — reduced padding to `12px 14px`, `border-radius: 14px`.
- **Form grid/group gaps** — reduced from `14–16px` to `10–12px`.
- **Form status bar** — smaller padding, lighter background, `0.88rem` font.
- **Chat panel** — `min-height` reduced from `78vh` → `60vh`.
- **Messages list** — `min-height` reduced from `360px` → `240px`.
- **Composer textarea** — `min-height` reduced from `96px` → `72px`.
- **Petition content** — `min-height` reduced from `260px` → `180px`.
- **Buttons** — `padding: 10px 16px`, `border-radius: 14px`, `font-size: 0.92rem`.
- **Panel/hero-card** — padding reduced to `20px`.
- **Sidebar/main-shell gap** — reduced from `20px` to `16px`.
- Removed `.interview-form-required` CSS rule (badge no longer rendered).

### HTML Structure Changes (`index.html`)
- Intake mode card inner structure updated: `<p>` → `<span class="intake-mode-text">` wrapping `<strong>` and `<span>` for correct horizontal layout.
- Optional enrichment panel inner structure: copy and actions wrapped in `.optional-enrichment-inner` flex container for horizontal layout. Button order: ghost "التخطي" first (visually right in RTL), then primary "إضافة".

### Files Modified
- `frontend/index.html`
- `frontend/css/styles.css`
- `frontend/js/components/interview-form.js`
- `frontend/js/components/draft-role.js`
- `frontend/js/phases/phase1.js`

---

## Conversational Intelligence + UI Polish Pass — 2026-05-15

**Scope:** Conversational intelligence improvements, smart assistance audit, targeted UI/UX redesign. No architectural, orchestration, or API contract changes.

### Part 1A — Conversational Correction Detection (`smart_interviewer.py`)
- Added `_CORRECTION_PREFIXES` tuple with 16 Arabic/English correction phrases: أقصد, اقصد, قصدي, لا الصحيح, الصحيح, بل, مو, مب, لا أقصد, غلط, خطأ, تصحيح, عفوًا, عفوا, سوري, sorry.
- Added `_is_correction_message()` — checks if user message starts with a correction prefix.
- Added `_extract_corrected_value()` — strips the correction prefix and returns the actual value.
- Added `_find_previous_field()` — finds the most recently filled field using `field_fill_order` metadata or by scanning `extracted_data` in reverse.
- Added `_handle_correction_if_detected()` — full async correction pipeline: detects correction, finds previous field, re-extracts + validates, updates `extracted_data`, and responds naturally. Returns `None` if not a correction (falls through to normal flow).
- Added `field_fill_order` tracking to `session.metadata` — appended whenever a field value is accepted, enabling accurate previous-field lookup.
- Correction detection runs early in `process_turn()`, after contradiction/enrichment checks but before standard extraction.

### Part 1B — Chat Intent Bridging (`phase1.js`)
- Added word sets: `_ENRICHMENT_ADD_WORDS`, `_ENRICHMENT_SKIP_WORDS`, `_ROLE_PRINCIPAL_WORDS`, `_ROLE_AGENT_WORDS`, `_MODE_CHAT_WORDS`, `_MODE_FORM_WORDS`.
- Added `matchChatIntent(message, step)` — matches user chat input against the current `currentStep` and returns an intent object `{action, value}` if matched.
- Modified `sendMessage()` to check for chat intent *before* sending to backend API. If matched:
  - `enrichment` → calls `onOptionalEnrichmentDecision()`
  - `role` → updates `petition.roleSelection` state + pushes confirmation chat message
  - `mode` → calls `onIntakeModeSelect()`
- Buttons remain available as shortcuts; chat input is an alternative path.

### Part 2 — Smart Assistance Audit
- **RepetitionGuard**: Removed `"مو إلزامي"` from `OFFER_SKIP` message, replaced with `"غير مانع للمتابعة"`.
- **Field examples**: Expanded `FIELD_EXAMPLES` dict with 6 new entries: بريد, جوال, وكالة, وكيل, تقدير, مستند. Shortened existing examples to be more concise (removed "يعني مثلاً:" prefix → "مثل:").
- **Uncertainty handler**: Softened reply in `_handle_uncertainty()` — changed to `"ما عليك، لو تتذكر..."` with clearer skip guidance.
- **Low-confidence handler**: Simplified reply text in `_handle_low_confidence()`.
- **Structured interviewer**: Removed all `"إلزامي"` from user-facing strings:
  - `aria_label`: `"حقل إلزامي"` → `"حقل أساسي"`
  - Attachment label: `"مرفق إلزامي"` → `"مرفق أساسي"`
  - Validation error: `"هذا الحقل إلزامي"` → `"يرجى إكمال هذا الحقل"`

### Part 3 — UI/UX Redesign

#### Hero Card (`index.html`, `styles.css`)
- Shortened hero title to single-line: `"وكيل قانوني ذكي لبناء صحيفة الدعوى"`.
- Condensed hero copy to a dash-separated pipeline summary.
- Removed admin link from hero (was redundant with status bar).
- Shortened badge labels to single words.
- Reduced badge padding (`5px 10px`), font size (`0.78rem`), gap (`6px`).
- Smaller decorative blob (`120px`, reduced offsets).
- Hero title font size reduced to `1.2rem`.
- Eyebrow font size reduced to `0.78rem`.

#### Step Indicator (NEW)
- Added `<nav id="step-indicator">` to `index.html` with 4 steps: التصنيف, جمع البيانات, الصياغة, المراجعة.
- Connected via `.step-connector` dividers.
- CSS: Horizontal flex layout, subtle teal background, dot + label per step.
- States: `.is-active` (teal dot + glow), `.is-completed` (green dot).
- Wired in `app.js` via `updateStepIndicator()` called from the render `subscribe()` loop.
- Step logic: phase 1 welcome/classify → step 0, phase 1 intake → step 1, phase 2 → step 2, phase 3 → step 3.

#### Chat Composer
- Wrapped in a subtle container: `border-radius: 16px`, light background + border.
- Input min-height reduced to `56px`, tighter border-radius (`12px`).
- Placeholder updated: `"اكتب هنا... صف الوقائع أو أجب على سؤال المساعد"`.

#### Message Cards
- Reduced padding (`10px 14px`), border-radius (`14px`), margin-bottom (`8px`).
- Font size `0.94rem`, line-height `1.8`.
- Softer background colors for both user and assistant cards.

#### Progress Track (sidebar)
- Track height reduced from `12px` → `6px`.
- Margin reduced `8px 0`.

#### Text Fixes
- Intake mode subtitle: `"حاور المساعد الذكي واجب بكلامك"` (واجب without hamza).
- No `"إلزامي"` remains in any frontend or user-facing backend string.

### Files Modified
- `backend/app/services/agent/smart_interviewer.py`
- `backend/app/services/agent/repetition_guard.py`
- `backend/app/services/agent/structured_interviewer.py`
- `frontend/index.html`
- `frontend/css/styles.css`
- `frontend/js/app.js`
- `frontend/js/phases/phase1.js`

---

## Stabilization Pass — 2026-05-15 (Enrichment + Retry UX)

**Scope:** Bug-fix/refinement only. No changes to hybrid architecture, orchestration contracts, API schemas, `extracted_data`, or drafting behavior.

### Root Causes
- **Coroutine crash in supplementary flow:** `SmartInterviewerService.process_turn()` returned `_continue_after_supplementary(...)` without `await` in two paths, producing `AttributeError: 'coroutine' object has no attribute 'reply'`.
- **Inconsistent chat enrichment intent:** phrase-level input (for example `إضافة بيانات إضافية`) was not recognized reliably because matching depended on exact single-token words.
- **Duplicate enrichment transitions/prompts:** chat-intent and button-click could both fire enrichment decision calls in close succession.

### Fixes Applied
- **Await correctness:**
  - Added missing `await` for both supplementary continuation returns in `smart_interviewer.py`.
- **Chat/button transition convergence:**
  - Kept one authoritative handler: `onOptionalEnrichmentDecision()` in `frontend/js/phases/phase1.js` (used by both chat intent path and button click path).
  - Added enrichment transition guard:
    - Requires current step `offer_optional_enrichment` and `awaitingDecision=true`.
    - Added in-flight dedupe key (`enrichmentDecisionInFlightKey`) to block duplicate triggers.
    - Optimistically flips `awaitingDecision=false` during request to prevent repeated clicks.
    - Restores `awaitingDecision=true` only on failure while still in same step.
- **Intent matching reliability:**
  - Frontend: `matchChatIntent()` now recognizes phrase-level add intent (`إضافة بيانات إضافية` / `اضافة بيانات اضافية`).
  - Backend fallback safety:
    - `smart_interviewer.py::_parse_enrichment_decision()`
    - `phase1_interviewer.py::_parse_enrichment_decision()`
    both accept phrase-level add intent.
- **Retry UX enhancement (without retry behavior change):**
  - In `smart_interviewer.py::_handle_uncertainty()`:
    - 1st uncertainty: unchanged core prompt (no extra example).
    - 2nd uncertainty branch (when reached): same prompt + one contextual example line.
    - fallback/escalation path unchanged.

### Files Modified (This Stabilization Pass)
- `backend/app/services/agent/smart_interviewer.py`
- `backend/app/services/agent/phase1_interviewer.py`
- `frontend/js/phases/phase1.js`

---

## Stabilization Pass — 2026-05-15 (Conversational State Sync)

**Scope:** Conversational/chat-flow synchronization and validation UX polish only.  
No changes to hybrid architecture, orchestration contracts, APIs, `extracted_data` contract, structured form flow, or drafting pipeline.

### Root Causes
- **Duplicate/overlapping assistant prompts** came from multiple `pushChatMessage("assistant", ...)` calls across transition paths and no last-message dedupe.
- **Chat-intent enrichment desync** occurred when an intent message was already pushed as user chat but frontend guards rejected the transition; flow then returned early without fallback to backend message handling.
- **Enrichment replay regression** happened when enrichment had already started but `supplementary_state` was not normalized before completion gating, allowing re-offer path to appear again in some transitions.
- **Field-generic validation message for email** because `AnswerValidationLayer` had no dedicated email field type.

### Fixes Applied
- **Authoritative transition sync (frontend):**
  - Added `pushAssistantMessage()` helper in `frontend/js/phases/phase1.js` with last-message dedupe.
  - Replaced direct assistant message pushes in phase1 controller with deduped helper.
  - `sendMessage()` now:
    - avoids duplicate user-message push on chat intents,
    - falls back to normal backend message path if intent handler returns unhandled.
  - `onOptionalEnrichmentDecision()` now returns `boolean` handled-state and keeps in-flight decision guard behavior.
- **No enrichment intro replay after start (backend conversational paths):**
  - In both `smart_interviewer.py` and `phase1_interviewer.py`:
    - set `session.metadata["enrichment_started"] = True` when add/skip decision is made.
    - normalize `supplementary_state` to `completed` when enrichment has started and required fields are complete.
  - In `smart_interviewer.py::handle_enrichment_decision(add)` removed redundant enrichment intro line and start directly with first supplementary question.
- **Field-aware email validation message:**
  - Added `email` field type detection + `_validate_email()` in `backend/app/services/agent/answer_validator.py`.
  - New message:
    - `يبدو أن البريد الإلكتروني غير مكتمل.`
    - `مثل: [example@email.com](mailto:example@email.com)`
- **Optional-field wording in conversational retries:**
  - In `smart_interviewer.py`, low-confidence/validation-failure handlers now use optional wording for supplementary fields:
    - `إذا متوفر تقدر تضيفه، أو تكتب «تخطي».`

### Files Modified (This Pass)
- `frontend/js/phases/phase1.js`
- `backend/app/services/agent/smart_interviewer.py`
- `backend/app/services/agent/phase1_interviewer.py`
- `backend/app/services/agent/answer_validator.py`

---

## Stabilization Pass — 2026-05-15 (Structured Form Consistency + Layout)

**Scope:** Targeted fixes only for structured-form data consistency, optional-flow control intents, and structured stage spacing polish.  
No changes to orchestration contracts, API schemas, retry architecture, or drafting pipeline architecture.

### Root Causes
- **False `[يحتاج استكمال]` despite structured supplementary input** came from weak downstream mapping in drafting context/fallback interpretation (especially for identity/address/agency/contact fields entered as supplementary labels).
- **Optional-flow skip instability** occurred when supplementary control intents were matched too strictly; phrases like `ممكن تخطي` or `اكتفي الآن` could fall through to validation/normal extraction paths.
- **Structured stage vertical whitespace** persisted because the main chat panel kept the same large grid/min-height behavior during structured-only action stages (`offer_optional_enrichment`, `select_petition_role`), leaving oversized empty visual areas.

### Fixes Applied
- **Drafting context mapping strengthened (`phase2_drafter.py`):**
  - Added explicit supplementary-context block in generation context:
    - `بيانات الوكيل`, `رقم الوكالة`, `رقم الهوية`, `العنوان الوطني`, `البريد الإلكتروني`, `الجوال`, `تقدير المطالبة`, `بيانات إضافية للأطراف`.
  - Updated fallback party extraction to:
    - recognize `وكالة` in representative detection,
    - avoid generic identity/address false-missing placeholders when those values already exist,
    - surface identity/contact/address enrichment lines as dedicated supplemental party data.
- **Control-intent priority hardening (before validation):**
  - `smart_interviewer.py`:
    - supplementary `تخطي` now advances immediately even with phrase-style input,
    - supplementary `اكتفي` variants now finalize optional enrichment immediately,
    - intent matching now handles tokenized phrase inputs, not only exact single-token equality.
  - `phase1_interviewer.py` (base fallback path):
    - added `اكتفي/يكفي/خلاص/كفاية` finish handling,
    - made `تخطي` phrase matching robust and ensured skip/finish execute before answer extraction.
- **Structured layout compaction only (`frontend/js/app.js`, `frontend/css/styles.css`):**
  - Added structured-stage compact class on chat panel in phase 1 structured steps.
  - Reduced stage min-height pressure and grid expansion for structured stages.
  - Hid chat stream/composer in structured action-only steps (`offer_optional_enrichment`, `select_petition_role`) to remove dead whitespace.
  - Refined role-selection and optional-enrichment card sizing/positioning for a centered, tighter, premium layout.

### Files Modified (This Pass)
- `backend/app/services/agent/phase2_drafter.py`
- `backend/app/services/agent/smart_interviewer.py`
- `backend/app/services/agent/phase1_interviewer.py`
- `frontend/js/app.js`
- `frontend/css/styles.css`

---

## Stabilization Pass — 2026-05-15 (Conversational Recovery + Intent Families)

**Scope:** Conversational robustness only.  
No orchestration, API, drafting architecture, extracted_data contract, or structured form flow redesign.

### Root Causes
- **Recovery gap after unknown answers:** when a field was marked as `[يحتاج استكمال لاحق]`, later natural user updates could be treated as answers to the current field instead of routing back to the unresolved field.
- **Brittle optional intents:** supplementary controls depended mainly on exact tokens, so variants like `عدي`, `التالي`, `ايوه أضف` were not consistently recognized.

### Fixes Applied
- **Lightweight recovery routing in `smart_interviewer.py`:**
  - Added guarded recovery hook between extraction and validation flow.
  - If current answer looks mismatched (or low-confidence) and strongly aligns with unresolved prior fields, it updates that prior field and continues the current question naturally.
  - Added conservative semantic gates to avoid aggressive rerouting.
- **Intent-family normalization/matching (conversational):**
  - Added normalized matching utilities (hamza/spacing/punctuation tolerant).
  - Supplementary intent families now support phrasing variants for:
    - skip (`تخطي`, `عدي`, `التالي`, …),
    - finish (`اكتفي`, `خلاص`, `كفاية`, …),
    - add enrichment (`أضف`, `ايوه أضف`, `إضافة بيانات إضافية`, …),
    - continue (`كمل`, `واصل`, …).
  - Control intents are resolved before validation/extraction in supplementary flow.
- **Fallback parity (`phase1_interviewer.py`):**
  - Expanded add/skip/finish phrase variants for base conversational fallback path.

### Files Modified (This Pass)
- `backend/app/services/agent/smart_interviewer.py`
- `backend/app/services/agent/phase1_interviewer.py`

---

## Stabilization Pass — 2026-05-15 (Uncertainty Phrase Coverage)

**Scope:** Small conversational uncertainty routing fix only.  
No changes to orchestration, APIs, extracted_data contract, drafting behavior, structured form flow, or retry thresholds.

### Root Cause
- Natural uncertainty variants (for example `ماني متأكد`) were not guaranteed to enter the uncertainty branch in all paths, because some turns were handled earlier by low-confidence extraction flow.
- Uncertainty retry gating in `smart_interviewer.py` had an off-by-one condition that could bypass the intended second retry response with contextual example.

### Fixes Applied
- **Expanded uncertainty normalization coverage (`answer_validator.py`):**
  - Added conversational variants to unknown indicators:
    - `ما اعرف`, `ماني عارف`, `ماني متأكد`, `مو متأكد`, `مش متأكد`, `ما أدري`, `مدري`, `غير متأكد`, `ما عندي فكرة`.
  - Hardened unknown normalization with hamza/spacing/punctuation normalization before matching.
- **Direct uncertainty intent routing (`smart_interviewer.py`):**
  - Added lightweight uncertainty intent matcher (normalized family matching).
  - Added early uncertainty branch in `process_turn()` before extraction/validation so uncertainty phrases reliably use `_handle_uncertainty()`.
- **Preserved intended retry behavior:**
  - Fixed uncertainty retry condition so:
    - first uncertainty → soft retry,
    - second uncertainty → retry + contextual example,
    - third/fallback → unresolved progression (`[يحتاج استكمال لاحق]`).

### Files Modified (This Pass)
- `backend/app/services/agent/answer_validator.py`
- `backend/app/services/agent/smart_interviewer.py`

---

## Stabilization Pass — 2026-05-15 (Conversational Intent Atomic Transitions)

**Scope:** Targeted conversational state-transition stabilization only.  
No orchestration/API/drafting/structured-flow redesign.

### Root Cause
- Explicit skip intents in conversational required-field flow returned filler-style `ask_field` responses without atomically resolving the transition (`state update + next field assignment + next question`).
- Some control variants (for example `التالي`, `عدي`, `خلاص` in decision stage) were not consistently routed through a fully resolved control-intent path, allowing occasional fallback-style behavior.

### Fixes Applied
- **Atomic explicit skip transition (`smart_interviewer.py`):**
  - Reworked `_handle_explicit_skip` to always return a fully resolved turn result.
  - For required (non-critical) fields, skip now uses `_mark_unknown_and_continue(...)` so the flow advances in the same reply and does not re-bind the next user message to the skipped field.
  - For optional fields, skip updates state, recalculates missing/completion, sets `current_field` to next field, and includes the next question in the same response.
- **Control-intent coverage hardening:**
  - Added `عدي` and `التالي` to explicit skip triggers for core conversational flow.
  - Expanded enrichment decision skip-family matching to include finish variants (`خلاص`, `اكتفي`, `يكفي`) so decision-stage control intents resolve immediately without offer/filler replay.

### Files Modified (This Pass)
- `backend/app/services/agent/smart_interviewer.py`

---

*This file should be updated whenever significant architectural changes, bug fixes, or design decisions are made. It serves as the project's institutional memory.*
