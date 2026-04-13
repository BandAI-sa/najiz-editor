from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.data.normalization import ClassificationNormalizer


def test_normalizer_matches_expected_counts():
    root = Path(__file__).resolve().parents[3]
    catalog = ClassificationNormalizer(
        root / "data/najiz-case-classifications-1447.json",
        root / "data/classification_enrichment.json",
    ).normalize()

    assert catalog.validation_report.mains == 7
    assert catalog.validation_report.subs == 43
    assert catalog.validation_report.cases == 244
    assert catalog.validation_report.is_valid is True


def test_all_case_types_have_normalized_requirements():
    root = Path(__file__).resolve().parents[3]
    catalog = ClassificationNormalizer(
        root / "data/najiz-case-classifications-1447.json",
        root / "data/classification_enrichment.json",
    ).normalize()

    case_nodes = [node for node in catalog.flat_nodes if node.kind == "case"]
    assert case_nodes
    assert all(node.requirements for node in case_nodes)
    assert all(node.requirements.data_fields for node in case_nodes)
    assert all(node.requirements.attachments for node in case_nodes)
