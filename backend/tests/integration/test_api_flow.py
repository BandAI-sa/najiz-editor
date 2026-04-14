from __future__ import annotations

import pytest

from app.models.classification import CaseSuggestion
from app.services.agent.phase1_classifier import Phase1ClassifierService


@pytest.mark.asyncio
async def test_health_and_classification_routes(client):
    health_response = await client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json()["storage"] == "memory"

    llm_config_response = await client.get("/api/config/llm")
    assert llm_config_response.status_code == 200
    assert len(llm_config_response.json()["providers"]) == 2
    assert llm_config_response.json()["providers"][0]["models"]

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
                path=["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
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
                path=["أحوال شخصية", "التصنيف العام", "التعويض عن أضرار التقاضي"],
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
                path=["أحوال شخصية", "التصنيف العام", "أتعاب المحامين والوكلاء"],
            ),
        ]

    monkeypatch.setattr(
        Phase1ClassifierService,
        "_classify_with_llm",
        fake_llm_classification,
    )

    classify_response = await client.post(
        "/api/agent/message",
        json={"message": "أرغب في إقامة حارس قضائي على تركة والدي المتنازع عليها."},
    )
    assert classify_response.status_code == 200
    classify_payload = classify_response.json()
    session_id = classify_payload["session_id"]
    assert len(classify_payload["suggestions"]) == 3

    confirm_response = await client.post(
        "/api/agent/message",
        json={"session_id": session_id, "message": "1", "phase": 1},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["next_action"] == "ask_field"

    while True:
        session_response = await client.get(f"/api/sessions/{session_id}")
        session = session_response.json()["session"]
        current_field = session["metadata"].get("current_field")
        if not current_field:
            break

        answer_response = await client.post(
            "/api/agent/message",
            json={"session_id": session_id, "message": f"{current_field}: بيانات اختبار", "phase": 1},
        )
        assert answer_response.status_code == 200
        if answer_response.json()["next_action"] == "go_to_phase2":
            break

    draft_response = await client.post("/api/agent/draft", json={"session_id": session_id})
    assert draft_response.status_code == 200
    draft_payload = draft_response.json()
    assert draft_payload["petition"]["facts"]["content"]
    assert draft_payload["petition"]["version"] >= 1

    update_response = await client.patch(
        f"/api/petitions/{session_id}/sections",
        json={"section": "facts", "content": "وقائع معدلة للاختبار."},
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()["petition"]
    assert update_payload["facts"]["content"] == "وقائع معدلة للاختبار."
    assert update_payload["version"] == draft_payload["petition"]["version"] + 1

    review_response = await client.post("/api/agent/review", json={"session_id": session_id})
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["review_report"]["recommendation"]
    assert review_payload["review_report"]["completeness_score"] >= 0

    stream_response = await client.get(f"/api/agent/draft/stream?session_id={session_id}")
    assert stream_response.status_code == 200
    assert "complete" in stream_response.text

    export_response = await client.get(f"/api/petitions/{session_id}/export")
    assert export_response.status_code == 200
    assert "<html" in export_response.text.lower()
    assert "صحيفة دعوى" in export_response.text
