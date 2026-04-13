from fastapi import APIRouter, Request

from app.models.api import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def healthcheck(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    storage = "mongo" if request.app.state.mongo_manager.database is not None else "memory"
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        llm_enabled=settings.llm_is_enabled,
        llm_provider=settings.llm_provider,
        storage=storage,
    )
