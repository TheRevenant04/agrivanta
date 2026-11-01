# AGENTS.md

Guidance for AI agents working in this repository.

## Project

Agrivanta's product vision is a responsive application for commercially
managed crop farms, combining farm operations, financial records,
profitability reporting, and a read-only AI analyst with traceable evidence.
The product vision is broader than the currently implemented features.

- Scope and requirements: [`_docs/plan.md`](_docs/plan.md)
- Implementation backlog (tasks 1–63): [`_docs/tasks.md`](_docs/tasks.md)

Current implementation: a Django 5.2 + DRF backend with farm-scoped
operations, inventory, financial, reporting, notification, and dashboard
APIs; a React 18 + TypeScript (Vite) frontend; and backend/frontend test
suites. Local backend development uses SQLite by default, with PostgreSQL
available through environment configuration. Celery/Redis and the AI analyst
remain in the product plan/backlog; do not describe them as implemented.
There is currently no GitHub Actions CI workflow.

## Repository layout

```text
_docs/                Product plan, backlog, and agent workflow rules
.agents/              Portable agent and skill definitions
.opencode/             OpenCode agents and the guardrails plugin
backend/              Django project, API app, migrations, and pytest suite
frontend/             React/Vite app, services, and Vitest suite
custom-agent/         Headless PM/engineer/QA issue orchestrator
mcp-server/           Read-only backlog + issues MCP server
openapi.yaml          Backend API contract
opencode.json         OpenCode config: permissions, MCP, instructions
pyproject.toml        Python project metadata and dependencies
README.md             Project overview and local setup
```

## Required reading

Follow these documents in full; they define repository policy:

- [`_docs/commit-message-guidelines.md`](_docs/commit-message-guidelines.md)
  — Conventional Commits format, allowed types, staging rules.
- [`_docs/branching-strategy.md`](_docs/branching-strategy.md) — feature
  branching, branch naming, PR workflow, and safety rules.
- [`_docs/permissions.md`](_docs/permissions.md) — what agents may and
  may not do; enforced rules and policy (machine-enforced parts live in
  `opencode.json` and `.opencode/plugins/guardrails.js`).

Summary of the non-negotiables:

- Commit messages use Conventional Commits:
  `<type>[scope][!]: <imperative description>` — ≤72 chars, lowercase start,
  no trailing period, no vague subjects.
- Work on short-lived branches (`feature/`, `fix/`, `docs/`, `refactor/`,
  `test/`, `ci/`, `build/`, `chore/`) and integrate through pull requests.
- `main` stays stable: no direct commits or pushes except to establish the
  repository base, which is already done.
- Never amend, rebase-published, force-push, or bypass hooks unless
  explicitly authorized.
- Never discard, reset, stash, or overwrite existing user changes; leave
  unrelated changes untouched.
- Never invent issue numbers, links, or ticket references.
- If changes contain unrelated concerns, make separate commits — but never
  leave the repository in a broken intermediate state.

## Workflow

1. Inspect before acting: `git status --short --branch`, then read the
   relevant `_docs` files and any `AGENTS.md` in subdirectories.
2. Keep changes limited to the task's scope; stage only intended files.
3. Run available checks before committing (currently none are configured —
   say so honestly rather than implying checks passed).
4. Report the commit hash, subject, and checks run. Do not claim success
   for work that did not complete.

## Commands

```bash
uv sync
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver
uv run pytest
uv run mcp-server/server.py      # read-only backlog MCP server
uv run custom-agent/agent.py     # headless issue lifecycle
```

Frontend commands run from `frontend/` after `npm ci`:

```bash
npm run dev
npm run lint
npm run format:check
npm run test
npm run build
```

The frontend defaults to mock services. Set `VITE_API_CLIENT=http` and
`VITE_API_BASE_URL=http://localhost:8000/api` in `frontend/.env` to use the
local backend. Backend tests use `uv run pytest`; frontend tests use Vitest
through `npm run test`.

## Process

- [_docs/process.md](_docs/process.md) - how work is organized
- [_docs/agent-extension-pack.md](_docs/agent-extension-pack.md) -
  skills, subagents, MCP server, guardrails, and custom agent index
- [_docs/demo.md](_docs/demo.md) - extension pack walkthrough
