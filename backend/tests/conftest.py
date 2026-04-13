from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application import create_app
from app.core.config import get_settings


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("USE_MEMORY_STORE", "true")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_ENABLE", "false")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("APP_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    get_settings.cache_clear()
    application = create_app()
    yield application
    get_settings.cache_clear()


@pytest.fixture
async def client(app):
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
            yield async_client
