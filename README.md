# Agrivanta

Agrivanta is a responsive farm-operations and financial-reporting application
for commercially managed crop farms. It brings farm setup, crop cycles,
activities, inventory, expenses, harvests, sales, profitability, and dashboard
KPIs together in one web application.

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

Run backend tests from the repository root:

```bash
uv run pytest
```

## Frontend

In a separate terminal, from `frontend/`:

```bash
npm ci
npm run dev
```

The frontend uses mock services by default and does not require the backend.
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

See [`frontend/README.md`](frontend/README.md) for environment details,
available scripts, and frontend architecture.

## Repository guide

- [`backend/`](backend/) — Django project, API app, migrations, and pytest
  suite
- [`frontend/`](frontend/) — Vite application and Vitest suite
- [`openapi.yaml`](openapi.yaml) — API contract
- [`_docs/`](_docs/) — product plan, backlog, and contribution workflows
- [`custom-agent/`](custom-agent/) — headless issue lifecycle runner
- [`mcp-server/`](mcp-server/) — read-only backlog and issue MCP server
- [`.agents/`](.agents/) and [`.opencode/`](.opencode/) — portable and
  OpenCode agent customizations

Agent workflow and repository policies are documented in
[`AGENTS.md`](AGENTS.md) and [`_docs/`](_docs/).
