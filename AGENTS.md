# Repository guidance

- Prefer small, focused changes without sacrificing correctness, quality,
  clarity, or maintainability. Avoid unrelated changes.
- Keep code understandable and maintainable by humans and AI: use clear
  structure and naming, avoid unnecessary duplication, and reuse existing logic
  where appropriate without needless abstraction.
- This is an initial scaffold for an agentic software factory experiment.
  `README.md` tracks completed CI access milestones. No application code is
  implemented yet.
- Keep documentation concise, maintainable, and synchronized with the code,
  scripts, and workflows it describes. CI examples live in `docs/`:
  - [AI tool setup and invocation](docs/ai-tools.md)
  - [Factory GitHub App setup](docs/github-app.md)
  - [PR creation](docs/create-pull-request.md)
  - [Issue creation](docs/create-issue.md)
  - [PR review](docs/pr-review.md)
  - [Issue triage and label handoff](docs/issue-triage.md)
  - [Issue implementation and follow-ups](docs/issue-implementation.md)
  - [Periodic workflow diagnostics](docs/workflow-diagnostics.md)
- No application toolchain, dependency manifest, or build/test/lint commands are
  configured. Automated workflow tests are deferred for now.
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  Copilot PR-creation test. See the linked examples for setup, permissions,
  invocation, and result verification.
- `.github/workflows/pr-review.yml` reviews non-draft, same-repository PRs on
  PR events and verifies that Copilot posted a review. See the PR-review example
  for triggering and bot-approval constraints.
- `.github/workflows/issue-triage.yml` assesses untriaged issues and clarification
  comments, then applies a unique tracking label followed by `triaged` when ready.
- `.github/workflows/issue-implementation.yml` implements triaged issues and feedback on
  their Factory PRs using the Factory App. See its example for permissions,
  shared-label concurrency, PR tracking, and result checks.
- `.github/workflows/workflow-diagnostics.yml` analyzes repository workflow runs
  daily or manually with parallel Copilot subagents and creates findings issues
  for normal triage. Copilot selects the window and records a report; a small
  read-only job checks report status and issue receipts. Its first invocation
  establishes a boundary without analysis.
