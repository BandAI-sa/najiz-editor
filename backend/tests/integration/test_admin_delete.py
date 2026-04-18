from __future__ import annotations

import pytest

from app.core.security import EncryptionService
from app.models.petition import PetitionDraft, PetitionSection, PetitionSectionName
from app.models.session import Session
from app.repositories.message_repository import MessageRepository
from app.repositories.petition_repository import PetitionRepository
from app.repositories.session_repository import SessionRepository


def build_petition(session_id: str, version: int, petition_id: str) -> PetitionDraft:
    return PetitionDraft(
        petition_id=petition_id,
        session_id=session_id,
        version=version,
        facts=PetitionSection(name=PetitionSectionName.FACTS, title="الوقائع", content="وقائع مختصرة"),
        evidence=PetitionSection(name=PetitionSectionName.EVIDENCE, title="الأسانيد", content="أسانيد مختصرة"),
        requests=PetitionSection(name=PetitionSectionName.REQUESTS, title="الطلبات", content="طلبات مختصرة"),
        full_text="نص صحيفة تجريبي",
    )


@pytest.mark.asyncio
async def test_admin_delete_removes_last_petition_and_cleans_orphaned_session_data(client, app):
    encryption = EncryptionService(app.state.settings.app_encryption_key)
    session_repo = SessionRepository(app.state.mongo_manager, encryption)
    petition_repo = PetitionRepository(app.state.mongo_manager, encryption)
    message_repo = MessageRepository(app.state.mongo_manager)

    session = Session(session_id="session-delete-one")
    await session_repo.create(session)
    await message_repo.save(session.session_id, "رسالة اختبار", "user", 1)
    petition = build_petition(session.session_id, 1, "petition-delete-one")
    await petition_repo.create(petition)

    response = await client.delete(f"/api/admin/petitions/{petition.petition_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["petition_id"] == petition.petition_id
    assert payload["deleted_session"] is True
    assert payload["deleted_message_count"] == 1
    assert payload["remaining_petitions_in_session"] == 0
    assert await petition_repo.get_by_id(petition.petition_id) is None
    assert await session_repo.get_by_id(session.session_id) is None
    assert await message_repo.list_all(session.session_id) == []


@pytest.mark.asyncio
async def test_admin_delete_keeps_session_when_other_petitions_still_exist(client, app):
    encryption = EncryptionService(app.state.settings.app_encryption_key)
    session_repo = SessionRepository(app.state.mongo_manager, encryption)
    petition_repo = PetitionRepository(app.state.mongo_manager, encryption)
    message_repo = MessageRepository(app.state.mongo_manager)

    session = Session(session_id="session-delete-two")
    await session_repo.create(session)
    await message_repo.save(session.session_id, "رسالة مرتبطة", "assistant", 2)
    first_petition = build_petition(session.session_id, 1, "petition-delete-two-a")
    second_petition = build_petition(session.session_id, 2, "petition-delete-two-b")
    await petition_repo.create(first_petition)
    await petition_repo.create(second_petition)

    response = await client.delete(f"/api/admin/petitions/{first_petition.petition_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["petition_id"] == first_petition.petition_id
    assert payload["deleted_session"] is False
    assert payload["deleted_message_count"] == 0
    assert payload["remaining_petitions_in_session"] == 1
    assert await petition_repo.get_by_id(first_petition.petition_id) is None
    assert await petition_repo.get_by_id(second_petition.petition_id) is not None
    assert await session_repo.get_by_id(session.session_id) is not None
    assert len(await message_repo.list_all(session.session_id)) == 1
