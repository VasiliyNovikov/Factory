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
  the whole outcome rather than duplicating child-owned work in a parent PR.
- Prefer AI-led task handling with concise prompts, existing tools, native GitHub
  features, and minimal workflow glue over custom scripted decision systems.
  Add scripts or orchestration only for a concrete requirement or a demonstrated
  reduction in overall complexity.
- In AI prompts and guidance, state **what** is required: goals, when to act or
  skip, constraints, and verifiable outcomes. Let capable models determine
  **how** using available tools and context. Keep instructions concise; prescribe
  procedures only where a required contract, safety boundary, or demonstrated
  failure makes them necessary. Avoid duplicating implementation details in docs.
- Make guidance easy to scan: group related rules under descriptive headers and
  use focused bullets, with one independently actionable rule or condition per
  bullet. Split dense paragraphs and multi-rule bullets; keep closely related
  qualifications together without adding repetition.
- Prefer nested bullets for sets of required inputs, conditions, or outcomes
  under a shared rule rather than dense inline lists. Keep short, simple lists
  inline when splitting would not improve scanning.
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
  scripts, and workflows it describes.
- Reusable CI examples live in `docs/examples/`:
  - [AI tool setup and invocation](docs/examples/ai-tools.md)
  - [PR creation](docs/examples/create-pull-request.md)
  - [Issue creation](docs/examples/create-issue.md)
- Factory workflow guidance and shared App setup live in `docs/factory/`:
  - [Factory GitHub App setup](docs/factory/github-app.md)
  - [Central event routing and dispatch](docs/factory/factory-router.md)
  - [PR review](docs/factory/pr-review.md)
  - [Issue triage and label handoff](docs/factory/issue-triage.md)
  - [Issue implementation and follow-ups](docs/factory/issue-implementation.md)
  - [Periodic workflow diagnostics](docs/factory/workflow-diagnostics.md)
- No application toolchain, dependency manifest, or build/test/lint commands are
  configured. Automated workflow tests are deferred for now.
- AI setup and issue/PR-creation examples are documentation snippets, not installed
  workflows. See those examples for setup, permissions, invocation, and result
  verification.
- `.github/workflows/factory-router.yml` analyzes issue, comment, PR-target, submitted-review,
  workflow-completion, and default-branch push events with Copilot. Pushes dispatch
  one default-branch maintenance worker per eligible Factory PR; other events
  dispatch at most one worker. Router jobs run independently; worker AI owns
  freshness checks and result verification. `docs/factory/factory-router.md` defines dispatch inputs.
- Submitted reviews directly run the router from the PR merge revision. Router
  and setup changes can execute before merge with the router's token permissions;
  this accepted risk and dispatch compatibility requirements are documented in
  `docs/factory/factory-router.md`. Other router triggers use the default branch.
- Review, triage, and implementation are dispatch-only workers. Factory setup
  checkouts use `github.workflow_sha`; manual jobs skip non-default refs.
- `.github/workflows/pr-review.yml` reviews non-draft, same-repository PRs and
  verifies that Copilot posted a review unless AI skipped a stale/handled task. See the PR-review guidance
  for triggering and bot-approval constraints.
- `.github/workflows/issue-triage.yml` assesses assigned untriaged issues and clarification
  comments, suggests decomposition when useful, and applies a unique tracking
  label followed by `triaged` when ready. It does not create issues or PRs.
- `.github/workflows/issue-implementation.yml` implements triaged issues and feedback on
  their Factory PRs, including default-branch merges and conflict resolution, or
  creates native sub-issues for independent delivery using the Factory App. Maintenance handles
  only the assigned PR. Its short invocation follows `docs/factory/issue-implementation.md`;
  Copilot owns decomposition, recovery, freshness, and result verification.
  Unlike triage and review, implementation intentionally has no deterministic receipt check.
  See that guidance for permissions, per-issue concurrency, and PR tracking.
- `.github/workflows/workflow-diagnostics.yml` analyzes repository workflow runs
  daily or manually with parallel Copilot subagents and creates findings issues
  for normal triage. Copilot selects same-repository runs, verifies its actions,
  and records results in the job summary. Its first invocation establishes a
  boundary without analysis. Diagnostics verification is AI-owned; no separate
  report/receipt-check job is required.

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
