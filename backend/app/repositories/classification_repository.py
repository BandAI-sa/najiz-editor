from __future__ import annotations

import re

from app.models.classification import ClassificationCatalog, ClassificationNode, ClassificationSelection


class ClassificationRepository:
    def __init__(self, catalog: ClassificationCatalog):
        self.catalog = catalog
        self._flat = {node.id: node for node in catalog.flat_nodes}
        self._case_nodes = [node for node in catalog.flat_nodes if node.kind == "case"]

    async def get_main_categories(self) -> list[ClassificationNode]:
        return self.catalog.main_categories

    async def get_subs(self, main_id: str) -> list[ClassificationNode]:
        main = next((node for node in self.catalog.main_categories if node.id == main_id), None)
        return [] if main is None else main.children

    async def get_cases(self, main_id: str, sub_id: str) -> list[ClassificationNode]:
        subs = await self.get_subs(main_id)
        sub = next((node for node in subs if node.id == sub_id), None)
        return [] if sub is None else sub.children

    async def get_case(self, case_id: str):
        return self._flat.get(case_id)

    async def resolve_selection(self, case_id: str) -> ClassificationSelection | None:
        case = self._flat.get(case_id)
        if case is None or len(case.path) < 3:
            return None
        sub = self._flat.get(case.parent_id or "")
        main = self._flat.get(sub.parent_id or "") if sub else None
        if not sub or not main:
            return None
        return ClassificationSelection(
            main_id=main.id,
            sub_id=sub.id,
            case_id=case.id,
            main_title=main.title,
            sub_title=sub.title,
            case_title=case.title,
            case_path=case.path,
        )

    async def resolve_selection_by_titles(
        self,
        *,
        case_title: str,
        sub_title: str | None = None,
        main_title: str | None = None,
    ) -> ClassificationSelection | None:
        normalized_case = self._normalize_text(case_title)
        normalized_sub = self._normalize_text(sub_title) if sub_title else None
        normalized_main = self._normalize_text(main_title) if main_title else None

        matches = [
            node
            for node in self._case_nodes
            if self._normalize_text(node.title) == normalized_case
        ]
        if normalized_sub is not None:
            matches = [
                node
                for node in matches
                if len(node.path) >= 2 and self._normalize_text(node.path[1]) == normalized_sub
            ]
        if normalized_main is not None:
            matches = [
                node
                for node in matches
                if len(node.path) >= 1 and self._normalize_text(node.path[0]) == normalized_main
            ]
        if len(matches) != 1:
            return None
        return await self.resolve_selection(matches[0].id)

    @staticmethod
    def normalize_case_id(case_id: str) -> str:
        value = case_id.strip()
        match = re.fullmatch(r"(case-\d{2}-\d{2})-(\d{1,3})", value)
        if not match:
            return value
        return f"{match.group(1)}-{match.group(2).zfill(3)}"

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip().lower()
        replacements = str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ة": "ه",
                "ى": "ي",
                "ؤ": "و",
                "ئ": "ي",
            }
        )
        normalized = normalized.translate(replacements)
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = " ".join(normalized.split())
        return normalized.strip().lower()

    async def all_case_nodes(self):
        return list(self._case_nodes)

    async def search_cases(self, query: str, limit: int = 40):
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return self._case_nodes[:limit]

        scored: list[tuple[int, ClassificationNode]] = []
        for node in self._case_nodes:
            haystack = self._normalize_text(node.search_text)
            title_text = self._normalize_text(" ".join(node.path))
            token_hits = sum(1 for token in query_tokens if token in haystack)
            title_hits = sum(1 for token in query_tokens if token in title_text)
            if token_hits == 0 and title_hits == 0:
                continue
            score = token_hits * 3 + title_hits * 5
            scored.append((score, node))

        scored.sort(key=lambda item: (item[0], len(item[1].path)), reverse=True)
        return [node for _, node in scored[:limit]]

    @classmethod
    def _tokenize(cls, value: str) -> list[str]:
        stopwords = {
            "اريد",
            "أريد",
            "ابي",
            "ابغى",
            "من",
            "في",
            "على",
            "الى",
            "إلى",
            "عن",
            "مع",
            "و",
            "او",
            "أو",
            "ثم",
            "هذا",
            "هذه",
            "ذلك",
            "زوجتي",
            "زوجي",
        }
        normalized = cls._normalize_text(value)
        tokens = [token for token in normalized.split() if len(token) >= 2]
        return [token for token in tokens if token not in stopwords]
