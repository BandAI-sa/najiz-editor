from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback
    return [item.strip() for item in value.split(",") if item.strip()]


LLMProviderName = Literal["openai", "gemini"]
LLMModelTier = Literal["flagship", "advanced", "balanced", "fast", "chat", "custom"]
LLMModelStage = Literal["stable", "preview", "alias", "custom"]
LLMModelTransport = Literal["chat_completions", "responses"]


@dataclass(frozen=True)
class LLMModelSpec:
    id: str
    label: str
    summary: str
    tier: LLMModelTier
    stage: LLMModelStage = "stable"
    notes: str = ""
    recommended: bool = False
    supports_native_structured_outputs: bool = True
    transport: LLMModelTransport = "chat_completions"


SUPPORTED_LLM_PROVIDERS: tuple[LLMProviderName, ...] = ("openai", "gemini")
LLM_PROVIDER_LABELS: dict[LLMProviderName, str] = {
    "openai": "OpenAI",
    "gemini": "Google Gemini",
}
LLM_PROVIDER_MODEL_CATALOG: dict[LLMProviderName, tuple[LLMModelSpec, ...]] = {
    "openai": (
        LLMModelSpec(
            id="gpt-5.4",
            label="GPT-5.4",
            summary="Flagship OpenAI preset for the strongest reasoning and legal drafting quality.",
            tier="flagship",
            recommended=True,
            notes="Best fit when quality matters more than latency or cost.",
        ),
        LLMModelSpec(
            id="gpt-5.2",
            label="GPT-5.2",
            summary="High-end GPT-5 family model for professional writing and complex analysis.",
            tier="advanced",
            notes="A strong heavier option below GPT-5.4 for demanding tasks.",
        ),
        LLMModelSpec(
            id="gpt-5.2-chat-latest",
            label="GPT-5.2 Chat Latest",
            summary="ChatGPT-tuned GPT-5.2 alias for more conversational behavior.",
            tier="chat",
            stage="alias",
            notes="Alias model that may track newer GPT-5.2 chat snapshots over time.",
        ),
        LLMModelSpec(
            id="gpt-5.4-mini",
            label="GPT-5.4 Mini",
            summary="Balanced lower-latency option that still handles strong reasoning well.",
            tier="balanced",
            notes="Good default when you want speed without dropping too much quality.",
        ),
        LLMModelSpec(
            id="gpt-5.4-nano",
            label="GPT-5.4 Nano",
            summary="Fastest and cheapest GPT-5.4-family preset for lighter, high-volume requests.",
            tier="fast",
            notes="Best for quick iterations and lower-cost workloads.",
        ),
    ),
    "gemini": (
        LLMModelSpec(
            id="gemini-3-pro-preview",
            label="Gemini 3 Pro Preview",
            summary="Most capable Gemini preset here for deeper reasoning and harder drafting tasks.",
            tier="flagship",
            stage="preview",
            notes="Preview model; quality is high, but behavior and availability can change.",
        ),
        LLMModelSpec(
            id="gemini-3-flash-preview",
            label="Gemini 3 Flash Preview",
            summary="Newer Gemini preview with a strong speed-to-quality balance.",
            tier="balanced",
            stage="preview",
            notes="Preview model tuned for fast, capable general work.",
        ),
        LLMModelSpec(
            id="gemini-2.5-pro",
            label="Gemini 2.5 Pro",
            summary="Stable advanced Gemini model for complex legal reasoning and long-form drafting.",
            tier="advanced",
            notes="The strongest stable Gemini preset in this app.",
        ),
        LLMModelSpec(
            id="gemini-2.5-flash",
            label="Gemini 2.5 Flash",
            summary="Stable default with strong price-performance for general legal workflows.",
            tier="balanced",
            recommended=True,
            notes="Best balance for everyday use if you prefer Gemini.",
        ),
        LLMModelSpec(
            id="gemini-2.5-flash-lite",
            label="Gemini 2.5 Flash-Lite",
            summary="Fastest budget-friendly Gemini preset for lower-latency tasks.",
            tier="fast",
            notes="Useful when responsiveness matters more than maximum depth.",
        ),
    ),
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
    allow_volatile_memory_store: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ALLOW_VOLATILE_MEMORY_STORE",
            "allow_volatile_memory_store",
        ),
    )
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

    @model_validator(mode="after")
    def validate_storage_settings(self) -> "Settings":
        normalized_env = self.app_env.strip().lower()
        if self.use_memory_store and normalized_env not in {"test", "testing"} and not self.allow_volatile_memory_store:
            raise ValueError(
                "USE_MEMORY_STORE=true disables Mongo persistence and causes dashboard history to disappear after app restarts. "
                "Set USE_MEMORY_STORE=false for deployed environments, or explicitly set ALLOW_VOLATILE_MEMORY_STORE=true "
                "only for intentional ephemeral runs."
            )

        if not self.use_memory_store and not self.mongodb_uri.strip():
            raise ValueError("MONGODB_URI is required when USE_MEMORY_STORE=false.")

        return self

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

    def configured_models_for_provider(self, provider: LLMProviderName) -> list[str]:
        if provider == "gemini":
            candidates = [
                self.gemini_model,
                self.gemini_classifier_model,
                self.gemini_interviewer_model,
                self.gemini_drafter_model,
                self.gemini_reviewer_model,
                self.gemini_guard_model,
            ]
        else:
            candidates = [
                self.openai_model,
                self.openai_classifier_model,
                self.openai_interviewer_model,
                self.openai_drafter_model,
                self.openai_reviewer_model,
                self.openai_guard_model,
            ]

        models: list[str] = []
        for model in candidates:
            if model and model not in models:
                models.append(model)
        return models

    def default_model_for_provider(self, provider: LLMProviderName) -> str:
        if provider == "gemini":
            return self.gemini_model
        return self.openai_model

    def is_provider_available(self, provider: LLMProviderName) -> bool:
        requested = self.llm_enable if self.llm_enable is not None else False
        return requested and bool(self.api_key_for(provider))

    def model_catalog_for_provider(self, provider: LLMProviderName) -> list[LLMModelSpec]:
        catalog = list(LLM_PROVIDER_MODEL_CATALOG[provider])
        known_ids = {item.id for item in catalog}
        default_model = self.default_model_for_provider(provider)

        for model_id in self.configured_models_for_provider(provider):
            if model_id in known_ids:
                continue
            catalog.insert(
                0,
                LLMModelSpec(
                    id=model_id,
                    label=model_id,
                    summary="Configured custom model from environment or per-capability override.",
                    tier="custom",
                    stage="custom",
                    notes="Custom model entry discovered from the current backend configuration.",
                    recommended=model_id == default_model,
                ),
            )
            known_ids.add(model_id)

        return catalog

    def suggested_models_for_provider(self, provider: LLMProviderName) -> list[str]:
        suggestions: list[str] = []
        for model in self.model_catalog_for_provider(provider):
            if model.id not in suggestions:
                suggestions.append(model.id)
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
