---
name: groom-issue
description: Use when the user asks to groom, refine, or prepare a GitHub issue before implementation - rewrites the issue into the four-section task template per the PM role.
---

# Groom an issue

You are acting as the PM. Read `_docs/team/pm.md` first and follow it.

1. Read `_docs/task-template.md`, `_docs/plan.md`, and the matching task in
   `_docs/tasks.md` when one exists. The backlog describes planned work; check
   current code and issues before assuming its dependencies are still open.
2. Read the issue: `gh issue view <N> --json title,body`. If no issue number
   was given, ask for it.
3. Rewrite the body with exactly these four sections, in order:
   `## Goal`, `## Acceptance criteria`, `## Out of scope`, `## Constraints`.
   - Every acceptance criterion is checkable by looking at the result or
     running a command - one line per case, including the awkward ones
     (missing input, duplicates, permission denied, empty data, boundaries).
   - Out-of-scope items link to real issue numbers only. If scope is moved
     out of the task, file a follow-up issue and link it; do not silently
     drop anything.
   - Constraints name the stack, directories, libraries, the tests that must
     pass, `_docs/branching-strategy.md`, and `_docs/commit-message-guidelines.md`.
4. Write the body to a temp file, then `gh issue edit <N> --body-file <file>`.
5. Re-read the issue and confirm all four sections are present.

Rules: never write code, never change the title, labels, or state, and never
invent issue numbers.
