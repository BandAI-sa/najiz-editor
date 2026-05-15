from __future__ import annotations

from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.models import AgentTurnResult


SUPPLEMENTARY_OPTIONAL_FIELDS: tuple[str, ...] = (
    "بيانات الوكيل",
    "رقم الوكالة",
    "العنوان الوطني",
    "رقم الهوية",
    "البريد الإلكتروني",
    "الجوال",
    "تقدير المطالبة",
    "بيانات إضافية للأطراف",
)


class Phase1InterviewerService:
    def __init__(self, repo: ClassificationRepository):
        self.repo = repo

    async def start(self, session: Session) -> AgentTurnResult:
        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply="تعذر تحميل متطلبات هذا النوع من الدعاوى.",
                next_action="await_manual_support",
            )
        next_field = self._next_required_field(case.requirements.data_fields, session.extracted_data)
        if next_field is None:
            return self._offer_optional_enrichment(session)
        session.flags.missing_fields = [item.name for item in case.requirements.data_fields if item.required]
        session.completion_percentage = 0
        session.metadata["current_field"] = next_field
        return AgentTurnResult(
            reply=f"لنبدأ بالبيانات الأساسية. ما قيمة الحقل التالي: {next_field}؟",
            next_action="ask_field",
        )

    async def process_turn(self, session: Session, message: str) -> AgentTurnResult:
        if session.metadata.get("supplementary_state") == "awaiting_decision":
            decision = self._parse_enrichment_decision(message)
            if decision:
                return await self.handle_enrichment_decision(
                    session, decision,
                )
            return AgentTurnResult(
                reply=(
                    "إذا رغبت، يمكنني إضافة بيانات اختيارية "
                    "مثل بيانات الوكيل أو وسائل التواصل قبل "
                    "التجهيز النهائي. اختر: إضافة أو تخطي."
                ),
                next_action="offer_optional_enrichment",
            )

        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply="لا توجد متطلبات مرتبطة بالتصنيف الحالي.",
                next_action="await_manual_support",
            )

        current_field = session.metadata.get("current_field")
        supplementary_mode = session.metadata.get("supplementary_state") == "collecting"
        if supplementary_mode and self._is_finish_supplementary(message):
            session.metadata["supplementary_state"] = "completed"
            return self._finalize_ready_to_draft(
                session,
                "تم الاكتفاء بالبيانات الإضافية الحالية. "
                "ننتقل الآن إلى اختيار صيغة الصحيفة ثم بدء الصياغة.",
            )
        if supplementary_mode and self._is_skip_message(message):
            if current_field:
                session.extracted_data[current_field] = ""
                session.extracted_field_names = sorted(
                    session.extracted_data.keys(),
                )
            next_supplementary = self._next_supplementary_field(
                session,
            )
            if next_supplementary:
                session.metadata["current_field"] = (
                    next_supplementary
                )
                return AgentTurnResult(
                    reply=(
                        f"ممتاز. معلومة اختيارية إضافية: "
                        f"{next_supplementary}.\n"
                        "يمكنك الإجابة أو كتابة «تخطي»، "
                        "ويمكنك كتابة «اكتفي» للانتقال مباشرة."
                    ),
                    next_action="ask_field",
                )
            session.metadata["supplementary_state"] = "completed"
            return self._finalize_ready_to_draft(
                session,
                "شكرًا لك. تم استكمال البيانات الأساسية "
                "وما توفر من البيانات الاختيارية.",
            )
        if current_field:
            session.extracted_data[current_field] = self._extract_answer(
                message,
            )
            session.extracted_field_names = sorted(session.extracted_data.keys())

        required_fields = [item.name for item in case.requirements.data_fields if item.required]
        completed_required = [name for name in required_fields if session.extracted_data.get(name)]
        missing_required = [name for name in required_fields if not session.extracted_data.get(name)]
        session.completion_percentage = round((len(completed_required) / max(len(required_fields), 1)) * 100)
        session.flags.missing_fields = missing_required

        if not missing_required:
            if supplementary_mode:
                next_supplementary = self._next_supplementary_field(session)
                if next_supplementary:
                    session.metadata["current_field"] = next_supplementary
                    return AgentTurnResult(
                        reply=(
                            f"ممتاز. معلومة اختيارية إضافية: "
                            f"{next_supplementary}.\n"
                            "يمكنك الإجابة أو كتابة «تخطي»."
                        ),
                        next_action="ask_field",
                    )
                session.metadata["supplementary_state"] = "completed"
                return self._finalize_ready_to_draft(
                    session,
                    "شكرًا لك. تم استكمال البيانات الأساسية "
                    "وما توفر من البيانات الاختيارية.",
                )
            if (
                session.metadata.get("enrichment_started")
                and session.metadata.get("supplementary_state")
                not in {"completed", "skipped"}
            ):
                session.metadata["supplementary_state"] = "completed"
            if session.metadata.get("supplementary_state") in {"completed", "skipped"}:
                return self._finalize_ready_to_draft(
                    session,
                    "اكتملت البيانات المطلوبة. أصبحت الجلسة جاهزة للصياغة.",
                )
            return self._offer_optional_enrichment(session)

        next_field = missing_required[0]
        session.metadata["current_field"] = next_field
        return AgentTurnResult(
            reply=f"شكرًا لك. الحقل الأساسي التالي: {next_field}.",
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
                "تم التخطي. ننتقل الآن إلى اختيار صيغة "
                "الصحيفة ثم بدء الصياغة.",
            )

        session.metadata["supplementary_state"] = "collecting"
        session.metadata["enrichment_started"] = True
        next_field = self._next_supplementary_field(session)
        if not next_field:
            session.metadata["supplementary_state"] = "completed"
            return self._finalize_ready_to_draft(
                session,
                "لا توجد بيانات إضافية غير مكتملة. "
                "يمكنك متابعة الصياغة.",
            )
        session.metadata["current_field"] = next_field
        return AgentTurnResult(
            reply=(
                "ممتاز. نبدأ بخطوة الإثراء الاختيارية.\n"
                f"المعلومة الأولى: {next_field}.\n"
                "يمكنك الإجابة أو كتابة «تخطي»."
            ),
            next_action="ask_field",
            metadata=self._intake_field_groups_metadata(),
        )

    @staticmethod
    def _next_required_field(fields, extracted_data: dict) -> str | None:
        for item in fields:
            if item.required and not extracted_data.get(item.name):
                return item.name
        return None

    @staticmethod
    def _extract_answer(message: str) -> str:
        if ":" in message:
            _, value = message.split(":", 1)
            if value.strip():
                return value.strip()
        return message.strip()

    @staticmethod
    def _parse_enrichment_decision(message: str) -> str | None:
        lowered = message.strip().rstrip(".!؟?،,").lower()
        add_tokens = {
            "إضافة", "اضافة", "أضف", "اضف", "نعم", "yes", "add",
            "ايوه", "ايوا", "اكمل", "كمل",
        }
        skip_tokens = {
            "تخطي", "تخطى", "تجاوز", "عدي", "التالي", "skip", "no", "لا",
        }
        if (
            lowered in add_tokens
            or "إضافة بيانات إضافية" in lowered
            or "اضافة بيانات اضافية" in lowered
            or "ايوه اضف" in lowered
            or "نعم اضف" in lowered
        ):
            return "add"
        if lowered in skip_tokens:
            return "skip"
        return None

    @staticmethod
    def _is_skip_message(message: str) -> bool:
        lowered = message.strip().rstrip(".!؟?،,").lower()
        if lowered in {"تخطي", "تخطى", "تجاوز", "عدي", "التالي", "skip", "next"}:
            return True
        return any(
            word in {"تخطي", "تخطى", "تجاوز", "عدي", "التالي", "skip", "next"}
            for word in lowered.split()
        )

    @staticmethod
    def _is_finish_supplementary(message: str) -> bool:
        lowered = message.strip().rstrip(".!؟?،,").lower()
        if lowered in {"اكتفي", "يكفي", "خلاص", "كفاية", "كفايه", "stop", "وقف"}:
            return True
        return any(
            word in {"اكتفي", "يكفي", "خلاص", "كفاية", "كفايه", "stop", "وقف"}
            for word in lowered.split()
        )

    def _next_supplementary_field(self, session: Session) -> str | None:
        for field_name in SUPPLEMENTARY_OPTIONAL_FIELDS:
            if not str(session.extracted_data.get(field_name, "")).strip():
                return field_name
        return None

    def _offer_optional_enrichment(
        self, session: Session,
    ) -> AgentTurnResult:
        session.status = SessionStatus.INTERVIEW
        session.phase = Phase.ONE
        session.completion_percentage = 100
        session.metadata["supplementary_state"] = "awaiting_decision"
        session.metadata.pop("current_field", None)
        return AgentTurnResult(
            reply=(
                "اكتملت البيانات الأساسية.\n"
                "إذا رغبت، يمكن إضافة بيانات اختيارية "
                "مثل بيانات الوكيل أو وسائل التواصل قبل "
                "التجهيز النهائي.\n"
                "اختر: إضافة أو تخطي."
            ),
            next_action="offer_optional_enrichment",
            metadata=self._intake_field_groups_metadata(),
        )

    @staticmethod
    def _finalize_ready_to_draft(
        session: Session, reply: str,
    ) -> AgentTurnResult:
        session.status = SessionStatus.READY_TO_DRAFT
        session.phase = Phase.TWO
        session.completion_percentage = 100
        session.metadata.pop("current_field", None)
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
            "supplementary_optional": list(SUPPLEMENTARY_OPTIONAL_FIELDS),
            "generated_later": list(SUPPLEMENTARY_OPTIONAL_FIELDS),
        }
