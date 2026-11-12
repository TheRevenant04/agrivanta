"""Static checks for the development and production Docker environments.

These tests do not require a Docker daemon. They assert the checked-in
configuration keeps the contracts described in issue #141: distinct dev/prod
stacks, no source mounts or dev server in production, environment templates,
and a hardened multi-stage production image.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]

DEV_COMPOSE = "docker-compose.yml"
PROD_COMPOSE = "docker-compose.prod.yml"
BACKEND_DOCKERFILE = "backend/Dockerfile"
FRONTEND_DOCKERFILE = "frontend/Dockerfile"

ENV_KEYS = {
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "DJANGO_ALLOWED_HOSTS",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "SENTRY_DSN",
    "VITE_API_CLIENT",
    "VITE_API_BASE_URL",
    "VITE_SENTRY_DSN",
}


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_compose(relative_path: str) -> dict:
    return yaml.safe_load(_read(relative_path))


def _env_value(environment: dict, key: str) -> str:
    value = environment[key]
    # Resolve Compose-style "${VAR:-default}" interpolation to its default so
    # assertions describe the effective built-in configuration.
    if isinstance(value, str) and value.startswith("${") and ":-" in value:
        return value.rsplit(":-", 1)[1].rstrip("}")
    return value


def _volume_targets(services: dict) -> list[str]:
    targets = []
    for service in services.values():
        for volume in service.get("volumes", []):
            targets.append(volume)
    return targets


def _assert_only_named_volumes(services: dict) -> None:
    for entry in _volume_targets(services):
        source = entry.split(":", 1)[0]
        assert not source.startswith((".", "/", "~")), (
            f"production compose must not bind-mount host paths: {entry}"
        )


def test_development_compose_runs_dev_servers_and_mounts_source() -> None:
    compose = _load_compose(DEV_COMPOSE)
    services = compose["services"]

    assert {"postgres", "redis", "web", "celery-worker", "frontend"} <= set(
        services
    )

    web = services["web"]
    assert web["build"]["target"] == "development"
    assert "runserver" in web["command"]
    assert "gunicorn" not in web["command"]
    assert _env_value(web["environment"], "DJANGO_DEBUG") == "1"
    assert "./backend:/app/backend" in web["volumes"]

    celery = services["celery-worker"]
    assert celery["build"]["target"] == "development"
    assert "celery" in celery["command"]
    assert "./backend:/app/backend" in celery["volumes"]

    frontend = services["frontend"]
    assert frontend["build"]["context"] == "./frontend"
    assert frontend["build"]["target"] == "development"
    assert "./frontend:/app" in frontend["volumes"]
    assert "frontend_node_modules:/app/node_modules" in frontend["volumes"]
    assert _env_value(frontend["environment"], "VITE_API_CLIENT") == "http"


def test_production_compose_uses_gunicorn_without_source_mounts() -> None:
    compose = _load_compose(PROD_COMPOSE)
    services = compose["services"]

    assert {"postgres", "redis", "web", "celery-worker"} <= set(services)
    assert "frontend" not in services

    web = services["web"]
    assert web["build"]["target"] == "production"
    assert "gunicorn" in web["command"]
    assert "runserver" not in web["command"]
    assert _env_value(web["environment"], "DJANGO_DEBUG") == "0"
    assert web["image"].startswith("agrivanta-backend:")
    assert "AGRIVANTA_VERSION" in web["image"]

    celery = services["celery-worker"]
    assert celery["build"]["target"] == "production"
    assert celery["image"] == web["image"]

    _assert_only_named_volumes(services)
    assert {"postgres_data", "media_data", "private_attachments_data"} <= set(
        compose["volumes"]
    )


def test_backend_dockerfile_builds_hardened_production_image() -> None:
    dockerfile = _read(BACKEND_DOCKERFILE)

    assert "AS frontend-builder" in dockerfile
    assert "AS python-base" in dockerfile
    assert "AS development" in dockerfile
    assert "AS production" in dockerfile

    development, production = dockerfile.split("AS production", 1)
    assert "runserver" in development
    assert "uv sync --frozen --no-install-project" in development

    assert "uv sync --frozen --no-dev" in production
    assert "collectstatic" in production
    assert "useradd" in production
    assert "USER app" in production
    assert "gunicorn" in production
    assert "runserver" not in production
    assert 'VITE_API_CLIENT=http' in dockerfile
    assert 'VITE_API_BASE_URL=/api' in dockerfile


def test_frontend_dockerfile_provides_vite_dev_server() -> None:
    dockerfile = _read(FRONTEND_DOCKERFILE)

    assert "AS development" in dockerfile
    assert "npm ci" in dockerfile
    assert '"npm", "run", "dev"' in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile


def test_environment_templates_list_required_variables() -> None:
    for template in (".env.dev.example", ".env.prod.example"):
        content = _read(template)
        keys = {
            line.split("=", 1)[0].strip()
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        }
        missing = ENV_KEYS - keys
        assert not missing, f"{template} is missing: {sorted(missing)}"

    prod = _read(".env.prod.example")
    assert "AGRIVANTA_VERSION" in prod
    assert "AGRIVANTA_REVISION" in prod
    assert "GUNICORN_WORKERS" in prod
    assert "replace-with" in prod
    assert "dev-only-insecure-key-change-me" not in prod


def test_env_templates_are_not_gitignored() -> None:
    gitignore = _read(".gitignore")

    assert "!.env.dev.example" in gitignore
    assert "!.env.prod.example" in gitignore
