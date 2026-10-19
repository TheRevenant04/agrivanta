# Agrivanta backlog MCP server

Read-only MCP server exposing the implementation backlog and open GitHub
issues to the agent. Registered in `opencode.json` as
`agrivanta-backlog`:

``` json
"mcp": {
  "agrivanta-backlog": {
    "type": "local",
    "command": ["uv", "run", "mcp-server/server.py"],
    "enabled": true
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `list_backlog_tasks(phase?)` | List tasks from `_docs/tasks.md` (number, title, phase, goal); optional phase filter |
| `get_backlog_task(number)` | Full backlog entry for one task number |
| `list_open_issues()` | Open GitHub issues via `gh` (number, title, labels) |

All tools are read-only, per `_docs/permissions.md`. Do not add write
tools.

## Running manually

``` bash
uv sync
uv run mcp-server/server.py   # stdio transport; normally started by opencode
```

Requires `uv` on `PATH`; `list_open_issues` additionally requires an
authenticated `gh` CLI.
