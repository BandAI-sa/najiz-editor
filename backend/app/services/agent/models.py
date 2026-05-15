from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models.classification import (
    CaseSuggestion,
    ClassificationSelection,
    InterviewForm,
)
from app.models.common import BaseSchema, GuardIssue, InlineNotice
from app.models.petition import PetitionDraft, ReviewReport


class AgentTurnResult(BaseSchema):
    reply: str
    next_action: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[CaseSuggestion] = Field(default_factory=list)
    classification: ClassificationSelection | None = None
    interview_form: InterviewForm | None = None
    inline_notice: InlineNotice | None = None
    petition: PetitionDraft | None = None
    review: ReviewReport | None = None
    guard_issues: list[GuardIssue] = Field(default_factory=list)
