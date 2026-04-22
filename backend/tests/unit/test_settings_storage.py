from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_reject_volatile_memory_store_outside_test_without_opt_in():
    with pytest.raises(ValidationError, match="USE_MEMORY_STORE=true disables Mongo persistence"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="staging",
            use_memory_store=True,
        )


def test_settings_allow_memory_store_in_development():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="development",
        use_memory_store=True,
    )

    assert settings.use_memory_store is True


def test_settings_allow_explicit_opt_in_for_ephemeral_runs():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="staging",
        use_memory_store=True,
        allow_volatile_memory_store=True,
    )

    assert settings.allow_volatile_memory_store is True


def test_settings_reject_volatile_memory_store_for_public_runtime_even_if_app_env_is_development():
    with pytest.raises(ValidationError, match="public/VPS deployment"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="development",
            use_memory_store=True,
            APP_ALLOWED_HOSTS="api.example.com,localhost",
        )


def test_settings_reject_localhost_mongodb_for_public_runtime_even_if_app_env_is_development():
    with pytest.raises(ValidationError, match="public-facing deployment"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="development",
            use_memory_store=False,
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="najiz_legal_agent",
            APP_ALLOWED_HOSTS="api.example.com,localhost",
        )


def test_settings_reject_localhost_mongodb_in_protected_env_without_opt_in():
    with pytest.raises(ValidationError, match="MONGODB_URI points to localhost"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="staging",
            use_memory_store=False,
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="najiz_legal_agent_staging",
        )


def test_settings_allow_explicit_opt_in_for_localhost_mongodb_in_protected_env():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="staging",
        use_memory_store=False,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="najiz_legal_agent_staging",
        allow_localhost_mongodb_in_protected_env=True,
        allow_unauthenticated_mongodb_in_protected_env=True,
    )

    assert settings.allow_localhost_mongodb_in_protected_env is True


def test_settings_reject_unauthenticated_mongodb_in_protected_runtime():
    with pytest.raises(ValidationError, match="must include authentication credentials"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="production",
            use_memory_store=False,
            mongodb_uri="mongodb://host.docker.internal:27017",
            mongodb_database="najiz_legal_agent",
        )


def test_settings_allow_authenticated_mongodb_in_protected_runtime():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="production",
        use_memory_store=False,
        mongodb_uri="mongodb://appuser:secret@host.docker.internal:27017/?authSource=admin",
        mongodb_database="najiz_legal_agent",
    )

    assert settings.mongodb_database == "najiz_legal_agent"


def test_settings_allow_mongodb_credentials_from_separate_env_fields():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="production",
        use_memory_store=False,
        mongodb_uri="mongodb://host.docker.internal:27017",
        mongodb_database="najiz_legal_agent",
        mongodb_username="najiz_app",
        mongodb_password="p@ss word",
        mongodb_auth_source="admin",
    )

    assert settings.mongodb_auth_credentials_present is True
    assert settings.mongodb_effective_auth_source == "admin"
    assert settings.resolved_mongodb_uri == (
        "mongodb://najiz_app:p%40ss%20word@host.docker.internal:27017?authSource=admin"
    )


def test_settings_reject_partial_mongodb_credentials_from_separate_env_fields():
    with pytest.raises(ValidationError, match="MONGODB_USERNAME and MONGODB_PASSWORD"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="production",
            use_memory_store=False,
            mongodb_uri="mongodb://host.docker.internal:27017",
            mongodb_database="najiz_legal_agent",
            mongodb_username="najiz_app",
        )


def test_settings_apply_mongodb_auth_source_to_existing_uri():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="production",
        use_memory_store=False,
        mongodb_uri="mongodb://najiz_app:secret@host.docker.internal:27017",
        mongodb_database="najiz_legal_agent",
        mongodb_auth_source="admin",
    )

    assert settings.resolved_mongodb_uri == (
        "mongodb://najiz_app:secret@host.docker.internal:27017?authSource=admin"
    )


def test_settings_allow_explicit_opt_in_for_unauthenticated_mongodb_in_protected_runtime():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="production",
        use_memory_store=False,
        mongodb_uri="mongodb://host.docker.internal:27017",
        mongodb_database="najiz_legal_agent",
        allow_unauthenticated_mongodb_in_protected_env=True,
    )

    assert settings.allow_unauthenticated_mongodb_in_protected_env is True


def test_settings_allow_memory_store_for_local_only_container_hosts():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="development",
        use_memory_store=True,
        APP_ALLOWED_HOSTS="localhost,127.0.0.1,backend,host.docker.internal",
        CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
    )

    assert settings.use_memory_store is True


def test_settings_allow_memory_store_for_ipv6_loopback_and_localhost_subdomains():
    settings = Settings(
        app_encryption_key="test-key-123",
        app_env="development",
        use_memory_store=True,
        APP_ALLOWED_HOSTS="[::1],editor.localhost",
        CORS_ORIGINS="http://[::1]:3000,http://editor.localhost:3000",
    )

    assert settings.use_memory_store is True


def test_settings_reject_non_production_database_name_in_production():
    with pytest.raises(ValidationError, match="staging/test database name"):
        Settings(
            app_encryption_key="test-key-123",
            app_env="production",
            use_memory_store=False,
            mongodb_uri="mongodb://appuser:secret@host.docker.internal:27017/?authSource=admin",
            mongodb_database="najiz_legal_agent_staging",
        )
