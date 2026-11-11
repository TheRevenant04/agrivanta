FROM node:24-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc* ./
RUN npm ci
COPY frontend/ ./
RUN VITE_BASE=/static/ npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY --from=frontend-builder /app/frontend/dist /app/backend/frontend_dist

WORKDIR /app/backend
RUN python manage.py collectstatic --no-input

EXPOSE 8000
