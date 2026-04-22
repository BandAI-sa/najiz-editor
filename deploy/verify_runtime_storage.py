from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.database import MongoManager  # noqa: E402


COLLECTION_NAMES = ("sessions", "messages", "petitions")


def _safe_mongodb_target(uri: str) -> str:
    parsed = urlsplit(uri)
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    scheme = parsed.scheme or "mongodb"
    return f"{scheme}://{host}{port}"


async def _collect_summary() -> dict[str, object]:
    settings = Settings()
    summary: dict[str, object] = {
        "app_env": settings.app_env,
        "protected_runtime": settings.is_protected_runtime,
        "storage": "memory" if settings.use_memory_store else "mongo",
        "mongodb_database": settings.mongodb_database,
        "mongodb_target": _safe_mongodb_target(settings.mongodb_uri),
        "collections": {},
    }

    if settings.use_memory_store:
        raise RuntimeError("USE_MEMORY_STORE=true disables persistence for the admin dashboard.")

    manager = MongoManager(settings)
    await manager.connect()

    try:
        if manager.database is None:
            raise RuntimeError("Mongo database handle is unavailable.")

        collections: dict[str, object] = {}
        ttl_indexes_by_collection: dict[str, list[str]] = {}

        for collection_name in COLLECTION_NAMES:
            collection = manager.database[collection_name]
            indexes = await collection.index_information()
            ttl_indexes = sorted(
                index_name
                for index_name, details in indexes.items()
                if "expireAfterSeconds" in details
            )
            collections[collection_name] = {
                "count": await collection.count_documents({}),
                "ttl_indexes": ttl_indexes,
            }
            if ttl_indexes:
                ttl_indexes_by_collection[collection_name] = ttl_indexes

        summary["collections"] = collections

        if ttl_indexes_by_collection:
            formatted = ", ".join(
                f"{collection}={','.join(indexes)}"
                for collection, indexes in ttl_indexes_by_collection.items()
            )
            raise RuntimeError(f"TTL indexes are still present on persisted collections: {formatted}")

        return summary
    finally:
        await manager.disconnect()


def main() -> int:
    try:
        summary = asyncio.run(_collect_summary())
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
