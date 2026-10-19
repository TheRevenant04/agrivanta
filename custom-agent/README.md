# Headless issue orchestrator

Custom agent implementing the `_docs/process.md` lifecycle without an
interactive session, suitable for CI or scheduled runs:

1. PM grooms the issue into the four-section template
2. Engineer implements it on a branch (fresh session per role)
3. QA verifies and posts the `## QA: PASS` / `## QA: FAIL` comment
4. On FAIL, the engineer retries with the QA comment as input
5. On PASS, the orchestrator pushes the branch, opens a PR, and closes
   the issue

Each role runs as `opencode run --agent <role> --auto`, so no context
is shared between roles. `--auto` approves only what
`_docs/permissions.md` and the `opencode.json` permission rules allow —
denied commands still fail.

## Usage

``` bash
uv run custom-agent/agent.py              # work the whole open backlog
uv run custom-agent/agent.py --issue 12   # work a single issue
uv run custom-agent/agent.py --issue 12 --dry-run   # print the plan only
uv run custom-agent/agent.py --max-attempts 5
```

## Requirements

- `uv`, `opencode`, and an authenticated `gh` CLI on `PATH`
- A provider configured for opencode (`opencode auth login`)
- Dry runs need `--issue` and make no network or agent calls

## Safety

The orchestrator never force-pushes, amends, or resets (enforced by
permission rules and the guardrails plugin), never closes an issue
before a QA PASS, and exits non-zero if any issue fails after
`--max-attempts`.
