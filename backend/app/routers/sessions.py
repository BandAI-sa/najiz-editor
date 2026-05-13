from fastapi import APIRouter, Request

from app.core.exceptions import NajizError, SessionNotFoundError
from app.models.api import (
    AgentResponse,
    CreateSessionResponse,
    InterviewFormSubmissionRequest,
    SessionResponse,
    UpdateClassificationRequest,
    UpdateIntakeModeRequest,
)
from app.models.session import IntakeMode, Session, SessionStatus
from app.routers.deps import build_dependencies


router = APIRouter(tags=["sessions"])


@router.post("/", response_model=CreateSessionResponse)
async def create_session(request: Request) -> CreateSessionResponse:
    deps = build_dependencies(request)
    session = Session()
    await deps["session_repo"].create(session)
    return CreateSessionResponse(session=session)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    return SessionResponse(session=session)


@router.patch("/{session_id}/classification", response_model=SessionResponse)
async def update_classification(
    session_id: str,
    payload: UpdateClassificationRequest,
    request: Request,
) -> SessionResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    selection = await deps["classification_repo"].resolve_selection(payload.case_id)
    if selection is None or selection.main_id != payload.main_id or selection.sub_id != payload.sub_id:
        raise NajizError(
            code="invalid_classification",
            message="التصنيف المحدد غير صالح.",
            status_code=422,
            recoverable=True,
        )

    session.classification = selection
    session.status = SessionStatus.INTERVIEW
    interview_result = await deps["interviewer"].start(session)
    session.metadata["pending_prompt"] = interview_result.reply
    await deps["session_repo"].save(session)
    return SessionResponse(session=session)


@router.patch(
    "/{session_id}/interview-form",
    response_model=AgentResponse,
)
async def submit_interview_form(
    session_id: str,
    payload: InterviewFormSubmissionRequest,
    request: Request,
) -> AgentResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    result = await deps["interviewer"].submit_form(
        session, payload.values,
    )
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
        metadata=result.metadata,
        suggestions=result.suggestions,
        classification=session.classification,
        interview_form=(
            result.interview_form or session.interview_form
        ),
        inline_notice=(
            result.inline_notice or session.inline_notice
        ),
        intake_mode=session.intake_mode,
        petition=result.petition,
        review_report=result.review,
    )


@router.patch(
    "/{session_id}/intake-mode",
    response_model=SessionResponse,
)
async def update_intake_mode(
    session_id: str,
    payload: UpdateIntakeModeRequest,
    request: Request,
) -> SessionResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    session.intake_mode = IntakeMode(payload.mode)

    if (
        session.intake_mode == IntakeMode.STRUCTURED
        and session.classification
    ):
        result = await deps["interviewer"].structured.start(
            session,
        )
        session.metadata["pending_prompt"] = result.reply

    await deps["session_repo"].save(session)
    return SessionResponse(session=session)

