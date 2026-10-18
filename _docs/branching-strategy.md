# Branching Strategy for AI Agents

## Purpose

This repository uses **feature branching**. Keep `main` stable, make
changes on short-lived branches, and integrate changes through pull
requests or the repository's explicitly approved review process.

These rules apply whenever an AI agent creates, switches, updates, or
merges Git branches.

## Branch types and naming

Use lowercase names with hyphens. Prefix a branch with the kind of work:

  ----------------------------------------------------------------------------------------
  Prefix                  Purpose                 Example
  ----------------------- ----------------------- ----------------------------------------
  `feature/`              New functionality or    `feature/crop-profitability-dashboard`
                          capability              

  `fix/`                  A non-urgent bug fix    `fix/cost-rounding`

  `hotfix/`               An urgent production    `hotfix/login-failure`
                          fix                     

  `docs/`                 Documentation-only work `docs/api-setup-guide`

  `refactor/`             Internal restructuring  `refactor/reporting-service`
                          without intended        
                          behavior changes        

  `test/`                 Test-only changes       `test/profit-calculation-cases`

  `ci/`                   CI pipeline or          `ci/test-workflow`
                          automation changes      

  `build/`                Build, dependency, or   `build/update-vite`
                          packaging changes       

  `chore/`                Maintenance that does   `chore/remove-unused-script`
                          not fit a more specific 
                          category                
  ----------------------------------------------------------------------------------------

Choose the prefix that best describes the branch's primary purpose. Use
a short, descriptive name that explains the task. Avoid names such as
`feature/new`, `fix/bug`, `test/changes`, personal names, and dates
unless the repository has a documented requirement for them.

Branch prefixes and Conventional Commit types are related but
independent: a branch name does not replace a correctly formatted commit
message.

## Branch model

### `main`

-   `main` is the stable integration branch and should remain in a
    working, releasable state.
-   Do not commit directly to `main`.
-   Do not push directly to `main` unless an explicitly approved
    repository workflow requires it.
-   Merge changes into `main` through a pull request or an explicitly
    authorized equivalent.
-   Keep `main` protected on the hosting platform when that feature is
    available.
-   Require appropriate checks and review before merging when supported
    by the repository's policies.

### Short-lived work branches

-   Create one branch per coherent feature, fix, or task.
-   Create new feature and fix branches from the latest appropriate
    `main` unless the user or repository workflow specifies another
    base.
-   Keep branches focused. Do not mix unrelated work in one branch.
-   Avoid permanent `develop`, `release`, or `staging` branches unless
    the repository's release or deployment process requires them.
-   Delete merged branches when safe and permitted by repository policy.

## Agent workflow

### 1. Inspect the repository first

Before changing branches or creating a branch:

1.  Run `git status --short --branch`.
2.  Identify the current branch and any staged, unstaged, or untracked
    changes.
3.  Inspect recent commit and branch conventions when useful.
4.  Read repository instructions such as `AGENTS.md` and any applicable
    contribution guide.

Never assume the working tree is clean.

### 2. Preserve existing work

-   Never discard, overwrite, reset, or clean away user changes.
-   Do not switch branches if doing so could lose or contaminate
    uncommitted work.
-   If unrelated changes are present, leave them untouched. Ask the user
    how to proceed if the task cannot be isolated safely.
-   Do not use destructive commands such as `git reset --hard`,
    `git clean -fd`, or force checkout to make branch creation easier
    unless explicitly authorized.
-   Do not stash, commit, or move existing user changes without
    authorization when their ownership or intent is unclear.

### 3. Create the branch

-   For a new task, create a short-lived branch from the latest
    appropriate base branch.
-   Fetch remote updates when appropriate and when network access is
    available; do not overwrite local work.
-   Check whether the proposed branch name already exists locally or
    remotely.
-   If the name is already in use, inspect the branch and choose a
    distinct name or ask the user. Do not repurpose another task's
    branch without permission.
-   Use a command such as:

``` bash
git switch main
git pull --ff-only
git switch -c feature/short-description
```

Run these commands only after confirming that switching to `main` is
safe and does not disturb existing work. If local changes or branch
divergence make this unsafe, preserve the current state and ask for
guidance.

For a non-feature task, substitute the appropriate prefix, such as
`fix/`, `docs/`, or `refactor/`.

### 4. Work and commit

-   Keep changes limited to the task's scope.
-   Run relevant tests, linting, type checks, and build checks as
    available.
-   Commit using the repository's Conventional Commits guidelines in
    `docs/commit-message-guidelines.md`, if present.
-   Make commits coherent and small enough to review.
-   Never amend commits, rewrite published history, force-push, or
    bypass hooks unless explicitly authorized.

### 5. Keep the branch current

-   If `main` advances, update the work branch only when useful and
    safe.
-   Prefer the repository's established merge or rebase policy.
-   If no policy exists, use a safe merge from `main` to avoid rewriting
    branch history, especially when a branch is shared or published.
-   Do not force-push to resolve divergence.
-   Resolve conflicts carefully, preserving valid intent from both
    sides. Do not guess when a conflict changes product behavior or
    requirements; ask the user.
-   Re-run relevant checks after integrating upstream changes.

### 6. Open a pull request

Before requesting integration:

-   Ensure the branch contains only changes related to its task.
-   Verify tests and checks, and report any that could not be run.
-   Review the complete diff against the target branch.
-   Confirm the commit messages follow Conventional Commits.
-   Write a pull request title that clearly describes the change; follow
    Conventional Commits for the title if that matches the repository's
    policy.
-   Summarize the problem, solution, tests, and any migration or
    configuration impact.
-   Link an issue only if a real issue reference is available.
-   Do not merge the pull request unless the user has authorized merging
    and repository policy permits it.

### 7. Finish and clean up

After merge:

-   Confirm that the intended change was merged into the correct target
    branch.
-   Delete the local or remote work branch only when it is merged, no
    longer needed, and deletion is permitted.
-   Never delete a branch with unmerged work without explicit
    authorization.
-   Report the branch name, commits made, checks run, and pull request
    or merge status when applicable.

If the user asks only for implementation and has not authorized a push,
pull request, or merge, do not assume that those remote actions are
approved.

## Hotfixes

Use `hotfix/` only for urgent production issues.

-   Start from the production branch, normally `main`, unless the
    repository's release model specifies another production branch.
-   Make the smallest safe fix and add regression coverage where
    practical.
-   Run relevant checks and seek the required review.
-   Merge through the normal approved process.
-   If the repository maintains supported release branches, ensure the
    fix is also applied to the appropriate branches. Do not invent a
    release process when none exists.

## Do not use by default

This repository does not use Gitflow by default. Unless explicitly
required, do not create permanent branches such as:

-   `develop`
-   `release/*`
-   `staging`
-   `integration`

Environment deployment should normally be managed by CI/CD configuration
and deployment targets, not by creating a permanent branch for each
environment.

## Final checklist

Before finishing branch work, verify:

-   [ ] The branch name uses the correct prefix and a descriptive
    lowercase hyphenated name.
-   [ ] The branch was based on the correct target branch.
-   [ ] Existing user changes were preserved.
-   [ ] The branch contains only task-related changes.
-   [ ] Commits follow the repository's Conventional Commits rules.
-   [ ] Relevant checks were run, with failures or omissions reported
    honestly.
-   [ ] No unauthorized history rewriting, force-pushing, merging, or
    deletion occurred.
-   [ ] The final report accurately states the branch, commits, checks,
    and integration status.
