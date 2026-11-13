import os
from pathlib import Path

import sentry_sdk
import structlog
from celery.schedules import crontab
from sentry_sdk.integrations.django import DjangoIntegration

from api.telemetry import add_trace_context

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-me-in-production",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
LLM_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# --- OpenTelemetry ---
# Telemetry is opt-in: without an OTLP endpoint the backend stays a no-op.
OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", ""
).strip()
OTEL_SERVICE_NAME = (
    os.environ.get("OTEL_SERVICE_NAME", "").strip() or "agrivanta-backend"
)
_OTEL_ALLOWED_ENVIRONMENTS = {"local", "dev", "staging", "production"}
_otel_environment = os.environ.get(
    "OTEL_DEPLOYMENT_ENVIRONMENT", "local"
).strip().lower()
OTEL_DEPLOYMENT_ENVIRONMENT = (
    _otel_environment
    if _otel_environment in _OTEL_ALLOWED_ENVIRONMENTS
    else "local"
)
AGRIVANTA_VERSION = os.environ.get("AGRIVANTA_VERSION", "").strip() or "local"
AGRIVANTA_REVISION = os.environ.get("AGRIVANTA_REVISION", "").strip()
OTEL_SERVICE_VERSION = (
    AGRIVANTA_VERSION if AGRIVANTA_VERSION not in ("", "unknown") else "local"
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "api.observability.RequestLoggingMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "api.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.NumericPasswordValidator"
        ),
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
STATICFILES_DIRS = []
frontend_dist = BASE_DIR / "frontend_dist"
if frontend_dist.exists():
    STATICFILES_DIRS.append(frontend_dist)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
    "attachments": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": BASE_DIR / "private_attachments",
            "base_url": None,
            "file_permissions_mode": 0o600,
            "directory_permissions_mode": 0o700,
        },
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

APPEND_SLASH = False

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.BearerTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "api.exceptions.api_exception_handler",
    "COERCE_DECIMAL_TO_STRING": False,
    "UNAUTHENTICATED_USER": None,
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "process-recurring-expense-reminders-daily": {
        "task": "api.tasks.process_recurring_expense_reminders",
        "schedule": crontab(hour=0, minute=0),
    }
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
            "foreign_pre_chain": [
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                add_trace_context,
            ],
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
    )
