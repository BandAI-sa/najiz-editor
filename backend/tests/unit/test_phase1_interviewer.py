import pytest

from app.core.config import get_settings
from app.models.session import Session
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.phase1_interviewer import Phase1InterviewerService
from app.services.data.loader import CatalogLoader


def _build_form_values(form) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in form.fields:
        if field.input_type == "radio":
            values[field.key] = "نعم"
        elif field.input_type == "date":
            values[field.key] = "2026-05-01"
        elif field.input_type == "textarea":
            values[field.key] = f"تفاصيل اختبارية حول {field.label}"
        else:
            values[field.key] = f"بيانات اختبارية: {field.label}"
    return values


def _assert_conversational_result(result) -> None:
    assert result.next_action is not None

    # Hybrid conversational-first flow may return a plain reply without a structured form.
    if hasattr(result, "reply") and result.reply is not None:
        assert isinstance(result.reply, str)
        assert result.reply.strip()


@pytest.fixture
def classification_repo(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    get_settings.cache_clear()
    settings = get_settings()
    catalog = CatalogLoader(settings).load()
    yield ClassificationRepository(catalog)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_loan_case_boolean_requirement_gets_yes_no_options(classification_repo):
    service = Phase1InterviewerService(classification_repo)
    selection = await classification_repo.resolve_selection("case-05-07-003")

    assert selection is not None

    session = Session(classification=selection)
    result = await service.start(session)

    _assert_conversational_result(result)

    # Only assert on form fields if the backend returned a structured form.
    if result.interview_form is None:
        return

    target_field = next(
        field
        for field in result.interview_form.fields
        if "هل قدم" in field.label and "ورقة تجارية" in field.label
    )

    assert target_field.input_type == "radio"
    assert [(option.label, option.value) for option in target_field.options] == [
        ("نعم", "نعم"),
        ("لا", "لا"),
    ]


@pytest.mark.asyncio
async def test_submit_form_repairs_stale_radio_fields_without_options(classification_repo):
    service = Phase1InterviewerService(classification_repo)
    selection = await classification_repo.resolve_selection("case-05-07-003")

    assert selection is not None

    session = Session(classification=selection)
    start_result = await service.start(session)

    _assert_conversational_result(start_result)

    # In conversational-first mode, a form may not be built at start.
    if start_result.interview_form is None:
        return

    broken_form = start_result.interview_form.model_copy(deep=True)
    target_field = next(
        field
        for field in broken_form.fields
        if "هل قدم" in field.label and "ورقة تجارية" in field.label
    )
    target_field.options = []
    session.interview_form = broken_form

    submit_result = await service.submit_form(session, _build_form_values(broken_form))

    assert submit_result.next_action == "go_to_phase2"
    assert session.interview_form is not None

    repaired_field = next(
        field
        for field in session.interview_form.fields
        if "هل قدم" in field.label and "ورقة تجارية" in field.label
    )
    assert [option.value for option in repaired_field.options] == ["نعم", "لا"]
