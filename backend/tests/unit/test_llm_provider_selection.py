from fastapi import FastAPI
from starlette.requests import Request

from app.core.config import Settings
from app.routers.deps import LLM_MODEL_HEADER, LLM_PROVIDER_HEADER, _resolve_llm_settings
from app.services.agent.phase1_classifier import _StructuredClassification
from app.services.llm.base import build_gemini_json_schema
from app.services.llm.factory import build_llm_client
from app.services.llm.gemini_client import GeminiResponseClient
from app.services.llm.openai_client import OpenAIResponseClient, _supports_native_structured_outputs


def test_build_openai_client_from_env(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = Settings(_env_file=None)
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

    settings = Settings(_env_file=None)
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

    settings = Settings(_env_file=None)

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

    settings = Settings(_env_file=None)
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

    settings = Settings(_env_file=None)
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


def test_model_catalog_includes_enriched_openai_and_gemini_options(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    settings = Settings(_env_file=None)

    openai_models = settings.suggested_models_for_provider("openai")
    gemini_models = settings.suggested_models_for_provider("gemini")

    assert "gpt-5.2" in openai_models
    assert "gpt-5.2-chat-latest" in openai_models
    assert "gemini-3-pro-preview" in gemini_models
    assert "gemini-3-flash-preview" in gemini_models


def test_structured_output_support_flags_pro_models_correctly():
    assert _supports_native_structured_outputs("gpt-5.2") is True
    assert _supports_native_structured_outputs("gpt-5.2-pro") is False
    assert _supports_native_structured_outputs("gpt-5.4-pro") is False


async def test_openai_structured_parse_falls_back_to_text_generation(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    settings = Settings(_env_file=None).with_llm_selection("openai", "gpt-5.2-pro")
    client = OpenAIResponseClient(settings)

    async def fake_generate_text(*args, **kwargs):
        return '{"suggestions":[{"case_id":"case-01-01-001","confidence":0.91,"rationale":"fallback"}]}'

    monkeypatch.setattr(client, "generate_text", fake_generate_text)

    parsed = await client.parse_structured(
        "classifier",
        "Return JSON.",
        [{"role": "user", "content": "facts"}],
        _StructuredClassification,
        temperature=0.2,
        max_output_tokens=200,
    )

    assert parsed.suggestions[0].case_id == "case-01-01-001"
    assert parsed.suggestions[0].confidence == 0.91


def test_gemini_schema_is_flattened_for_structured_output():
    schema = build_gemini_json_schema(_StructuredClassification)

    assert "$defs" not in schema
    assert "title" not in schema
    assert schema["properties"]["suggestions"]["items"]["type"] == "object"
    assert "$ref" not in str(schema)


def test_gemini_extract_generation_result_skips_thought_only_parts():
    result = GeminiResponseClient._extract_generation_result(
        {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {
                        "parts": [
                            {"text": "internal reasoning", "thought": True},
                        ]
                    },
                },
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": "الجواب الكامل"},
                        ]
                    },
                },
            ]
        }
    )

    assert result.text == "الجواب الكامل"
    assert result.finish_reason == "STOP"
    assert result.candidate_index == 1


async def test_gemini_flash_classifier_disables_dynamic_thinking(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    settings = Settings(_env_file=None).with_llm_selection("gemini", "gemini-2.5-flash")
    client = GeminiResponseClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(model: str, payload: dict[str, object]):
        captured["model"] = model
        captured["payload"] = payload
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "ok"}]},
                }
            ]
        }

    monkeypatch.setattr(client, "_post_generate_content", fake_post)

    result = await client.generate_text(
        "classifier",
        "Return a classification.",
        "facts",
        temperature=0.2,
        max_output_tokens=200,
    )

    assert result == "ok"
    assert captured["model"] == "gemini-2.5-flash"
    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["thinkingConfig"] == {"thinkingBudget": 0}


async def test_gemini_pro_drafter_uses_bounded_thinking_budget(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    settings = Settings(_env_file=None).with_llm_selection("gemini", "gemini-2.5-pro")
    client = GeminiResponseClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(model: str, payload: dict[str, object]):
        captured["payload"] = payload
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "draft"}]},
                }
            ]
        }

    monkeypatch.setattr(client, "_post_generate_content", fake_post)

    result = await client.generate_text(
        "drafter",
        "Draft the section.",
        "facts",
        temperature=0.3,
        max_output_tokens=2400,
    )

    assert result == "draft"
    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["thinkingConfig"] == {"thinkingBudget": 1536}


async def test_gemini_3_flash_uses_thinking_level(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_ENABLE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    settings = Settings(_env_file=None).with_llm_selection("gemini", "gemini-3.1-flash-lite")
    client = GeminiResponseClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(model: str, payload: dict[str, object]):
        captured["payload"] = payload
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "review"}]},
                }
            ]
        }

    monkeypatch.setattr(client, "_post_generate_content", fake_post)

    result = await client.generate_text(
        "reviewer",
        "Review the section.",
        "facts",
        temperature=0.2,
        max_output_tokens=1200,
    )

    assert result == "review"
    thinking_config = captured["payload"]["generationConfig"]["thinkingConfig"]
    assert thinking_config == {"thinkingLevel": "low"}
