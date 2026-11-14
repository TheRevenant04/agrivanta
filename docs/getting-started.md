# Getting Started with Agrivanta

This guide walks you through setting up Agrivanta locally for development and evaluation.

## Prerequisites

- **Docker Desktop** (Windows/macOS) or **Docker Engine** with Compose v2 plugin (Linux)
- **Node.js 24.x** (for frontend development outside Docker)
- **Python 3.13+** with `uv` (for backend development outside Docker)
- **Git** for cloning the repository

No local PostgreSQL, Redis, Python, or Node.js installation is required when using Docker.

## Quick Start (Docker Development Stack)

The fastest way to run Agrivanta locally:

```bash
# Clone the repository
git clone <repository-url>
cd agrivanta

# Copy development environment template (optional - defaults work out of the box)
cp .env.dev.example .env.dev

# Start all services
docker compose --env-file .env.dev up --build
```

**Services started:**
| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | React application with hot reload |
| Backend API | http://localhost:8000/api | Django REST API |
| Health Check | http://localhost:8000/healthz | Liveness probe |
| Readiness Check | http://localhost:8000/readyz | Database readiness |

**Default login credentials (mock mode):**
| Email | Password | Role |
|-------|----------|------|
| owner@agrivanta.test | password123 | Farm Owner |
| manager@agrivanta.test | password123 | Farm Manager |

## Quick Start (Local Development)

For faster iteration during development, run services outside Docker:

### Backend
```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```
API available at http://localhost:8000/api/

### Frontend
```bash
cd frontend
npm ci
npm run dev
```
App available at http://localhost:5173/ (uses mock services by default)

To connect frontend to local backend:
```bash
# In frontend/.env
VITE_API_CLIENT=http
VITE_API_BASE_URL=http://localhost:8000/api
```

## Production-like Stack

For a production-like environment locally:

```bash
cp .env.prod.example .env.prod
# Edit .env.prod with secure secrets
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Application served at http://localhost:8000/

## Next Steps

- [Architecture Overview](architecture.md) — Understand the system design
- [API Reference](api-reference.md) — Explore the REST API
- [Development Guide](development.md) — Contribute to the codebase
- [CI/CD & Cloud Deployment](ci-cd.md) — CI pipeline, CD guidance, and cloud deployment options
- [Deployment Guide](deployment.md) — Deploy to production
- [Configuration Reference](configuration.md) — All environment variables
- [Project Structure](project-structure.md) — Directory layout and modules