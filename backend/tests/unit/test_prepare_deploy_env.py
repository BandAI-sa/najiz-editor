from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "deploy" / "prepare_deploy_env.py"
MODULE_SPEC = importlib.util.spec_from_file_location("prepare_deploy_env", MODULE_PATH)
prepare_deploy_env_module = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = prepare_deploy_env_module
MODULE_SPEC.loader.exec_module(prepare_deploy_env_module)

DeployEnvError = prepare_deploy_env_module.DeployEnvError
prepare_deploy_env = prepare_deploy_env_module.prepare_deploy_env


def test_prepare_deploy_env_normalizes_localhost_uri_and_defaults_ports(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "USE_MEMORY_STORE=false",
                "MONGODB_URI=mongodb://localhost:27017",
                "MONGODB_DATABASE=najiz_legal_agent",
                "APP_ALLOWED_HOSTS=localhost,127.0.0.1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    prepared = prepare_deploy_env(
        env_file,
        env_file,
        mode="production",
        vps_host="198.51.100.10",
    )

    content = env_file.read_text(encoding="utf-8")
    assert prepared.backend_port == "8000"
    assert prepared.frontend_port == "3000"
    assert "MONGODB_URI=mongodb://host.docker.internal:27017" in content
    assert "APP_ALLOWED_HOSTS=198.51.100.10,localhost,127.0.0.1" in content
    assert "COMPOSE_PROJECT_NAME=najiz-main" in content
    assert "BACKEND_PORT=8000" in content
    assert "FRONTEND_PORT=3000" in content


def test_prepare_deploy_env_defaults_allowed_hosts_when_missing(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "USE_MEMORY_STORE=false",
                "MONGODB_URI=mongodb://host.docker.internal:27017",
                "MONGODB_DATABASE=najiz_legal_agent",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    prepare_deploy_env(
        env_file,
        env_file,
        mode="production",
        vps_host="198.51.100.10",
    )

    content = env_file.read_text(encoding="utf-8")
    assert "APP_ALLOWED_HOSTS=198.51.100.10,localhost,127.0.0.1,backend" in content


def test_prepare_deploy_env_handles_exported_and_quoted_values(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "export APP_ENV=production",
                "USE_MEMORY_STORE=false",
                'MONGODB_URI="mongodb://localhost:27017" # keep local during authoring',
                "MONGODB_DATABASE=najiz_legal_agent",
                'APP_ALLOWED_HOSTS="localhost,127.0.0.1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    prepare_deploy_env(
        env_file,
        env_file,
        mode="production",
        vps_host="198.51.100.10",
    )

    content = env_file.read_text(encoding="utf-8")
    assert "MONGODB_URI=mongodb://host.docker.internal:27017" in content
    assert "APP_ALLOWED_HOSTS=198.51.100.10,localhost,127.0.0.1" in content
    assert "export APP_ENV=production" in content


def test_prepare_deploy_env_rejects_ephemeral_storage_for_production(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "USE_MEMORY_STORE=true",
                "MONGODB_URI=mongodb://host.docker.internal:27017",
                "MONGODB_DATABASE=najiz_legal_agent",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DeployEnvError, match="USE_MEMORY_STORE=true"):
        prepare_deploy_env(
            env_file,
            env_file,
            mode="production",
            vps_host="198.51.100.10",
        )


def test_prepare_deploy_env_rejects_staging_database_name_for_production(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "USE_MEMORY_STORE=false",
                "MONGODB_URI=mongodb://host.docker.internal:27017",
                "MONGODB_DATABASE=najiz_legal_agent_staging",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DeployEnvError, match="non-production database name"):
        prepare_deploy_env(
            env_file,
            env_file,
            mode="production",
            vps_host="198.51.100.10",
        )


def test_prepare_deploy_env_rejects_staging_stack_name_for_production(tmp_path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "USE_MEMORY_STORE=false",
                "MONGODB_URI=mongodb://host.docker.internal:27017",
                "MONGODB_DATABASE=najiz_legal_agent",
                "COMPOSE_PROJECT_NAME=najiz-pr-staging",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DeployEnvError, match="staging/test stack name"):
        prepare_deploy_env(
            env_file,
            env_file,
            mode="production",
            vps_host="198.51.100.10",
        )
