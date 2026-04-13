from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.models.common import BaseSchema, ValidationReport


class ClassificationKind(StrEnum):
    MAIN = "main"
    SUB = "sub"
    CASE = "case"


class RequirementItem(BaseSchema):
    name: str
    required: bool = True
    hint: str | None = None


class CaseRequirements(BaseSchema):
    notes: list[str] = Field(default_factory=list)
    data_fields: list[RequirementItem] = Field(default_factory=list)
    attachments: list[RequirementItem] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)


class ClassificationNode(BaseSchema):
    id: str
    title: str
    description: str
    level: int
    kind: ClassificationKind
    parent_id: str | None = None
    path: list[str]
    source_pages: list[int] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    requirements: CaseRequirements | None = None
    children: list["ClassificationNode"] = Field(default_factory=list)


class ClassificationFlatNode(BaseSchema):
    id: str
    title: str
    description: str
    level: int
    kind: ClassificationKind
    parent_id: str | None = None
    path: list[str]
    source_pages: list[int] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    requirements: CaseRequirements | None = None
    search_text: str


class ClassificationSelection(BaseSchema):
    main_id: str
    sub_id: str
    case_id: str
    main_title: str
    sub_title: str
    case_title: str
    case_path: list[str]


class CaseSuggestion(BaseSchema):
    case_id: str
    case_title: str
    main_id: str
    main_title: str
    sub_id: str
    sub_title: str
    confidence: float
    rationale: str
    path: list[str]


class ClassificationCatalog(BaseSchema):
    source: dict
    main_categories: list[ClassificationNode]
    flat_nodes: list[ClassificationFlatNode]
    validation_report: ValidationReport
    flat_index: str


ClassificationNode.model_rebuild()
