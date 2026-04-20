from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


NON_PRODUCTION_NAME_PATTERN = re.compile(r"(^|[-_])(staging|stage|test|pr)([-_]|$)", re.IGNORECASE)
LOCALHOST_PREFIXES = ("mongodb://localhost", "mongodb://127.0.0.1")
INTEGER_SETTING_NAMES = (
    "APP_PORT",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "SESSION_EXPIRY_HOURS",
    "SESSION_TURN_LIMIT",
    "PETITION_VERSION_LIMIT",
    "DISPUTE_VALUE_THRESHOLD",
)


class DeployEnvError(ValueError):
    """Raised when a deploy environment file is unsafe for the requested deploy mode."""


@dataclass(frozen=True)
class PreparedDeployEnv:
    backend_port: str
    frontend_port: str


def _parse_env_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()

    if "=" not in stripped:
        return None

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = raw_value.strip()
    if not value:
        return key, ""

    if value[0] in {'"', "'"}:
        quote = value[0]
        closing_quote = value.find(quote, 1)
        if closing_quote != -1:
            return key, value[1:closing_quote]
        return key, value[1:]

    comment_index = value.find(" #")
    if comment_index != -1:
        value = value[:comment_index]

    return key, value.rstrip()


def _read_env_lines(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}

    for line in lines:
        assignment = _parse_env_assignment(line)
        if assignment is None:
            continue
        key, value = assignment
        values[key] = value

    return lines, values


def _upsert_env_line(lines: list[str], key: str, value: str) -> None:
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        assignment = _parse_env_assignment(line)
        if assignment is None:
            continue
        existing_key, _ = assignment
        if existing_key == key:
            lines[index] = replacement
            return
    lines.append(replacement)


def _write_env_lines(path: Path, lines: list[str]) -> None:
    content = "\n".join(lines)
    if lines:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_allowed_hosts(value: str | None, required_item: str) -> str:
    items = [item.strip() for item in (value or "").split(",") if item.strip()]
    if not items:
        items = [required_item, "localhost", "127.0.0.1", "backend"]
        return ",".join(items)
    if required_item not in items:
        items.insert(0, required_item)
    return ",".join(items)


def _normalize_mongodb_uri(value: str) -> str:
    for prefix in LOCALHOST_PREFIXES:
        if value.startswith(prefix):
            return value.replace(prefix, "mongodb://host.docker.internal", 1)
    return value


def _validate_integer_settings(values: dict[str, str]) -> None:
    for name in INTEGER_SETTING_NAMES:
        raw_value = values.get(name)
        if raw_value is None or not raw_value.strip():
            continue
        try:
            int(raw_value.strip())
        except ValueError as exc:
            raise DeployEnvError(
                f"{name} must be a plain integer value in the deploy env file; got {raw_value!r}."
            ) from exc


def _validate_deploy_mode(values: dict[str, str], mode: str) -> None:
    app_env = values.get("APP_ENV", "").strip().lower()
    expected_envs = {"production", "prod"} if mode == "production" else {"staging", "stage"}
    if app_env not in expected_envs:
        expected = ", ".join(sorted(expected_envs))
        raise DeployEnvError(f"APP_ENV must be one of [{expected}] for a {mode} deploy.")


def _validate_production_names(values: dict[str, str]) -> None:
    mongodb_database = values.get("MONGODB_DATABASE", "").strip()
    if not mongodb_database:
        raise DeployEnvError("MONGODB_DATABASE is required for deployment.")
    if NON_PRODUCTION_NAME_PATTERN.search(mongodb_database):
        raise DeployEnvError(
            "MONGODB_DATABASE looks like a non-production database name. Refusing to deploy main against it."
        )

    compose_project_name = values.get("COMPOSE_PROJECT_NAME", "").strip()
    if compose_project_name and NON_PRODUCTION_NAME_PATTERN.search(compose_project_name):
        raise DeployEnvError(
            "COMPOSE_PROJECT_NAME looks like a staging/test stack name. Refusing to deploy main against it."
        )


def prepare_deploy_env(
    input_path: Path,
    output_path: Path,
    *,
    mode: str,
    vps_host: str,
) -> PreparedDeployEnv:
    lines, values = _read_env_lines(input_path)

    if not vps_host.strip():
        raise DeployEnvError("VPS host is required.")

    if _is_truthy(values.get("USE_MEMORY_STORE")):
        raise DeployEnvError(
            "USE_MEMORY_STORE=true disables Mongo persistence and clears admin history after restarts."
        )

    _validate_deploy_mode(values, mode)
    _validate_integer_settings(values)

    mongodb_uri = values.get("MONGODB_URI", "").strip()
    if not mongodb_uri:
        raise DeployEnvError("MONGODB_URI is required for deployment.")

    if mode == "production":
        _validate_production_names(values)

    normalized_mongodb_uri = _normalize_mongodb_uri(mongodb_uri)
    allowed_hosts = _normalize_allowed_hosts(values.get("APP_ALLOWED_HOSTS"), vps_host)
    compose_project_name = values.get("COMPOSE_PROJECT_NAME", "").strip() or (
        "najiz-main" if mode == "production" else "najiz-staging"
    )
    backend_port = values.get("BACKEND_PORT", "").strip() or "8000"
    frontend_port = values.get("FRONTEND_PORT", "").strip() or "3000"

    _upsert_env_line(lines, "MONGODB_URI", normalized_mongodb_uri)
    _upsert_env_line(lines, "APP_ALLOWED_HOSTS", allowed_hosts)
    _upsert_env_line(lines, "COMPOSE_PROJECT_NAME", compose_project_name)
    _upsert_env_line(lines, "BACKEND_PORT", backend_port)
    _upsert_env_line(lines, "FRONTEND_PORT", frontend_port)
    _write_env_lines(output_path, lines)

    return PreparedDeployEnv(backend_port=backend_port, frontend_port=frontend_port)


def _append_github_outputs(path: Path, prepared: PreparedDeployEnv) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"backend_port={prepared.backend_port}\n")
        handle.write(f"frontend_port={prepared.frontend_port}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and normalize deployment environment files.")
    parser.add_argument("--input", dest="input_path", required=True, type=Path)
    parser.add_argument("--output", dest="output_path", required=True, type=Path)
    parser.add_argument("--mode", choices=("production", "staging"), required=True)
    parser.add_argument("--vps-host", required=True)
    parser.add_argument("--github-output", dest="github_output", type=Path)
    args = parser.parse_args()

    prepared = prepare_deploy_env(
        args.input_path,
        args.output_path,
        mode=args.mode,
        vps_host=args.vps_host,
    )
    if args.github_output is not None:
        _append_github_outputs(args.github_output, prepared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
