# Git Commit Message Guidelines for AI Agents

## Purpose

Follow these guidelines whenever you create a Git commit in this
repository. Use **Conventional Commits** so commit history is
consistent, searchable, and suitable for automated changelogs and
release tooling.

## Required format

Use this structure:

``` text
<type>[optional scope][!]: <short description>

[optional body]

[optional footer(s)]
```

Examples:

``` text
feat(auth): add password reset flow
fix(api): handle missing customer records
docs: clarify local development setup
refactor!: remove deprecated configuration format
```

### Header rules

-   Use a valid Conventional Commit type.
-   Keep the subject concise and specific; aim for **72 characters or
    fewer** for the complete header.
-   Use the imperative mood in the description: `add`, `fix`, `remove`,
    `update`.
-   Start the description with a lowercase letter unless a proper noun
    or required spelling makes that inappropriate.
-   Do not end the description with a period.
-   Do not include vague descriptions such as `update code`,
    `fix stuff`, `changes`, or `misc`.
-   Do not add unnecessary prefixes such as `commit:`, `update:`, or a
    ticket number unless the repository explicitly requires them.
-   Do not put a period after the type or scope.

## Allowed types

Choose the type that best describes the **primary intent** of the
change.

  -----------------------------------------------------------------------
  Type                                Use it for
  ----------------------------------- -----------------------------------
  `feat`                              Add user-visible functionality or a
                                      new capability

  `fix`                               Correct a bug or unintended
                                      behavior

  `docs`                              Documentation-only changes

  `style`                             Formatting or stylistic changes
                                      that do not affect behavior, such
                                      as whitespace or semicolons

  `refactor`                          Restructure or improve code without
                                      changing its external behavior

  `perf`                              Improve performance

  `test`                              Add, update, or fix tests without
                                      changing production behavior

  `build`                             Build system, dependency, or
                                      packaging changes

  `ci`                                CI pipelines and automation
                                      configuration

  `chore`                             Routine maintenance that does not
                                      fit a more specific type

  `revert`                            Revert a previous commit
  -----------------------------------------------------------------------

Use the repository's existing conventions if it has an established, more
specific type list. Do not invent new types casually.

### Choosing between similar types

-   A new capability is `feat`, even if it requires internal code
    changes.
-   A bug fix is `fix`, even if it also includes tests.
-   A refactor is `refactor` only when behavior is intended to remain
    unchanged.
-   Use `test` when the change is exclusively about tests. If tests
    accompany a feature or fix, use `feat` or `fix`.
-   Use `docs` when the change is exclusively documentation.
-   Use `build` for dependency manifests, build scripts, bundlers, and
    packaging configuration.
-   Use `ci` for continuous-integration workflows and pipeline
    configuration.
-   Use `chore` only when no more informative type applies.
-   Use `style` only for non-functional formatting changes, not UI
    styling or behavior changes.

## Scope

A scope is optional. Use it to identify the affected area, such as a
module, feature, service, or package.

Examples:

``` text
feat(auth): add email verification
fix(api): return 404 for unknown resources
test(payments): cover declined transactions
docs(readme): explain environment variables
```

Scope rules:

-   Prefer a short, consistent name already used in the repository.
-   Use lowercase scope names unless established repository conventions
    differ.
-   Omit the scope when the change affects multiple areas or a
    meaningful scope is unclear.
-   Do not use a file path as the scope by default; use a meaningful
    component or domain.

## Body

A body is optional. Add one when the reason for the change, important
implementation details, or trade-offs are not clear from the header.

-   Separate the header from the body with a blank line.
-   Explain **why** the change was made and relevant context, not just
    repeat the header.
-   Wrap long lines where practical.
-   Use bullets for multiple distinct points when they improve
    readability.
-   Do not add a body merely to make a small commit look longer.

Example:

``` text
fix(import): preserve leading zeros in account codes

Treat account codes as strings during CSV parsing so values such as
00124 are not converted to 124.
```

## Breaking changes

Mark a breaking change with `!` immediately after the type or scope, and
explain it in the footer using `BREAKING CHANGE:`.

Example:

``` text
feat(api)!: rename the customer lookup endpoint

BREAKING CHANGE: Replace GET /customers/:id with GET /clients/:id.
Clients using the old endpoint must update their requests.
```

A breaking change must only be declared when the change is incompatible
with existing behavior, APIs, configuration, data formats, or workflows.
Do not mark a change as breaking merely because the implementation
changed.

## Footers and issue references

Use footers for issue references, attribution required by repository
policy, or other relevant metadata.

Examples:

``` text
Fixes #123
Refs #456
BREAKING CHANGE: Remove support for the legacy config file.
```

-   Use `Fixes #<number>` or the repository's supported syntax when a
    commit genuinely resolves an issue.
-   Do not invent issue numbers, links, or ticket references.
-   Include a `BREAKING CHANGE:` footer when applicable.
-   Follow repository-specific requirements for signed-off commits or
    other required trailers.

## AI agent workflow

Before committing:

1.  Inspect `git status` and identify the changes that are intended for
    this commit.
2.  Review the diff, including staged changes, to understand the actual
    behavior and scope.
3.  Check nearby commit history for repository-specific conventions when
    useful.
4.  Select the type based on the primary purpose of the change.
5.  Add a scope only when it improves clarity.
6.  Write a subject that accurately describes the change; do not claim
    work that the diff does not support.
7.  Include a body or footer only when useful or required.
8.  Ensure unrelated changes are not accidentally included.

When staging and committing:

-   Do not stage unrelated user changes.
-   Do not discard, overwrite, or amend user work unless explicitly
    authorized.
-   Do not use `git commit --amend`, force-push, or rewrite commit
    history unless explicitly instructed.
-   Do not bypass hooks or commit checks with flags such as
    `--no-verify` unless explicitly authorized.
-   If the repository requires a specific workflow, follow it.
-   If the changes contain multiple unrelated concerns, prefer separate
    commits when safe and practical. Do not split changes in a way that
    leaves the repository in a broken intermediate state.
-   If the intent is ambiguous, inspect the code and tests first. Ask
    for clarification only when the intent cannot reasonably be
    established from the repository and diff.

After committing, report the commit hash and subject, and summarize any
checks run. If a commit could not be created, explain why rather than
implying it succeeded.

## Examples

### Good

``` text
feat(search): add filters for release year
fix(auth): reject expired reset tokens
docs: document database migration steps
test(api): cover empty request payloads
refactor(cache): isolate cache key generation
perf(reports): avoid repeated aggregation queries
ci: run unit tests on pull requests
build(deps): update express to the approved version
chore: remove obsolete development script
revert: revert "feat(search): add filters for release year"
```

### Avoid

``` text
fixed bug                 # Missing Conventional Commit type
update: stuff             # Vague description
Feat(Auth): Added Login.  # Inconsistent casing, past tense, trailing punctuation
feat: changes             # Does not describe the change
fix(api): improve code    # Too vague to be useful
feat: add feature         # No meaningful detail
```

## Final checklist

Before creating a commit, verify:

-   [ ] The type accurately represents the primary intent.
-   [ ] The optional scope is meaningful and consistent.
-   [ ] The description is concise, specific, and imperative.
-   [ ] The header has no unnecessary trailing punctuation.
-   [ ] The body explains context when needed and does not repeat the
    header.
-   [ ] Breaking changes are clearly marked and documented.
-   [ ] Issue references and other metadata are real and relevant.
-   [ ] The commit includes only the intended changes.
-   [ ] No user changes were discarded or history rewritten without
    authorization.
