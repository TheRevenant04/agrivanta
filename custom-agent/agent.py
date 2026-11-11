#!/usr/bin/env python3
"""Headless orchestrator for the Agrivanta issue lifecycle.

Implements _docs/process.md without an interactive session: the PM
grooms, the engineer implements, QA verifies, and the orchestrator opens
the PR and closes the issue only after QA outputs PASS. Each role runs
in a fresh `opencode run` session, so no context is ever shared across
roles.

Usage:
    uv run custom-agent/agent.py              # work the whole backlog
    uv run custom-agent/agent.py --issue 12   # work one issue
    uv run custom-agent/agent.py --issue 12 --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QA_PASS = "## QA: PASS"
QA_FAIL = "## QA: FAIL"
GROOMED_SECTIONS = ("## Goal", "## Acceptance criteria", "## Out of scope", "## Constraints")


def run(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({result.returncode}):\n{result.stderr.strip()}")
    return result.stdout.strip()


def opencode_run(agent: str, prompt: str, *, dry_run: bool) -> str:
    if dry_run:
        print(f"[dry-run] {agent}: {prompt.splitlines()[0][:100]}")
        return ""
    return run(["opencode", "run", "--agent", agent, "--auto", prompt])


def open_issue_numbers() -> list[int]:
    raw = run(["gh", "issue", "list", "--state", "open", "--json", "number"])
    return sorted(item["number"] for item in json.loads(raw or "[]"))


def issue_view(number: int, *fields: str) -> dict:
    raw = run(["gh", "issue", "view", str(number), "--json", ",".join(fields)])
    return json.loads(raw)


def is_groomed(body: str) -> bool:
    return all(section in body for section in GROOMED_SECTIONS)


def last_qa_comment(number: int) -> str:
    comments = issue_view(number, "comments").get("comments", [])
    for comment in reversed(comments):
        if comment.get("body", "").startswith("## QA:"):
            return comment["body"]
    return ""


def qa_passed(output: str) -> bool:
    return QA_PASS in output and QA_FAIL not in output


def process_issue(number: int, *, max_attempts: int, dry_run: bool) -> bool:
    print(f"== Issue #{number} ==")
    title = issue_view(number, "title").get("title", "") if not dry_run else ""
    body = issue_view(number, "body").get("body", "") if not dry_run else ""

    if dry_run or not is_groomed(body):
        print("PM: grooming")
        opencode_run("pm", f"Groom issue #{number} into the four-section task template.", dry_run=dry_run)
    else:
        print("PM: already groomed, skipping")

    verdict_output = ""
    review_output = ""
    for attempt in range(1, max_attempts + 1):
        print(f"Engineer: attempt {attempt}")
        engineer_prompt = f"Implement issue #{number}. Work only on that issue."
        if attempt > 1:
            qa_comment = last_qa_comment(number) if not dry_run else verdict_output
            feedback = []
            if qa_comment:
                feedback.append(f"QA verdict:\n{qa_comment}")
            if review_output and "BLOCKING" in review_output:
                feedback.append(f"Code Reviewer blocking findings:\n{review_output}")
            if feedback:
                engineer_prompt += f"\n\nPrevious attempt failed. Address the following feedback:\n" + "\n\n".join(feedback)
        opencode_run("software-engineer", engineer_prompt, dry_run=dry_run)

        print("Code Reviewer: reviewing")
        review_output = opencode_run(
            "code-reviewer",
            f"Review the current branch changes for issue #{number} against plan, security, and branching strategy.",
            dry_run=dry_run,
        )
        if not dry_run and "BLOCKING" in review_output:
            print("Code Reviewer: BLOCKING findings found, sending back to engineer")
            continue

        print("QA: verifying")
        verdict_output = opencode_run(
            "qa-engineer",
            f"Verify issue #{number} against its acceptance criteria and post the verdict comment.",
            dry_run=dry_run,
        )
        if dry_run or qa_passed(verdict_output):
            print("QA: PASS")
            break
        print("QA: FAIL, sending back to the engineer")
    else:
        print(f"Issue #{number}: FAILED after {max_attempts} attempts")
        return False

    if dry_run:
        return True

    branch = run(["git", "branch", "--show-current"])
    run(["git", "push", "--set-upstream", "origin", branch])
    run(["gh", "pr", "create", "--title", title, "--body", f"Closes #{number}"])
    run(["gh", "issue", "close", str(number)])
    print(f"Issue #{number}: PR opened from '{branch}' and issue closed")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless PM/engineer/QA lifecycle for one issue or the backlog.")
    parser.add_argument("--issue", type=int, help="work a single issue instead of the whole backlog")
    parser.add_argument("--max-attempts", type=int, default=3, help="engineer retries after QA FAIL (default 3)")
    parser.add_argument("--dry-run", action="store_true", help="print each step without running agents (requires --issue)")
    args = parser.parse_args()

    if args.dry_run and not args.issue:
        parser.error("--dry-run requires --issue N")

    issues = [args.issue] if args.issue else open_issue_numbers()
    if not issues:
        print("Backlog is empty.")
        return 0

    failures = [n for n in issues if not process_issue(n, max_attempts=args.max_attempts, dry_run=args.dry_run)]
    if failures:
        print(f"Failed issues: {', '.join(f'#{n}' for n in failures)}")
        return 1
    print("All issues processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
