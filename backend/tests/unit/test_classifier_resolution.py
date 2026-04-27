import pytest

from app.core.exceptions import LLMParseError
from app.core.config import get_settings
from app.models.classification import CaseSuggestion
from app.models.session import Session
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.phase1_classifier import Phase1ClassifierService, _StructuredSuggestion
from app.services.data.loader import CatalogLoader


class DummyLLM:
    provider = "test"

    async def parse_structured(self, *args, **kwargs):
        raise NotImplementedError

    async def generate_text(self, *args, **kwargs):
        return None


@pytest.fixture
def classification_repo(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    get_settings.cache_clear()
    settings = get_settings()
    catalog = CatalogLoader(settings).load()
    yield ClassificationRepository(catalog)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_repository_normalizes_case_id_padding(classification_repo):
    selection = await classification_repo.resolve_selection(
        classification_repo.normalize_case_id("case-01-04-2")
    )

    assert selection is not None
    assert selection.case_id == "case-01-04-002"


@pytest.mark.asyncio
async def test_classifier_resolves_by_case_title_when_case_id_is_invalid(classification_repo):
    service = Phase1ClassifierService(classification_repo, DummyLLM())
    suggestion = _StructuredSuggestion(
        case_id="case-02-04-0",
        case_title="إثبات طلاق",
        main_title="أحوال شخصية",
        sub_title="دعاوى الزواج والفرقة",
        confidence=0.88,
        rationale="اقتراح اختباري.",
    )

    selection = await service._resolve_structured_suggestion(suggestion)

    assert selection is not None
    assert selection.case_id == "case-01-04-002"
    assert selection.case_title == "إثبات طلاق"


@pytest.mark.asyncio
async def test_repository_search_cases_finds_divorce_related_entries(classification_repo):
    results = await classification_repo.search_cases("اريد طلاق زوجتي", limit=10)
    result_ids = {node.id for node in results}

    assert "case-01-04-002" in result_ids


class RecoveryLLM(DummyLLM):
    async def parse_structured(self, *args, **kwargs):
        raise LLMParseError("classifier")

    async def generate_text(self, *args, **kwargs):
        return "[case-01-04-002] | confidence=0.91 | rationale=الوقائع أقرب إلى دعوى إثبات طلاق."


@pytest.mark.asyncio
async def test_classifier_text_recovery_returns_valid_suggestion(classification_repo):
    service = Phase1ClassifierService(classification_repo, RecoveryLLM())
    suggestions = await service._classify_with_llm("اريد طلاق زوجتي", classification_repo.catalog.flat_index)

    assert len(suggestions) == 3
    assert suggestions[0].case_id == "case-01-04-002"
    assert suggestions[0].case_title == "إثبات طلاق"
    assert suggestions[0].confidence == 0.91
    assert len({item.case_id for item in suggestions}) == 3


@pytest.mark.asyncio
async def test_classifier_returns_inline_warning_for_ambiguous_input(classification_repo, monkeypatch):
    service = Phase1ClassifierService(classification_repo, DummyLLM())
    session = Session()

    suggestions = [
      CaseSuggestion(
          case_id="case-01-01-001",
          case_title="إقامة حارس قضائي",
          main_id="main-01",
          main_title="أحوال شخصية",
          sub_id="sub-01-01",
          sub_title="التصنيف العام",
          confidence=0.78,
          rationale="اقتراح أول.",
          path=["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
      ),
      CaseSuggestion(
          case_id="case-01-01-002",
          case_title="التعويض عن أضرار التقاضي",
          main_id="main-01",
          main_title="أحوال شخصية",
          sub_id="sub-01-01",
          sub_title="التصنيف العام",
          confidence=0.74,
          rationale="اقتراح ثانٍ.",
          path=["أحوال شخصية", "التصنيف العام", "التعويض عن أضرار التقاضي"],
      ),
    ]

    async def fake_classify_with_llm(message, flat_index):
        return suggestions

    monkeypatch.setattr(service, "_classify_with_llm", fake_classify_with_llm)

    result = await service.classify(session, "طلاق", classification_repo.catalog.flat_index)

    assert result.next_action == "clarify_classification"
    assert result.suggestions == []
    assert result.inline_notice is not None
    assert "لم نتمكن من تحديد نوع ورقة الدعوى" in result.inline_notice.message
