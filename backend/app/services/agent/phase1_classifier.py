from __future__ import annotations

import logging
import re
from typing import Iterable

from pydantic import BaseModel, Field

from app.core.exceptions import LLMParseError
from app.models.classification import CaseSuggestion, ClassificationSelection
from app.models.common import InlineNotice
from app.models.session import Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.models import AgentTurnResult
from app.services.llm.base import LLMClient


logger = logging.getLogger("uvicorn.error")


class _StructuredSuggestion(BaseModel):
    case_id: str
    case_title: str | None = None
    main_title: str | None = None
    sub_title: str | None = None
    confidence: float
    rationale: str


class _StructuredClassification(BaseModel):
    suggestions: list[_StructuredSuggestion] = Field(default_factory=list, max_length=3)


class Phase1ClassifierService:
    def __init__(
        self,
        repo: ClassificationRepository,
        llm: LLMClient,
        classify_temperature: float = 0.2,
    ):
        self.repo = repo
        self.llm = llm
        self.classify_temperature = classify_temperature

    async def classify(self, session: Session, message: str, flat_index: str) -> AgentTurnResult:
        logger.info(
            "Classification requested: provider=%s session_id=%s status=%s message=%s",
            self.llm.provider,
            session.session_id,
            session.status,
            self._truncate_for_logs(message),
        )
        suggestions = await self._classify_with_llm(message, flat_index)
        if not suggestions:
            logger.warning(
                "Classification fallback to manual selection: provider=%s session_id=%s message=%s",
                self.llm.provider,
                session.session_id,
                self._truncate_for_logs(message),
            )
            return AgentTurnResult(
                reply=(
                    "التصنيف الأولي مضبوط الآن ليعتمد على نموذج لغوي. "
                    "لم أتمكن من الحصول على اقتراحات لأن مزود الـ LLM المختار غير مفعّل أو لم يُرجع نتيجة صالحة. "
                    "فعّل `LLM_ENABLE=true` مع مفتاح المزود المختار (`OPENAI_API_KEY` أو `GEMINI_API_KEY`) "
                    "أو اختر التصنيف يدويًا من القوائم."
                ),
                next_action="manual_classification_required",
            )

        if self._should_request_clarification(message, suggestions):
            warning = self._build_ambiguity_warning()
            session.inline_notice = warning
            session.interview_form = None
            session.metadata.pop("classification_suggestions", None)
            logger.info(
                "Classification marked ambiguous: provider=%s session_id=%s top_case_id=%s top_confidence=%.2f",
                self.llm.provider,
                session.session_id,
                suggestions[0].case_id if suggestions else "none",
                suggestions[0].confidence if suggestions else 0.0,
            )
            return AgentTurnResult(
                reply=warning.message,
                next_action="clarify_classification",
                inline_notice=warning,
            )

        session.status = SessionStatus.AWAITING_CLASSIFICATION_CONFIRM
        session.inline_notice = None
        session.interview_form = None
        session.metadata["classification_backend"] = self.llm.provider
        session.metadata["classification_suggestions"] = [item.model_dump(mode="json") for item in suggestions]
        logger.info(
            "Classification produced %s suggestion(s): provider=%s session_id=%s case_ids=%s",
            len(suggestions),
            self.llm.provider,
            session.session_id,
            ", ".join(item.case_id for item in suggestions),
        )

        numbered = "\n".join(
            f"{index}. {item.main_title} > {item.sub_title} > {item.case_title} ({round(item.confidence * 100)}%)"
            for index, item in enumerate(suggestions, start=1)
        )
        reply = (
            "هذه أقرب التصنيفات المتاحة بناءً على الوقائع الحالية:\n"
            f"{numbered}\n\n"
            "يمكنك تأكيد أحدها بكتابة الرقم، أو اختيار تصنيف يدويًا من القوائم."
        )
        return AgentTurnResult(
            reply=reply,
            next_action="confirm_classification",
            suggestions=suggestions,
        )

    async def handle_confirmation(self, session: Session, message: str) -> AgentTurnResult:
        suggestions = [CaseSuggestion.model_validate(item) for item in session.metadata.get("classification_suggestions", [])]
        selected = await self._pick_selection(message, suggestions)
        if selected is None:
            return AgentTurnResult(
                reply="لم يتم تأكيد التصنيف بعد. اختر رقمًا من الاقتراحات أو استخدم التصنيف اليدوي من القوائم.",
                next_action="confirm_classification",
                suggestions=suggestions,
            )

        session.classification = selected
        session.status = SessionStatus.INTERVIEW
        session.inline_notice = None
        return AgentTurnResult(
            reply=f"تم اعتماد التصنيف: {selected.main_title} > {selected.sub_title} > {selected.case_title}",
            next_action="start_interview",
            classification=selected,
        )

    async def _classify_with_llm(self, message: str, flat_index: str) -> list[CaseSuggestion]:
        suggestions: list[CaseSuggestion] = []
        structured: _StructuredClassification | None = None
        try:
            structured = await self.llm.parse_structured(
                "classifier",
                instructions=(
                    "أنت وكيل قانوني ذكي متخصص في القانون السعودي وكتابة صحائف الدعاوى الشرعية.\n"
                    "هويتك وأسلوبك:\n"
                    "- تتحدث العربية الفصحى القانونية الرسمية في المخرجات القانونية\n"
                    "- تتسم بالحياد والدقة وعدم المبالغة\n"
                    "- لا تُصدر أحكامًا على صحة الوقائع بل تصوغها كما أُعطيت لك\n"
                    "قيودك الصارمة:\n"
                    "- لا تختراع وقائع أو أرقامًا لم يذكرها المستخدم\n"
                    "- إذا كانت المعلومات ناقصة، لا تملأ الفراغات بافتراضات\n\n"
                    "أنت الآن في مرحلة تصنيف الدعوى وفق هرم تصنيفات منصة ناجز.\n"
                    "مهمتك:\n"
                    "1. اقرأ وقائع المستخدم بعناية\n"
                    "2. حدد أفضل 3 أنواع دعوى مناسبة مرتبةً من الأكثر ملاءمة إلى الأقل من الفهرس المرسل\n"
                    "3. لكل اقتراح وضّح سبب الاقتراح مرتبطًا بكلمات المستخدم، ودرجة الثقة.\n"
                    "4. انسخ case_id حرفيًا من الفهرس بين الأقواس، ولا تختصره أو تحذف الأصفار.\n"
                    "5. أعد من 1 إلى 3 اقتراحات فقط.\n"
                    "أعد JSON منظمًا مع case_id وcase_title وmain_title وsub_title والثقة والمبرر."
                ),
                user_input=[
                    {
                        "role": "system",
                        "content": (
                            "استخدم فقط المعرّفات الموجودة في الفهرس. "
                            "انسخ case_id كاملًا كما هو، مع كل الأصفار. "
                            "أعد حتى 3 اقتراحات فقط."
                        ),
                    },
                    {"role": "user", "content": f"الفهرس:\n{flat_index}\n\nالوقائع:\n{message}"},
                ],
                schema=_StructuredClassification,
                temperature=self.classify_temperature,
                max_output_tokens=800,
            )
        except LLMParseError:
            logger.warning("Classification structured parse failed; attempting text recovery.")

        structured_suggestions = await self._build_suggestions_from_structured(structured)
        if structured_suggestions:
            logger.info(
                "Classification structured resolution succeeded with %s suggestion(s).",
                len(structured_suggestions),
            )
            suggestions = self._merge_suggestions(suggestions, structured_suggestions)

        if len(suggestions) < 3:
            recovered = await self._classify_with_text_recovery(message, flat_index)
            if recovered:
                logger.info("Classification text recovery succeeded with %s suggestion(s).", len(recovered))
                suggestions = self._merge_suggestions(suggestions, recovered)

        if len(suggestions) < 3:
            same_sub_padding = await self._build_repo_padding(
                message,
                suggestions,
                include_same_sub=True,
                include_same_main=False,
                include_general=False,
            )
            if same_sub_padding:
                logger.info(
                    "Classification repository same-sub padding added %s suggestion(s).",
                    len(same_sub_padding),
                )
                suggestions = self._merge_suggestions(suggestions, same_sub_padding)

        if len(suggestions) < 3:
            shortlist_recovered = await self._classify_with_candidate_recovery(message)
            if shortlist_recovered:
                logger.info(
                    "Classification candidate recovery succeeded with %s suggestion(s).",
                    len(shortlist_recovered),
                )
                suggestions = self._merge_suggestions(suggestions, shortlist_recovered)

        if len(suggestions) < 3:
            repo_padding = await self._build_repo_padding(
                message,
                suggestions,
                include_same_sub=False,
                include_same_main=True,
                include_general=True,
            )
            if repo_padding:
                logger.info(
                    "Classification repository padding added %s suggestion(s).",
                    len(repo_padding),
                )
                suggestions = self._merge_suggestions(suggestions, repo_padding)

        return suggestions[:3]

    async def _build_suggestions_from_structured(
        self,
        structured: _StructuredClassification | None,
    ) -> list[CaseSuggestion]:
        if structured is None:
            return []

        suggestions: list[CaseSuggestion] = []
        for item in structured.suggestions[:3]:
            selection = await self._resolve_structured_suggestion(item)
            if selection is None:
                logger.warning(
                    "Classifier suggestion could not be resolved: case_id=%s case_title=%s main_title=%s sub_title=%s rationale=%s",
                    item.case_id,
                    item.case_title,
                    item.main_title,
                    item.sub_title,
                    item.rationale,
                )
                continue
            suggestions.append(
                CaseSuggestion(
                    case_id=selection.case_id,
                    case_title=selection.case_title,
                    main_id=selection.main_id,
                    main_title=selection.main_title,
                    sub_id=selection.sub_id,
                    sub_title=selection.sub_title,
                    confidence=max(0.1, min(0.99, item.confidence)),
                    rationale=item.rationale,
                    path=selection.case_path,
                )
            )
        return suggestions

    async def _classify_with_text_recovery(
        self,
        message: str,
        flat_index: str,
    ) -> list[CaseSuggestion]:
        text = await self.llm.generate_text(
            "classifier",
            instructions=(
                "أنت في محاولة استرداد لتصنيف دعوى من فهرس ناجز.\n"
                "اختر من 1 إلى 3 أسطر فقط من الفهرس تكون الأقرب للوقائع.\n"
                "انسخ case_id كاملًا كما هو من الفهرس، ثم confidence بين 0 و1، ثم rationale موجز.\n"
                "صيغة كل سطر يجب أن تكون هكذا فقط:\n"
                "[case-xx-xx-xxx] | confidence=0.95 | rationale=...\n"
                "لا تضف أي سطور أخرى."
            ),
            user_input=[
                {
                    "role": "system",
                    "content": "اختر فقط من الفهرس المرفق، ولا تخترع case_id غير موجود.",
                },
                {
                    "role": "user",
                    "content": f"الفهرس:\n{flat_index}\n\nالوقائع:\n{message}",
                },
            ],
            temperature=self.classify_temperature,
            max_output_tokens=500,
        )
        if not text:
            return []

        suggestions: list[CaseSuggestion] = []
        seen_case_ids: set[str] = set()
        for line in text.splitlines():
            case_match = re.search(r"\[(case-\d{2}-\d{2}-\d{3})\]", line)
            if not case_match:
                continue
            case_id = case_match.group(1)
            if case_id in seen_case_ids:
                continue
            selection = await self.repo.resolve_selection(case_id)
            if selection is None:
                continue
            seen_case_ids.add(case_id)

            confidence_match = re.search(r"confidence\s*=\s*([01](?:\.\d+)?)", line)
            confidence = float(confidence_match.group(1)) if confidence_match else 0.75
            rationale_match = re.search(r"rationale\s*=\s*(.+)$", line)
            rationale = rationale_match.group(1).strip() if rationale_match else "اقتراح مستخرج من محاولة الاسترداد النصية."

            suggestions.append(
                CaseSuggestion(
                    case_id=selection.case_id,
                    case_title=selection.case_title,
                    main_id=selection.main_id,
                    main_title=selection.main_title,
                    sub_id=selection.sub_id,
                    sub_title=selection.sub_title,
                    confidence=max(0.1, min(0.99, confidence)),
                    rationale=rationale,
                    path=selection.case_path,
                )
            )
            if len(suggestions) >= 3:
                break

        return suggestions

    async def _classify_with_candidate_recovery(self, message: str) -> list[CaseSuggestion]:
        candidate_nodes = await self.repo.search_cases(message, limit=30)
        if not candidate_nodes:
            logger.warning("Classification candidate recovery skipped because shortlist is empty.")
            return []

        candidate_index = "\n".join(
            f"[{node.id}] {' > '.join(node.path)}: {node.description}"
            for node in candidate_nodes
        )
        logger.info(
            "Classification candidate recovery shortlist size=%s top_candidates=%s",
            len(candidate_nodes),
            " | ".join(f"{node.id}:{' > '.join(node.path)}" for node in candidate_nodes[:10]),
        )
        return await self._classify_with_text_recovery(message, candidate_index)

    async def _build_repo_padding(
        self,
        message: str,
        suggestions: list[CaseSuggestion],
        *,
        include_same_sub: bool,
        include_same_main: bool,
        include_general: bool,
    ) -> list[CaseSuggestion]:
        if not suggestions:
            return []

        seed = suggestions[0]
        seen_case_ids = {item.case_id for item in suggestions}
        ranked_nodes = await self.repo.search_cases(message, limit=40)
        same_sub: list[CaseSuggestion] = []
        same_main: list[CaseSuggestion] = []
        general: list[CaseSuggestion] = []

        for node in ranked_nodes:
            if node.id in seen_case_ids:
                continue
            selection = await self.repo.resolve_selection(node.id)
            if selection is None:
                continue
            suggestion = self._build_repo_suggestion(selection, seed=seed, rank=len(same_sub) + len(same_main) + len(general))
            if selection.sub_id == seed.sub_id:
                same_sub.append(suggestion)
            elif selection.main_id == seed.main_id:
                same_main.append(suggestion)
            else:
                general.append(suggestion)

        ordered: list[CaseSuggestion] = []
        if include_same_sub:
            ordered.extend(same_sub)
        if include_same_main:
            ordered.extend(same_main)
        if include_general:
            ordered.extend(general)
        return ordered

    def _build_repo_suggestion(
        self,
        selection: ClassificationSelection,
        *,
        seed: CaseSuggestion,
        rank: int,
    ) -> CaseSuggestion:
        if selection.sub_id == seed.sub_id:
            confidence = max(0.55, min(seed.confidence - 0.08 - (rank * 0.03), 0.88))
            rationale = "اقتراح قريب من نفس التصنيف الفرعي وقد ينسجم مع الوقائع بحسب التفاصيل الإضافية."
        elif selection.main_id == seed.main_id:
            confidence = max(0.42, min(seed.confidence - 0.16 - (rank * 0.03), 0.78))
            rationale = "اقتراح بديل من نفس التصنيف الرئيسي ويحتاج تأكيدًا بحسب وصف النزاع التفصيلي."
        else:
            confidence = max(0.3, min(seed.confidence - 0.24 - (rank * 0.03), 0.68))
            rationale = "اقتراح إضافي قريب دلاليًا من كلمات الواقعة ويحتاج تأكيد المستخدم."

        return CaseSuggestion(
            case_id=selection.case_id,
            case_title=selection.case_title,
            main_id=selection.main_id,
            main_title=selection.main_title,
            sub_id=selection.sub_id,
            sub_title=selection.sub_title,
            confidence=confidence,
            rationale=rationale,
            path=selection.case_path,
        )

    @staticmethod
    def _merge_suggestions(
        existing: list[CaseSuggestion],
        additional: list[CaseSuggestion],
    ) -> list[CaseSuggestion]:
        merged = list(existing)
        seen = {item.case_id for item in existing}
        for item in additional:
            if item.case_id in seen:
                continue
            merged.append(item)
            seen.add(item.case_id)
        return merged

    @staticmethod
    def _truncate_for_logs(value: str, limit: int = 240) -> str:
        text = value.strip()
        return text if len(text) <= limit else f"{text[:limit]}..."

    def _should_request_clarification(
        self,
        message: str,
        suggestions: list[CaseSuggestion],
    ) -> bool:
        meaningful_tokens = self.repo._tokenize(message)
        if len(meaningful_tokens) < 2:
            return True
        if not suggestions:
            return True

        top = suggestions[0]
        second = suggestions[1] if len(suggestions) > 1 else None
        top_gap = top.confidence - second.confidence if second else top.confidence
        distinct_mains = {item.main_id for item in suggestions[:2]}
        distinct_subs = {item.sub_id for item in suggestions}

        if top.confidence < 0.72:
            return True
        if second and top.confidence < 0.82 and top_gap <= 0.08:
            return True
        if len(distinct_mains) > 1 and top.confidence < 0.86:
            return True
        if len(distinct_subs) > 1 and top.confidence < 0.78 and top_gap <= 0.12:
            return True
        return False

    @staticmethod
    def _build_ambiguity_warning() -> InlineNotice:
        return InlineNotice(
            tone="warning",
            icon="⚠️",
            title="البيانات الحالية غير كافية لتحديد نوع الدعوى",
            message=(
                "لم نتمكن من تحديد نوع ورقة الدعوى بناءً على المعلومات المدخلة. "
                "يرجى تقديم مزيد من التفاصيل حول طبيعة القضية، الأطراف المعنية، أو موضوع النزاع."
            ),
            aria_label="تنبيه: تعذر تصنيف نوع الدعوى لعدم كفاية التفاصيل.",
        )

    async def _resolve_structured_suggestion(
        self,
        item: _StructuredSuggestion,
    ) -> ClassificationSelection | None:
        direct = await self.repo.resolve_selection(item.case_id)
        if direct is not None:
            return direct

        normalized_id = self.repo.normalize_case_id(item.case_id)
        if normalized_id != item.case_id:
            normalized = await self.repo.resolve_selection(normalized_id)
            if normalized is not None:
                return normalized

        if item.case_title:
            by_title = await self.repo.resolve_selection_by_titles(
                case_title=item.case_title,
                sub_title=item.sub_title,
                main_title=item.main_title,
            )
            if by_title is not None:
                return by_title

        return None

    async def _pick_selection(
        self, message: str, suggestions: Iterable[CaseSuggestion]
    ) -> ClassificationSelection | None:
        text = message.strip()
        case_match = re.search(r"(case-\d{2}-\d{2}-\d{3})", text)
        if case_match:
            return await self.repo.resolve_selection(case_match.group(1))

        normalized = text.replace("الأول", "1").replace("الثاني", "2").replace("الثالث", "3")
        if normalized in {"نعم", "موافق"}:
            normalized = "1"
        for index, suggestion in enumerate(suggestions, start=1):
            if normalized == str(index):
                return await self.repo.resolve_selection(suggestion.case_id)
        return None
