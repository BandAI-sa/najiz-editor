from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.models.session import Session
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.phase2_drafter import Phase2DrafterService
from app.services.agent.phase2_evidence import Phase2EvidenceService
from app.services.data.normalization import ClassificationNormalizer
from app.services.legal.store import LegalReferenceStore


class DummyLLM:
    enabled = False

    async def generate_text(self, *args, **kwargs):
        return None


def _repo():
    root = Path(__file__).resolve().parents[3]
    catalog = ClassificationNormalizer(
        root / "data/najiz-case-classifications-1447.json",
        root / "data/classification_enrichment.json",
    ).normalize()
    return ClassificationRepository(catalog)


def _legal_store():
    root = Path(__file__).resolve().parents[3]
    return LegalReferenceStore(root / "legal_references/sources.json")


@pytest.mark.asyncio
async def test_phase2_facts_fallback_is_structured_and_practical():
    repo = _repo()
    selection = await repo.resolve_selection("case-01-01-001")
    case_context = await repo.get_case("case-01-01-001")
    service = Phase2DrafterService(
        repo=None,
        classification_repo=repo,
        evidence_service=Phase2EvidenceService(_legal_store(), DummyLLM()),
        llm=DummyLLM(),
    )

    session = Session(
        classification=selection,
        extracted_data={
            "بيانات المدعي": "نواف بن خالد - هوية 123",
            "بيانات المدعى عليه": "ورثة متنازع عليهم",
            "تاريخ المطالبة": "1447-01-01",
            "بيان الأموال محل النزاع": "تركة تشمل عقارًا وحسابًا بنكيًا",
        },
        metadata={},
    )
    facts = await service._build_facts(session, case_context)

    assert "أولًا: بيانات الأطراف بحسب المتاح" in facts.content
    assert "ثالثًا: وقائع الدعوى" in facts.content
    assert "رابعًا: المستندات والقرائن المرتبطة بالوقائع" in facts.content
    assert "إقامة حارس قضائي" in facts.content


@pytest.mark.asyncio
async def test_phase2_evidence_fallback_links_documents_and_procedure():
    repo = _repo()
    selection = await repo.resolve_selection("case-01-01-001")
    case_context = await repo.get_case("case-01-01-001")
    service = Phase2EvidenceService(_legal_store(), DummyLLM())

    section = await service.build(
        selection=selection,
        facts_text="وقائع الدعوى...",
        extracted_data={
            "عقد اتفاق": "محرر بين الأطراف",
            "هوية المدعي": "1234567890",
        },
        case_context=case_context,
    )

    assert "أولًا: الأسانيد المستندية" in section.content
    assert "ثانيًا: الأسانيد النظامية والإجرائية" in section.content
    assert "رابعًا: قاعدة الربط بين الطلب والسبب والدليل" in section.content
    assert "[يُوصى بالتحقق]" in section.content
