from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.database import MongoManager


@pytest.mark.asyncio
async def test_ensure_indexes_drops_existing_ttl_indexes_before_creating_standard_indexes():
    settings = SimpleNamespace(
        use_memory_store=False,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="najiz_legal_agent",
    )
    manager = MongoManager(settings)

    sessions = AsyncMock()
    sessions.index_information.return_value = {
        "_id_": {"key": [("_id", 1)]},
        "updated_at_1": {"key": [("updated_at", 1)], "expireAfterSeconds": 86400},
    }
    messages = AsyncMock()
    messages.index_information.return_value = {
        "_id_": {"key": [("_id", 1)]},
        "created_at_1": {"key": [("created_at", 1)], "expireAfterSeconds": 86400},
    }
    petitions = AsyncMock()
    petitions.index_information.return_value = {
        "_id_": {"key": [("_id", 1)]},
        "updated_at_-1": {"key": [("updated_at", -1)], "expireAfterSeconds": 86400},
    }
    classifications = AsyncMock()
    classifications.index_information.return_value = {"_id_": {"key": [("_id", 1)]}}

    manager.database = {
        "sessions": sessions,
        "messages": messages,
        "petitions": petitions,
        "classifications": classifications,
    }

    await manager.ensure_indexes()

    sessions.drop_index.assert_awaited_once_with("updated_at_1")
    messages.drop_index.assert_awaited_once_with("created_at_1")
    petitions.drop_index.assert_awaited_once_with("updated_at_-1")
