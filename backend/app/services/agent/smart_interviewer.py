from __future__ import annotations

import logging
import re
from typing import Any

from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.answer_validator import AnswerValidationLayer, ValidationResult
from app.services.agent.completeness_policy import CompletenessPolicy
from app.services.agent.contradiction_checker import ContradictionChecker
from app.services.agent.memory_injector import ConversationMemoryInjector
from app.services.agent.models import AgentTurnResult
from app.services.agent.phase1_interviewer import (
    SUPPLEMENTARY_OPTIONAL_FIELDS,
    Phase1InterviewerService,
)
from app.services.agent.question_humanizer import QuestionHumanizer
from app.services.agent.repetition_guard import (
    FieldCriticality,
    RepetitionAction,
    RepetitionGuard,
    classify_field_criticality,
)
from app.services.agent.semantic_extractor import ExtractionResult, SemanticAnswerExtractor

logger = logging.getLogger("uvicorn.error")

_SKIP_TRIGGERS = frozenset(
    {"تجاوز", "تخطي", "skip", "تخطى", "تجاوزه", "عدي", "التالي"}
)
_CONTINUE_TRIGGERS = frozenset({"متابعة", "نعم", "استمر", "صحيح", "صحيحة", "continue", "yes"})
_ADD_ENRICHMENT_TRIGGERS = frozenset(
    {"إضافة", "اضافة", "نعم", "اكمل", "استمر", "yes", "add"}
)
_FINISH_SUPPLEMENTARY_TRIGGERS = frozenset(
    {"اكتفي", "يكفي", "خلاص", "stop", "كفاية"}
)
_SUPPLEMENTARY_SKIP_WORDS = frozenset(
    {
        "تخطي",
        "تخطى",
        "تجاوز",
        "عدي",
        "عد",
        "التالي",
        "بعده",
        "skip",
        "next",
    }
)
_SUPPLEMENTARY_SKIP_PHRASES = frozenset(
    {
        "عدي",
        "عدي السؤال",
        "تخطي",
        "تخطي السؤال",
        "السوال التالي",
        "السؤال التالي",
        "اللي بعده",
        "روح للي بعده",
        "خلنا نعدي",
        "خلنا نتجاوز",
        "خلنا نروح للي بعده",
    }
)
_ADD_ENRICHMENT_PHRASES = frozenset(
    {
        "اضف",
        "أضف",
        "اضافة بيانات اضافية",
        "إضافة بيانات إضافية",
        "ايوه اضف",
        "ايوه أضف",
        "نعم اضف",
        "نعم أضف",
        "ابي اضيف",
        "ابغى اضيف",
        "اكمل الاضافة",
        "اكمل الاضافه",
    }
)
_FINISH_SUPPLEMENTARY_WORDS = frozenset(
    {"اكتفي", "يكفي", "خلاص", "كفاية", "كفايه", "وقف", "stop"}
)
_FINISH_SUPPLEMENTARY_PHRASES = frozenset(
    {
        "اكتفي",
        "خلاص كذا",
        "خلاص يكفي",
        "يكفي كذا",
        "كفاية كذا",
        "كفايه كذا",
        "وقف هنا",
    }
)
_CONTINUE_WORDS = frozenset(
    {"متابعة", "متابعه", "استمر", "اكمل", "كمل", "واصل", "continue", "yes", "نعم"}
)
_CONTINUE_PHRASES = frozenset(
    {"كمل", "كمّل", "واصل", "نعم كمل", "نعم كمّل", "نعم استمر"}
)
_UNCERTAINTY_WORDS = frozenset(
    {
        "مدري",
        "ماادري",
        "ماعرف",
    }
)
_UNCERTAINTY_PHRASES = frozenset(
    {
        "ما اعرف",
        "ماني عارف",
        "ماني متاكد",
        "مو متاكد",
        "مش متاكد",
        "ما ادري",
        "مدري",
        "غير متاكد",
        "ما عندي فكرة",
    }
)
_UNKNOWN_MARKER = "[يحتاج استكمال لاحق]"
_UNCERTAINTY_MAX_RETRIES = 2

_CORRECTION_PREFIXES: tuple[str, ...] = (
    "أقصد",
    "اقصد",
    "قصدي",
    "لا الصحيح",
    "الصحيح",
    "بل",
    "مو ",
    "مب ",
    "لا أقصد",
    "غلط",
    "خطأ",
    "تصحيح",
    "عفوًا",
    "عفوا",
    "سوري",
    "sorry",
)


class SmartInterviewerService(Phase1InterviewerService):
    """Drop-in replacement for Phase1InterviewerService.

    Inherits from Phase1InterviewerService so the AgentOrchestrator
    can accept it via the same ``interviewer`` parameter unchanged.
    """

    def __init__(
        self,
        repo: ClassificationRepository,
        *,
        extractor: SemanticAnswerExtractor | None = None,
        validator: AnswerValidationLayer | None = None,
        guard: RepetitionGuard | None = None,
        memory: ConversationMemoryInjector | None = None,
        humanizer: QuestionHumanizer | None = None,
        completeness: CompletenessPolicy | None = None,
        contradiction_checker: ContradictionChecker | None = None,
    ):
        super().__init__(repo)
        self.extractor = extractor
        self.validator = validator
        self.guard = guard
        self.memory = memory
        self.humanizer = humanizer or QuestionHumanizer()
        self.completeness = completeness
        self.contradiction_checker = contradiction_checker

    # ── Interview entry ──────────────────────────────────────────────

    async def start(self, session: Session) -> AgentTurnResult:
        result = await super().start(session)
        if result.next_action == "ask_field":
            field_name = session.metadata.get("current_field", "")
            hint = self._hint_for_field(session, field_name)
            result.reply = self.humanizer.humanize(
                field_name, hint=hint, is_first_question=True,
            )
        return result

    # ── Main turn handler ────────────────────────────────────────────

    async def process_turn(self, session: Session, message: str) -> AgentTurnResult:
        if session.metadata.get("pending_contradictions"):
            return self._handle_contradiction_response(session, message)

        if session.metadata.get("supplementary_state") == "awaiting_decision":
            decision = self._parse_enrichment_decision(message)
            if decision:
                return await self.handle_enrichment_decision(
                    session, decision,
                )
            return AgentTurnResult(
                reply=self._build_enrichment_offer_reply(),
                next_action="offer_optional_enrichment",
                metadata=self._intake_field_groups_metadata(),
            )

        correction_result = await self._handle_correction_if_detected(
            session, message,
        )
        if correction_result is not None:
            return correction_result

        case = (
            await self.repo.get_case(session.classification.case_id)
            if session.classification else None
        )
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply="لا توجد متطلبات مرتبطة بالتصنيف الحالي.",
                next_action="await_manual_support",
            )

        supplementary_mode = (
            session.metadata.get("supplementary_state") == "collecting"
        )
        current_field = session.metadata.get("current_field")
        field_items = case.requirements.data_fields
        required_fields = [item.name for item in field_items if item.required]
        all_field_names = [item.name for item in field_items]
        supplementary_fields = list(SUPPLEMENTARY_OPTIONAL_FIELDS)
        if supplementary_mode:
            all_field_names.extend(supplementary_fields)
        required_set = set(required_fields)
        hint_map = {item.name: item.hint for item in field_items}
        hint_map.update(self._supplementary_hint_map())

        if supplementary_mode and self._is_finish_supplementary(message):
            session.metadata["supplementary_state"] = "completed"
            return self._try_complete(
                session, field_items, None, None,
            )

        if supplementary_mode and self._is_supplementary_skip_intent(
            message,
        ):
            if current_field and current_field in supplementary_fields:
                session.extracted_data[current_field] = ""
                self._mark_supplementary_skipped(session, current_field)
                if self.guard:
                    RepetitionGuard.reset_field(
                        session.metadata, current_field,
                    )
                session.extracted_field_names = sorted(
                    session.extracted_data.keys(),
                )
            return await self._continue_after_supplementary(
                session,
                field_items,
                None,
                current_field,
                hint_map,
            )

        if current_field and self._is_explicit_skip(message):
            return self._handle_explicit_skip(
                session=session,
                field_name=current_field,
                field_required=current_field in required_set,
                field_items=field_items,
                required_fields=required_fields,
                hint_map=hint_map,
            )
        if current_field and self._is_uncertainty_intent(message):
            return self._handle_uncertainty(
                session=session,
                field_name=current_field,
                field_items=field_items,
                required_fields=required_fields,
                hint_map=hint_map,
                extraction=None,
            )

        extraction: ExtractionResult | None = None
        if current_field:
            extraction = await self._smart_extract(
                message, current_field, all_field_names, session.extracted_data,
            )

            recovery_result = await self._try_recovery_routing(
                session=session,
                message=message,
                current_field=current_field,
                extraction=extraction,
                all_field_names=all_field_names,
                required_fields=required_fields,
                hint_map=hint_map,
            )
            if recovery_result is not None:
                return recovery_result

            confidence_floor = self.extractor.confidence_threshold if self.extractor else 0.5
            if extraction.needs_clarification or extraction.primary_confidence < confidence_floor:
                return self._handle_low_confidence(
                    session,
                    current_field,
                    current_field in required_set,
                    hint=hint_map.get(current_field),
                    raw_message=message,
                    required_fields=required_fields,
                    field_items=field_items,
                    hint_map=hint_map,
                    extraction=extraction,
                )

            validation = self._smart_validate(current_field, extraction.primary_value)
            if not validation.valid:
                if validation.field_type == "unknown":
                    return self._handle_uncertainty(
                        session=session,
                        field_name=current_field,
                        field_items=field_items,
                        required_fields=required_fields,
                        hint_map=hint_map,
                        extraction=extraction,
                    )
                return self._handle_validation_failure(
                    session=session,
                    field_name=current_field,
                    validation=validation,
                    submitted_value=extraction.primary_value,
                    field_required=current_field in required_set,
                    required_fields=required_fields,
                    field_items=field_items,
                    hint_map=hint_map,
                    extraction=extraction,
                )

            session.extracted_data[current_field] = validation.cleaned_value
            if supplementary_mode and current_field in supplementary_fields:
                self._clear_supplementary_skipped(session, current_field)
            self._reset_adaptive_failure(session.metadata, current_field)
            if self.guard:
                RepetitionGuard.reset_field(session.metadata, current_field)
            fill_order = session.metadata.setdefault(
                "field_fill_order", [],
            )
            if current_field not in fill_order:
                fill_order.append(current_field)
            elif fill_order[-1] != current_field:
                fill_order.append(current_field)
            logger.info(
                "SmartInterviewer: accepted field=%s confidence=%.2f value=%s",
                current_field, extraction.primary_confidence,
                validation.cleaned_value[:60],
            )

            self._batch_extract_extras(
                extraction, all_field_names, current_field, session,
            )
            session.extracted_field_names = sorted(session.extracted_data.keys())

        completed = [n for n in required_fields if session.extracted_data.get(n)]
        missing = [n for n in required_fields if not session.extracted_data.get(n)]
        session.completion_percentage = round(
            (len(completed) / max(len(required_fields), 1)) * 100
        )
        session.flags.missing_fields = missing

        if not missing:
            if supplementary_mode:
                return await self._continue_after_supplementary(
                    session,
                    field_items,
                    extraction,
                    current_field,
                    hint_map,
                )
            if (
                session.metadata.get("enrichment_started")
                and session.metadata.get("supplementary_state")
                not in {"completed", "skipped"}
            ):
                session.metadata["supplementary_state"] = "completed"
            if session.metadata.get("supplementary_state") in {
                "completed",
                "skipped",
            }:
                return self._try_complete(
                    session, field_items, extraction, current_field,
                )
            session.metadata["supplementary_state"] = "awaiting_decision"
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply=self._build_enrichment_offer_reply(),
                next_action="offer_optional_enrichment",
                metadata=self._intake_field_groups_metadata(),
            )
        next_field = missing[0]
        session.metadata["current_field"] = next_field
        batch_count = self._count_batch_extras(extraction, all_field_names, current_field, session)
        hint = hint_map.get(next_field) or self._hint_for_field(session, next_field)
        question = self.humanizer.humanize(
            next_field, hint=hint, batch_extracted_count=batch_count,
        )
        return AgentTurnResult(reply=question, next_action="ask_field")

    # ── Completion gate ──────────────────────────────────────────────

    def _try_complete(
        self,
        session: Session,
        field_items: list,
        extraction: ExtractionResult | None,
        current_field: str | None,
    ) -> AgentTurnResult:
        supplementary_state = session.metadata.get("supplementary_state")
        if supplementary_state in {"collecting", "awaiting_decision"}:
            session.metadata["supplementary_state"] = "completed"
        if supplementary_state in {"completed", "skipped"}:
            return self._finalize_ready_to_draft(
                session,
                reply="ممتاز، البيانات جاهزة. ننتقل الآن إلى الصياغة.",
            )

        if self.contradiction_checker:
            contradictions = self.contradiction_checker.check(session.extracted_data)
            if contradictions:
                first = contradictions[0]
                session.metadata["pending_contradictions"] = [
                    {
                        "code": c.code,
                        "field_a": c.field_a,
                        "field_b": c.field_b,
                        "description": c.description,
                        "suggestion": c.suggestion,
                    }
                    for c in contradictions
                ]
                session.metadata["contradiction_attempts"] = 0
                return AgentTurnResult(
                    reply=(
                        f"قبل ما نبدأ الصياغة، لاحظت شي:\n"
                        f"{first.description}\n\n"
                        f"{first.suggestion}\n\n"
                        f"إذا المعلومات صحيحة اكتب «متابعة»، أو صحّح اللي تبي تعدّله."
                    ),
                    next_action="confirm_contradictions",
                )

        if self.completeness:
            fields_with_req = [(item.name, item.required) for item in field_items]
            verdict = self.completeness.evaluate(fields_with_req, session.extracted_data)
            if not verdict.may_proceed:
                if verdict.missing_critical:
                    next_critical = verdict.missing_critical[0]
                    session.metadata["current_field"] = next_critical
                    session.flags.missing_fields = verdict.missing_critical
                    return AgentTurnResult(
                        reply=verdict.user_message,
                        next_action="ask_field",
                    )

        session.status = SessionStatus.READY_TO_DRAFT
        session.phase = Phase.TWO
        session.completion_percentage = 100
        session.metadata.pop("current_field", None)
        session.metadata.pop("pending_contradictions", None)
        session.metadata["supplementary_state"] = "awaiting_decision"

        batch_count = len(extraction.extracted_fields) if extraction and current_field else 0
        suffix = ""
        if batch_count > 0:
            suffix = f"\n(تم تسجيل {batch_count + 1} معلومات من ردك الأخير)"
        return AgentTurnResult(
            reply=(
                "ممتاز، اكتملت جميع البيانات الأساسية."
                f"{suffix}\n"
                f"{self._build_enrichment_offer_reply()}"
            ),
            next_action="offer_optional_enrichment",
            metadata=self._intake_field_groups_metadata(),
        )

    # ── Skip handling ────────────────────────────────────────────────

    @classmethod
    def _normalize_intent_text(cls, message: str) -> str:
        text = (message or "").strip().lower()
        text = text.translate(
            str.maketrans(
                {
                    "أ": "ا",
                    "إ": "ا",
                    "آ": "ا",
                    "ى": "ي",
                    "ة": "ه",
                    "ؤ": "و",
                    "ئ": "ي",
                }
            )
        )
        text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def _matches_intent_family(
        cls,
        message: str,
        *,
        words: frozenset[str],
        phrases: frozenset[str],
    ) -> bool:
        normalized = cls._normalize_intent_text(message)
        if not normalized:
            return False
        words_set = set(normalized.split())
        if words & words_set:
            return True
        return any(
            cls._normalize_intent_text(phrase) in normalized
            for phrase in phrases
        )

    @classmethod
    def _is_explicit_skip(cls, message: str) -> bool:
        return cls._matches_intent_family(
            message,
            words=_SKIP_TRIGGERS,
            phrases=frozenset({"تخطي", "تخطى", "تجاوز"}),
        )

    @classmethod
    def _is_supplementary_skip_intent(cls, message: str) -> bool:
        return cls._matches_intent_family(
            message,
            words=_SUPPLEMENTARY_SKIP_WORDS | _SKIP_TRIGGERS,
            phrases=_SUPPLEMENTARY_SKIP_PHRASES,
        )

    @classmethod
    def _is_continue_intent(cls, message: str) -> bool:
        return cls._matches_intent_family(
            message,
            words=_CONTINUE_WORDS | _CONTINUE_TRIGGERS,
            phrases=_CONTINUE_PHRASES,
        )

    @classmethod
    def _is_uncertainty_intent(cls, message: str) -> bool:
        normalized = cls._normalize_intent_text(message).replace(" ", "")
        if normalized in {"ماادري", "مدري", "مااعرف"}:
            return True
        return cls._matches_intent_family(
            message,
            words=_UNCERTAINTY_WORDS,
            phrases=_UNCERTAINTY_PHRASES,
        )

    def _handle_explicit_skip(
        self,
        *,
        session: Session,
        field_name: str,
        field_required: bool,
        field_items: list,
        required_fields: list[str],
        hint_map: dict[str, str | None],
    ) -> AgentTurnResult:
        supplementary_mode = (
            session.metadata.get("supplementary_state") == "collecting"
        )
        if supplementary_mode and field_name in SUPPLEMENTARY_OPTIONAL_FIELDS:
            session.extracted_data[field_name] = ""
            if self.guard:
                RepetitionGuard.reset_field(
                    session.metadata, field_name,
                )
            return AgentTurnResult(
                reply=(
                    "تم تجاوزه. إذا رغبت نكمل بقية البيانات "
                    "الاختيارية أو ننتقل للصياغة."
                ),
                next_action="ask_field",
            )
        tier = classify_field_criticality(field_name, required=field_required)
        if tier == FieldCriticality.CRITICAL:
            return AgentTurnResult(
                reply=(
                    f"هذه المعلومة أساسية لسلامة الصحيفة، "
                    f"ويُفضّل إدخالها قبل المتابعة.\n"
                    f"أعطني منها ما يتوفر لديك حتى لو بصورة "
                    "مبدئية."
                ),
                next_action="ask_field",
            )
        if field_required:
            return self._mark_unknown_and_continue(
                session=session,
                field_name=field_name,
                field_items=field_items,
                required_fields=required_fields,
                hint_map=hint_map,
                extraction=None,
                reason_message=(
                    f"تم تجاوز «{field_name}» بناءً على طلبك."
                ),
            )
        session.extracted_data[field_name] = ""
        if self.guard:
            RepetitionGuard.reset_field(session.metadata, field_name)
        self._reset_adaptive_failure(session.metadata, field_name)
        session.extracted_field_names = sorted(session.extracted_data.keys())
        missing = [n for n in required_fields if not session.extracted_data.get(n)]
        completed = [n for n in required_fields if session.extracted_data.get(n)]
        session.completion_percentage = round((len(completed) / max(len(required_fields), 1)) * 100)
        session.flags.missing_fields = missing
        if not missing:
            if session.metadata.get("supplementary_state") in {"completed", "skipped"}:
                result = self._try_complete(session, field_items, None, field_name)
                if result.next_action == "go_to_phase2":
                    result.reply = (
                        f"تم تجاوز «{field_name}» بناءً على طلبك.\n"
                        f"{result.reply}"
                    )
                return result
            session.metadata["supplementary_state"] = "awaiting_decision"
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply=(
                    f"تم تجاوز «{field_name}» بناءً على طلبك.\n"
                    f"{self._build_enrichment_offer_reply()}"
                ),
                next_action="offer_optional_enrichment",
                metadata=self._intake_field_groups_metadata(),
            )
        next_field = missing[0]
        session.metadata["current_field"] = next_field
        hint = hint_map.get(next_field) or self._hint_for_field(session, next_field)
        question = self.humanizer.humanize(next_field, hint=hint)
        return AgentTurnResult(
            reply=(
                f"تم تجاوز «{field_name}» بناءً على طلبك.\n"
                f"{question}"
            ),
            next_action="ask_field",
        )

    # ── Contradiction confirmation ──────────────────────────────────

    def _handle_contradiction_response(
        self, session: Session, message: str,
    ) -> AgentTurnResult:
        stripped = message.strip().rstrip(".!؟?")
        if self._is_continue_intent(stripped):
            session.metadata.pop("pending_contradictions", None)
            session.metadata.pop("contradiction_attempts", None)
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply=(
                    "تم اعتماد البيانات الحالية بعد "
                    "المراجعة. ننتقل الآن للصياغة."
                ),
                next_action="go_to_phase2",
            )
        contradictions = session.metadata.get("pending_contradictions", [])
        attempts = int(session.metadata.get("contradiction_attempts", 0)) + 1
        session.metadata["contradiction_attempts"] = attempts
        first_code = contradictions[0].get("code", "") if contradictions else ""
        logger.info(
            "SmartInterviewer: user correcting contradiction=%s with message=%s",
            first_code, message[:60],
        )
        if attempts >= _UNCERTAINTY_MAX_RETRIES:
            unknown_fields = session.metadata.setdefault("unknown_fields", [])
            for item in contradictions:
                for key in ("field_a", "field_b"):
                    field = item.get(key)
                    if not field:
                        continue
                    session.extracted_data[field] = _UNKNOWN_MARKER
                    if field not in unknown_fields:
                        unknown_fields.append(field)
            session.metadata.pop("pending_contradictions", None)
            session.metadata.pop("contradiction_attempts", None)
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply=(
                    "واضح أن فيه تعارض غير محسوم حاليًا 👍\n"
                    f"سجّلت الحقول المتعارضة كـ {_UNKNOWN_MARKER} ونكمل الصياغة."
                ),
                next_action="go_to_phase2",
            )
        return AgentTurnResult(
            reply="شكرًا لك. للتأكيد فقط: وضّح المعلومة المتعارضة بشكل أدق عشان نكمل.",
            next_action="ask_field",
        )

    # ── Correction detection ────────────────────────────────────────

    @staticmethod
    def _is_correction_message(message: str) -> bool:
        lowered = message.strip()
        for prefix in _CORRECTION_PREFIXES:
            if lowered.startswith(prefix):
                return True
        return False

    @staticmethod
    def _extract_corrected_value(message: str) -> str:
        """Strip the correction prefix and return the actual value."""
        lowered = message.strip()
        for prefix in _CORRECTION_PREFIXES:
            if lowered.startswith(prefix):
                remainder = lowered[len(prefix):].lstrip("،:,. ")
                if remainder:
                    return remainder
        return lowered

    @staticmethod
    def _find_previous_field(session: Session) -> str | None:
        """Find the most recently filled field before current_field."""
        history: list[str] = session.metadata.get(
            "field_fill_order", [],
        )
        if history:
            return history[-1]
        current = session.metadata.get("current_field")
        for key, value in reversed(list(session.extracted_data.items())):
            if key != current and value and value != _UNKNOWN_MARKER:
                return key
        return None

    async def _handle_correction_if_detected(
        self, session: Session, message: str,
    ) -> AgentTurnResult | None:
        if not self._is_correction_message(message):
            return None

        prev_field = self._find_previous_field(session)
        if not prev_field:
            return None

        corrected_value = self._extract_corrected_value(message)
        if not corrected_value:
            return None

        extraction = await self._smart_extract(
            corrected_value,
            prev_field,
            list(session.extracted_data.keys()),
            session.extracted_data,
        )
        confidence_floor = (
            self.extractor.confidence_threshold if self.extractor else 0.5
        )
        if extraction.primary_confidence >= confidence_floor:
            validation = self._smart_validate(
                prev_field, extraction.primary_value,
            )
            if validation.valid:
                old_value = session.extracted_data.get(prev_field, "")
                session.extracted_data[prev_field] = validation.cleaned_value
                session.extracted_field_names = sorted(
                    session.extracted_data.keys(),
                )
                logger.info(
                    "SmartInterviewer: correction accepted "
                    "field=%s old=%s new=%s",
                    prev_field,
                    str(old_value)[:40],
                    validation.cleaned_value[:40],
                )
                current_field = session.metadata.get("current_field")
                current_hint = (
                    f"\nنكمل مع الحقل الحالي: {current_field}."
                    if current_field
                    else ""
                )
                return AgentTurnResult(
                    reply=(
                        f"تم تحديث «{prev_field}» بنجاح."
                        f"{current_hint}"
                    ),
                    next_action="ask_field",
                )

        return AgentTurnResult(
            reply=(
                f"ما قدرت أفهم التصحيح بشكل واضح لـ«{prev_field}». "
                "ممكن توضح القيمة الصحيحة مرة ثانية؟"
            ),
            next_action="ask_field",
        )

    @staticmethod
    def _is_narrative_field(field_name: str) -> bool:
        return any(
            token in field_name
            for token in ("وصف", "وقائع", "تفاصيل", "موضوع", "طلب")
        )

    @staticmethod
    def _is_party_like_message(message: str) -> bool:
        if not message.strip():
            return False
        return any(
            token in message
            for token in (
                "شركة",
                "مؤسسة",
                "المدعي",
                "المدعى",
                "الطرف",
                "وكيل",
                "سجل",
                "هوية",
            )
        )

    @staticmethod
    def _is_party_field(field_name: str) -> bool:
        return any(
            token in field_name
            for token in (
                "مدعي",
                "مدعى",
                "طرف",
                "وكيل",
                "هوية",
                "سجل",
                "عنوان",
                "جوال",
                "بريد",
            )
        )

    @staticmethod
    def _field_affinity_score(field_name: str, message: str) -> int:
        score = 0
        text = message.strip()
        if not text:
            return score
        families: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
            (
                ("مدعي", "مدعى", "طرف", "وكيل"),
                ("مدعي", "مدعى", "طرف", "شركة", "مؤسسة", "وكيل"),
            ),
            (
                ("هوية", "سجل", "رقم"),
                ("هوية", "اقامة", "إقامة", "سجل", "رقم"),
            ),
            (
                ("عنوان",),
                ("عنوان", "حي", "شارع", "مدينة", "وطني"),
            ),
            (
                ("جوال", "هاتف", "بريد"),
                ("جوال", "هاتف", "اتصال", "@", "بريد", "email"),
            ),
            (
                ("تاريخ", "تواريخ"),
                ("تاريخ", "/", "-", "يونيو", "مايو", "محرم"),
            ),
            (
                ("مستند", "مرفق", "إثبات", "اثبات", "دليل"),
                ("مستند", "مرفق", "عقد", "فاتورة", "رسالة", "صك"),
            ),
            (
                ("وصف", "وقائع", "تفاصيل", "طلب"),
                ("وقائع", "تفاصيل", "سبب", "طلب", "تعويض", "نزاع"),
            ),
        ]
        for field_tokens, msg_tokens in families:
            if any(token in field_name for token in field_tokens):
                score += sum(1 for token in msg_tokens if token in text)
        return score

    @staticmethod
    def _recovery_candidate_fields(
        session: Session,
        required_fields: list[str],
        current_field: str,
    ) -> list[str]:
        unknown_fields = list(
            session.metadata.get("unknown_fields", []),
        )
        marker_fields = [
            key
            for key, value in session.extracted_data.items()
            if str(value).strip() == _UNKNOWN_MARKER
        ]
        candidates: list[str] = []
        for field in unknown_fields + marker_fields:
            if field and field != current_field and field not in candidates:
                candidates.append(field)
        for field in required_fields:
            value = str(session.extracted_data.get(field, "")).strip()
            if not value and field != current_field and field not in candidates:
                candidates.append(field)
        return candidates

    async def _try_recovery_routing(
        self,
        *,
        session: Session,
        message: str,
        current_field: str,
        extraction: ExtractionResult,
        all_field_names: list[str],
        required_fields: list[str],
        hint_map: dict[str, str | None],
    ) -> AgentTurnResult | None:
        if session.metadata.get("supplementary_state") == "collecting":
            return None
        text = (message or "").strip()
        if not text:
            return None
        candidates = self._recovery_candidate_fields(
            session, required_fields, current_field,
        )
        if not candidates:
            return None

        confidence_floor = (
            self.extractor.confidence_threshold
            if self.extractor else 0.5
        )
        current_validation = self._smart_validate(
            current_field, extraction.primary_value,
        )
        current_affinity = self._field_affinity_score(
            current_field, text,
        )
        looks_mismatch = (
            extraction.needs_clarification
            or extraction.primary_confidence < confidence_floor
            or not current_validation.valid
            or (
                self._is_narrative_field(current_field)
                and self._is_party_like_message(text)
            )
        )
        if not looks_mismatch:
            return None

        best: tuple[str, str, float, int] | None = None
        for candidate in candidates:
            candidate_extraction = await self._smart_extract(
                text,
                candidate,
                all_field_names,
                session.extracted_data,
            )
            candidate_validation = self._smart_validate(
                candidate, candidate_extraction.primary_value,
            )
            if not candidate_validation.valid:
                continue
            candidate_affinity = self._field_affinity_score(
                candidate, text,
            )
            min_confidence = max(confidence_floor + 0.12, 0.68)
            is_semantically_strong = (
                candidate_affinity >= max(current_affinity + 2, 2)
            )
            is_confidently_stronger = (
                candidate_extraction.primary_confidence
                >= max(extraction.primary_confidence + 0.2, min_confidence)
            )
            party_recovery_hint = (
                self._is_narrative_field(current_field)
                and self._is_party_field(candidate)
                and self._is_party_like_message(text)
                and candidate_affinity >= 1
            )
            if not (
                is_semantically_strong
                or is_confidently_stronger
                or party_recovery_hint
            ):
                continue

            current_best = (
                candidate,
                candidate_validation.cleaned_value,
                float(candidate_extraction.primary_confidence),
                candidate_affinity,
            )
            if best is None:
                best = current_best
                continue
            if (
                current_best[3] > best[3]
                or (
                    current_best[3] == best[3]
                    and current_best[2] > best[2]
                )
            ):
                best = current_best

        if best is None:
            return None

        recovered_field, recovered_value, _, _ = best
        session.extracted_data[recovered_field] = recovered_value
        unknown_fields = session.metadata.get("unknown_fields")
        if isinstance(unknown_fields, list) and recovered_field in unknown_fields:
            unknown_fields.remove(recovered_field)
        session.extracted_field_names = sorted(
            session.extracted_data.keys(),
        )
        fill_order = session.metadata.setdefault(
            "field_fill_order", [],
        )
        if recovered_field not in fill_order:
            fill_order.append(recovered_field)
        elif fill_order[-1] != recovered_field:
            fill_order.append(recovered_field)

        hint = hint_map.get(current_field) or self._hint_for_field(
            session, current_field,
        )
        next_question = self.humanizer.humanize(
            current_field, hint=hint,
        )
        return AgentTurnResult(
            reply=(
                f"يبدو أنك تقصد تحديث «{recovered_field}» 👍\n"
                "تم تحديثها بنجاح، ونكمل مع "
                f"«{current_field}».\n"
                f"{next_question}"
            ),
            next_action="ask_field",
        )

    async def handle_enrichment_decision(
        self, session: Session, action: str,
    ) -> AgentTurnResult:
        normalized_action = (action or "").strip().lower()
        if normalized_action == "skip":
            session.metadata["supplementary_state"] = "skipped"
            session.metadata["enrichment_started"] = True
            return self._finalize_ready_to_draft(
                session,
                reply=(
                    "تم التخطي. ننتقل الآن إلى اختيار "
                    "صيغة الصحيفة ثم بدء الصياغة."
                ),
            )

        session.metadata["supplementary_state"] = "collecting"
        session.metadata["enrichment_started"] = True
        next_field = self._next_supplementary_field(session)
        if not next_field:
            session.metadata["supplementary_state"] = "completed"
            return self._finalize_ready_to_draft(
                session,
                reply=(
                    "لا توجد بيانات اختيارية غير مكتملة "
                    "حاليًا. ننتقل للصياغة."
                ),
            )
        session.metadata["current_field"] = next_field
        hint = self._supplementary_hint_map().get(next_field)
        question = self.humanizer.humanize(
            next_field,
            hint=hint,
            is_first_question=True,
        )
        return AgentTurnResult(
            reply=(
                f"{question}\n"
                "وإذا ما ودك تكمل، اكتب «تخطي»."
            ),
            next_action="ask_field",
            metadata=self._intake_field_groups_metadata(),
        )

    # ── Failure handlers ─────────────────────────────────────────────

    def _handle_low_confidence(
        self,
        session: Session,
        field_name: str,
        field_required: bool,
        *,
        hint: str | None = None,
        raw_message: str = "",
        required_fields: list[str],
        field_items: list,
        hint_map: dict[str, str | None],
        extraction: ExtractionResult | None,
    ) -> AgentTurnResult:
        if (
            session.metadata.get("supplementary_state") == "collecting"
            and field_name in SUPPLEMENTARY_OPTIONAL_FIELDS
        ):
            return AgentTurnResult(
                reply=(
                    f"غير واضح حاليًا «{field_name}».\n"
                    "إذا متوفر تقدر تضيفه، أو تكتب «تخطي»."
                ),
                next_action="ask_field",
            )
        if not self._is_pure_garbage(raw_message):
            if self._adaptive_failure_count(session.metadata, field_name, "unusable") >= _UNCERTAINTY_MAX_RETRIES:
                return self._mark_unknown_and_continue(
                    session=session,
                    field_name=field_name,
                    field_items=field_items,
                    required_fields=required_fields,
                    hint_map=hint_map,
                    extraction=extraction,
                    reason_message=(
                        f"واضح أن إجابتك على «{field_name}» غير واضحة حاليًا 👍\n"
                        f"سأضعها كـ {_UNKNOWN_MARKER} ونكمّل."
                    ),
                )

        if self.guard:
            tier = classify_field_criticality(field_name, required=field_required)
            action = self.guard.check_and_increment(
                session.metadata, field_name,
                field_required=field_required, criticality=tier,
            )
            contextual_example = self._contextual_example(field_name, session)
            if action == RepetitionAction.SKIP_OPTIONAL:
                session.extracted_data[field_name] = ""
                return AgentTurnResult(
                    reply=self.guard.build_rephrase_message(
                        field_name, action, custom_example=contextual_example,
                    ),
                    next_action="ask_field",
                )
            if action != RepetitionAction.NORMAL:
                return AgentTurnResult(
                    reply=self.guard.build_rephrase_message(
                        field_name, action, custom_example=contextual_example,
                    ),
                    next_action="ask_field",
                )

        example = self._contextual_example(field_name, session)
        example_line = f"\n{example}" if example else ""
        reply = (
            f"ما قدرت أفهم إجابتك بوضوح.{example_line}\n"
            f"ممكن توضحها بطريقة ثانية؟"
        )
        return AgentTurnResult(reply=reply, next_action="ask_field")

    def _handle_validation_failure(
        self,
        *,
        session: Session,
        field_name: str,
        validation: ValidationResult,
        submitted_value: str,
        field_required: bool,
        required_fields: list[str],
        field_items: list,
        hint_map: dict[str, str | None],
        extraction: ExtractionResult | None,
    ) -> AgentTurnResult:
        if (
            session.metadata.get("supplementary_state") == "collecting"
            and field_name in SUPPLEMENTARY_OPTIONAL_FIELDS
        ):
            return AgentTurnResult(
                reply=(
                    f"{validation.error_message}\n"
                    "إذا متوفر تقدر تضيفه، أو تكتب «تخطي»."
                ),
                next_action="ask_field",
            )
        if validation.field_type != "garbage" and not self._is_pure_garbage(submitted_value):
            if self._adaptive_failure_count(session.metadata, field_name, "invalid") >= _UNCERTAINTY_MAX_RETRIES:
                return self._mark_unknown_and_continue(
                    session=session,
                    field_name=field_name,
                    field_items=field_items,
                    required_fields=required_fields,
                    hint_map=hint_map,
                    extraction=extraction,
                    reason_message=(
                        f"واضح أن «{field_name}» غير متوفر بشكل واضح الآن 👍\n"
                        f"سأضعه كـ {_UNKNOWN_MARKER} ونكمّل."
                    ),
                )

        if self.guard:
            tier = classify_field_criticality(field_name, required=field_required)
            action = self.guard.check_and_increment(
                session.metadata, field_name,
                field_required=field_required, criticality=tier,
            )
            contextual_example = self._contextual_example(field_name, session)
            if action == RepetitionAction.SKIP_OPTIONAL:
                session.extracted_data[field_name] = ""
                return AgentTurnResult(
                    reply=self.guard.build_rephrase_message(
                        field_name, action, custom_example=contextual_example,
                    ),
                    next_action="ask_field",
                )
            if action != RepetitionAction.NORMAL:
                return AgentTurnResult(
                    reply=self.guard.build_rephrase_message(
                        field_name, action, custom_example=contextual_example,
                    ),
                    next_action="ask_field",
                )

        return AgentTurnResult(reply=validation.error_message, next_action="ask_field")

    def _handle_uncertainty(
        self,
        *,
        session: Session,
        field_name: str,
        field_items: list,
        required_fields: list[str],
        hint_map: dict[str, str | None],
        extraction: ExtractionResult | None,
    ) -> AgentTurnResult:
        count = self._adaptive_failure_count(session.metadata, field_name, "uncertainty")

        if count <= _UNCERTAINTY_MAX_RETRIES:
            if count == 1:
                return AgentTurnResult(
                    reply=(
                        f"ما عليك، لو تتذكر «{field_name}» حتى بشكل "
                        f"تقريبي اكتبها.\n"
                        f"وإذا مو متوفرة الحين اكتب «تخطي»."
                    ),
                    next_action="ask_field",
                )
            example = self._contextual_example(field_name, session)
            example_line = f"\n{example}" if example else ""
            return AgentTurnResult(
                reply=(
                    f"ما عليك، لو تتذكر «{field_name}» حتى بشكل "
                    f"تقريبي اكتبها.{example_line}\n"
                    f"وإذا مو متوفرة الحين اكتب «تخطي»."
                ),
                next_action="ask_field",
            )

        return self._mark_unknown_and_continue(
            session=session,
            field_name=field_name,
            field_items=field_items,
            required_fields=required_fields,
            hint_map=hint_map,
            extraction=extraction,
            reason_message=(
                f"واضح أنك غير متأكد من «{field_name}» حاليًا 👍\n"
                f"سأضعها كـ {_UNKNOWN_MARKER} ونكمل."
            ),
        )

    # ── Extraction helpers ───────────────────────────────────────────

    async def _smart_extract(
        self,
        message: str,
        current_field: str,
        all_fields: list[str],
        prior: dict[str, Any],
    ) -> ExtractionResult:
        if self.extractor:
            return await self.extractor.extract(
                message=message,
                current_field=current_field,
                all_fields=all_fields,
                prior_extracted=prior,
            )
        return SemanticAnswerExtractor._fallback_extraction(message, current_field)

    def _smart_validate(self, field_name: str, value: str) -> ValidationResult:
        if self.validator:
            return self.validator.validate(field_name, value)
        return ValidationResult(valid=bool(value.strip()), cleaned_value=value.strip())

    def _batch_extract_extras(
        self,
        extraction: ExtractionResult,
        all_field_names: list[str],
        current_field: str,
        session: Session,
    ) -> None:
        for extra in extraction.extracted_fields:
            if extra.field_name not in all_field_names or extra.field_name == current_field:
                continue
            if session.extracted_data.get(extra.field_name):
                continue
            extra_validation = self._smart_validate(extra.field_name, extra.value)
            if extra_validation.valid and extra.confidence >= 0.5:
                session.extracted_data[extra.field_name] = extra_validation.cleaned_value
                logger.info(
                    "SmartInterviewer: batch-extracted field=%s confidence=%.2f",
                    extra.field_name, extra.confidence,
                )

    @staticmethod
    def _count_batch_extras(
        extraction: ExtractionResult | None,
        all_field_names: list[str],
        current_field: str | None,
        session: Session,
    ) -> int:
        if not extraction or not current_field:
            return 0
        return sum(
            1 for ef in extraction.extracted_fields
            if ef.field_name in all_field_names
            and ef.field_name != current_field
            and session.extracted_data.get(ef.field_name)
        )

    @staticmethod
    def _hint_for_field(session: Session, field_name: str) -> str | None:
        if not session.classification:
            return None
        return None

    @staticmethod
    def _adaptive_failure_count(metadata: dict, field_name: str, kind: str) -> int:
        failures = metadata.setdefault("adaptive_failures", {})
        per_field = failures.setdefault(field_name, {})
        count = int(per_field.get(kind, 0)) + 1
        per_field[kind] = count
        return count

    @staticmethod
    def _reset_adaptive_failure(metadata: dict, field_name: str) -> None:
        failures = metadata.get("adaptive_failures")
        if failures and field_name in failures:
            del failures[field_name]

    @staticmethod
    def _is_pure_garbage(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        # Arabic words, digits, and date separators are likely meaningful.
        has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in stripped)
        if has_arabic:
            return False
        has_digit = any(ch.isdigit() for ch in stripped)
        if has_digit:
            return False
        # Pure non-Arabic text/symbol spam is treated as garbage and never advances.
        return True

    def _mark_unknown_and_continue(
        self,
        *,
        session: Session,
        field_name: str,
        field_items: list,
        required_fields: list[str],
        hint_map: dict[str, str | None],
        extraction: ExtractionResult | None,
        reason_message: str,
    ) -> AgentTurnResult:
        session.extracted_data[field_name] = _UNKNOWN_MARKER
        unknown_fields = session.metadata.setdefault("unknown_fields", [])
        if field_name not in unknown_fields:
            unknown_fields.append(field_name)
        self._reset_adaptive_failure(session.metadata, field_name)
        if self.guard:
            RepetitionGuard.reset_field(session.metadata, field_name)

        missing = [n for n in required_fields if not session.extracted_data.get(n)]
        completed = [n for n in required_fields if session.extracted_data.get(n)]
        session.completion_percentage = round((len(completed) / max(len(required_fields), 1)) * 100)
        session.flags.missing_fields = missing
        if not missing:
            result = self._try_complete(session, field_items, extraction, field_name)
            if result.next_action == "go_to_phase2":
                result.reply = (
                    f"{reason_message}\n"
                    "بنفس الوقت، اكتملت بقية البيانات ونقدر ننتقل للصياغة."
                )
            return result

        next_field = missing[0]
        session.metadata["current_field"] = next_field
        hint = hint_map.get(next_field) or self._hint_for_field(session, next_field)
        question = self.humanizer.humanize(next_field, hint=hint)
        return AgentTurnResult(
            reply=f"{reason_message}\n{question}",
            next_action="ask_field",
        )

    @staticmethod
    def _contextual_example(field_name: str, session: Session) -> str | None:
        field = field_name.strip()
        case_title = (session.classification.case_title if session.classification else "") or ""
        domain = "generic"
        if any(k in case_title for k in ("شحن", "نقل", "توريد", "تجاري", "بضاعة", "لوجستي")):
            domain = "shipping"
        elif any(k in case_title for k in ("حضانة", "نفقة", "زيارة", "طلاق", "أسرة", "أحوال")):
            domain = "family"
        elif any(k in case_title for k in ("تنفيذ", "سند", "شيك", "أمر", "حكم")):
            domain = "execution"

        if "تاريخ" in field or "تواريخ" in field:
            if domain == "shipping":
                return "مثال مناسب لحالتك: تأخرت الشحنة شهرين ووصلت بتاريخ 2024-01-15."
            if domain == "family":
                return "مثال مناسب لحالتك: غادرت المدعى عليها المنزل بتاريخ 2024-02-10."
            if domain == "execution":
                return "مثال مناسب لحالتك: سددت جزءًا من المبلغ بتاريخ 2024-03-01."
            return RepetitionGuard.format_example_for_field(field_name)

        if any(k in field for k in ("مستند", "أسانيد", "إثبات", "دليل")):
            if domain == "shipping":
                return "مثال مناسب: بوليصة الشحن، خطاب المطالبة، صور التلف، مراسلات المورد."
            if domain == "family":
                return "مثال مناسب: تقارير اجتماعية، رسائل بين الطرفين، شهادات شهود."
            if domain == "execution":
                return "مثال مناسب: سند تنفيذي، إشعار السداد، كشف حساب، محاضر تنفيذ."
            return RepetitionGuard.format_example_for_field(field_name)

        if any(k in field for k in ("وقائع", "تفاصيل", "وصف")):
            if domain == "shipping":
                return "مثال مناسب: تأخرت الشحنة شهرين ووصل جزء من البضاعة تالف."
            if domain == "family":
                return "مثال مناسب: يوجد خلاف على مواعيد الزيارة والاستضافة منذ بداية العام."
            if domain == "execution":
                return "مثال مناسب: سددت جزءًا من المبلغ وبقي جزء لم يتم سداده."
            return RepetitionGuard.format_example_for_field(field_name)

        return RepetitionGuard.format_example_for_field(field_name)

    async def _continue_after_supplementary(
        self,
        session: Session,
        field_items: list,
        extraction: ExtractionResult | None,
        current_field: str | None,
        hint_map: dict[str, str | None],
    ) -> AgentTurnResult:
        next_field = self._next_supplementary_field(session)
        if not next_field:
            session.metadata["supplementary_state"] = "completed"
            return self._try_complete(
                session, field_items, extraction, current_field,
            )
        session.metadata["current_field"] = next_field
        question = self.humanizer.humanize(
            next_field,
            hint=hint_map.get(next_field),
        )
        return AgentTurnResult(
            reply=(
                f"{question}\n"
                "يمكنك الإجابة أو كتابة «تخطي»، "
                "ويمكنك كتابة «اكتفي» للانتقال مباشرة."
            ),
            next_action="ask_field",
            metadata=self._intake_field_groups_metadata(),
        )

    def _next_supplementary_field(self, session: Session) -> str | None:
        skipped_fields = set(
            session.metadata.get("supplementary_skipped_fields", []),
        )
        for field_name in SUPPLEMENTARY_OPTIONAL_FIELDS:
            if field_name in skipped_fields:
                continue
            if not str(session.extracted_data.get(field_name, "")).strip():
                return field_name
        return None

    @staticmethod
    def _mark_supplementary_skipped(
        session: Session, field_name: str,
    ) -> None:
        skipped = session.metadata.setdefault(
            "supplementary_skipped_fields", [],
        )
        if field_name not in skipped:
            skipped.append(field_name)

    @staticmethod
    def _clear_supplementary_skipped(
        session: Session, field_name: str,
    ) -> None:
        skipped = session.metadata.get("supplementary_skipped_fields")
        if isinstance(skipped, list) and field_name in skipped:
            skipped.remove(field_name)

    @staticmethod
    def _supplementary_hint_map() -> dict[str, str]:
        return {
            "بيانات الوكيل": "اختياري: اسم الوكيل وصفته وبياناته الأساسية.",
            "رقم الوكالة": "اختياري: رقم الوكالة وتاريخها وجهة إصدارها.",
            "العنوان الوطني": "اختياري: العنوان الوطني أو عنوان التبليغ.",
            "رقم الهوية": "اختياري: رقم هوية إضافي إذا كان متاحًا.",
            "البريد الإلكتروني": "اختياري: بريد للتواصل عند الحاجة.",
            "الجوال": "اختياري: رقم جوال للتواصل.",
            "تقدير المطالبة": "اختياري: قيمة تقديرية للمطالبة إن وُجدت.",
            "بيانات إضافية للأطراف": "اختياري: أي تفاصيل داعمة عن الأطراف.",
        }

    @staticmethod
    def _build_enrichment_offer_reply() -> str:
        return (
            "إذا تحب، أقدر أضيف بيانات الوكيل أو "
            "بيانات التواصل الآن قبل تجهيز الصحيفة "
            "النهائية.\n"
            "اختر: إضافة بيانات إضافية أو التخطي والمتابعة."
        )

    @staticmethod
    def _parse_enrichment_decision(message: str) -> str | None:
        if SmartInterviewerService._matches_intent_family(
            message,
            words=_ADD_ENRICHMENT_TRIGGERS
            | frozenset({"اضف", "أضف"}),
            phrases=_ADD_ENRICHMENT_PHRASES,
        ):
            return "add"
        if SmartInterviewerService._matches_intent_family(
            message,
            words=_SUPPLEMENTARY_SKIP_WORDS
            | _SKIP_TRIGGERS
            | _FINISH_SUPPLEMENTARY_WORDS
            | frozenset({"لا", "no"}),
            phrases=_SUPPLEMENTARY_SKIP_PHRASES
            | _FINISH_SUPPLEMENTARY_PHRASES
            | frozenset({"خلاص", "اكتفي", "يكفي"}),
        ):
            return "skip"
        return None

    @staticmethod
    def _is_finish_supplementary(message: str) -> bool:
        return SmartInterviewerService._matches_intent_family(
            message,
            words=_FINISH_SUPPLEMENTARY_TRIGGERS
            | _FINISH_SUPPLEMENTARY_WORDS,
            phrases=_FINISH_SUPPLEMENTARY_PHRASES,
        )

    @staticmethod
    def _finalize_ready_to_draft(
        session: Session, *, reply: str,
    ) -> AgentTurnResult:
        session.status = SessionStatus.READY_TO_DRAFT
        session.phase = Phase.TWO
        session.completion_percentage = 100
        session.metadata.pop("current_field", None)
        session.metadata.pop("pending_contradictions", None)
        return AgentTurnResult(
            reply=reply,
            next_action="go_to_phase2",
        )

    @staticmethod
    def _intake_field_groups_metadata() -> dict[str, list[str]]:
        return {
            "core_required": [
                "بيانات المدعي",
                "بيانات المدعى عليه",
                "وصف الطلب الأساسي",
                "الوقائع الجوهرية",
                "التواريخ الجوهرية",
                "المستندات المتاحة",
            ],
            "supplementary_optional": list(
                SUPPLEMENTARY_OPTIONAL_FIELDS,
            ),
            "generated_later": list(
                SUPPLEMENTARY_OPTIONAL_FIELDS,
            ),
        }
