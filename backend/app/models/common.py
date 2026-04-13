from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now_utc() -> datetime:
    return datetime.now(UTC)


def generate_uuid() -> str:
    return str(uuid4())


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
        extra="forbid",
    )


class SeverityLevel(StrEnum):
    CRITICAL = "حرج"
    WARNING = "تنبيه"
    SUGGESTION = "اقتراح"


class GuardIssue(BaseSchema):
    code: str
    severity: SeverityLevel
    title: str
    description: str
    recommendation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseSchema):
    code: str
    level: str
    message: str
    node_id: str | None = None
    path: list[str] = Field(default_factory=list)


class ValidationReport(BaseSchema):
    mains: int
    subs: int
    cases: int
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        blocking = [issue for issue in self.issues if issue.level in {"error", "critical"}]
        return self.mains == 7 and self.subs == 43 and self.cases == 244 and not blocking
