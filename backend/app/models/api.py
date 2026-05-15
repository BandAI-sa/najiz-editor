from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.classification import (
    CaseSuggestion,
    ClassificationSelection,
    InterviewForm,
)
from app.models.common import BaseSchema, InlineNotice
from app.models.petition import PetitionDraft, PetitionSectionName, ReviewReport
from app.models.session import Session, SessionFlags, SessionStatus


class ErrorResponse(BaseSchema):
    error_code: str
    message: str
    recoverable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseSchema):
    status: str
    app_name: str
    llm_enabled: bool
    llm_provider: str
    storage: str


class LLMModelOption(BaseSchema):
    id: str
    label: str
    summary: str
    tier: str
    stage: str
    notes: str = ""
    recommended: bool = False


class LLMProviderOption(BaseSchema):
    id: str
    label: str
    enabled: bool
    default_model: str
    suggested_models: list[str] = Field(default_factory=list)
    models: list[LLMModelOption] = Field(default_factory=list)


class LLMConfigResponse(BaseSchema):
    current_provider: str
    current_model: str
    providers: list[LLMProviderOption] = Field(default_factory=list)


class CreateSessionResponse(BaseSchema):
    session: Session


class SessionResponse(BaseSchema):
    session: Session


class UpdateClassificationRequest(BaseSchema):
    main_id: str
    sub_id: str
    case_id: str


class InterviewFormSubmissionRequest(BaseSchema):
    values: dict[str, str] = Field(default_factory=dict)


class UpdateIntakeModeRequest(BaseSchema):
    mode: str


class EnrichmentDecisionRequest(BaseSchema):
    action: Literal["add", "skip"]


class AgentMessageRequest(BaseSchema):
    session_id: str | None = None
    message: str
    phase: int | None = None


class DraftRequest(BaseSchema):
    session_id: str
    petition_role: Literal["principal", "agent"] | None = None


class ReviewRequest(BaseSchema):
    session_id: str


class FixRequest(BaseSchema):
    session_id: str
    issue_id: str | None = None
    instruction: str


class PetitionSectionUpdateRequest(BaseSchema):
    section: PetitionSectionName
    content: str


class PetitionResponse(BaseSchema):
    petition: PetitionDraft


class AdminPetitionStats(BaseSchema):
    total_petitions: int
    total_sessions: int
    completed_sessions: int
    average_review_score: int | None = None


class AdminPetitionSummary(BaseSchema):
    petition_id: str
    session_id: str
    version: int
    model: str | None = None
    created_at: datetime
    updated_at: datetime
    session_updated_at: datetime | None = None
    session_status: SessionStatus | None = None
    phase: int | None = None
    case_title: str | None = None
    case_path: list[str] = Field(default_factory=list)
    review_score: int | None = None
    issue_count: int = 0
    extracted_field_count: int = 0
    message_count: int = 0
    preview: str = ""


class AdminPetitionListResponse(BaseSchema):
    items: list[AdminPetitionSummary] = Field(default_factory=list)
    total: int
    stats: AdminPetitionStats


class AdminPetitionDetailResponse(BaseSchema):
    petition: PetitionDraft
    session: Session | None = None


class AdminDeletePetitionResponse(BaseSchema):
    petition_id: str
    session_id: str
    remaining_petitions_in_session: int
    deleted_session: bool = False
    deleted_message_count: int = 0


class AgentResponse(BaseSchema):
    session_id: str
    reply: str
    phase: int
    session_status: SessionStatus
    completion_percentage: int = 0
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    flags: SessionFlags
    next_action: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[CaseSuggestion] = Field(default_factory=list)
    classification: ClassificationSelection | None = None
    interview_form: InterviewForm | None = None
    inline_notice: InlineNotice | None = None
    intake_mode: str = "conversational"
    petition: PetitionDraft | None = None
    review_report: ReviewReport | None = None
