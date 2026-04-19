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
                case_title="\u0625\u0642\u0627\u0645\u0629 \u062d\u0627\u0631\u0633 \u0642\u0636\u0627\u0626\u064a",
                main_id="main-01",
                main_title="\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                sub_id="sub-01-01",
                sub_title="\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                confidence=0.96,
                rationale="\u0645\u0637\u0627\u0628\u0642\u0629 \u0627\u0644\u0648\u0642\u0627\u0626\u0639 \u0645\u0639 \u0637\u0644\u0628 \u0625\u0642\u0627\u0645\u0629 \u062d\u0627\u0631\u0633 \u0642\u0636\u0627\u0626\u064a \u0639\u0644\u0649 \u0627\u0644\u062a\u0631\u0643\u0629.",
                path=[
                    "\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                    "\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                    "\u0625\u0642\u0627\u0645\u0629 \u062d\u0627\u0631\u0633 \u0642\u0636\u0627\u0626\u064a",
                ],
            ),
            CaseSuggestion(
                case_id="case-01-01-002",
                case_title="\u0627\u0644\u062a\u0639\u0648\u064a\u0636 \u0639\u0646 \u0623\u0636\u0631\u0627\u0631 \u0627\u0644\u062a\u0642\u0627\u0636\u064a",
                main_id="main-01",
                main_title="\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                sub_id="sub-01-01",
                sub_title="\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                confidence=0.42,
                rationale="\u0627\u0642\u062a\u0631\u0627\u062d \u062b\u0627\u0646\u0648\u064a \u062a\u062c\u0631\u064a\u0628\u064a.",
                path=[
                    "\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                    "\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                    "\u0627\u0644\u062a\u0639\u0648\u064a\u0636 \u0639\u0646 \u0623\u0636\u0631\u0627\u0631 \u0627\u0644\u062a\u0642\u0627\u0636\u064a",
                ],
            ),
            CaseSuggestion(
                case_id="case-01-01-003",
                case_title="\u0623\u062a\u0639\u0627\u0628 \u0627\u0644\u0645\u062d\u0627\u0645\u064a\u0646 \u0648\u0627\u0644\u0648\u0643\u0644\u0627\u0621",
                main_id="main-01",
                main_title="\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                sub_id="sub-01-01",
                sub_title="\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                confidence=0.31,
                rationale="\u0627\u0642\u062a\u0631\u0627\u062d \u062b\u0627\u0644\u062b \u062a\u062c\u0631\u064a\u0628\u064a.",
                path=[
                    "\u0623\u062d\u0648\u0627\u0644 \u0634\u062e\u0635\u064a\u0629",
                    "\u0627\u0644\u062a\u0635\u0646\u064a\u0641 \u0627\u0644\u0639\u0627\u0645",
                    "\u0623\u062a\u0639\u0627\u0628 \u0627\u0644\u0645\u062d\u0627\u0645\u064a\u0646 \u0648\u0627\u0644\u0648\u0643\u0644\u0627\u0621",
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
            "message": "\u0623\u0631\u063a\u0628 \u0641\u064a \u0625\u0642\u0627\u0645\u0629 \u062d\u0627\u0631\u0633 \u0642\u0636\u0627\u0626\u064a \u0639\u0644\u0649 \u062a\u0631\u0643\u0629 \u0648\u0627\u0644\u062f\u064a \u0627\u0644\u0645\u062a\u0646\u0627\u0632\u0639 \u0639\u0644\u064a\u0647\u0627."
        },
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
            json={
                "session_id": session_id,
                "message": f"{current_field}: \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u062e\u062a\u0628\u0627\u0631",
                "phase": 1,
            },
        )
        assert answer_response.status_code == 200
        if answer_response.json()["next_action"] == "go_to_phase2":
            break

    draft_response = await client.post(
        "/api/agent/draft",
        json={"session_id": session_id, "petition_role": "agent"},
    )
    assert draft_response.status_code == 200
    draft_payload = draft_response.json()
    assert draft_payload["petition"]["facts"]["content"]
    assert draft_payload["petition"]["version"] >= 1
    assert draft_payload["petition"]["model"] == "gpt-5.4-mini"
    assert draft_payload["petition"]["metadata"]["petition_role"] == "agent"

    update_response = await client.patch(
        f"/api/petitions/{session_id}/sections",
        json={"section": "facts", "content": "\u0648\u0642\u0627\u0626\u0639 \u0645\u0639\u062f\u0644\u0629 \u0644\u0644\u0627\u062e\u062a\u0628\u0627\u0631."},
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()["petition"]
    assert update_payload["facts"]["content"] == "\u0648\u0642\u0627\u0626\u0639 \u0645\u0639\u062f\u0644\u0629 \u0644\u0644\u0627\u062e\u062a\u0628\u0627\u0631."
    assert update_payload["model"] == draft_payload["petition"]["model"]
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
    assert "\u0635\u062d\u064a\u0641\u0629 \u062f\u0639\u0648\u0649" in export_response.text

    petition_id = draft_payload["petition"]["petition_id"]
    admin_list_response = await client.get("/api/admin/petitions")
    assert admin_list_response.status_code == 200
    admin_list_payload = admin_list_response.json()
    assert admin_list_payload["total"] >= 1
    matching_item = next(
        item for item in admin_list_payload["items"] if item["petition_id"] == petition_id
    )
    assert matching_item["session_id"] == session_id
    assert matching_item["model"] == "gpt-5.4-mini"
    assert matching_item["case_title"] == "\u0625\u0642\u0627\u0645\u0629 \u062d\u0627\u0631\u0633 \u0642\u0636\u0627\u0626\u064a"
    assert admin_list_payload["stats"]["average_review_score"] == review_payload["review_report"]["completeness_score"]

    admin_detail_response = await client.get(f"/api/admin/petitions/{petition_id}")
    assert admin_detail_response.status_code == 200
    admin_detail_payload = admin_detail_response.json()
    assert admin_detail_payload["petition"]["petition_id"] == petition_id
    assert admin_detail_payload["petition"]["model"] == "gpt-5.4-mini"
    assert admin_detail_payload["session"]["session_id"] == session_id
