# syntax=docker/dockerfile:1

# Build the Vite frontend once and reuse the static assets in the production
# backend image. The development target does not include this stage.
FROM node:24-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc* ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_CLIENT=http
ARG VITE_API_BASE_URL=/api
ARG VITE_SENTRY_DSN=
ENV VITE_API_CLIENT=${VITE_API_CLIENT} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
RUN VITE_BASE=/static/ npm run build

FROM python:3.13-slim AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

# Development image: includes dev dependencies and leaves source mounted by
# Compose. Runs as root so bind-mounted files stay easy to edit on any host.
FROM python-base AS development

RUN uv sync --frozen --no-install-project

COPY backend ./backend

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Production image: runtime dependencies only, immutable source, collected
# static assets, and an unprivileged user.
FROM python-base AS production

ARG AGRIVANTA_VERSION=local
ARG AGRIVANTA_REVISION=unknown

LABEL org.opencontainers.image.title="agrivanta-backend" \
      org.opencontainers.image.version="${AGRIVANTA_VERSION}" \
      org.opencontainers.image.revision="${AGRIVANTA_REVISION}"

RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY --from=frontend-builder /app/frontend/dist /app/backend/frontend_dist

WORKDIR /app/backend

RUN python manage.py collectstatic --no-input \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /app/backend/media /app/backend/private_attachments \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
