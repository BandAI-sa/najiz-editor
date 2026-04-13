from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import Field

from app.models.classification import ClassificationSelection
from app.models.common import BaseSchema, GuardIssue, generate_uuid, now_utc


class Phase(IntEnum):
    ONE = 1
    TWO = 2
    THREE = 3


class SessionStatus(StrEnum):
    NEW = "NEW"
    AWAITING_CLASSIFICATION_CONFIRM = "AWAITING_CLASSIFICATION_CONFIRM"
    INTERVIEW = "INTERVIEW"
    READY_TO_DRAFT = "READY_TO_DRAFT"
    DRAFTING = "DRAFTING"
    DRAFT_READY = "DRAFT_READY"
    REVIEW = "REVIEW"
    COMPLETE = "COMPLETE"


class SessionFlags(BaseSchema):
    needs_human_review: bool = False
    critical_issues: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    guard_issues: list[GuardIssue] = Field(default_factory=list)


class Session(BaseSchema):
    session_id: str = Field(default_factory=generate_uuid)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    status: SessionStatus = SessionStatus.NEW
    phase: Phase = Phase.ONE
    classification: ClassificationSelection | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    extracted_data_ciphertext: str | None = None
    extracted_field_names: list[str] = Field(default_factory=list)
    completion_percentage: int = 0
    message_count: int = 0
    petition_version: int = 0
    flags: SessionFlags = Field(default_factory=SessionFlags)
    metadata: dict[str, Any] = Field(default_factory=dict)
