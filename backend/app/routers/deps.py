from __future__ import annotations

from typing import cast

from fastapi import Request

from app.core.config import SUPPORTED_LLM_PROVIDERS, LLMProviderName
from app.core.security import EncryptionService
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.petition_repository import PetitionRepository
from app.repositories.session_repository import SessionRepository
from app.services.agent.agent_orchestrator import AgentOrchestrator
from app.services.agent.guard_checker import GuardChecker
from app.services.agent.phase1_classifier import Phase1ClassifierService
from app.services.agent.phase1_interviewer import Phase1InterviewerService
from app.services.agent.phase2_drafter import Phase2DrafterService
from app.services.agent.phase2_evidence import Phase2EvidenceService
from app.services.agent.phase3_reviewer import Phase3ReviewerService
from app.services.llm.factory import build_llm_client


LLM_PROVIDER_HEADER = "X-LLM-Provider"
LLM_MODEL_HEADER = "X-LLM-Model"


def _resolve_llm_settings(request: Request):
    settings = request.app.state.settings
    provider_value = (
        request.headers.get(LLM_PROVIDER_HEADER)
        or request.query_params.get("llm_provider")
        or settings.llm_provider
    )
    requested_provider = provider_value.strip().lower()
    if requested_provider not in SUPPORTED_LLM_PROVIDERS:
        return settings

    provider = cast(LLMProviderName, requested_provider)
    if not settings.is_provider_available(provider):
        return settings

    requested_model = (
        request.headers.get(LLM_MODEL_HEADER)
        or request.query_params.get("llm_model")
        or settings.default_model_for_provider(provider)
    ).strip()

    if not requested_model:
        return settings

    return settings.with_llm_selection(provider, requested_model)


def build_dependencies(request: Request):
    settings = _resolve_llm_settings(request)
    manager = request.app.state.mongo_manager
    catalog = request.app.state.catalog
    legal_store = request.app.state.legal_store

    encryption = EncryptionService(settings.app_encryption_key)
    llm = build_llm_client(settings)
    classification_repo = ClassificationRepository(catalog)
    session_repo = SessionRepository(manager, encryption)
    message_repo = MessageRepository(manager)
    petition_repo = PetitionRepository(manager, encryption)
    evidence_service = Phase2EvidenceService(
        legal_store,
        llm,
        draft_temperature=settings.draft_temperature,
    )
    classifier = Phase1ClassifierService(
        classification_repo,
        llm,
        classify_temperature=settings.classify_temperature,
    )
    interviewer = Phase1InterviewerService(classification_repo)
    drafter = Phase2DrafterService(
        petition_repo,
        classification_repo,
        evidence_service,
        llm,
        draft_temperature=settings.draft_temperature,
        draft_model_name=settings.model_for("drafter"),
    )
    reviewer = Phase3ReviewerService(petition_repo, classification_repo)
    guard = GuardChecker(classification_repo, settings.session_turn_limit, settings.dispute_value_threshold)
    orchestrator = AgentOrchestrator(
        settings=settings,
        session_repo=session_repo,
        message_repo=message_repo,
        classifier=classifier,
        interviewer=interviewer,
        drafter=drafter,
        reviewer=reviewer,
        guard_checker=guard,
        flat_index=catalog.flat_index,
    )
    return {
        "settings": settings,
        "classification_repo": classification_repo,
        "session_repo": session_repo,
        "message_repo": message_repo,
        "petition_repo": petition_repo,
        "classifier": classifier,
        "interviewer": interviewer,
        "drafter": drafter,
        "reviewer": reviewer,
        "orchestrator": orchestrator,
    }
