from __future__ import annotations

from typing import Any

from app.core.database import MongoManager
from app.core.security import EncryptionService
from app.models.session import Session


class SessionRepository:
    def __init__(self, manager: MongoManager, encryption: EncryptionService):
        self.manager = manager
        self.encryption = encryption

    async def create(self, session: Session) -> Session:
        document = self._to_document(session)
        if self.manager.database is None:
            self.manager.memory_store.sessions[session.session_id] = document
        else:
            await self.manager.database["sessions"].insert_one(document)
        return session

    async def save(self, session: Session) -> Session:
        document = self._to_document(session)
        if self.manager.database is None:
            self.manager.memory_store.sessions[session.session_id] = document
        else:
            await self.manager.database["sessions"].replace_one({"session_id": session.session_id}, document, upsert=True)
        return session

    async def get_by_id(self, session_id: str) -> Session | None:
        if self.manager.database is None:
            document = self.manager.memory_store.sessions.get(session_id)
        else:
            document = await self.manager.database["sessions"].find_one({"session_id": session_id})
        if document is None:
            return None
        return self._from_document(document)

    async def update_extracted_data(
        self,
        session_id: str,
        new_fields: dict[str, Any],
        completion_percentage: int,
        missing_fields: list[str],
    ) -> Session | None:
        session = await self.get_by_id(session_id)
        if session is None:
            return None
        session.extracted_data.update(new_fields)
        session.extracted_field_names = sorted(session.extracted_data.keys())
        session.completion_percentage = completion_percentage
        session.flags.missing_fields = missing_fields
        return await self.save(session)

    def _to_document(self, session: Session) -> dict[str, Any]:
        document = session.model_dump(mode="json")
        document["extracted_data_ciphertext"] = self.encryption.encrypt_json(session.extracted_data)
        document["extracted_data"] = {}
        return document

    def _from_document(self, document: dict[str, Any]) -> Session:
        payload = dict(document)
        payload["extracted_data"] = self.encryption.decrypt_json(payload.get("extracted_data_ciphertext"))
        payload.pop("_id", None)
        return Session.model_validate(payload)
