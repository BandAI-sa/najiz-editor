from __future__ import annotations

import json
import logging
from typing import Any, Type

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import LLMParseError
from app.services.llm.base import normalize_prompt_payload


logger = logging.getLogger("uvicorn.error")

_UNSUPPORTED_TEMPERATURE_PREFIXES = ("o1", "o3", "o4")
_RESPONSES_ONLY_MODEL_PREFIXES = ("gpt-5-pro", "gpt-5.2-pro", "gpt-5.4-pro")
_NATIVE_STRUCTURED_OUTPUT_UNSUPPORTED_PREFIXES = ("gpt-5.2-pro", "gpt-5.4-pro")


def _strip_temperature_if_unsupported(model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    if any(model.startswith(prefix) for prefix in _UNSUPPORTED_TEMPERATURE_PREFIXES):
        removed = kwargs.pop("temperature", None)
        if removed is not None:
            logger.debug(
                "Temperature=%.2f removed for model '%s' (not supported by this model).",
                removed,
                model,
            )
    return kwargs


def _uses_responses_api(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in _RESPONSES_ONLY_MODEL_PREFIXES)


def _supports_native_structured_outputs(model: str) -> bool:
    return not any(model.startswith(prefix) for prefix in _NATIVE_STRUCTURED_OUTPUT_UNSUPPORTED_PREFIXES)


def _strip_code_fences(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _to_response_input(conversation: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "role": message["role"],
            "content": [{"type": "input_text", "text": message["content"]}],
        }
        for message in conversation
    ]


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
        model = self.settings.model_for(capability)
        if _uses_responses_api(model):
            return await self._generate_text_with_responses(
                model,
                system_instruction=system_instruction,
                conversation=conversation,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )

        messages = [{"role": "system", "content": system_instruction}, *conversation]
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_completion_tokens"] = max_output_tokens

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

        system_instruction, conversation = normalize_prompt_payload(instructions, user_input)
        model = self.settings.model_for(capability)
        try:
            if _uses_responses_api(model) or not _supports_native_structured_outputs(model):
                return await self._parse_structured_via_text_generation(
                    model=model,
                    capability=capability,
                    instructions=system_instruction,
                    conversation=conversation,
                    schema=schema,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )

            messages = [{"role": "system", "content": system_instruction}, *conversation]
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "response_format": schema,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_output_tokens is not None:
                kwargs["max_completion_tokens"] = max_output_tokens

            kwargs = _strip_temperature_if_unsupported(model, kwargs)
            response = await self.client.beta.chat.completions.parse(**kwargs)
            return response.choices[0].message.parsed
        except Exception as exc:  # pragma: no cover - network/API dependent
            logger.exception(
                "OpenAI structured parse failed: capability=%s model=%s message_count=%s",
                capability,
                model,
                len(conversation),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
                },
            ) from exc

    async def _generate_text_with_responses(
        self,
        model: str,
        *,
        system_instruction: str,
        conversation: list[dict[str, str]],
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> str | None:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": _to_response_input(conversation) or "",
        }
        if system_instruction:
            kwargs["instructions"] = system_instruction
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens

        kwargs = _strip_temperature_if_unsupported(model, kwargs)
        response = await self.client.responses.create(**kwargs)
        return response.output_text

    async def _parse_structured_via_text_generation(
        self,
        *,
        model: str,
        capability: str,
        instructions: str,
        conversation: list[dict[str, str]],
        schema: Type[Any],
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> Any | None:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        json_text = await self.generate_text(
            capability,
            instructions=(
                f"{instructions}\n\n"
                "Return valid JSON only with no markdown fences and no commentary. "
                "The JSON must match this schema exactly:\n"
                f"{schema_json}"
            ),
            user_input=conversation,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        if not json_text:
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
                    "parse_stage": "text_generation_empty",
                },
            )

        try:
            return schema.model_validate_json(_strip_code_fences(json_text))
        except ValueError as exc:
            logger.exception(
                "OpenAI text-based structured parse failed: capability=%s model=%s",
                capability,
                model,
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
                    "parse_stage": "text_generation_validation",
                },
            ) from exc
