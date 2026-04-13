from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.classification import ClassificationSelection
from app.models.session import Session
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.guard_checker import GuardChecker
from app.services.data.normalization import ClassificationNormalizer


def _repo():
    root = Path(__file__).resolve().parents[3]
    catalog = ClassificationNormalizer(
        root / "data/najiz-case-classifications-1447.json",
        root / "data/classification_enrichment.json",
    ).normalize()
    return ClassificationRepository(catalog)


def test_guard_detects_date_contradiction_and_high_value():
    repo = _repo()
    selection = asyncio.run(repo.resolve_selection("case-01-01-001"))
    checker = GuardChecker(repo, turn_limit=10, dispute_value_threshold=100000)
    session = Session(
        classification=ClassificationSelection.model_validate(selection.model_dump()),
        extracted_data={
            "تاريخ الزواج": "2024-10-01",
            "تاريخ الطلاق": "2024-01-01",
            "مبلغ التعويض": "150000 ريال",
        },
        message_count=12,
    )

    issues = asyncio.run(checker.check(session))
    codes = {issue.code for issue in issues}

    assert "date_contradiction" in codes
    assert "high_value_dispute" in codes
    assert "turn_limit" in codes
