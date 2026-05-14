from __future__ import annotations

import logging
from typing import Any

from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.answer_validator import AnswerValidationLayer, ValidationResult
from app.services.agent.completeness_policy import CompletenessPolicy
from app.services.agent.contradiction_checker import ContradictionChecker
from app.services.agent.memory_injector import ConversationMemoryInjector
from app.services.agent.models import AgentTurnResult
from app.services.agent.phase1_interviewer import Phase1InterviewerService
from app.services.agent.question_humanizer import QuestionHumanizer
from app.services.agent.repetition_guard import (
    FieldCriticality,
    RepetitionAction,
    RepetitionGuard,
    classify_field_criticality,
)
from app.services.agent.semantic_extractor import ExtractionResult, SemanticAnswerExtractor

logger = logging.getLogger("uvicorn.error")

_SKIP_TRIGGERS = frozenset({"تجاوز", "تخطي", "skip", "تخطى", "تجاوزه"})
_CONTINUE_TRIGGERS = frozenset({"متابعة", "نعم", "استمر", "صحيح", "صحيحة", "continue", "yes"})
_UNKNOWN_MARKER = "[يحتاج استكمال لاحق]"
_UNCERTAINTY_MAX_RETRIES = 2


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

        case = (
            await self.repo.get_case(session.classification.case_id)
            if session.classification else None
        )
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply="لا توجد متطلبات مرتبطة بالتصنيف الحالي.",
                next_action="await_manual_support",
            )

        current_field = session.metadata.get("current_field")
        field_items = case.requirements.data_fields
        required_fields = [item.name for item in field_items if item.required]
        all_field_names = [item.name for item in field_items]
        required_set = set(required_fields)
        hint_map = {item.name: item.hint for item in field_items}

        if current_field and self._is_explicit_skip(message):
            return self._handle_explicit_skip(session, current_field, current_field in required_set)

        extraction: ExtractionResult | None = None
        if current_field:
            extraction = await self._smart_extract(
                message, current_field, all_field_names, session.extracted_data,
            )

            confidence_floor = self.extractor.confidence_threshold if self.extractor else 0.5
            if extraction.needs_clarification or extraction.primary_confidence < confidence_floor:
                return self._handle_low_confidence(
                    session, current_field, current_field in required_set,
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
            self._reset_adaptive_failure(session.metadata, current_field)
            if self.guard:
                RepetitionGuard.reset_field(session.metadata, current_field)
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
            return self._try_complete(session, field_items, extraction, current_field)

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

        batch_count = len(extraction.extracted_fields) if extraction and current_field else 0
        suffix = ""
        if batch_count > 0:
            suffix = f"\n(تم تسجيل {batch_count + 1} معلومات من ردك الأخير)"
        return AgentTurnResult(
            reply=f"ممتاز، اكتملت جميع البيانات المطلوبة. الحين نبدأ بصياغة صحيفة الدعوى.{suffix}",
            next_action="go_to_phase2",
        )

    # ── Skip handling ────────────────────────────────────────────────

    @staticmethod
    def _is_explicit_skip(message: str) -> bool:
        return message.strip().rstrip(".!؟?") in _SKIP_TRIGGERS

    def _handle_explicit_skip(
        self, session: Session, field_name: str, field_required: bool,
    ) -> AgentTurnResult:
        tier = classify_field_criticality(field_name, required=field_required)
        if tier == FieldCriticality.CRITICAL:
            return AgentTurnResult(
                reply=(
                    f"هالمعلومة أساسية وما نقدر نتجاوزها — "
                    f"المحكمة ما تقبل الصحيفة بدونها.\n"
                    f"حاول تعطيني اللي تعرفه."
                ),
                next_action="ask_field",
            )
        session.extracted_data[field_name] = ""
        if self.guard:
            RepetitionGuard.reset_field(session.metadata, field_name)
        return AgentTurnResult(
            reply="تمام، تجاوزناه. تقدر تضيفه لاحقًا عند تعديل الصحيفة.",
            next_action="ask_field",
        )

    # ── Contradiction confirmation ──────────────────────────────────

    def _handle_contradiction_response(
        self, session: Session, message: str,
    ) -> AgentTurnResult:
        stripped = message.strip().rstrip(".!؟?")
        if stripped in _CONTINUE_TRIGGERS:
            session.metadata.pop("pending_contradictions", None)
            session.metadata.pop("contradiction_attempts", None)
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply="تمام، نكمّل مع الصياغة بالبيانات الحالية.",
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
            f"ما قدرت أفهم إجابتك بشكل واضح.{example_line}\n"
            f"ممكن تعيد صياغتها بطريقة ثانية؟"
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

        if count < _UNCERTAINTY_MAX_RETRIES:
            example = self._contextual_example(field_name, session)
            example_line = f"\n{example}" if example else ""
            return AgentTurnResult(
                reply=(
                    f"واضح أنك غير متأكد من «{field_name}» حاليًا.{example_line}\n"
                    f"إذا تتذكر حتى بشكل تقريبي اكتبها، وإذا لا بنحاول مرة ثانية."
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
