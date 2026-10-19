# AGENTS.md

Guidance for AI agents working in this repository.

## Project

Agrivanta is a responsive web application for commercially managed crop
farms: farm operations, financial records, profitability reporting, and a
read-only AI analyst that answers natural-language questions from recorded
data with traceable evidence.

- Scope and requirements: [`_docs/plan.md`](_docs/plan.md)
- Implementation backlog (tasks 1–63): [`_docs/tasks.md`](_docs/tasks.md)

Planned stack (not yet built): Django 5 + DRF backend, PostgreSQL,
Celery + Redis, React 18 + TypeScript (Vite) frontend.

Current state: a minimal Python 3.13 project managed with `uv`
(`pyproject.toml`, `.python-version`, sample `main.py`). There is no
application code, test suite, or CI yet — start with Phase 0 of the backlog
unless the user directs otherwise.

## Repository layout

``` text
_docs/               Product plan, backlog, and agent workflow rules
.agents/             Portable agent and skill definitions
.opencode/           OpenCode agents and the guardrails plugin
custom-agent/        Headless PM/engineer/QA orchestrator
mcp-server/          Read-only backlog + issues MCP server
main.py              Sample script (PyCharm scaffold)
opencode.json        OpenCode config: permissions, MCP, instructions
pyproject.toml       Project metadata and dependencies
README.md            Setup instructions (currently empty)
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

``` bash
uv sync                          # install dependencies
uv run main.py                   # run the sample script
uv run mcp-server/server.py      # backlog MCP server (normally auto-started by opencode)
uv run custom-agent/agent.py     # headless issue lifecycle (--issue N, --dry-run)
```

Test, lint, and build commands do not exist yet; add them to this file when
the toolchain from `_docs/tasks.md` Phase 0 is in place.

## Process

- [_docs/process.md](_docs/process.md) - how work is organized
- [_docs/agent-extension-pack.md](_docs/agent-extension-pack.md) -
  skills, subagents, MCP server, guardrails, and custom agent index
- [_docs/demo.md](_docs/demo.md) - extension pack walkthrough