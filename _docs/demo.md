# Demo

Six-step walkthrough of the agent extension pack. Run from the repo
root; requirement mapping is in
[`_docs/agent-extension-pack.md`](agent-extension-pack.md).

1. **The agent reads the project instructions.** Start `opencode`.
   `AGENTS.md` and `_docs/permissions.md` load automatically. Ask
   "what are the rules for committing here?" — the answer comes from
   the loaded instructions, not a guess.

2. **A reusable workflow is invoked.** Say "groom issue #N". The
   `groom-issue` skill loads and rewrites the issue into the
   four-section template using the PM role.

3. **A specialized subagent reviews an API change.** Say "review PR
   #N". The `review-pr` skill launches the read-only `code-reviewer`
   subagent on the diff; its frontmatter denies edits, so it can only
   report BLOCKING / NON-BLOCKING findings.

4. **The agent calls an MCP tool.** Ask "what is still open in the
   backlog?". The agent calls `agrivanta-backlog` tools
   (`list_backlog_tasks`, `get_backlog_task`, `list_open_issues`)
   instead of guessing from memory. Verify with `opencode mcp list` —
   the server shows as connected.

5. **A guardrail blocks an unsafe action.** Ask the agent to run
   `git push --force`. The `opencode.json` permission rule denies it
   and the guardrails plugin throws; `.opencode/guardrails.log` records
   the attempt alongside every bash command and file edit from the
   session (the log is gitignored).

6. **Review the final diff.** `git diff` or the open PR shows exactly
   what changed; the audit log shows what was run to get there.

## Headless variant

`uv run custom-agent/agent.py --issue N --dry-run` prints the full
PM → engineer → QA lifecycle for one issue without running agents;
drop `--dry-run` to execute it (requires `opencode` and `gh`
authenticated). Each role runs in a fresh session, and the issue is
closed only after a QA PASS.
