from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models.classification import CaseSuggestion, ClassificationSelection
from app.models.common import BaseSchema
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


class CreateSessionResponse(BaseSchema):
    session: Session


class SessionResponse(BaseSchema):
    session: Session


class UpdateClassificationRequest(BaseSchema):
    main_id: str
    sub_id: str
    case_id: str


class AgentMessageRequest(BaseSchema):
    session_id: str | None = None
    message: str
    phase: int | None = None


class DraftRequest(BaseSchema):
    session_id: str


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
    petition: PetitionDraft | None = None
    review_report: ReviewReport | None = None
