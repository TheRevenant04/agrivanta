# Agrivanta

Agrivanta is a responsive farm-operations and financial-reporting application
for commercially managed crop farms. It brings farm setup, crop cycles,
activities, inventory, expenses, harvests, sales, profitability, and dashboard
KPIs together in one web application. It also includes CSV/Excel imports,
in-app notifications, predefined reports and exports, and an evidence-backed
read-only AI chat interface.

The repository currently contains a Django REST Framework backend and a React
18 + TypeScript frontend. The frontend can run against browser-based mock
services or the backend API. Product scope and longer-term requirements are in
[`_docs/plan.md`](_docs/plan.md); the implementation backlog is in
[`_docs/tasks.md`](_docs/tasks.md).

## Requirements

- Python 3.13 or newer, with [`uv`](https://docs.astral.sh/uv/)
- Node.js 24.x and npm for the frontend

The backend uses SQLite by default for local development. Set `POSTGRES_DB`
and the related `POSTGRES_*` environment variables to use PostgreSQL instead.

## Backend

From the repository root:

```bash
uv sync
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver
```

The API is available under `http://localhost:8000/api/`. The backend uses
development defaults when no environment is configured; set an appropriate
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, and `DJANGO_ALLOWED_HOSTS` before any
non-development deployment.
The backend-maintained OpenAPI contract is available at
`http://localhost:8000/openapi.yaml` and is stored in
[`backend/api/openapi.yaml`](backend/api/openapi.yaml).
`http://localhost:8000/healthz` is the liveness endpoint;
`http://localhost:8000/readyz` checks database readiness.

## Local development with Docker Compose

Install Docker Desktop (Windows/macOS) or Docker Engine with the Docker Compose
v2 plugin, then run these commands from the repository root. No local Python,
Node.js, PostgreSQL, or Redis installation is needed for this stack.

```bash
docker compose up --build
```

This builds the backend and frontend images, runs database migrations, and
starts PostgreSQL, Redis, the Django development server, the Vite frontend
development server, and a Celery worker. The API is available at
`http://localhost:8000/api/` with its health endpoint at
`http://localhost:8000/healthz`; the frontend is at `http://localhost:5173/`.
Compose waits for PostgreSQL and Redis health checks before starting Django,
for Django to become healthy before starting the worker and frontend, and
configures the frontend to call the backend over HTTP instead of using mock
services. Django and the frontend are published on loopback only
(`127.0.0.1:8000` and `127.0.0.1:5173`).

Compose defaults `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` to
`agrivanta`; override them in the shell or Compose environment when needed.
The default credentials and debug configuration are for local development
only. PostgreSQL and Redis are not published to the host by this Compose file.
The stack starts a Celery worker, not a Celery beat scheduler, so configured
periodic tasks are not automatically scheduled by Compose.

PDF report exports are not available in the default Compose image: they
require the optional Playwright dependency and a Chromium-compatible browser,
which the image does not include. PDF export requests return `503` without
these dependencies.

In another terminal, follow the application, frontend, and worker logs with:

```bash
docker compose logs -f web frontend celery-worker
```

Stop and remove the containers and network with:

```bash
docker compose down
```

The PostgreSQL data volume is preserved by `down`; use `docker compose down -v`
only when you also want to delete the local database data.

Run backend tests from the repository root:

```bash
uv run pytest
```

## Frontend

The Compose stack already runs the frontend at `http://localhost:5173/`. To run
it outside Docker, use a separate terminal from `frontend/`:

```bash
npm ci
npm run dev
```

The frontend uses React 18, TypeScript, Tailwind CSS v4, and shadcn/ui
components. It uses mock services by default and does not require the backend.
To use the local API, set the following in `frontend/.env`:

```dotenv
VITE_API_CLIENT=http
VITE_API_BASE_URL=http://localhost:8000/api
```

Frontend checks, run from `frontend/`:

```bash
npm run lint
npm run format:check
npm run test
npm run build
```

After changing the backend OpenAPI contract, run `npm run api:generate` in
`frontend/` and commit the regenerated client files. See the frontend guide for
the optional schema URL and why chat uses a separate streaming transport.
AI chat requires the HTTP client; mock services do not implement it.
Generated answers use the backend's OpenAI adapter, configured with
`OPENAI_API_KEY` and optionally `OPENAI_MODEL`. The default Compose file does
not pass these variables to the web container; configure them separately in
the container environment to use provider-backed answers. Do not commit keys.

See [`frontend/README.md`](frontend/README.md) for environment details,
available scripts, and frontend architecture.

## Repository guide

- [`backend/`](backend/) — Django project, API app, migrations, and pytest
  suite
- [`frontend/`](frontend/) — Vite application and Vitest suite
- [`backend/api/openapi.yaml`](backend/api/openapi.yaml) — backend API contract
- [`_docs/`](_docs/) — product plan, backlog, and contribution workflows
- [`custom-agent/`](custom-agent/) — headless issue lifecycle runner
- [`mcp-server/`](mcp-server/) — read-only backlog and issue MCP server
- [`.agents/`](.agents/) and [`.opencode/`](.opencode/) — portable and
  OpenCode agent customizations

Agent workflow and repository policies are documented in
[`AGENTS.md`](AGENTS.md) and [`_docs/`](_docs/).
