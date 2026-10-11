# Repository guidance

## Working style

- Prefer small, focused changes without sacrificing correctness, quality, clarity,
  or maintainability. Use clear names and structure; avoid unrelated edits,
  duplication, and needless abstractions.
- Keep tightly coupled work together. Split code, docs, workflows, or tasks only
  when it improves understanding, review, or independent delivery.
- Give issues and PRs a bounded scope, verifiable acceptance criteria, and explicit
  dependencies. Use native sub-issues for independent work; the parent tracks the
  outcome instead of duplicating child work in a PR.
- Keep decisions in the component that owns them. Reuse existing logic and
  contracts rather than spreading implementation details across boundaries.
- Prefer existing tools and native GitHub features. Add scripts or orchestration
  only for a concrete need or a clear reduction in complexity; remove unnecessary
  mechanisms rather than renaming them.

## AI-led work

- State goals, when to act, hold, or skip, constraints, and verifiable outcomes. Let
  capable models choose how to meet them with the available tools and context;
  design for future improvements without weakening permissions, safety checks,
  or result verification.
- Do not expand already-clear requests; add only missing context or decisions
  needed to act and verify. Keep detailed requirements in the owning guidance
  document and link to it instead of repeating them; prompts supply only the task
  and run-specific context.
- Prescribe procedures only for a required contract, safety boundary, or known
  failure.
- Strengthen shared rules when review reveals a gap, rather than adding a checklist
  per scenario. Consolidate overlaps without weakening required checks.
- When changing prompts or agent instructions (including workflow prompts, this
  file, and Factory guides), research current official recommendations for the
  affected models/providers rather than relying on memory. For shared Factory
  guidance, cover OpenAI and Anthropic plus other applicable providers. Assess the
  change against that research, distinguishing general advice from model-specific
  recommendations. In the PR or change report, link sources and summarize relevant
  conclusions and justified deviations; report unavailable research or unresolved
  conflicts without claiming verification. Provider advice never overrides
  repository permissions, token boundaries, trust rules, decision markers, or
  verification contracts.

## Writing docs and comments

- Be brief by default and use plain language in docs, issue/PR bodies, comments,
  and reviews. Include only useful scope, evidence, decisions, blockers, or next
  steps; avoid repeated context and process narration. Keep documentation aligned
  with the code and workflows.
- Durable docs, guides, and prompts describe current behavior and decisions; put
  change history (superseded approaches, change-specific issue/PR/run/commit
  references, per-change verification evidence) in PR descriptions, comments, or
  commit messages. Preserve README milestones, owning-guide links, durable
  verification requirements and limits, and required evidence links and markers
  in issue/PR bodies, comments, and reports.
- Lead with the outcome or request. Start AI-written PR descriptions, issue
  bodies, triage assessments, and other longer comments, reviews, or reports with
  a `## TL;DR` section: one or two short, plain-language sentences before supporting
  detail. Already-brief replies do not need a separate summary.
- Retain required links, markers, checked revisions, verification results, and
  failure details. Concision must not hide uncertainty.
- Use descriptive headings and focused bullets when they help scanning. Group
  related conditions under a shared bullet; do not force short replies into a
  template.

## Repository map

This is an agentic software factory scaffold, with no application code or
toolchain yet. [README.md](README.md) tracks completed CI milestones. There are no
configured build/test/lint commands; automated workflow tests are deferred.

Use the owning guide for each workflow's behavior, permissions, and verification:

| Area | Guidance |
|---|---|
| Factory host, target identity, and checkout separation | [Target context](docs/factory/target-context.md) |
| App identities and credentials | [GitHub App setup](docs/factory/github-app.md) |
| External requests and owner decisions | [Participant approval](docs/factory/participant-approval.md) |
| Event routing and dispatch | [Factory router](docs/factory/factory-router.md) |
| PR assessments | [PR review](docs/factory/pr-review.md) |
| Readiness and label handoff | [Issue triage](docs/factory/issue-triage.md) |
| Code, feedback, base merges, and sub-issues | [Issue implementation](docs/factory/issue-implementation.md) |
| Run-history analysis | [Workflow diagnostics](docs/factory/workflow-diagnostics.md) |
| Full source analysis | [Repository review](docs/factory/repository-review.md) |
| Model selection and improvement findings | [Model profile improvement](docs/factory/model-profile-improvement.md) |
| Recurring owner feedback and guidance findings | [Owner feedback learning](docs/factory/owner-feedback.md) |

Participant approval is AI-owned: non-owner (external) requests need scoped owner
approval; verified configured automation's own work is exempt under the shared
policy. Router/triage may request approval; this is not a pre-Copilot gate.
Workers recheck each request.

Factory tooling checkouts use `github.workflow_sha`; target code and project
guidance stay separate. Only the Factory-local target is enabled. Manual jobs skip
non-default refs.
Eligible submitted reviews are the router exception: they run PR-merge-revision
code before merge, with the [documented risk](docs/factory/factory-router.md#accepted-risk-router-changes-can-run-before-merge).

Workflows share [`.github/actions/ai`](docs/examples/ai-tools.md#shared-factory-action)
from the pinned Factory checkout for installation and invocation. Checkout,
credentials, Git identity, prompts, and receipt checks stay in callers.

[AI setup](docs/examples/ai-tools.md), [PR creation](docs/examples/create-pull-request.md),
and [issue creation](docs/examples/create-issue.md) are reusable documentation
snippets, not installed workflows.

## GitHub CLI pagination

When using `gh api --paginate --slurp`, filter the collected pages with external
`jq`. Do not combine `--slurp` with gh's `--jq` or `--template`; these options are
incompatible.

### GraphQL reads

Follow GitHub's [node limit](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api#node-limit)
and [cursor pagination](https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api).

- Keep every query, including the first, within 500,000 worst-case nodes across
  all nested and sibling connections, with `first`/`last` bounds of 1-100.
- Read all required bodies, discussions, reviews, inline replies, and edit/deletion
  histories. Verify every required connection reaches its terminal page using its
  own cursor, including each object's nested connections. `gh api graphql --paginate`
  [follows only the first `pageInfo`](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/api/pagination.go);
  a successful command does not prove complete pagination.
- Preserve the owning guide's evidence, freshness, and approval requirements.
  Missing, partial, or failed required provenance is a blocker, not evidence of
  no activity or grounds for a skip.

## GitHub Actions logs

For Actions-log reads in any Factory workflow, follow the
[shared log guidance](docs/factory/actions-logs.md) from the first needed read.
The calling workflow's guide still owns source eligibility, token selection,
permissions, and verification.

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
