from __future__ import annotations

import json
import logging
from typing import Any, Type

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMParseError
from app.services.llm.base import build_gemini_json_schema, normalize_prompt_payload, render_conversation_prompt


logger = logging.getLogger("uvicorn.error")


class GeminiResponseClient:
    provider = "gemini"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.gemini_api_key if settings.llm_provider == "gemini" and settings.llm_is_enabled else None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

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

        payload = self._build_payload(
            instructions=instructions,
            user_input=user_input,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            response_json = await self._post_generate_content(self.settings.model_for(capability), payload)
            return self._extract_text(response_json)
        except Exception:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini text generation failed: capability=%s model=%s prompt_chars=%s",
                capability,
                self.settings.model_for(capability),
                len(render_conversation_prompt(normalize_prompt_payload(instructions, user_input)[1])),
            )
            raise

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
        prompt = render_conversation_prompt(conversation)
        flattened_schema = build_gemini_json_schema(schema)
        payload = self._build_payload(
            instructions=system_instruction,
            user_input=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=flattened_schema,
        )
        try:
            response_json = await self._post_generate_content(self.settings.model_for(capability), payload)
            text = self._extract_text(response_json)
            if not text:
                logger.error(
                    "Gemini structured parse returned empty text: capability=%s model=%s raw_response=%s",
                    capability,
                    self.settings.model_for(capability),
                    self._truncate_for_logs(response_json),
                )
            return schema.model_validate_json(self._strip_code_fences(text))
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network/API dependent
            response_body = exc.response.text if exc.response is not None else ""
            logger.error(
                "Gemini structured parse HTTP error: capability=%s model=%s status=%s body=%s schema=%s prompt_chars=%s",
                capability,
                self.settings.model_for(capability),
                exc.response.status_code if exc.response is not None else "unknown",
                self._truncate_for_logs(response_body),
                schema.__name__,
                len(prompt),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": self.settings.model_for(capability),
                    "status_code": exc.response.status_code if exc.response is not None else None,
                },
            ) from exc
        except ValueError as exc:
            repaired = await self._repair_structured_json(
                capability=capability,
                schema=schema,
                flattened_schema=flattened_schema,
                invalid_text=text,
                max_output_tokens=max_output_tokens,
            )
            if repaired is not None:
                return repaired
            logger.error(
                "Gemini structured parse validation failed: capability=%s model=%s text=%s schema=%s",
                capability,
                self.settings.model_for(capability),
                self._truncate_for_logs(text),
                schema.__name__,
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": self.settings.model_for(capability),
                    "parse_stage": "schema_validation",
                },
            ) from exc
        except Exception as exc:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini structured parse failed unexpectedly: capability=%s model=%s schema=%s prompt_chars=%s",
                capability,
                self.settings.model_for(capability),
                schema.__name__,
                len(prompt),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": self.settings.model_for(capability),
                },
            ) from exc

    def _build_payload(
        self,
        *,
        instructions: str,
        user_input: Any,
        temperature: float | None,
        max_output_tokens: int | None,
        response_mime_type: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system_instruction, conversation = normalize_prompt_payload(instructions, user_input)
        prompt = render_conversation_prompt(conversation)

        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = max_output_tokens
        if response_mime_type is not None:
            generation_config["responseMimeType"] = response_mime_type
        if response_json_schema is not None:
            generation_config["responseJsonSchema"] = response_json_schema

        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt or "ابدأ التنفيذ وفق التعليمات المعطاة.",
                        }
                    ]
                }
            ]
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        if generation_config:
            payload["generationConfig"] = generation_config
        return payload

    async def _post_generate_content(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/{model}:generateContent",
                headers={
                    "x-goog-api-key": self.api_key or "",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        return response.json()

    async def _repair_structured_json(
        self,
        *,
        capability: str,
        schema: Type[Any],
        flattened_schema: dict[str, Any],
        invalid_text: str,
        max_output_tokens: int | None,
    ) -> Any | None:
        logger.warning(
            "Gemini structured output repair attempt: capability=%s model=%s schema=%s",
            capability,
            self.settings.model_for(capability),
            schema.__name__,
        )
        repair_payload = self._build_payload(
            instructions=(
                "أعد تشكيل النص التالي إلى JSON صالح ومطابق تمامًا للمخطط المرفق. "
                "أخرج JSON فقط دون أي شرح أو Markdown أو تعليقات."
            ),
            user_input=(
                "المخطط المطلوب:\n"
                f"{json.dumps(flattened_schema, ensure_ascii=False)}\n\n"
                "النص المراد إصلاحه:\n"
                f"{invalid_text}"
            ),
            temperature=0,
            max_output_tokens=max(max_output_tokens or 0, 400),
            response_mime_type="application/json",
            response_json_schema=flattened_schema,
        )
        try:
            response_json = await self._post_generate_content(self.settings.model_for(capability), repair_payload)
            repaired_text = self._extract_text(response_json)
            if not repaired_text:
                return None
            repaired = schema.model_validate_json(self._strip_code_fences(repaired_text))
            logger.info(
                "Gemini structured output repair succeeded: capability=%s model=%s schema=%s",
                capability,
                self.settings.model_for(capability),
                schema.__name__,
            )
            return repaired
        except Exception:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini structured output repair failed: capability=%s model=%s schema=%s",
                capability,
                self.settings.model_for(capability),
                schema.__name__,
            )
            return None

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if part.get("text")]
        return "".join(text_parts).strip()

    @staticmethod
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

    @staticmethod
    def _truncate_for_logs(value: Any, limit: int = 1200) -> str:
        if isinstance(value, str):
            text = value
        else:
            text = str(value)
        return text if len(text) <= limit else f"{text[:limit]}...<truncated>"
