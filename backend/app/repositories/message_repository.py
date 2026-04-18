from __future__ import annotations

from app.core.database import MongoManager
from app.models.message import MessageRecord, MessageRole


class MessageRepository:
    def __init__(self, manager: MongoManager):
        self.manager = manager

    async def save(
        self,
        session_id: str,
        content: str,
        role: MessageRole | str,
        phase: int,
        metadata: dict | None = None,
    ) -> MessageRecord:
        message = MessageRecord(
            session_id=session_id,
            role=role,
            content=content,
            phase=phase,
            metadata=metadata or {},
        )
        document = message.model_dump(mode="json")
        if self.manager.database is None:
            self.manager.memory_store.messages.append(document)
        else:
            await self.manager.database["messages"].insert_one(document)
        return message

    async def list_recent(self, session_id: str, limit: int = 5) -> list[MessageRecord]:
        if self.manager.database is None:
            rows = [item for item in self.manager.memory_store.messages if item["session_id"] == session_id]
            rows = rows[-limit:]
        else:
            cursor = self.manager.database["messages"].find({"session_id": session_id}).sort("created_at", -1).limit(limit)
            rows = list(reversed(await cursor.to_list(length=limit)))
        return [MessageRecord.model_validate(row) for row in rows]

    async def list_all(self, session_id: str) -> list[MessageRecord]:
        if self.manager.database is None:
            rows = [item for item in self.manager.memory_store.messages if item["session_id"] == session_id]
        else:
            cursor = self.manager.database["messages"].find({"session_id": session_id}).sort("created_at", 1)
            rows = await cursor.to_list(length=None)
        return [MessageRecord.model_validate(row) for row in rows]

    async def delete_by_session(self, session_id: str) -> int:
        if self.manager.database is None:
            before_count = len(self.manager.memory_store.messages)
            self.manager.memory_store.messages = [
                item for item in self.manager.memory_store.messages if item["session_id"] != session_id
            ]
            return before_count - len(self.manager.memory_store.messages)

        result = await self.manager.database["messages"].delete_many({"session_id": session_id})
        return int(result.deleted_count)
