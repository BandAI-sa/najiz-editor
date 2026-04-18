from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

from app.core.config import Settings
from app.models.classification import ClassificationCatalog


@dataclass
class MemoryStore:
    classifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    petitions: list[dict[str, Any]] = field(default_factory=list)


class MongoManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: AsyncIOMotorClient | None = None
        self.database: AsyncIOMotorDatabase | None = None
        self.memory_store = MemoryStore()

    async def connect(self) -> None:
        if self.settings.use_memory_store:
            return
        self.client = AsyncIOMotorClient(self.settings.mongodb_uri)
        self.database = self.client[self.settings.mongodb_database]
        await self.client.admin.command("ping")

    async def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.database = None

    async def ensure_indexes(self) -> None:
        if self.database is None:
            return
        await self._drop_ttl_indexes("sessions")
        await self._drop_ttl_indexes("messages")
        await self._drop_ttl_indexes("petitions")

        await self.database["classifications"].create_index([("id", ASCENDING)], unique=True)
        await self.database["classifications"].create_index([("path", ASCENDING)])
        await self.database["classifications"].create_index([("title", TEXT)])

        await self.database["sessions"].create_index([("session_id", ASCENDING)], unique=True)
        await self.database["sessions"].create_index([("updated_at", ASCENDING)])
        await self.database["sessions"].create_index([("status", ASCENDING), ("phase", ASCENDING)])

        await self.database["messages"].create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])

        await self.database["petitions"].create_index([("session_id", ASCENDING), ("version", DESCENDING)])
        await self.database["petitions"].create_index([("petition_id", ASCENDING)], unique=True)
        await self.database["petitions"].create_index([("updated_at", DESCENDING)])

    async def _drop_ttl_indexes(self, collection_name: str) -> None:
        if self.database is None:
            return

        collection = self.database[collection_name]
        indexes = await collection.index_information()
        for index_name, details in indexes.items():
            if index_name == "_id_" or "expireAfterSeconds" not in details:
                continue
            await collection.drop_index(index_name)

    async def seed_catalog(self, catalog: ClassificationCatalog) -> None:
        flat_docs = [node.model_dump(mode="json") for node in catalog.flat_nodes]
        if self.database is None:
            self.memory_store.classifications = {doc["id"]: doc for doc in flat_docs}
            return
        collection = self.database["classifications"]
        existing = await collection.count_documents({})
        if existing:
            return
        if flat_docs:
            await collection.insert_many(flat_docs)
