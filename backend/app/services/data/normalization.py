from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.classification import (
    CaseRequirements,
    ClassificationCatalog,
    ClassificationFlatNode,
    ClassificationKind,
    ClassificationNode,
    RequirementItem,
)
from app.models.common import ValidationIssue, ValidationReport


class ClassificationNormalizer:
    def __init__(self, data_path: Path, enrichment_path: Path):
        self.data_path = data_path
        self.enrichment_path = enrichment_path

    def normalize(self) -> ClassificationCatalog:
        raw = self._read_json(self.data_path)
        enrichment = self._read_json(self.enrichment_path)

        defaults = enrichment.get("defaults", {}).get("case_type", {})
        overrides = enrichment.get("case_overrides", {})
        optional_markers = enrichment.get("optional_markers", [])

        issues: list[ValidationIssue] = []
        flat_nodes: list[ClassificationFlatNode] = []
        mains: list[ClassificationNode] = []
        counts = {"mains": 0, "subs": 0, "cases": 0}

        for main_raw in raw.get("main_categories", []):
            main_node = self._normalize_node(
                node=main_raw,
                defaults=defaults,
                overrides=overrides,
                optional_markers=optional_markers,
                issues=issues,
                flat_nodes=flat_nodes,
                counts=counts,
                parent_id=None,
            )
            mains.append(main_node)

        report = ValidationReport(
            mains=counts["mains"],
            subs=counts["subs"],
            cases=counts["cases"],
            issues=issues,
        )
        flat_index = self.build_flat_index(mains)

        return ClassificationCatalog(
            source={
                "schema_version": raw.get("schema_version"),
                "source": raw.get("source"),
                "summary": raw.get("summary"),
            },
            main_categories=mains,
            flat_nodes=flat_nodes,
            validation_report=report,
            flat_index=flat_index,
        )

    def build_flat_index(self, classifications: list[ClassificationNode]) -> str:
        lines: list[str] = []
        for main in classifications:
            for sub in main.children:
                for case in sub.children:
                    lines.append(
                        f"[{case.id}] {main.title} > {sub.title} > {case.title}: {case.description[:100]}"
                    )
        return "\n".join(lines)

    def _normalize_node(
        self,
        node: dict[str, Any],
        defaults: dict[str, Any],
        overrides: dict[str, Any],
        optional_markers: list[str],
        issues: list[ValidationIssue],
        flat_nodes: list[ClassificationFlatNode],
        counts: dict[str, int],
        parent_id: str | None,
    ) -> ClassificationNode:
        level = int(node.get("level", 0))
        kind = self._kind_for_level(level)
        path = [self._clean_text(part) for part in node.get("path", [])]
        title = self._clean_text(node.get("title", ""))

        description = self._clean_text(node.get("description", ""))
        if kind == ClassificationKind.CASE and not description:
            description = defaults.get("description_template", "دعوى {case_title}.").format(
                case_title=title,
                sub_title=path[1] if len(path) > 1 else "",
                main_title=path[0] if path else "",
            )
            issues.append(
                ValidationIssue(
                    code="defaulted_description",
                    level="warning",
                    message="تم استكمال الوصف بقيمة افتراضية.",
                    node_id=node.get("id"),
                    path=path,
                )
            )

        children = [
            self._normalize_node(
                child,
                defaults,
                overrides,
                optional_markers,
                issues,
                flat_nodes,
                counts,
                parent_id=node.get("id"),
            )
            for child in node.get("children", [])
        ]

        requirements = None
        if kind == ClassificationKind.CASE:
            counts["cases"] += 1
            requirements = self._normalize_requirements(
                node=node,
                path=path,
                defaults=defaults,
                override=overrides.get(node.get("id"), {}),
                optional_markers=optional_markers,
                issues=issues,
            )
        elif kind == ClassificationKind.MAIN:
            counts["mains"] += 1
        elif kind == ClassificationKind.SUB:
            counts["subs"] += 1

        normalized = ClassificationNode(
            id=node["id"],
            title=title,
            description=description or title,
            level=level,
            kind=kind,
            parent_id=parent_id,
            path=path,
            source_pages=node.get("source_pages", []),
            hints=[self._clean_text(item) for item in node.get("hints", []) if self._clean_text(item)],
            exceptions=[self._clean_text(item) for item in node.get("exceptions", []) if self._clean_text(item)],
            requirements=requirements,
            children=children,
        )
        flat_nodes.append(
            ClassificationFlatNode(
                **normalized.model_dump(exclude={"children"}),
                search_text=self._build_search_text(normalized),
            )
        )
        return normalized

    def _normalize_requirements(
        self,
        node: dict[str, Any],
        path: list[str],
        defaults: dict[str, Any],
        override: dict[str, Any],
        optional_markers: list[str],
        issues: list[ValidationIssue],
    ) -> CaseRequirements:
        requirements = node.get("requirements", {})
        raw_data_fields = requirements.get("data_fields") or override.get("data_fields") or []
        raw_attachments = requirements.get("attachments") or override.get("attachments") or []

        if not raw_data_fields:
            raw_data_fields = defaults.get("data_fields", [])
            issues.append(
                ValidationIssue(
                    code="defaulted_data_fields",
                    level="warning",
                    message="تم استكمال حقول البيانات بقيم افتراضية.",
                    node_id=node.get("id"),
                    path=path,
                )
            )
        if not raw_attachments:
            raw_attachments = defaults.get("attachments", [])
            issues.append(
                ValidationIssue(
                    code="defaulted_attachments",
                    level="warning",
                    message="تم استكمال المرفقات المطلوبة بقيم افتراضية.",
                    node_id=node.get("id"),
                    path=path,
                )
            )

        optional_fields = {self._clean_text(item) for item in override.get("optional_fields", [])}
        optional_attachments = {self._clean_text(item) for item in override.get("optional_attachments", [])}

        normalized = CaseRequirements(
            notes=[self._clean_text(item) for item in requirements.get("notes", []) if self._clean_text(item)],
            data_fields=self._normalize_items(raw_data_fields, optional_fields, optional_markers),
            attachments=self._normalize_items(raw_attachments, optional_attachments, optional_markers),
            scenarios=[self._clean_text(item) for item in requirements.get("scenarios", []) if self._clean_text(item)],
        )

        if not normalized.data_fields:
            issues.append(
                ValidationIssue(
                    code="missing_data_fields",
                    level="error",
                    message="الحالة لا تحتوي على حقول بيانات بعد التطبيع.",
                    node_id=node.get("id"),
                    path=path,
                )
            )
        if not normalized.attachments:
            issues.append(
                ValidationIssue(
                    code="missing_attachments",
                    level="error",
                    message="الحالة لا تحتوي على قائمة مرفقات بعد التطبيع.",
                    node_id=node.get("id"),
                    path=path,
                )
            )
        return normalized

    def _normalize_items(
        self,
        items: list[str],
        explicit_optional: set[str],
        optional_markers: list[str],
    ) -> list[RequirementItem]:
        normalized_items: list[RequirementItem] = []
        for item in items:
            cleaned = self._clean_text(item)
            if not cleaned:
                continue
            required = cleaned not in explicit_optional and not any(marker in cleaned for marker in optional_markers)
            normalized_items.append(RequirementItem(name=cleaned, required=required))
        return normalized_items

    def _kind_for_level(self, level: int) -> ClassificationKind:
        if level == 1:
            return ClassificationKind.MAIN
        if level == 2:
            return ClassificationKind.SUB
        return ClassificationKind.CASE

    def _build_search_text(self, node: ClassificationNode) -> str:
        parts = [node.title, node.description, " ".join(node.path), " ".join(node.hints)]
        if node.requirements:
            parts.extend(item.name for item in node.requirements.data_fields)
            parts.extend(item.name for item in node.requirements.attachments)
            parts.extend(node.requirements.notes)
            parts.extend(node.requirements.scenarios)
        return " ".join(part for part in parts if part)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").replace("\u200f", "").replace("\u200e", "").strip()
