from __future__ import annotations

import pytest

from app.models.classification import CaseSuggestion
from app.services.agent.phase1_classifier import Phase1ClassifierService


def _build_form_values(form: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in form.get("fields", []):
        if field["input_type"] == "radio":
            values[field["key"]] = field["options"][0]["value"]
        elif field["input_type"] == "date":
            values[field["key"]] = "2026-04-27"
        elif field["input_type"] == "textarea":
            values[field["key"]] = f"تفاصيل اختبارية حول {field['label']}"
        else:
            values[field["key"]] = f"بيانات اختبارية: {field['label']}"
    return values


def _assert_conversational_payload(payload: dict) -> None:
    assert payload.get("next_action")

    # Hybrid conversational-first flow may return a plain reply without a structured form.
    if "reply" in payload and payload["reply"] is not None:
        assert isinstance(payload["reply"], str)
        assert payload["reply"].strip()


@pytest.mark.asyncio
async def test_health_and_classification_routes(client):
    health_response = await client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json()["storage"] == "memory"

    llm_config_response = await client.get("/api/config/llm")
    assert llm_config_response.status_code == 200
    llm_config = llm_config_response.json()
    assert len(llm_config["providers"]) == 2

    configured_model_ids = {
        model["id"]
        for provider in llm_config["providers"]
        for model in provider["models"]
    }
    assert configured_model_ids == {
        "o3",
        "gpt-5.2",
        "gpt-5.4",
        "gemini-2.5-pro",
        "gemini-3-pro-preview",
    }

    classifications_response = await client.get("/api/classifications/")
    assert classifications_response.status_code == 200
    assert len(classifications_response.json()) == 7


@pytest.mark.asyncio
async def test_full_phase_flow_and_export(client, monkeypatch):
    async def fake_llm_classification(self, message, flat_index):
        return [
            CaseSuggestion(
                case_id="case-01-01-001",
                case_title="إقامة حارس قضائي",
                main_id="main-01",
                main_title="أحوال شخصية",
                sub_id="sub-01-01",
                sub_title="التصنيف العام",
                confidence=0.96,
                rationale="مطابقة الوقائع مع طلب إقامة حارس قضائي على التركة.",
                path=[
                    "أحوال شخصية",
                    "التصنيف العام",
                    "إقامة حارس قضائي",
                ],
            ),
            CaseSuggestion(
                case_id="case-01-01-002",
                case_title="التعويض عن أضرار التقاضي",
                main_id="main-01",
                main_title="أحوال شخصية",
                sub_id="sub-01-01",
                sub_title="التصنيف العام",
                confidence=0.42,
                rationale="اقتراح ثانوي تجريبي.",
                path=[
                    "أحوال شخصية",
                    "التصنيف العام",
                    "التعويض عن أضرار التقاضي",
                ],
            ),
            CaseSuggestion(
                case_id="case-01-01-003",
                case_title="أتعاب المحامين والوكلاء",
                main_id="main-01",
                main_title="أحوال شخصية",
                sub_id="sub-01-01",
                sub_title="التصنيف العام",
                confidence=0.31,
                rationale="اقتراح ثالث تجريبي.",
                path=[
                    "أحوال شخصية",
                    "التصنيف العام",
                    "أتعاب المحامين والوكلاء",
                ],
            ),
        ]

    monkeypatch.setattr(
        Phase1ClassifierService,
        "_classify_with_llm",
        fake_llm_classification,
    )

    classify_response = await client.post(
        "/api/agent/message",
        json={
            "message": "أرغب في إقامة حارس قضائي على تركة والدي المتنازع عليها."
        },
    )
    assert classify_response.status_code == 200
    classify_payload = classify_response.json()
    session_id = classify_payload["session_id"]
    assert classify_payload["next_action"] == "confirm_classification"
    assert len(classify_payload["suggestions"]) == 3

    confirm_response = await client.post(
        "/api/agent/message",
        json={"session_id": session_id, "message": "1", "phase": 1},
    )
    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.json()

    # Hybrid flow: may return select_intake_mode and may or may not include a structured form.
    assert confirm_payload["next_action"] in {"select_intake_mode", "fill_form"}
    _assert_conversational_payload(confirm_payload)

    # Only submit the form if the backend actually produced one.
    if confirm_payload.get("interview_form"):
        assert confirm_payload["interview_form"].get("fields")

        session_response = await client.get(f"/api/sessions/{session_id}")
        assert session_response.status_code == 200
        session_payload = session_response.json()["session"]
        assert session_payload["status"] == "INTERVIEW"

        form_values = _build_form_values(confirm_payload["interview_form"])
        submit_response = await client.patch(
            f"/api/sessions/{session_id}/interview-form",
            json={"values": form_values},
        )
        assert submit_response.status_code == 200
        submit_payload = submit_response.json()
        assert submit_payload["next_action"] == "go_to_phase2"
        assert submit_payload["phase"] == 2
        assert submit_payload["inline_notice"] is None

    draft_response = await client.post(
        "/api/agent/draft",
        json={"session_id": session_id, "petition_role": "agent"},
    )
    assert draft_response.status_code == 200
    draft_payload = draft_response.json()
    assert draft_payload["petition"]["facts"]["content"]
    assert draft_payload["petition"]["version"] >= 1
    assert draft_payload["petition"]["model"] == "o3"
    assert draft_payload["petition"]["metadata"]["petition_role"] == "agent"

    update_response = await client.patch(
        f"/api/petitions/{session_id}/sections",
        json={"section": "facts", "content": "وقائع معدلة للاختبار."},
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()["petition"]
    assert update_payload["facts"]["content"] == "وقائع معدلة للاختبار."
    assert update_payload["model"] == draft_payload["petition"]["model"]
    assert update_payload["version"] == draft_payload["petition"]["version"] + 1

    review_response = await client.post(
        "/api/agent/review", json={"session_id": session_id}
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["review_report"]["recommendation"]
    assert review_payload["review_report"]["completeness_score"] >= 0

    stream_response = await client.get(
        f"/api/agent/draft/stream?session_id={session_id}"
    )
    assert stream_response.status_code == 200
    assert "complete" in stream_response.text

    export_response = await client.get(f"/api/petitions/{session_id}/export")
    assert export_response.status_code == 200
    assert "<html" in export_response.text.lower()
    assert "صحيفة دعوى" in export_response.text

    petition_id = draft_payload["petition"]["petition_id"]
    admin_list_response = await client.get("/api/admin/petitions")
    assert admin_list_response.status_code == 200
    admin_list_payload = admin_list_response.json()
    assert admin_list_payload["total"] >= 1
    matching_item = next(
        item
        for item in admin_list_payload["items"]
        if item["petition_id"] == petition_id
    )
    assert matching_item["session_id"] == session_id
    assert matching_item["model"] == "o3"
    assert matching_item["case_title"] == "إقامة حارس قضائي"
    assert (
        admin_list_payload["stats"]["average_review_score"]
        == review_payload["review_report"]["completeness_score"]
    )

    admin_detail_response = await client.get(f"/api/admin/petitions/{petition_id}")
    assert admin_detail_response.status_code == 200
    admin_detail_payload = admin_detail_response.json()
    assert admin_detail_payload["petition"]["petition_id"] == petition_id
    assert admin_detail_payload["petition"]["model"] == "o3"
    assert admin_detail_payload["session"]["session_id"] == session_id
