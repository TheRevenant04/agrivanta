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

## Docker environments

Prerequisites: Docker Desktop (Windows/macOS) or Docker Engine with the Docker
Compose v2 plugin. No local Python, Node.js, PostgreSQL, or Redis installation
is needed. Both stacks use the base images already used by the project:
Python 3.13, Node.js 24, PostgreSQL 17, and Redis 7.

The repository ships two Compose files that use the same services but different
runtime behaviour:

| Stack            | Compose file             | Purpose                                                                                                                                                    |
| ---------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Development      | `docker-compose.yml`     | Fast local iteration: bind-mounted source, Django `runserver` auto-reload, Vite dev server with HMR, Celery worker.                                        |
| Production-like  | `docker-compose.prod.yml` | Immutable images: Gunicorn, built static assets served by Django/WhiteNoise, non-root user, no source mounts, `DJANGO_DEBUG=0`, Celery worker.             |

Both stacks read variables from the process environment and from an optional
Compose env file. The checked-in templates are:

- [`.env.dev.example`](.env.dev.example) — development credentials and ports.
- [`.env.prod.example`](.env.prod.example) — production-like placeholders for
  the Django secret key, database password, image tag, workers, and frontend
  build.

Copy a template to `.env.dev` or `.env.prod`; those files are gitignored.
Never commit real secrets.

### Development stack

From the repository root:

```bash
docker compose --env-file .env.dev up --build
```

`--env-file` is optional: without it, Compose uses the development defaults in
`docker-compose.yml`. Copying `.env.dev.example` is only needed when you want to
override the defaults.

The development stack runs:

| Service         | Host port            | Notes                                                                                   |
| --------------- | -------------------- | --------------------------------------------------------------------------------------- |
| `frontend`      | `127.0.0.1:5173`     | Vite dev server with hot module replacement, configured to call the backend at `/api`. |
| `web`           | `127.0.0.1:8000`     | Django `runserver` with auto-reload, `DJANGO_DEBUG=1`.                                  |
| `celery-worker` | —                    | Celery worker using Redis.                                                              |
| `postgres`      | —                    | PostgreSQL 17, not published to the host.                                               |
| `redis`         | —                    | Redis 7, not published to the host.                                                     |

Open the UI at `http://localhost:5173/`. The API is at
`http://localhost:8000/api/`, with health endpoints at
`http://localhost:8000/healthz` and `http://localhost:8000/readyz`. Source is
bind-mounted from `./backend` and `./frontend`, so edits reload automatically.
Compose waits for PostgreSQL and Redis health checks before starting Django,
and for Django to become healthy before starting the worker.

Follow logs with:

```bash
docker compose logs -f web frontend celery-worker
```

Stop the stack with:

```bash
docker compose down
```

### Production-like stack

Build and start the production-like stack from the repository root:

```bash
cp .env.prod.example .env.prod
# replace the secret placeholders in .env.prod
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Set `AGRIVANTA_VERSION` to an explicit release version or commit SHA in
`.env.prod` (or export it in the shell) so images are tagged, for example
`agrivanta-backend:$(git rev-parse --short HEAD)`. Add `AGRIVANTA_REVISION` with
the same value to record it as an OCI image label. Builds use `npm ci` and
`uv sync --frozen`, so they are reproducible from a clean clone.

This stack builds one multi-stage backend image that:

- compiles the Vite frontend and copies the assets into the image;
- installs runtime dependencies only (`--no-dev`);
- runs `collectstatic`;
- runs Gunicorn as the non-root `app` user; and
- serves the built UI and API from `http://127.0.0.1:8000/`.

PostgreSQL and Redis are internal to the Compose network. PostgreSQL data,
uploaded media, and private attachments use named volumes. There are no source
bind mounts, and Compose does not start a Celery beat scheduler.

Check both health endpoints after the containers are healthy:

```bash
curl --fail http://127.0.0.1:8000/healthz
curl --fail http://127.0.0.1:8000/readyz
```

Stop the stack with:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

The named volumes are preserved by `down`; use `down -v` only when you also want
to delete the database, media, and attachment data.

### Differences between the stacks

| Aspect          | Development (`docker-compose.yml`)        | Production-like (`docker-compose.prod.yml`)                    |
| --------------- | ----------------------------------------- | -------------------------------------------------------------- |
| Backend server  | `runserver` (auto-reload)                 | Gunicorn                                                       |
| Debug           | `DJANGO_DEBUG=1`                          | `DJANGO_DEBUG=0`                                               |
| Source code     | Bind-mounted from the host                | Copied into the immutable image                                |
| Frontend        | Vite dev server on port 5173              | Built assets served by Django on port 8000                     |
| Static files    | Served by the development servers         | `collectstatic` + WhiteNoise                                   |
| Container user  | Image default (root in the dev image)     | Non-root `app` user (UID/GID 10001)                            |
| Image tag       | Built on demand                           | `agrivanta-backend:${AGRIVANTA_VERSION}`                       |
| Restart policy  | Default                                   | `unless-stopped`                                               |
| Secrets         | Development placeholders                  | Required from `.env.prod`; no committed secrets                |

Both stacks publish the web port on loopback and default to `8000`, so run one
at a time or set `AGRIVANTA_WEB_PORT` to a free port. The development frontend
port can be changed with `AGRIVANTA_FRONTEND_PORT`.

PDF report exports are not available in the Compose images: they require the
optional Playwright dependency and a Chromium-compatible browser, which the
images do not include. PDF export requests return `503` without these
dependencies.

Run backend tests outside Docker from the repository root:

```bash
uv run pytest
```

## Frontend

To run the frontend for local development outside Docker, use a separate
terminal from `frontend/`:

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
