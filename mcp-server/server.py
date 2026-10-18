"""Read-only MCP server exposing the Agrivanta backlog and GitHub issues.

Tools are deliberately read-only (see _docs/permissions.md): they parse
_docs/tasks.md and list issues via the gh CLI. No tool writes anything.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from mcp.server.mcpserver import MCPServer

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO_ROOT / "_docs" / "tasks.md"

PHASE_HEADER = re.compile(r"^## (Phase .+)$")
TASK_HEADER = re.compile(r"^## (\d+)\. (.+)$")

mcp = MCPServer("agrivanta-backlog")


def parse_backlog() -> list[dict]:
    tasks: list[dict] = []
    phase: str | None = None
    current: dict | None = None
    for line in TASKS_FILE.read_text(encoding="utf-8").splitlines():
        if match := PHASE_HEADER.match(line):
            phase = match.group(1).strip()
            current = None
        elif match := TASK_HEADER.match(line):
            current = {
                "number": int(match.group(1)),
                "title": match.group(2).strip(),
                "phase": phase,
                "goal": "",
                "description": "",
            }
            tasks.append(current)
        elif current is not None and line.startswith("Goal:"):
            current["goal"] = line.removeprefix("Goal:").strip()
        elif current is not None and line.startswith("Description:"):
            current["description"] = line.removeprefix("Description:").strip()
    return tasks


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


@mcp.tool()
def list_backlog_tasks(phase: str | None = None) -> str:
    """List backlog tasks from _docs/tasks.md as JSON (number, title, phase,
    goal). Optionally filter by a phase substring, e.g. "Phase 3"."""
    tasks = parse_backlog()
    if phase:
        tasks = [t for t in tasks if phase.lower() in (t["phase"] or "").lower()]
    summary = [{"number": t["number"], "title": t["title"], "phase": t["phase"], "goal": t["goal"]} for t in tasks]
    return json.dumps({"count": len(summary), "tasks": summary}, indent=2)


@mcp.tool()
def get_backlog_task(number: int) -> str:
    """Return the full backlog entry (phase, title, goal, description) for a
    single task number from _docs/tasks.md."""
    for task in parse_backlog():
        if task["number"] == number:
            return json.dumps(task, indent=2)
    return json.dumps({"error": f"no backlog task {number} found in _docs/tasks.md"})


@mcp.tool()
def list_open_issues() -> str:
    """List open GitHub issues for this repository as JSON (number, title,
    labels) using the gh CLI. Read-only."""
    try:
        raw = run(["gh", "issue", "list", "--state", "open", "--json", "number,title,labels"])
    except (FileNotFoundError, RuntimeError) as exc:
        return json.dumps({"error": f"gh CLI unavailable: {exc}"})
    issues = json.loads(raw or "[]")
    return json.dumps({"count": len(issues), "issues": issues}, indent=2)


if __name__ == "__main__":
    mcp.run()
