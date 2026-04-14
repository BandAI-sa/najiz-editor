from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import MongoManager
from app.core.exceptions import NajizError
from app.routers import agent, classifications, config, health, petitions, sessions
from app.services.data.loader import CatalogLoader
from app.services.legal.store import LegalReferenceStore


logger = logging.getLogger("uvicorn.error")


def create_app() -> FastAPI:
    settings = get_settings()
    mongo_manager = MongoManager(settings)
    loader = CatalogLoader(settings)
    legal_store = LegalReferenceStore(settings.legal_references_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        catalog = loader.load()
        app.state.settings = settings
        app.state.catalog = catalog
        app.state.legal_store = legal_store
        app.state.mongo_manager = mongo_manager
        app.state.memory_store = mongo_manager.memory_store

        logger.info(
            "LLM configuration loaded: provider=%s enabled=%s api_key_present=%s default_model=%s classifier_model=%s",
            settings.llm_provider,
            settings.llm_is_enabled,
            bool(settings.llm_provider_api_key),
            settings.model_for("drafter"),
            settings.model_for("classifier"),
        )

        await mongo_manager.connect()
        await mongo_manager.ensure_indexes()
        if settings.auto_seed_on_startup:
            await mongo_manager.seed_catalog(catalog)

        yield

        await mongo_manager.disconnect()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        default_response_class=JSONResponse,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-LLM-Provider", "X-LLM-Model"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.exception_handler(NajizError)
    async def handle_najiz_error(_, exc: NajizError):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(mode="json"),
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(config.router, prefix="/api/config")
    app.include_router(classifications.router, prefix="/api/classifications")
    app.include_router(sessions.router, prefix="/api/sessions")
    app.include_router(agent.router, prefix="/api/agent")
    app.include_router(petitions.router, prefix="/api/petitions")
    return app
