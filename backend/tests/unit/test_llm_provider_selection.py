from fastapi import FastAPI
from starlette.requests import Request

from app.core.config import Settings
from app.routers.deps import LLM_MODEL_HEADER, LLM_PROVIDER_HEADER, _resolve_llm_settings
from app.services.agent.phase1_classifier import _StructuredClassification
from app.services.llm.base import build_gemini_json_schema
from app.services.llm.factory import build_llm_client
from app.services.llm.gemini_client import GeminiResponseClient
from app.services.llm.openai_client import OpenAIResponseClient


def test_build_openai_client_from_env(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = Settings()
    client = build_llm_client(settings)

    assert isinstance(client, OpenAIResponseClient)
    assert client.provider == "openai"
    assert client.enabled is True
    assert settings.llm_is_enabled is True
    assert settings.model_for("classifier") == settings.openai_model


def test_build_gemini_client_from_env(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_CLASSIFIER_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = Settings()
    client = build_llm_client(settings)

    assert isinstance(client, GeminiResponseClient)
    assert client.provider == "gemini"
    assert client.enabled is True
    assert settings.llm_is_enabled is True
    assert settings.model_for("classifier") == "gemini-2.5-flash-lite"


def test_openai_enable_llm_alias_still_supported(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_ENABLE", raising=False)
    monkeypatch.setenv("OPENAI_ENABLE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    settings = Settings()

    assert settings.llm_is_enabled is True
    assert settings.openai_enable_llm is True


def _build_request(settings: Settings, headers: dict[str, str] | None = None) -> Request:
    app = FastAPI()
    app.state.settings = settings
    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/agent/message",
        "raw_path": b"/api/agent/message",
        "query_string": b"",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "app": app,
    }
    return Request(scope)


def test_request_headers_override_provider_and_model(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    settings = Settings()
    request = _build_request(
        settings,
        headers={
            LLM_PROVIDER_HEADER: "gemini",
            LLM_MODEL_HEADER: "gemini-2.5-pro",
        },
    )

    resolved = _resolve_llm_settings(request)

    assert resolved.llm_provider == "gemini"
    assert resolved.model_for("classifier") == "gemini-2.5-pro"
    assert resolved.model_for("drafter") == "gemini-2.5-pro"


def test_request_override_falls_back_when_provider_is_unavailable(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = Settings()
    request = _build_request(
        settings,
        headers={
            LLM_PROVIDER_HEADER: "gemini",
            LLM_MODEL_HEADER: "gemini-2.5-pro",
        },
    )

    resolved = _resolve_llm_settings(request)

    assert resolved.llm_provider == "openai"
    assert resolved.model_for("classifier") == settings.openai_model


def test_gemini_schema_is_flattened_for_structured_output():
    schema = build_gemini_json_schema(_StructuredClassification)

    assert "$defs" not in schema
    assert "title" not in schema
    assert schema["properties"]["suggestions"]["items"]["type"] == "object"
    assert "$ref" not in str(schema)
