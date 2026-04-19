from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.exceptions import NajizError
from app.models.api import (
    AdminDeletePetitionResponse,
    AdminPetitionDetailResponse,
    AdminPetitionListResponse,
    AdminPetitionStats,
    AdminPetitionSummary,
)
from app.models.petition import PetitionDraft
from app.models.session import Session, SessionStatus
from app.routers.deps import build_dependencies
from app.utils.markdown import strip_markdown_text


router = APIRouter(tags=["admin"])
PETITION_NOT_FOUND_MESSAGE = (
    "\u0644\u0627 \u062a\u0648\u062c\u062f \u0635\u062d\u064a\u0641\u0629 "
    "\u0645\u062d\u0641\u0648\u0638\u0629 \u0628\u0647\u0630\u0627 \u0627\u0644\u0645\u0639\u0631\u0651\u0641."
)


def _build_preview(text: str, max_length: int = 180) -> str:
    normalized = strip_markdown_text(text)
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def _match_query(query: str, petition: PetitionDraft, session: Session | None) -> bool:
    parts = [
        petition.petition_id,
        petition.session_id,
        str(petition.version),
        petition.model,
        petition.full_text,
    ]

    if session is not None:
        parts.extend(
            [
                session.status,
                str(session.phase),
                " ".join(session.extracted_field_names),
            ]
        )
        if session.classification is not None:
            parts.extend(
                [
                    session.classification.main_title,
                    session.classification.sub_title,
                    session.classification.case_title,
                    " ".join(session.classification.case_path),
                ]
            )
        parts.extend(
            str(value)
            for value in session.extracted_data.values()
            if isinstance(value, (str, int, float))
        )

    return query in " ".join(part for part in parts if part).casefold()


@router.get("/petitions", response_model=AdminPetitionListResponse)
async def list_admin_petitions(
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=500),
    q: str | None = Query(default=None),
    status: SessionStatus | None = Query(default=None),
) -> AdminPetitionListResponse:
    deps = build_dependencies(request)
    petitions = await deps["petition_repo"].list_all()
    session_ids = sorted({petition.session_id for petition in petitions})
    sessions = await deps["session_repo"].get_many_by_ids(session_ids)
    session_map = {session.session_id: session for session in sessions}
    normalized_query = (q or "").strip().casefold()

    items: list[AdminPetitionSummary] = []

    for petition in petitions:
        session = session_map.get(petition.session_id)
        if status is not None and (session is None or session.status != status):
            continue
        if normalized_query and not _match_query(normalized_query, petition, session):
            continue

        review_score = petition.review_report.completeness_score if petition.review_report else None
        issue_count = len(petition.review_report.issues) if petition.review_report else 0
        summary = AdminPetitionSummary(
            petition_id=petition.petition_id,
            session_id=petition.session_id,
            version=petition.version,
            model=petition.model,
            created_at=petition.created_at,
            updated_at=petition.updated_at,
            session_updated_at=session.updated_at if session is not None else None,
            session_status=session.status if session is not None else None,
            phase=session.phase if session is not None else None,
            case_title=session.classification.case_title if session and session.classification else None,
            case_path=session.classification.case_path if session and session.classification else [],
            review_score=review_score,
            issue_count=issue_count,
            extracted_field_count=len(session.extracted_field_names) if session is not None else 0,
            message_count=session.message_count if session is not None else 0,
            preview=_build_preview(petition.full_text),
        )
        items.append(summary)

    visible_session_ids = {item.session_id for item in items}
    completed_session_ids = {
        item.session_id for item in items if item.session_status == SessionStatus.COMPLETE
    }
    review_scores = [item.review_score for item in items if item.review_score is not None]
    average_review_score = round(sum(review_scores) / len(review_scores)) if review_scores else None
    total_items = len(items)

    if limit is not None:
        items = items[:limit]

    return AdminPetitionListResponse(
        items=items,
        total=total_items,
        stats=AdminPetitionStats(
            total_petitions=total_items,
            total_sessions=len(visible_session_ids),
            completed_sessions=len(completed_session_ids),
            average_review_score=average_review_score,
        ),
    )


@router.get("/petitions/{petition_id}", response_model=AdminPetitionDetailResponse)
async def get_admin_petition_detail(petition_id: str, request: Request) -> AdminPetitionDetailResponse:
    deps = build_dependencies(request)
    petition = await deps["petition_repo"].get_by_id(petition_id)
    if petition is None:
        raise NajizError(
            code="petition_not_found",
            message=PETITION_NOT_FOUND_MESSAGE,
            status_code=404,
            recoverable=False,
        )

    session = await deps["session_repo"].get_by_id(petition.session_id)
    return AdminPetitionDetailResponse(petition=petition, session=session)


@router.delete("/petitions/{petition_id}", response_model=AdminDeletePetitionResponse)
async def delete_admin_petition(petition_id: str, request: Request) -> AdminDeletePetitionResponse:
    deps = build_dependencies(request)
    petition = await deps["petition_repo"].delete_by_id(petition_id)
    if petition is None:
        raise NajizError(
            code="petition_not_found",
            message=PETITION_NOT_FOUND_MESSAGE,
            status_code=404,
            recoverable=False,
        )

    remaining_petitions = await deps["petition_repo"].count_by_session(petition.session_id)
    deleted_session = False
    deleted_message_count = 0

    if remaining_petitions == 0:
        deleted_session = await deps["session_repo"].delete_by_id(petition.session_id)
        deleted_message_count = await deps["message_repo"].delete_by_session(petition.session_id)

    return AdminDeletePetitionResponse(
        petition_id=petition.petition_id,
        session_id=petition.session_id,
        remaining_petitions_in_session=remaining_petitions,
        deleted_session=deleted_session,
        deleted_message_count=deleted_message_count,
    )
