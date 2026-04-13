from __future__ import annotations

import json
from pathlib import Path

from app.models.legal_reference import LegalSource, VerifiedReference


class LegalReferenceStore:
    def __init__(self, path: Path):
        self.path = path
        self.sources = self._load_sources()

    def _load_sources(self) -> list[LegalSource]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [LegalSource.model_validate(source) for source in payload.get("sources", [])]

    def search(self, query: str) -> list[VerifiedReference]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        matches: list[VerifiedReference] = []
        for source in self.sources:
            for entry in source.verified_entries:
                haystack = f"{source.title} {entry.citation} {entry.text} {' '.join(entry.tags)}".lower()
                if normalized in haystack:
                    matches.append(entry)
        return matches

    def citation_lines(self, query: str) -> list[str]:
        matches = self.search(query)
        if matches:
            return [f"{item.citation}: {item.text}" for item in matches]
        return [f"[يُوصى بالتحقق] لا توجد مرجعية موثقة مطابقة لعبارة: {query}"]
