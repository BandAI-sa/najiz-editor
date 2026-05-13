from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import SessionNotFoundError
from app.models.api import AgentMessageRequest, AgentResponse
from app.models.session import Phase, Session, SessionStatus
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository
from app.services.agent.guard_checker import GuardChecker
from app.services.agent.models import AgentTurnResult
from app.services.agent.phase1_classifier import Phase1ClassifierService
from app.services.agent.phase1_interviewer import Phase1InterviewerService
from app.services.agent.phase2_drafter import Phase2DrafterService
from app.services.agent.phase3_reviewer import Phase3ReviewerService


class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        classifier: Phase1ClassifierService,
        interviewer: Phase1InterviewerService,
        drafter: Phase2DrafterService,
        reviewer: Phase3ReviewerService,
        guard_checker: GuardChecker,
        flat_index: str,
    ):
        self.settings = settings
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.classifier = classifier
        self.interviewer = interviewer
        self.drafter = drafter
        self.reviewer = reviewer
        self.guard_checker = guard_checker
        self.flat_index = flat_index

    async def handle_message(self, request: AgentMessageRequest) -> AgentResponse:
        session = await self._get_or_create_session(request.session_id)
        await self.message_repo.save(session.session_id, request.message, "user", int(session.phase))
        session.message_count += 1

        result = await self._dispatch(session, request.message)
        await self._apply_guard_checks(session, result)

        await self.session_repo.save(session)
        await self.message_repo.save(
            session.session_id,
            result.reply,
            "assistant",
            int(session.phase),
            metadata={"next_action": result.next_action},
        )

        return AgentResponse(
            session_id=session.session_id,
            reply=result.reply,
            phase=int(session.phase),
            session_status=session.status,
            completion_percentage=session.completion_percentage,
            extracted_data=session.extracted_data,
            flags=session.flags,
            next_action=result.next_action,
            metadata=result.metadata,
            suggestions=result.suggestions,
            classification=session.classification,
            interview_form=result.interview_form or session.interview_form,
            inline_notice=result.inline_notice or session.inline_notice,
            intake_mode=session.intake_mode,
            petition=result.petition,
            review_report=result.review,
        )

    async def _dispatch(self, session: Session, message: str) -> AgentTurnResult:
        if session.status == SessionStatus.NEW:
            return await self.classifier.classify(session, message, self.flat_index)

        if session.status == SessionStatus.AWAITING_CLASSIFICATION_CONFIRM:
            result = await self.classifier.handle_confirmation(
                session, message,
            )
            if result.next_action == "start_interview":
                session.status = SessionStatus.INTERVIEW
                result.next_action = "select_intake_mode"
                result.classification = session.classification
            return result

        if session.status == SessionStatus.INTERVIEW:
            return await self.interviewer.process_turn(session, message)

        if session.status == SessionStatus.READY_TO_DRAFT:
            return await self.drafter.draft(session)

        if session.status in {SessionStatus.DRAFTING, SessionStatus.DRAFT_READY}:
            if "راجع" in message or "مراجعة" in message:
                return await self.reviewer.review(session)
            return await self.drafter.handle_edit_request(session, message)

        if session.status == SessionStatus.REVIEW:
            return await self.reviewer.handle_fix_request(session, message)

        return AgentTurnResult(
            reply="تم إنهاء الجلسة الحالية. يمكنك تصدير الصحيفة أو بدء جلسة جديدة.",
            next_action="complete",
        )

    async def _get_or_create_session(self, session_id: str | None) -> Session:
        if session_id:
            session = await self.session_repo.get_by_id(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            return session
        session = Session()
        await self.session_repo.create(session)
        return session

    async def _apply_guard_checks(self, session: Session, result: AgentTurnResult) -> None:
        if session.phase not in {Phase.ONE, Phase.TWO}:
            return
        issues = await self.guard_checker.check(session)
        if not issues:
            return
        session.flags.guard_issues = issues
        session.flags.critical_issues = [issue.title for issue in issues if issue.severity == "حرج"]
        session.flags.needs_human_review = any(issue.severity == "حرج" for issue in issues)
        result.guard_issues = issues
