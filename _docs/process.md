# Issue lifecycle and orchestration

- GitHub issues are the units of work. Each issue has its own branch and
  isolated git worktree.
- Read and preserve the acceptance criteria before implementation and before
  QA.
- Commit regularly using the repository's commit-message guidelines.

## Roles

- PM - grooms a task before anyone implements it, follows _docs/team/pm.md
- Engineer - implements one groomed task, follows _docs/team/software-engineer.md
- QA - checks the result against the acceptance criteria, follows _docs/team/qa-engineer.md

The orchestrator may run up to five independent issue tracks in parallel.
Each track must have its own worktree, branch, issue scope, and clear file
ownership. Do not run dependent issues concurrently; start them when their
prerequisites are integrated or otherwise available in the track's base.

The orchestrator coordinates work and does not groom, implement, or test
issues itself. Its job is to:

- Select eligible open issues and identify their dependencies.
- Assign each issue track a separate worktree and unambiguous file ownership.
- Keep available agent slots occupied while eligible independent work remains.
- Use a fresh QA agent for each implementation and a fresh reviewer for each
  completed change.
- Send QA or review findings back to the engineer responsible for that issue.
- Integrate changes through pull requests in dependency order.

## Lifecycle

1. Select an open issue whose prerequisites are available.
2. PM grooms it using `_docs/task-template.md`. Skip grooming only when the
   issue already has all four required sections.
3. Engineer implements the acceptance criteria in the issue's worktree,
   writes tests, commits the change, and comments on the issue. The engineer
   does not close the issue.
4. A fresh QA agent checks the running code against every acceptance
   criterion, runs the relevant tests, and comments `## QA: PASS` or
   `## QA: FAIL`. QA does not modify code.
5. On FAIL, a fresh engineer session addresses the QA findings; repeat QA
   until the result is PASS or the work is blocked.
6. On PASS, the orchestrator pushes the branch and opens a pull request.
7. Send the pull request to a fresh reviewer. Resolve blocking findings with
   the engineer and repeat QA when a change affects acceptance criteria.
8. After QA PASS and resolution of blocking review findings, the orchestrator
   closes the issue. Merge the pull request only when authorized by the user
   and permitted by repository policy.
9. Continue with eligible issues until the requested scope is complete.

## Rules

- Do not skip grooming unless the issue already has the required template.
- The engineer does not close the issue.
- QA does not fix the code; QA reports PASS or FAIL.
- The orchestrator closes the issue only after QA outputs PASS.
- Never use the same subagent context for PM, engineer, QA, or review roles.
- The headless `custom-agent/` runner processes issues sequentially; use
  separate worktrees and the orchestrated workflow for parallel tracks. The
  runner does not perform the independent PR review stage.
