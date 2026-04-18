from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

try:  # pragma: no cover - optional dependency path
    from sse_starlette.sse import EventSourceResponse
except ImportError:  # pragma: no cover - local fallback
    class EventSourceResponse(StreamingResponse):
        def __init__(self, content, *args, **kwargs):
            super().__init__(content, media_type="text/event-stream", *args, **kwargs)

from app.core.exceptions import SessionNotFoundError
from app.models.api import AgentMessageRequest, AgentResponse, DraftRequest, FixRequest, ReviewRequest
from app.routers.deps import build_dependencies


router = APIRouter(tags=["agent"])


@router.post("/message", response_model=AgentResponse)
async def message(payload: AgentMessageRequest, request: Request) -> AgentResponse:
    deps = build_dependencies(request)
    return await deps["orchestrator"].handle_message(payload)


@router.post("/classify", response_model=AgentResponse)
async def classify(payload: AgentMessageRequest, request: Request) -> AgentResponse:
    deps = build_dependencies(request)
    session = await deps["orchestrator"]._get_or_create_session(payload.session_id)
    result = await deps["classifier"].classify(session, payload.message, request.app.state.catalog.flat_index)
    await deps["session_repo"].save(session)
    return AgentResponse(
        session_id=session.session_id,
        reply=result.reply,
        phase=int(session.phase),
        session_status=session.status,
        completion_percentage=session.completion_percentage,
        extracted_data=session.extracted_data,
        flags=session.flags,
        next_action=result.next_action,
        suggestions=result.suggestions,
        classification=session.classification,
    )


@router.post("/draft", response_model=AgentResponse)
async def draft(payload: DraftRequest, request: Request) -> AgentResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(payload.session_id)
    if session is None:
        raise SessionNotFoundError(payload.session_id)
    result = await deps["drafter"].draft(session, petition_role=payload.petition_role)
    await deps["session_repo"].save(session)
    return AgentResponse(
        session_id=session.session_id,
        reply=result.reply,
        phase=int(session.phase),
        session_status=session.status,
        completion_percentage=session.completion_percentage,
        extracted_data=session.extracted_data,
        flags=session.flags,
        next_action=result.next_action,
        petition=result.petition,
        classification=session.classification,
    )


@router.get("/draft/stream")
async def draft_stream(session_id: str, request: Request):
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    async def event_generator():
        async for event in deps["drafter"].stream(session):
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: {event['type']}\ndata: {payload}\n\n"
        await deps["session_repo"].save(session)

    return EventSourceResponse(event_generator())


@router.post("/review", response_model=AgentResponse)
async def review(payload: ReviewRequest, request: Request) -> AgentResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(payload.session_id)
    if session is None:
        raise SessionNotFoundError(payload.session_id)
    result = await deps["reviewer"].review(session)
    await deps["session_repo"].save(session)
    return AgentResponse(
        session_id=session.session_id,
        reply=result.reply,
        phase=int(session.phase),
        session_status=session.status,
        completion_percentage=session.completion_percentage,
        extracted_data=session.extracted_data,
        flags=session.flags,
        next_action=result.next_action,
        petition=result.petition,
        review_report=result.review,
        classification=session.classification,
    )


@router.post("/fix", response_model=AgentResponse)
async def fix(payload: FixRequest, request: Request) -> AgentResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(payload.session_id)
    if session is None:
        raise SessionNotFoundError(payload.session_id)
    result = await deps["reviewer"].handle_fix_request(session, payload.instruction, payload.issue_id)
    await deps["session_repo"].save(session)
    return AgentResponse(
        session_id=session.session_id,
        reply=result.reply,
        phase=int(session.phase),
        session_status=session.status,
        completion_percentage=session.completion_percentage,
        extracted_data=session.extracted_data,
        flags=session.flags,
        next_action=result.next_action,
        petition=result.petition,
        review_report=result.review,
        classification=session.classification,
    )
