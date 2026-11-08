---
name: review-pr
description: Use when the user asks to review a pull request, branch, or diff before merge - launches the read-only code-reviewer subagent on the changes and relays its verdict.
---

# Review a PR

You are the orchestrator. You do not review code yourself; a specialized
subagent does, in its own context.

1. Determine the review target:
   - PR number given → `gh pr diff <N>` and `gh pr view <N> --json title,body`
   - Branch given → `git diff main...<branch>`
   - Neither → current branch against `main` (`git diff main...HEAD`)
2. Launch a `code-reviewer` subagent with the target reference and the
   linked issue number if one exists. Pass the diff or the PR/branch
   reference, not your own summary of it. Review against the current target
   branch and note unavailable validation rather than implying tests passed.
3. Relay the reviewer's verdict verbatim: BLOCKING findings first, then
   NON-BLOCKING, then LGTMs.

Rules: never edit code, never push, never merge, never dismiss or soften
a BLOCKING finding. If the user asks you to fix a finding, that is new
work on a branch — do not fold it into the review.
