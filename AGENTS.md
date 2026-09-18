# Repository guidance

- Prefer small, focused changes without sacrificing correctness, quality,
  clarity, or maintainability. Avoid unrelated changes.
- Keep code understandable and maintainable by humans and AI: use clear
  structure and naming, avoid unnecessary duplication, and reuse existing logic
  where appropriate without needless abstraction.
- Prefer AI-led task handling with concise prompts, existing tools, native GitHub
  features, and minimal workflow glue over custom scripted decision systems.
  Add scripts or orchestration only for a concrete requirement or a demonstrated
  reduction in overall complexity.
- Apply separation of concerns and information hiding: keep decisions in the
  component or stage that owns them and reuse existing contracts. Do not expose
  internal details or spread local changes across boundaries without a concrete
  need.
- Apply KISS (keep it simple) and YAGNI (you aren't gonna need it): avoid
  speculative machinery. During implementation and review, remove unnecessary
  mechanisms rather than merely renaming concepts, while preserving required
  safety checks and verification.
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
- No application toolchain or dependency manifest is configured. Focused workflow
  checks use `python -m unittest discover -s tests -v` with Python's standard
  library, Bash, and `jq`; see the PR-review example for their scope and limits.
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  Copilot PR-creation test. See the linked examples for setup, permissions,
  invocation, and result verification.
- `.github/workflows/pr-review.yml` reviews open, non-draft, same-repository PRs on
  commit, description-edit, and Factory review-request label events, then verifies
  the posted review. See the PR-review example for triggering and bot-approval
  constraints.
- `.github/workflows/issue-triage.yml` assesses untriaged issues and clarification
  comments, then applies a unique tracking label followed by `triaged` when ready.
- `.github/workflows/issue-implementation.yml` implements triaged issues and feedback on
  their Factory PRs using the Factory App. See its example for permissions,
  shared-label concurrency, PR tracking, and result checks.

## Test value and verification

- Before adding or requesting a test, identify the requirement or credible
  regression it protects, the observable outcome, and why existing coverage is
  insufficient. Prefer the smallest useful check with existing tools; do not add
  tests, harnesses, or dependencies merely because files changed or to meet a
  test-count expectation.
- Test behavior or a required contract, not a copy of the implementation,
  incidental source/prompt/documentation wording, or the mock setup itself.
  Behavior tests should fail for the targeted regression and survive harmless
  refactoring or equivalent prose.
- Static/contract checks are useful when the checked representation is itself a
  requirement, such as a schema, protocol token, or workflow permission.
  Focused mocked tests should exercise real production logic and check relevant
  outputs, side effects, or rejected operations, rather than only replay fixtures.
- Preserve necessary regression and safety coverage and all required checks.
  Guidance-only changes may use direct inspection instead of a new suite of
  wording assertions; this is not permission to skip meaningful verification.
- In review, missing-test findings must name a concrete uncovered risk, the
  observable behavior to check, and why existing coverage is insufficient.
- Report what checks actually establish and their limits. Source-text assertions
  and mocked tests do not prove AI adherence or live end-to-end GitHub behavior.
