from __future__ import annotations

from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.models import AgentTurnResult


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
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            return AgentTurnResult(
                reply="البيانات الأساسية مكتملة. يمكنك الآن طلب صياغة الصحيفة.",
                next_action="go_to_phase2",
            )
        session.flags.missing_fields = [item.name for item in case.requirements.data_fields if item.required]
        session.completion_percentage = 0
        session.metadata["current_field"] = next_field
        return AgentTurnResult(
            reply=f"لنبدأ بجمع البيانات اللازمة. ما هي قيمة الحقل التالي: {next_field}؟",
            next_action="ask_field",
        )

    async def process_turn(self, session: Session, message: str) -> AgentTurnResult:
        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply="لا توجد متطلبات مرتبطة بالتصنيف الحالي.",
                next_action="await_manual_support",
            )

        current_field = session.metadata.get("current_field")
        if current_field:
            session.extracted_data[current_field] = self._extract_answer(message)
            session.extracted_field_names = sorted(session.extracted_data.keys())

        required_fields = [item.name for item in case.requirements.data_fields if item.required]
        completed_required = [name for name in required_fields if session.extracted_data.get(name)]
        missing_required = [name for name in required_fields if not session.extracted_data.get(name)]
        session.completion_percentage = round((len(completed_required) / max(len(required_fields), 1)) * 100)
        session.flags.missing_fields = missing_required

        if not missing_required:
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            session.metadata.pop("current_field", None)
            return AgentTurnResult(
                reply="اكتملت الحقول المطلوبة. أصبحت الجلسة جاهزة للصياغة.",
                next_action="go_to_phase2",
            )

        next_field = missing_required[0]
        session.metadata["current_field"] = next_field
        return AgentTurnResult(
            reply=f"شكرًا. الحقل التالي المطلوب هو: {next_field}. يرجى تزويدي به.",
            next_action="ask_field",
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
