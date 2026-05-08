from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import LLMParseError
from app.services.llm.base import LLMClient

logger = logging.getLogger("uvicorn.error")


class ExtractedField(BaseModel):
    field_name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    primary_value: str = ""
    primary_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_message: str = ""
    extracted_fields: list[ExtractedField] = Field(default_factory=list)


class _LLMExtractionSchema(BaseModel):
    """Schema sent to LLM parse_structured for answer extraction."""
    primary_value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_reason: str = ""
    additional_fields: list[ExtractedField] = Field(default_factory=list)


class SemanticAnswerExtractor:
    """Uses LLM to extract structured answers from natural-language user input.

    Supports:
    - Single-field extraction with confidence scoring
    - Multi-field extraction (user answers several things at once)
    - Clarification detection (ambiguous or partial answers)

    Falls back to raw string extraction if the LLM is unavailable.
    """

    def __init__(
        self,
        llm: LLMClient,
        temperature: float = 0.1,
        max_output_tokens: int = 400,
        confidence_threshold: float = 0.5,
    ):
        self.llm = llm
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.confidence_threshold = confidence_threshold

    async def extract(
        self,
        message: str,
        current_field: str | None,
        all_fields: list[str] | None = None,
        prior_extracted: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        if not self.llm.enabled:
            return self._fallback_extraction(message, current_field)

        try:
            return await self._extract_with_llm(
                message, current_field, all_fields, prior_extracted
            )
        except Exception:
            logger.warning(
                "SemanticAnswerExtractor: LLM extraction failed for field=%s, "
                "falling back to simple extraction.",
                current_field,
                exc_info=True,
            )
            return self._fallback_extraction(message, current_field)

    async def _extract_with_llm(
        self,
        message: str,
        current_field: str | None,
        all_fields: list[str] | None,
        prior_extracted: dict[str, Any] | None,
    ) -> ExtractionResult:
        field_context = f"الحقل المطلوب حاليًا: {current_field}" if current_field else ""

        remaining_fields = ""
        if all_fields:
            already = set((prior_extracted or {}).keys())
            missing = [f for f in all_fields if f not in already]
            if missing:
                remaining_fields = f"\nالحقول المتبقية: {', '.join(missing[:10])}"

        prior_context = ""
        if prior_extracted:
            prior_lines = [f"- {k}: {v}" for k, v in prior_extracted.items() if v]
            if prior_lines:
                prior_context = "\nالبيانات المجمعة سابقًا:\n" + "\n".join(prior_lines[:10])

        instructions = (
            "أنت مساعد متخصص في استخلاص البيانات من إجابات المستخدمين باللغة العربية.\n"
            "مهمتك:\n"
            "1. استخلص قيمة الحقل المطلوب من رسالة المستخدم\n"
            "2. إذا أجاب المستخدم عن حقول إضافية في نفس الرسالة، استخلصها في additional_fields\n"
            "3. حدد درجة الثقة (0-1) في صحة الاستخلاص\n"
            "4. إذا كانت الإجابة غامضة أو ناقصة، اضبط needs_clarification=true\n\n"
            "قواعد:\n"
            "- استخلص القيمة الفعلية فقط، بدون تكرار اسم الحقل\n"
            "- لا تخترع بيانات لم يذكرها المستخدم\n"
            "- إذا قال المستخدم «لا أعلم» أو ما شابه، اضبط confidence=0 و needs_clarification=true\n"
            "- إذا كانت الإجابة سؤالاً أو استفسارًا وليست إجابة، اضبط confidence=0\n"
        )

        user_content = f"{field_context}{remaining_fields}{prior_context}\n\nرسالة المستخدم:\n{message}"

        parsed: _LLMExtractionSchema | None = None
        try:
            parsed = await self.llm.parse_structured(
                "interviewer",
                instructions=instructions,
                user_input=[{"role": "user", "content": user_content}],
                schema=_LLMExtractionSchema,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
            )
        except LLMParseError:
            logger.warning("SemanticAnswerExtractor: structured parse failed, trying text fallback.")
            return self._fallback_extraction(message, current_field)

        if parsed is None:
            return self._fallback_extraction(message, current_field)

        return ExtractionResult(
            primary_value=parsed.primary_value.strip(),
            primary_confidence=parsed.confidence,
            needs_clarification=parsed.needs_clarification,
            clarification_message=parsed.clarification_reason,
            extracted_fields=parsed.additional_fields,
        )

    @staticmethod
    def _fallback_extraction(message: str, current_field: str | None) -> ExtractionResult:
        """Mirrors the original _extract_answer logic from Phase1InterviewerService."""
        text = message.strip()
        if ":" in text:
            _, value = text.split(":", 1)
            if value.strip():
                text = value.strip()

        return ExtractionResult(
            primary_value=text,
            primary_confidence=0.6 if text else 0.0,
            needs_clarification=not bool(text),
        )
