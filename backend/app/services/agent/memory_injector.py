from __future__ import annotations

import logging
from typing import Any

from app.models.session import Session
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger("uvicorn.error")

LLMMessage = dict[str, str]


class ConversationMemoryInjector:
    """Retrieves recent chat history from the *existing* MessageRepository
    and injects it into LLM prompt context.

    No new database, no new collection — uses messages already stored by
    AgentOrchestrator.handle_message().
    """

    def __init__(self, message_repo: MessageRepository, window_size: int = 8):
        self.repo = message_repo
        self.window_size = window_size

    async def enrich_prompt(
        self,
        session_id: str,
        base_input: list[LLMMessage],
    ) -> list[LLMMessage]:
        if not session_id or self.window_size <= 0:
            return base_input

        try:
            recent = await self.repo.list_recent(session_id, limit=self.window_size)
        except Exception:
            logger.warning(
                "ConversationMemoryInjector: failed to load history for session=%s, "
                "falling back to base prompt.",
                session_id,
            )
            return base_input

        if not recent:
            return base_input

        history: list[LLMMessage] = []
        for msg in recent:
            role = "assistant" if msg.role == "assistant" else "user"
            content = msg.content.strip()
            if content:
                history.append({"role": role, "content": content})

        if not history:
            return base_input

        logger.info(
            "ConversationMemoryInjector: injecting %d history messages for session=%s",
            len(history),
            session_id,
        )
        return history + base_input

    def build_session_summary(self, session: Session) -> str | None:
        if not session.extracted_data:
            return None

        lines = ["البيانات المجمعة حتى الآن:"]
        for field_name, value in session.extracted_data.items():
            display_value = str(value).strip()
            if display_value:
                lines.append(f"- {field_name}: {display_value}")

        if len(lines) <= 1:
            return None

        return "\n".join(lines)

    async def build_interview_context(
        self,
        session: Session,
        current_field: str | None,
        missing_fields: list[str],
    ) -> list[LLMMessage]:
        context_parts: list[str] = []

        summary = self.build_session_summary(session)
        if summary:
            context_parts.append(summary)

        if current_field:
            context_parts.append(f"الحقل المطلوب حاليًا: {current_field}")

        if missing_fields:
            remaining = "، ".join(missing_fields[:5])
            context_parts.append(f"الحقول المتبقية: {remaining}")

        if not context_parts:
            return []

        return [{"role": "system", "content": "\n\n".join(context_parts)}]
