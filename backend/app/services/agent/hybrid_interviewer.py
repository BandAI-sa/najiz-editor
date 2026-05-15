"""Hybrid interviewer that dispatches to structured or conversational
mode based on ``session.intake_mode``.

The AgentOrchestrator receives this as its ``interviewer`` dependency
and calls ``start()`` / ``process_turn()`` without knowing which
implementation is active.
"""

from __future__ import annotations

from app.models.session import IntakeMode, Session
from app.services.agent.models import AgentTurnResult


class HybridInterviewerService:
    """Routes interview calls to the correct backend based on
    ``session.intake_mode``.

    Attributes:
        structured: StructuredInterviewerService instance.
        smart: SmartInterviewerService (or base
               Phase1InterviewerService) instance.
    """

    def __init__(self, structured, smart):
        self.structured = structured
        self.smart = smart

    async def start(
        self, session: Session,
    ) -> AgentTurnResult:
        if session.intake_mode == IntakeMode.STRUCTURED:
            return await self.structured.start(session)
        return await self.smart.start(session)

    async def process_turn(
        self, session: Session, message: str,
    ) -> AgentTurnResult:
        if session.intake_mode == IntakeMode.STRUCTURED:
            return await self.structured.process_turn(
                session, message,
            )
        return await self.smart.process_turn(
            session, message,
        )

    async def submit_form(
        self, session: Session, values: dict[str, str],
    ) -> AgentTurnResult:
        """Form submissions always go to the structured
        interviewer regardless of mode."""
        return await self.structured.submit_form(
            session, values,
        )

    async def handle_enrichment_decision(
        self, session: Session, action: str,
    ) -> AgentTurnResult:
        if session.intake_mode == IntakeMode.STRUCTURED:
            return await self.structured.handle_enrichment_decision(
                session, action,
            )
        return await self.smart.handle_enrichment_decision(
            session, action,
        )
