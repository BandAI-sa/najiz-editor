from __future__ import annotations

import pytest

from app.core.security import EncryptionService
from app.models.petition import PetitionDraft, PetitionSection, PetitionSectionName
from app.models.session import Session
from app.repositories.petition_repository import PetitionRepository
from app.repositories.session_repository import SessionRepository


def build_petition(session_id: str, version: int, petition_id: str) -> PetitionDraft:
    return PetitionDraft(
        petition_id=petition_id,
        session_id=session_id,
        version=version,
        model="gpt-5.4-mini",
        facts=PetitionSection(name=PetitionSectionName.FACTS, title="الوقائع", content="وقائع مختصرة"),
        evidence=PetitionSection(name=PetitionSectionName.EVIDENCE, title="الأسانيد", content="أسانيد مختصرة"),
        requests=PetitionSection(name=PetitionSectionName.REQUESTS, title="الطلبات", content="طلبات مختصرة"),
        full_text="نص صحيفة تجريبي",
    )


@pytest.mark.asyncio
async def test_admin_petitions_limit_preserves_total_count(client, app):
    encryption = EncryptionService(app.state.settings.app_encryption_key)
    session_repo = SessionRepository(app.state.mongo_manager, encryption)
    petition_repo = PetitionRepository(app.state.mongo_manager, encryption)

    first_session = Session(session_id="session-admin-limit-a")
    second_session = Session(session_id="session-admin-limit-b")
    await session_repo.create(first_session)
    await session_repo.create(second_session)
    await petition_repo.create(build_petition(first_session.session_id, 1, "petition-admin-limit-a"))
    await petition_repo.create(build_petition(second_session.session_id, 1, "petition-admin-limit-b"))

    response = await client.get("/api/admin/petitions?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["total"] == 2
    assert payload["stats"]["total_petitions"] == 2
    assert payload["stats"]["total_sessions"] == 2
