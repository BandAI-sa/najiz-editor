from __future__ import annotations

import logging
from typing import Any, Type

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import LLMParseError
from app.services.llm.base import normalize_prompt_payload


logger = logging.getLogger("uvicorn.error")

# نماذج OpenAI التي لا تدعم تخصيص temperature (تقبل القيمة الافتراضية 1 فقط)
_UNSUPPORTED_TEMPERATURE_PREFIXES = ("o1", "o3", "o4")


def _strip_temperature_if_unsupported(model: str, kwargs: dict) -> dict:
    if any(model.startswith(prefix) for prefix in _UNSUPPORTED_TEMPERATURE_PREFIXES):
        removed = kwargs.pop("temperature", None)
        if removed is not None:
            logger.debug(
                "Temperature=%.2f removed for model '%s' (not supported by this model).",
                removed,
                model,
            )
    return kwargs


class OpenAIResponseClient:
    provider = "openai"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncOpenAI(api_key=settings.openai_api_key)
            if settings.llm_provider == "openai" and settings.llm_is_enabled and settings.openai_api_key
            else None
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def generate_text(
        self,
        capability: str,
        instructions: str,
        user_input: Any,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str | None:
        if not self.enabled:
            return None

        system_instruction, conversation = normalize_prompt_payload(instructions, user_input)
        messages = [{"role": "system", "content": system_instruction}, *conversation]

        model = self.settings.model_for(capability)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_completion_tokens"] = max_output_tokens

        # ← الإصلاح: احذف temperature إذا كان النموذج لا يدعمها
        kwargs = _strip_temperature_if_unsupported(model, kwargs)

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def parse_structured(
        self,
        capability: str,
        instructions: str,
        user_input: Any,
        schema: Type[Any],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any | None:
        if not self.enabled:
            return None
        try:
            system_instruction, conversation = normalize_prompt_payload(instructions, user_input)
            messages = [{"role": "system", "content": system_instruction}, *conversation]

            model = self.settings.model_for(capability)
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "response_format": schema,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_output_tokens is not None:
                kwargs["max_completion_tokens"] = max_output_tokens

            # ← الإصلاح: احذف temperature إذا كان النموذج لا يدعمها
            kwargs = _strip_temperature_if_unsupported(model, kwargs)

            response = await self.client.beta.chat.completions.parse(**kwargs)
            return response.choices[0].message.parsed
        except Exception as exc:  # pragma: no cover - network/API dependent
            logger.exception(
                "OpenAI structured parse failed: capability=%s model=%s message_count=%s",
                capability,
                self.settings.model_for(capability),
                len(messages),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": self.settings.model_for(capability),
                },
            ) from exc