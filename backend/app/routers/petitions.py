from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import NajizError, SessionNotFoundError
from app.models.api import PetitionResponse, PetitionSectionUpdateRequest
from app.models.petition import PetitionSectionName
from app.models.session import Phase, SessionStatus
from app.routers.deps import build_dependencies
from app.utils.export import build_printable_html, build_markdown, build_pdf
from fastapi.responses import HTMLResponse, PlainTextResponse, Response


router = APIRouter(tags=["petitions"])


@router.get("/{session_id}")
async def get_latest_petition(session_id: str, request: Request):
    deps = build_dependencies(request)
    petition = await deps["petition_repo"].get_latest_by_session(session_id)
    if petition is None:
        raise NajizError(
            code="petition_not_found",
            message="لا توجد صحيفة مرتبطة بهذه الجلسة.",
            status_code=404,
            recoverable=False,
        )
    return petition


@router.patch("/{session_id}/sections", response_model=PetitionResponse)
async def update_petition_section(
    session_id: str,
    payload: PetitionSectionUpdateRequest,
    request: Request,
) -> PetitionResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

    petition = await deps["petition_repo"].get_latest_by_session(session_id)
    if petition is None:
        raise NajizError(
            code="petition_not_found",
            message="لا توجد صحيفة حالية قابلة للتعديل.",
            status_code=404,
            recoverable=False,
        )

    target = payload.section
    if target == PetitionSectionName.FACTS:
        petition.facts.content = payload.content
    elif target == PetitionSectionName.EVIDENCE:
        petition.evidence.content = payload.content
    else:
        petition.requests.content = payload.content

    petition.version += 1
    petition.review_report = None
    petition.full_text = "\n\n".join(
        [
            f"{petition.facts.title}\n{'=' * len(petition.facts.title)}\n{petition.facts.content}",
            f"{petition.evidence.title}\n{'=' * len(petition.evidence.title)}\n{petition.evidence.content}",
            f"{petition.requests.title}\n{'=' * len(petition.requests.title)}\n{petition.requests.content}",
        ]
    )
    await deps["petition_repo"].save(petition)

    session.petition_version = petition.version
    session.phase = Phase.TWO
    session.status = SessionStatus.DRAFT_READY
    await deps["session_repo"].save(session)

    return PetitionResponse(petition=petition)


@router.get("/{session_id}/export", response_class=HTMLResponse)
async def export_petition(session_id: str, request: Request) -> HTMLResponse:
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    petition = await deps["petition_repo"].get_latest_by_session(session_id)
    if petition is None:
        raise NajizError(
            code="petition_not_found",
            message="لا توجد صحيفة جاهزة للتصدير.",
            status_code=404,
            recoverable=False,
        )
    html = build_printable_html(session, petition)
    return HTMLResponse(html)

@router.get("/{session_id}/export/md", response_class=PlainTextResponse)
async def export_petition_md(session_id: str, request: Request):
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    petition = await deps["petition_repo"].get_latest_by_session(session_id)
    if petition is None:
        raise NajizError(code="petition_not_found", message="لا توجد صحيفة جاهزة للتصدير.", status_code=404, recoverable=False)
    
    md_text = build_markdown(session, petition)
    return Response(
        content=md_text,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=petition_{session_id}.md"}
    )

@router.get("/{session_id}/export/pdf")
async def export_petition_pdf(session_id: str, request: Request):
    deps = build_dependencies(request)
    session = await deps["session_repo"].get_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    petition = await deps["petition_repo"].get_latest_by_session(session_id)
    if petition is None:
        raise NajizError(code="petition_not_found", message="لا توجد صحيفة جاهزة للتصدير.", status_code=404, recoverable=False)
    
    pdf_bytes = build_pdf(session, petition)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=petition_{session_id}.pdf"}
    )
