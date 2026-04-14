from fastapi import APIRouter, Request

from app.core.config import SUPPORTED_LLM_PROVIDERS
from app.models.api import LLMConfigResponse, LLMModelOption, LLMProviderOption


router = APIRouter(tags=["config"])


@router.get("/llm", response_model=LLMConfigResponse)
async def llm_config(request: Request) -> LLMConfigResponse:
    settings = request.app.state.settings
    providers = [
        LLMProviderOption(
            id=provider,
            label=settings.provider_label(provider),
            enabled=settings.is_provider_available(provider),
            default_model=settings.default_model_for_provider(provider),
            suggested_models=settings.suggested_models_for_provider(provider),
            models=[
                LLMModelOption(
                    id=model.id,
                    label=model.label,
                    summary=model.summary,
                    tier=model.tier,
                    stage=model.stage,
                    notes=model.notes,
                    recommended=model.recommended or model.id == settings.default_model_for_provider(provider),
                )
                for model in settings.model_catalog_for_provider(provider)
            ],
        )
        for provider in SUPPORTED_LLM_PROVIDERS
    ]
    return LLMConfigResponse(
        current_provider=settings.llm_provider,
        current_model=settings.default_model_for_provider(settings.llm_provider),
        providers=providers,
    )
