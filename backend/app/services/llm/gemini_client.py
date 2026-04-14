from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Type

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMParseError
from app.services.llm.base import build_gemini_json_schema, normalize_prompt_payload, render_conversation_prompt


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class GeminiGenerationResult:
    text: str
    finish_reason: str | None = None
    finish_message: str | None = None
    block_reason: str | None = None
    candidate_index: int = 0


class GeminiResponseClient:
    provider = "gemini"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _SHORT_FORM_CAPABILITIES = frozenset({"classifier", "interviewer", "guard"})

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

        model = self.settings.model_for(capability)
        payload = self._build_payload(
            model=model,
            capability=capability,
            instructions=instructions,
            user_input=user_input,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            response_json = await self._post_generate_content(model, payload)
            result = self._extract_generation_result(response_json)
            self._log_generation_result(
                capability=capability,
                model=model,
                result=result,
                prompt_chars=len(render_conversation_prompt(normalize_prompt_payload(instructions, user_input)[1])),
            )
            return result.text
        except Exception:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini text generation failed: capability=%s model=%s prompt_chars=%s",
                capability,
                model,
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
        model = self.settings.model_for(capability)
        payload = self._build_payload(
            model=model,
            capability=capability,
            instructions=system_instruction,
            user_input=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=flattened_schema,
        )
        text = ""
        try:
            response_json = await self._post_generate_content(model, payload)
            result = self._extract_generation_result(response_json)
            self._log_generation_result(
                capability=capability,
                model=model,
                result=result,
                prompt_chars=len(prompt),
                schema_name=schema.__name__,
            )
            text = result.text
            if not text:
                logger.error(
                    "Gemini structured parse returned empty text: capability=%s model=%s raw_response=%s",
                    capability,
                    model,
                    self._truncate_for_logs(response_json),
                )
            return schema.model_validate_json(self._strip_code_fences(text))
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network/API dependent
            response_body = exc.response.text if exc.response is not None else ""
            logger.error(
                "Gemini structured parse HTTP error: capability=%s model=%s status=%s body=%s schema=%s prompt_chars=%s",
                capability,
                model,
                exc.response.status_code if exc.response is not None else "unknown",
                self._truncate_for_logs(response_body),
                schema.__name__,
                len(prompt),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
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
                model,
                self._truncate_for_logs(text),
                schema.__name__,
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
                    "parse_stage": "schema_validation",
                },
            ) from exc
        except Exception as exc:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini structured parse failed unexpectedly: capability=%s model=%s schema=%s prompt_chars=%s",
                capability,
                model,
                schema.__name__,
                len(prompt),
            )
            raise LLMParseError(
                capability,
                details={
                    "provider": self.provider,
                    "model": model,
                },
            ) from exc

    def _build_payload(
        self,
        *,
        model: str,
        capability: str,
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

        thinking_config = self._build_thinking_config(model=model, capability=capability)
        if thinking_config:
            generation_config["thinkingConfig"] = thinking_config

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

    def _build_thinking_config(self, *, model: str, capability: str) -> dict[str, Any] | None:
        normalized_model = model.strip().lower()

        if normalized_model.startswith("gemini-3"):
            thinking_level = self._thinking_level_for(normalized_model, capability)
            return {"thinkingLevel": thinking_level} if thinking_level else None

        if normalized_model.startswith("gemini-2.5"):
            thinking_budget = self._thinking_budget_for(normalized_model, capability)
            return {"thinkingBudget": thinking_budget} if thinking_budget is not None else None

        return None

    def _thinking_budget_for(self, model: str, capability: str) -> int | None:
        if "pro" in model:
            if capability in self._SHORT_FORM_CAPABILITIES:
                return 256
            if capability == "reviewer":
                return 1024
            if capability == "drafter":
                return 1536
            return 512

        if "flash-lite" in model:
            if capability in self._SHORT_FORM_CAPABILITIES:
                return 0
            return 512

        if "flash" in model:
            if capability in self._SHORT_FORM_CAPABILITIES:
                return 0
            if capability == "reviewer":
                return 512
            if capability == "drafter":
                return 1024
            return 256

        return None

    def _thinking_level_for(self, model: str, capability: str) -> str | None:
        if "pro" in model:
            if capability in self._SHORT_FORM_CAPABILITIES:
                return "low"
            return "medium"

        if "flash-lite" in model or "flash" in model:
            if capability in self._SHORT_FORM_CAPABILITIES:
                return "minimal"
            return "low"

        return "low"

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
        model = self.settings.model_for(capability)
        logger.warning(
            "Gemini structured output repair attempt: capability=%s model=%s schema=%s",
            capability,
            model,
            schema.__name__,
        )
        repair_payload = self._build_payload(
            model=model,
            capability=capability,
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
            response_json = await self._post_generate_content(model, repair_payload)
            repaired_result = self._extract_generation_result(response_json)
            repaired_text = repaired_result.text
            if not repaired_text:
                return None
            repaired = schema.model_validate_json(self._strip_code_fences(repaired_text))
            logger.info(
                "Gemini structured output repair succeeded: capability=%s model=%s schema=%s",
                capability,
                model,
                schema.__name__,
            )
            return repaired
        except Exception:  # pragma: no cover - network/API dependent
            logger.exception(
                "Gemini structured output repair failed: capability=%s model=%s schema=%s",
                capability,
                model,
                schema.__name__,
            )
            return None

    @staticmethod
    def _extract_generation_result(payload: dict[str, Any]) -> GeminiGenerationResult:
        prompt_feedback = payload.get("promptFeedback") or {}
        block_reason = prompt_feedback.get("blockReason")
        candidates = payload.get("candidates") or []
        if not candidates:
            return GeminiGenerationResult(text="", block_reason=block_reason)

        fallback_reason = None
        fallback_message = None
        for index, candidate in enumerate(candidates):
            finish_reason = candidate.get("finishReason")
            finish_message = candidate.get("finishMessage")
            if fallback_reason is None:
                fallback_reason = finish_reason
                fallback_message = finish_message

            parts = candidate.get("content", {}).get("parts", [])
            text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if part.get("thought"):
                    continue
                text = part.get("text")
                if text:
                    text_parts.append(str(text))

            text_value = "".join(text_parts).strip()
            if text_value:
                return GeminiGenerationResult(
                    text=text_value,
                    finish_reason=finish_reason,
                    finish_message=finish_message,
                    block_reason=block_reason,
                    candidate_index=index,
                )

        return GeminiGenerationResult(
            text="",
            finish_reason=fallback_reason,
            finish_message=fallback_message,
            block_reason=block_reason,
        )

    def _log_generation_result(
        self,
        *,
        capability: str,
        model: str,
        result: GeminiGenerationResult,
        prompt_chars: int,
        schema_name: str | None = None,
    ) -> None:
        extra = f" schema={schema_name}" if schema_name else ""

        if result.block_reason:
            logger.warning(
                "Gemini response blocked: capability=%s model=%s block_reason=%s prompt_chars=%s%s",
                capability,
                model,
                result.block_reason,
                prompt_chars,
                extra,
            )

        if result.finish_reason == "MAX_TOKENS":
            logger.warning(
                "Gemini response hit MAX_TOKENS: capability=%s model=%s prompt_chars=%s candidate_index=%s%s",
                capability,
                model,
                prompt_chars,
                result.candidate_index,
                extra,
            )
        elif result.finish_reason and result.finish_reason not in {"STOP", "FINISH_REASON_UNSPECIFIED"}:
            logger.warning(
                "Gemini response finished with non-default reason: capability=%s model=%s finish_reason=%s prompt_chars=%s%s",
                capability,
                model,
                result.finish_reason,
                prompt_chars,
                extra,
            )

        if not result.text:
            logger.warning(
                "Gemini response returned no answer text: capability=%s model=%s finish_reason=%s block_reason=%s prompt_chars=%s%s",
                capability,
                model,
                result.finish_reason,
                result.block_reason,
                prompt_chars,
                extra,
            )

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
