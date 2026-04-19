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
