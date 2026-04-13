from __future__ import annotations

from app.core.config import Settings
from app.services.llm.base import LLMClient
from app.services.llm.gemini_client import GeminiResponseClient
from app.services.llm.openai_client import OpenAIResponseClient


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "gemini":
        return GeminiResponseClient(settings)
    return OpenAIResponseClient(settings)
