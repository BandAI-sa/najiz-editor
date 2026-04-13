from __future__ import annotations

import json

from app.core.database import MongoManager
from app.core.security import EncryptionService
from app.models.petition import PetitionDraft


class PetitionRepository:
    def __init__(self, manager: MongoManager, encryption: EncryptionService):
        self.manager = manager
        self.encryption = encryption

    async def create(self, petition: PetitionDraft) -> PetitionDraft:
        document = self._to_document(petition)
        if self.manager.database is None:
            self.manager.memory_store.petitions.append(document)
        else:
            await self.manager.database["petitions"].insert_one(document)
        return petition

    async def save(self, petition: PetitionDraft) -> PetitionDraft:
        document = self._to_document(petition)
        if self.manager.database is None:
            self.manager.memory_store.petitions = [
                row for row in self.manager.memory_store.petitions if row["petition_id"] != petition.petition_id
            ]
            self.manager.memory_store.petitions.append(document)
        else:
            await self.manager.database["petitions"].replace_one({"petition_id": petition.petition_id}, document, upsert=True)
        return petition

    async def get_latest_by_session(self, session_id: str) -> PetitionDraft | None:
        if self.manager.database is None:
            rows = [row for row in self.manager.memory_store.petitions if row["session_id"] == session_id]
            if not rows:
                return None
            document = sorted(rows, key=lambda item: item["version"], reverse=True)[0]
        else:
            document = await self.manager.database["petitions"].find_one(
                {"session_id": session_id},
                sort=[("version", -1)],
            )
        if document is None:
            return None
        return self._from_document(document)

    async def get_by_id(self, petition_id: str) -> PetitionDraft | None:
        if self.manager.database is None:
            document = next((row for row in self.manager.memory_store.petitions if row["petition_id"] == petition_id), None)
        else:
            document = await self.manager.database["petitions"].find_one({"petition_id": petition_id})
        if document is None:
            return None
        return self._from_document(document)

    def _to_document(self, petition: PetitionDraft) -> dict:
        document = petition.model_dump(mode="json")
        sensitive = {
            "facts": petition.facts.model_dump(mode="json"),
            "evidence": petition.evidence.model_dump(mode="json"),
            "requests": petition.requests.model_dump(mode="json"),
            "full_text": petition.full_text,
        }
        document["encrypted_payload"] = self.encryption.encrypt_text(json.dumps(sensitive, ensure_ascii=False))
        document["facts"] = {}
        document["evidence"] = {}
        document["requests"] = {}
        document["full_text"] = ""
        return document

    def _from_document(self, document: dict) -> PetitionDraft:
        payload = dict(document)
        payload.pop("_id", None)
        sensitive = json.loads(self.encryption.decrypt_text(payload.get("encrypted_payload")))
        payload["facts"] = sensitive["facts"]
        payload["evidence"] = sensitive["evidence"]
        payload["requests"] = sensitive["requests"]
        payload["full_text"] = sensitive["full_text"]
        return PetitionDraft.model_validate(payload)
