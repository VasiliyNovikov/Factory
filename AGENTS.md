# Repository guidance

- Prefer small, focused changes without sacrificing correctness, quality,
  clarity, or maintainability. Avoid unrelated changes.
- Keep code understandable and maintainable by humans and AI: use clear
  structure and naming, avoid unnecessary duplication, and reuse existing logic
  where appropriate without needless abstraction.
- Decompose code, documentation, workflows, issues, and PRs into cohesive,
  manageable units with clear responsibilities. Split work when it improves
  understanding, review, or independent delivery, not merely to make more pieces.
  Keep tightly coupled changes together and avoid fragmentation or duplicated logic.
- Give each issue and PR a bounded scope and verifiable acceptance criteria.
  Make dependencies and shared context explicit; use native sub-issues for
  independently actionable parts of a larger request. A decomposed parent tracks
  the whole outcome rather than receiving its own implementation handoff.
- Prefer AI-led task handling with simple prompts and existing tools over
  unnecessary custom workflow scripts or scripted decision logic. Keep automation
  simple and flexible; use scripts when critical performance needs or lower
  overall complexity justify them.
- Design for capable, current AI models and continued improvement rather than
  incidental limitations of today's models. This preference does not relax
  required permissions, safety boundaries, or result verification.
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
- No application toolchain or dependency manifest is configured.
- Workflow regression checks: `python3 -B -m unittest discover -s tests -v`
  (Python standard library, Bash, and `jq`; no live GitHub mutations).
  `.github/workflows/workflow-checks.yml` runs them on PRs and pushes to `master`.
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  Copilot PR-creation test. See the linked examples for setup, permissions,
  invocation, and result verification.
- `.github/workflows/pr-review.yml` reviews non-draft, same-repository PRs on
  PR events and verifies that Copilot posted a review. See the PR-review example
  for triggering and bot-approval constraints.
- `.github/workflows/issue-triage.yml` assesses untriaged issues and clarification
  comments, then either hands off ready work with its own tracking label and
  `triaged`, or protects a `decomposed` parent and creates native sub-issues for
  normal child triage. See its example for partial-attempt recovery.
- `.github/workflows/issue-implementation.yml` implements triaged issues and feedback on
  their Factory PRs using the Factory App. See its example for permissions,
  shared-label concurrency, PR tracking, and result checks.
