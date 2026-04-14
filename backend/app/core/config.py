from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback
    return [item.strip() for item in value.split(",") if item.strip()]


LLMProviderName = Literal["openai", "gemini"]
SUPPORTED_LLM_PROVIDERS: tuple[LLMProviderName, ...] = ("openai", "gemini")
LLM_PROVIDER_LABELS: dict[LLMProviderName, str] = {
    "openai": "OpenAI",
    "gemini": "Google Gemini",
}
LLM_PROVIDER_SUGGESTED_MODELS: dict[LLMProviderName, tuple[str, ...]] = {
    "openai": ("gpt-5.4-mini", "gpt-5.4", "gpt-5.2"),
    "gemini": ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Najiz Legal Agent"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "najiz_legal_agent"
    use_memory_store: bool = False
    auto_seed_on_startup: bool = True

    llm_provider: Literal["openai", "gemini"] = Field(
        default="openai",
        validation_alias="LLM_PROVIDER",
    )
    llm_enable: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_ENABLE", "OPENAI_ENABLE_LLM"),
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    openai_classifier_model: str | None = None
    openai_interviewer_model: str | None = None
    openai_drafter_model: str | None = None
    openai_reviewer_model: str | None = None
    openai_guard_model: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_classifier_model: str | None = None
    gemini_interviewer_model: str | None = None
    gemini_drafter_model: str | None = None
    gemini_reviewer_model: str | None = None
    gemini_guard_model: str | None = None

    classify_temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices("CLASSIFY_TEMPERATURE", "OPENAI_TEMPERATURE_CLASSIFY"),
    )
    interview_temperature: float = Field(
        default=0.3,
        validation_alias="INTERVIEW_TEMPERATURE",
    )
    draft_temperature: float = Field(
        default=0.4,
        validation_alias=AliasChoices("DRAFT_TEMPERATURE", "OPENAI_TEMPERATURE_DRAFT"),
    )
    review_temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices("REVIEW_TEMPERATURE", "OPENAI_TEMPERATURE_REVIEW"),
    )

    classify_max_tokens: int = 800
    interview_max_tokens: int = 400
    draft_max_tokens: int = 3000
    review_max_tokens: int = 2000

    app_encryption_key: str = Field(min_length=8)
    session_expiry_hours: int = 24
    session_turn_limit: int = 30
    petition_version_limit: int = 10
    dispute_value_threshold: int = 100000

    cors_origins_raw: str = Field(
        default="http://localhost:8080,http://127.0.0.1:8080",
        validation_alias="CORS_ORIGINS",
    )
    allowed_hosts_raw: str = Field(
        default="localhost,127.0.0.1,testserver",
        validation_alias="APP_ALLOWED_HOSTS",
    )

    classification_data_file: str = "data/najiz-case-classifications-1447.json"
    classification_enrichment_file: str = "data/classification_enrichment.json"
    legal_references_file: str = "legal_references/sources.json"

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def classification_data_path(self) -> Path:
        return self.repo_root / self.classification_data_file

    @property
    def classification_enrichment_path(self) -> Path:
        return self.repo_root / self.classification_enrichment_file

    @property
    def legal_references_path(self) -> Path:
        return self.repo_root / self.legal_references_file

    @property
    def cors_origins(self) -> list[str]:
        return _parse_csv(
            self.cors_origins_raw,
            ["http://localhost:8080", "http://127.0.0.1:8080"],
        )

    @property
    def allowed_hosts(self) -> list[str]:
        return _parse_csv(
            self.allowed_hosts_raw,
            ["localhost", "127.0.0.1", "testserver"],
        )

    @property
    def llm_provider_api_key(self) -> str | None:
        if self.llm_provider == "gemini":
            return self.gemini_api_key
        return self.openai_api_key

    def api_key_for(self, provider: LLMProviderName) -> str | None:
        if provider == "gemini":
            return self.gemini_api_key
        return self.openai_api_key

    @property
    def llm_is_enabled(self) -> bool:
        requested = self.llm_enable if self.llm_enable is not None else False
        return requested and bool(self.llm_provider_api_key)

    @property
    def openai_enable_llm(self) -> bool:
        return self.llm_provider == "openai" and self.llm_is_enabled

    def provider_label(self, provider: LLMProviderName) -> str:
        return LLM_PROVIDER_LABELS[provider]

    def default_model_for_provider(self, provider: LLMProviderName) -> str:
        if provider == "gemini":
            return self.gemini_model
        return self.openai_model

    def is_provider_available(self, provider: LLMProviderName) -> bool:
        requested = self.llm_enable if self.llm_enable is not None else False
        return requested and bool(self.api_key_for(provider))

    def suggested_models_for_provider(self, provider: LLMProviderName) -> list[str]:
        if provider == "gemini":
            configured_models = [
                self.gemini_model,
                self.gemini_classifier_model,
                self.gemini_interviewer_model,
                self.gemini_drafter_model,
                self.gemini_reviewer_model,
                self.gemini_guard_model,
            ]
        else:
            configured_models = [
                self.openai_model,
                self.openai_classifier_model,
                self.openai_interviewer_model,
                self.openai_drafter_model,
                self.openai_reviewer_model,
                self.openai_guard_model,
            ]

        suggestions: list[str] = []
        for model in [*configured_models, *LLM_PROVIDER_SUGGESTED_MODELS[provider]]:
            if model and model not in suggestions:
                suggestions.append(model)
        return suggestions

    def with_llm_selection(self, provider: LLMProviderName, model: str | None = None) -> "Settings":
        selected_model = (model or self.default_model_for_provider(provider)).strip()
        updates: dict[str, str] = {"llm_provider": provider}

        if provider == "gemini":
            for field_name in (
                "gemini_model",
                "gemini_classifier_model",
                "gemini_interviewer_model",
                "gemini_drafter_model",
                "gemini_reviewer_model",
                "gemini_guard_model",
            ):
                updates[field_name] = selected_model
        else:
            for field_name in (
                "openai_model",
                "openai_classifier_model",
                "openai_interviewer_model",
                "openai_drafter_model",
                "openai_reviewer_model",
                "openai_guard_model",
            ):
                updates[field_name] = selected_model

        return self.model_copy(update=updates)

    def model_for(self, capability: str) -> str:
        if self.llm_provider == "gemini":
            overrides = {
                "classifier": self.gemini_classifier_model,
                "interviewer": self.gemini_interviewer_model,
                "drafter": self.gemini_drafter_model,
                "reviewer": self.gemini_reviewer_model,
                "guard": self.gemini_guard_model,
            }
            return overrides.get(capability) or self.gemini_model

        overrides = {
            "classifier": self.openai_classifier_model,
            "interviewer": self.openai_interviewer_model,
            "drafter": self.openai_drafter_model,
            "reviewer": self.openai_reviewer_model,
            "guard": self.openai_guard_model,
        }
        return overrides.get(capability) or self.openai_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
