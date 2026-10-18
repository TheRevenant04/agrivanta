# Agent extension pack

Map of the Module 5 agent-extension-pack requirements to the files in
this repository. Demo walkthrough: [`_docs/demo.md`](demo.md).

| Requirement | Where |
| --- | --- |
| Project instructions | [`AGENTS.md`](../AGENTS.md) (auto-loaded), plus [`_docs/permissions.md`](permissions.md) via `instructions` in `opencode.json` |
| Reusable workflow / skill | [`.agents/skills/groom-issue/`](../.agents/skills/groom-issue/SKILL.md), [`.agents/skills/implement-issue/`](../.agents/skills/implement-issue/SKILL.md), [`.agents/skills/review-pr/`](../.agents/skills/review-pr/SKILL.md) |
| Specialized subagent | [`.opencode/agent/`](../.opencode/agent/) — `pm`, `software-engineer`, `qa-engineer`, `code-reviewer` (portable copies under `.agents/agents/`) |
| MCP tool / server | [`mcp-server/server.py`](../mcp-server/server.py), registered as `agrivanta-backlog` in `opencode.json` |
| Hook or guardrail | `permission` deny rules in `opencode.json` plus [`.opencode/plugins/guardrails.js`](../.opencode/plugins/guardrails.js) (blocks denied commands, logs every bash/edit to `.opencode/guardrails.log`) |
| Plugin or custom agent | [`custom-agent/agent.py`](../custom-agent/agent.py) — headless orchestrator for the [`_docs/process.md`](process.md) lifecycle, suitable for CI |
| Permission / security note | [`_docs/permissions.md`](permissions.md) — enforced rules, policy, and how to raise access |

All MCP tools are read-only by policy; do not add write tools to
`mcp-server/`. Guardrails and permission rules must not be weakened by
agents — see the raising-access section of the permissions note.
