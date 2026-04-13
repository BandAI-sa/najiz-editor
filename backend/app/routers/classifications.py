from fastapi import APIRouter, Request

from app.routers.deps import build_dependencies


router = APIRouter(tags=["classifications"])


@router.get("/")
async def get_mains(request: Request):
    deps = build_dependencies(request)
    return await deps["classification_repo"].get_main_categories()


@router.get("/{main_id}/subs")
async def get_subs(main_id: str, request: Request):
    deps = build_dependencies(request)
    return await deps["classification_repo"].get_subs(main_id)


@router.get("/{main_id}/{sub_id}/cases")
async def get_cases(main_id: str, sub_id: str, request: Request):
    deps = build_dependencies(request)
    return await deps["classification_repo"].get_cases(main_id, sub_id)


@router.get("/case/{case_id}")
async def get_case(case_id: str, request: Request):
    deps = build_dependencies(request)
    return await deps["classification_repo"].get_case(case_id)
