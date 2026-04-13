from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models.common import BaseSchema, generate_uuid, now_utc


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageRecord(BaseSchema):
    message_id: str = Field(default_factory=generate_uuid)
    session_id: str
    role: MessageRole
    content: str
    phase: int
    created_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)
