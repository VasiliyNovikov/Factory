# Repository guidance

## Working style

- Make small, focused changes with clear names and structure. Avoid unrelated
  edits, duplication, and needless abstractions.
- Keep tightly coupled work together. Split code, docs, workflows, or tasks only
  when it improves understanding, review, or independent delivery.
- Give issues and PRs a bounded scope, verifiable acceptance criteria, and explicit
  dependencies. Use native sub-issues for independent work; the parent tracks the
  outcome instead of duplicating child work in a PR.
- Keep decisions in the component that owns them. Reuse existing logic and
  contracts rather than spreading implementation details across boundaries.
- Prefer existing tools and native GitHub features. Add scripts or orchestration
  only for a concrete need or a clear reduction in complexity.

## AI-led work

- State goals, when to act or skip, constraints, and verifiable outcomes. Let
  capable models choose how to meet them with the available tools and context.
- A clear request may already be enough. Do not turn a short prompt into a large
  spec; add only missing context or decisions needed to act and verify the result.
- Keep detailed requirements in the owning guidance document. Prompts should
  link to it and supply only the task and run-specific context.
- Prescribe procedures only for a required contract, safety boundary, or known
  failure. Remove unnecessary mechanisms, not just rename them.
- Design for capable models and future improvements, without weakening
  permissions, safety checks, or result verification.

## Writing docs and comments

- Use concise, plain language in docs, issue/PR bodies, comments, and reviews.
  Keep documentation aligned with the code and workflows.
- Lead with the outcome or request. Include only useful scope, evidence,
  decisions, blockers, or next steps; avoid repeated context and process narration.
- Be brief by default, but retain required links, markers, checked revisions,
  verification results, and failure details. Concision must not hide uncertainty.
- Use descriptive headings and focused bullets when they help scanning. Group
  related conditions under a shared bullet; do not force short replies into a
  template or expand an already-clear request.
- Link to the owning guidance instead of repeating it.

## Repository map

This is an agentic software factory scaffold, with no application code or
toolchain yet. [README.md](README.md) tracks completed CI milestones. There are no
configured build/test/lint commands; automated workflow tests are deferred.

Use the owning guide for each workflow's behavior, permissions, and verification:

| Area | Guidance |
|---|---|
| App identities and credentials | [GitHub App setup](docs/factory/github-app.md) |
| Event routing and dispatch | [Factory router](docs/factory/factory-router.md) |
| PR assessments | [PR review](docs/factory/pr-review.md) |
| Readiness and label handoff | [Issue triage](docs/factory/issue-triage.md) |
| Code, feedback, base merges, and sub-issues | [Issue implementation](docs/factory/issue-implementation.md) |
| Run-history analysis | [Workflow diagnostics](docs/factory/workflow-diagnostics.md) |
| Full source analysis | [Repository review](docs/factory/repository-review.md) |

Factory checkouts use `github.workflow_sha`; manual jobs skip non-default refs.
Submitted reviews are the router exception: they run PR-merge-revision code before
merge, with the [documented risk](docs/factory/factory-router.md#accepted-risk-router-changes-can-run-before-merge).

Workflows share [`.github/actions/ai`](docs/examples/ai-tools.md#shared-factory-action)
for installation and invocation. Checkout, credentials, Git identity, prompts,
and receipt checks stay in callers.

[AI setup](docs/examples/ai-tools.md), [PR creation](docs/examples/create-pull-request.md),
and [issue creation](docs/examples/create-issue.md) are reusable documentation
snippets, not installed workflows.

## Test value and verification

- Before adding or requesting a test, name the requirement or credible regression,
  its observable outcome, and the gap in existing coverage. Use the smallest
  useful check with existing tools, not tests or dependencies for their own sake.
- Test behavior or required contracts, not incidental wording, copied logic, or
  mock setup. Tests should catch the regression and survive harmless refactoring.
- Use static checks when the representation is the contract, such as a schema,
  protocol token, or permission. Mocked tests should exercise production logic
  and check outputs, side effects, or rejected operations.
- Preserve required checks and useful regression/safety coverage. Guidance-only
  changes may use direct inspection instead of wording-test suites.
- Missing-test findings must name the uncovered risk, observable behavior, and
  coverage gap.
- State what verification proves and its limits. Source assertions and mocks
  do not prove AI adherence or live end-to-end GitHub behavior.
