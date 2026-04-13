from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models.common import BaseSchema, generate_uuid, now_utc


class PetitionSectionName(StrEnum):
    FACTS = "facts"
    EVIDENCE = "evidence"
    REQUESTS = "requests"


class PetitionSection(BaseSchema):
    name: PetitionSectionName
    title: str
    content: str
    citations: list[str] = Field(default_factory=list)


class ReviewIssue(BaseSchema):
    issue_id: str = Field(default_factory=generate_uuid)
    severity: str
    category: str
    description: str
    suggestion: str
    auto_fixable: bool = False
    section: str | None = None


class ReviewReport(BaseSchema):
    completeness_score: int
    issues: list[ReviewIssue] = Field(default_factory=list)
    recommendation: str
    summary: str


class PetitionDraft(BaseSchema):
    petition_id: str = Field(default_factory=generate_uuid)
    session_id: str
    version: int
    facts: PetitionSection
    evidence: PetitionSection
    requests: PetitionSection
    full_text: str
    review_report: ReviewReport | None = None
    encrypted_payload: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
