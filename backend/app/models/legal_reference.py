from __future__ import annotations

from pydantic import Field

from app.models.common import BaseSchema


class VerifiedReference(BaseSchema):
    reference_id: str
    citation: str
    text: str
    tags: list[str] = Field(default_factory=list)
    verified: bool = True


class LegalSource(BaseSchema):
    source_id: str
    title: str
    kind: str = "statute"
    jurisdiction: str
    authority_url: str = ""
    verified_entries: list[VerifiedReference] = Field(default_factory=list)
