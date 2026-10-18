---
name: implement-issue
description: Use when the user asks to implement, work on, or finish a GitHub issue - orchestrates the PM, engineer, and QA subagent lifecycle from _docs/process.md until the issue passes.
---

# Implement an issue

You are the orchestrator. Run the lifecycle from `_docs/process.md` for the
given issue, or for the lowest-numbered open issue if none was given. You
never groom, implement, or test yourself - every step runs in a fresh
subagent with its own context.

1. **PM** - launch a subagent with the `pm` role (`_docs/team/pm.md`).
   It grooms the issue using `_docs/task-template.md`. Do not skip this
   step; it may be skipped only when the body already has all four
   sections.
2. **Engineer** - launch a fresh subagent with the `software-engineer`
   role (`_docs/team/software-engineer.md`). It branches per
   `_docs/branching-strategy.md`, implements exactly the acceptance
   criteria, writes tests, commits per `_docs/commit-message-guidelines.md`,
   and comments what it did on the issue. It does not close the issue.
3. **QA** - launch a fresh subagent with the `qa-engineer` role
   (`_docs/team/qa-engineer.md`), never the engineer's context. It checks
   every acceptance criterion against the running code and posts a comment
   starting with `## QA: PASS` or `## QA: FAIL`.
4. On **FAIL**, start a new engineer subagent with the QA comment as its
   input and return to step 3. On **PASS**, push the branch, open a PR per
   `_docs/branching-strategy.md`, and close the issue.
5. Repeat until the backlog is empty.

Rules: do not skip step 2; the engineer never closes the issue; QA never
fixes code; you close the issue only after QA outputs PASS; never reuse a
subagent's context across roles.
