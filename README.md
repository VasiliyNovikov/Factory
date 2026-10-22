# Factory

An agentic software factory experiment, starting with small CI milestones:

- [x] Run GitHub Copilot CLI in CI
- [x] Read and write repository content, issues, and PRs from CI
- [x] Review PRs and post comments or approvals
- [x] Turn issues and follow-up comments into PRs or Factory replies
- [x] Check shell syntax, model JSON, and [launcher contracts offline](docs/examples/ai-tools.md#offline-checks)

## Factory workflow

The [router](docs/factory/factory-router.md) sends events to Copilot workers for
triage, implementation, or review. Workers check current state and verify results.

Assignments carry an explicit target repository, defaulting to this Factory host
for existing callers. **External targets are disabled.** Factory tooling and
policies stay at the executing workflow revision in a separate checkout from
editable target code and project guidance. APIs, receipts, ownership, concurrency,
and reports use the [host/target contract](docs/factory/target-context.md).

```mermaid
flowchart TD
    issue["New issue"] --> router{"Router"}
    feedback["Created/edited comments, submitted reviews, or current-PR CI failures"] --> router
    base["Default-branch update"] --> router
    router -->|Untriaged issue| triage["Triage"]
    triage -->|External issue needs approval| ownerRequest["Ask owner; labels unchanged"]
    ownerRequest --> ownerDecision["Owner approval or rejection in a new comment"]
    ownerDecision --> router
    triage -->|Ready: tracking label, then triaged| router
    triage -->|Not ready| reply["Clarification or explanation"]
    router -->|Ready issue, feedback, or base update| implementation["Implementation"]
    implementation --> pr["Create or update the issue's PR"]
    implementation --> children["Create or reuse native sub-issues"]
    children -->|New issue| router
    implementation -->|Blocked or already satisfied| reply
    reply -->|Human or bot follow-up| feedback
    implementation -->|Verified same-head review correction| reviewContext["PR metadata edit or result reply"]
    reviewContext --> router
    pr -->|PR events| router
    router -->|Non-draft, same-repository PR| review["Review"]
    review -->|Findings| feedback
    review -->|Clean and permitted| approval["Approval"]
    router -->|No actionable work| skip["Skip with reason"]
```

People and other bots provide input under their own accounts. The router runs as
`github-actions[bot]`; Factory work uses `factory-worker-bot[bot]`, and reviews use
`factory-reviewer-bot[bot]`.

The owner's requests and verified configured automation proceed normally;
requests from other humans/bots need scoped
[repository-owner approval](docs/factory/participant-approval.md). AI may request
approval before normal triage; approval neither marks an issue ready nor adopts
unrelated feedback. This is an AI-owned hold, not a pre-Copilot gate or spending limit.

Each shared AI action call sets its own [invocation budget](docs/examples/ai-tools.md#invocation-budget).
Copilot and its subtasks share that deadline; setup and receipt checks run
outside it, under GitHub's default job limit.

Factory opts Copilot invocations into native
[Copilot Memory](docs/factory/copilot-memory.md) for useful repository facts,
including earlier decisions and reviewed helper locations. Memory is optional,
never replaces live checks, and still needs storage/recall verification with
Factory's workflow authentication.

PR reviewers may run PR code, tests, and focused experiments under the
[PR-review execution rules](docs/factory/pr-review.md#local-checks).

Implementation keeps eligible PRs current with the default branch and resolves
conflicts, but never merges PRs or closes issues. It self-reviews changed candidates
with the `review` profile before publication, except for clean default-branch-only
maintenance.
Independent PR review still runs. Verified clean base-merge heads can reuse prior
coverage for a [scoped reassessment](docs/factory/pr-review.md#clean-default-branch-merges),
with a fresh review of the new head.
Review-relevant PR metadata edits and Factory PR replies also reach the router:
verified corrections or already-addressed findings can need
[fresh review at the same head](docs/factory/pr-review.md#review-coverage).
Cosmetic edits and already-covered or equivalent active work cause no redispatch;
only the independent reviewer decides approval.
See [implementation guidance](docs/factory/issue-implementation.md) for eligibility,
parent/child ownership, split recovery, and verification.

**Before-merge risk:** eligible submitted reviews run the PR-merge-revision router.
Router/setup changes can therefore execute before merge with the router's token.
Other events and workers use the default branch. See the
[accepted risk](docs/factory/factory-router.md#accepted-risk-router-changes-can-run-before-merge).
PR checks also run in a credentialed reviewer job, with the
[accepted risk of approval-token access or receipt-check bypass](docs/factory/pr-review.md#accepted-risk-pr-code-runs-in-the-reviewer-job).
Removing environment variables does not isolate credentials.

## Periodic recovery

[Factory maintenance](docs/factory/factory-maintenance.md) runs every six hours at
00:00, 06:00, 12:00, and 18:00 UTC, or manually on the default branch. It discovers
missed or interrupted triage handoffs, implementation, reviews, feedback, and default-branch updates,
then dispatches the existing workers using the router's
[shared policy](docs/factory/routing-policy.md).

```mermaid
flowchart TD
    trigger["Every 6 hours UTC or manual<br/>Default branch"] --> discover["Factory maintenance coordinator<br/>Discover unattended issue / PR work"]
    discover --> policy{"Shared eligibility and owner approval<br/>Holds, duplicates and retry checks"}
    discover -->|Incomplete discovery| incomplete["Report incomplete coverage / failures"]
    policy -->|Missing or failed evidence| incomplete
    policy -->|No action or blocked| noAction["Report no-action / blocked reasons"]
    policy -->|Eligible; recheck live state| dispatch["Dispatch only the next needed stage<br/>Including uncovered same-head review context"]
    dispatch --> worker["Existing worker<br/>Triage, implementation or PR review"]
    dispatch -->|Verify acceptance / run evidence| report["Report dispatch evidence<br/>Acceptance is not completed recovery"]
    dispatch -->|Uncertain or failed| incomplete
```

The coordinator uses the built-in token for read-only discovery and workflow
dispatch, not comments, labels, code changes, or new issues/PRs. It reconciles
active/handled work across sweeps and ordinary routing, respects human/approval
holds and child-owned scope, and reports coverage, dispatch evidence, and partial
failures in the job summary. Dispatch acceptance is not completed recovery.

## Workflow diagnostics

[Workflow diagnostics](docs/factory/workflow-diagnostics.md) uses parallel read-only
native subagents to compare same-repository runs and GitHub outcomes against each
run's contracts, including successful runs and expected skips or handoffs.
Diagnostics also assesses time-budget utilization and recommends evidence-backed
timeout changes through the existing findings path.

```mermaid
flowchart TD
    trigger["Every 3 days, restarting monthly<br/>00:07 UTC or manual; default branch"] --> diagnostics{"Workflow diagnostics"}
    diagnostics -->|First invocation| boundary["Record boundary only<br/>No analysis or findings"]
    diagnostics -->|Later invocations| analysis["Analyze same-repository runs<br/>Since previous invocation"]
    analysis --> duplicates["Check issues and PRs<br/>All states"]
    duplicates -->|New actionable findings| issues["Create unlabeled issues"]
    issues --> router["Factory router"] --> triage["Issue triage"]
```

## Repository review

[Repository review](docs/factory/repository-review.md) reads the whole source
snapshot from scratch and may run focused checks or experiments without changing
the reviewed source.

```mermaid
flowchart TD
    trigger["Days 1, 4, ..., 31 at 00:07 UTC or manual<br/>Each month; default branch"] --> review["Review with optional checks<br/>Full repository snapshot"]
    review --> duplicates["Check issues and PRs<br/>All states"]
    duplicates -->|New actionable findings| issues["Create unlabeled issues"]
    issues --> router["Factory router"] --> triage["Issue triage"]
```

Both workflows publish only new actionable findings as unlabeled Factory issues
for triage and report supported conclusions and coverage gaps in the job summary.

## Model profile improvement

[Model profile improvement](docs/factory/model-profile-improvement.md) discovers
models available to Copilot, researches current provider guidance, and assesses
every Factory workflow individually, prioritizing **intelligence > speed > cost**.

```mermaid
flowchart TD
    trigger["Monday 00:07 UTC or manual<br/>Default branch"] --> assess["Discover models and research guidance<br/>Assess every workflow"]
    assess -->|Complete assessment| findings{"Justified improvement?"}
    assess -->|Missing evidence or failure| incomplete["Report incomplete / partial"]
    findings -->|No| unchanged["Report no change"]
    findings -->|Yes| duplicates["Check issues and PRs<br/>All states"]
    duplicates -->|Already covered| covered["Link existing work"]
    duplicates -->|New finding| issues["Create and verify unlabeled issues"]
    issues -->|Publication or verification failure| incomplete
    issues --> router["Factory router"] --> triage["Issue triage"]
```

Recommendations become **new untriaged Factory issues**, not direct PRs or
profile edits. Findings and the run summary record capability checks,
per-workflow decisions, and dated evidence.

## Owner feedback learning

[Owner feedback learning](docs/factory/owner-feedback.md) runs weekly on
**Monday at 00:17 UTC** or manually on the default branch. It reviews the last
**90 days** of the owner's issue/PR discussions and reviews, including inline
feedback on older or closed work, for recurring preferences that current
instructions, docs, or prompts do not yet address.

```mermaid
flowchart TD
    trigger["Monday 00:17 UTC or manual<br/>Default branch"] --> assess["Review owner feedback<br/>Last 90 days; check current guidance"]
    assess -->|Complete assessment| findings{"Recurring actionable gap?<br/>Two independent owner examples"}
    assess -->|Missing evidence or failure| incomplete["Report incomplete / partial"]
    findings -->|No| unchanged["Report no new actionable finding"]
    findings -->|Yes| duplicates["Check issues and PRs<br/>All states"]
    duplicates -->|Already covered| covered["Link existing work"]
    duplicates -->|Incomplete evidence| incomplete
    duplicates -->|New finding| issues["Create and verify unlabeled issues"]
    issues -->|Publication or verification failure| incomplete
    issues --> router["Factory router"] --> workers["Normal triage and implementation"]
```

Findings need multiple independent owner examples, current-guidance checks, and
provider research where applicable. The evaluator reconciles issues and PRs in
all states, then creates only new **unlabeled Factory issues** for normal triage
and implementation. It does not directly edit guidance or existing discussions.
No new actionable pattern means no new issue; incomplete coverage and failures
are reported explicitly in the job summary and retained log.

## CI examples

These are reusable snippets, not installed workflows. Basic examples use the
built-in token and need no PAT or custom secret. Factory uses
[GitHub Apps](docs/factory/github-app.md) for downstream events and separate
author/reviewer identities.

1. [Install Copilot and run a prompt](docs/examples/ai-tools.md)
2. [Create a pull request](docs/examples/create-pull-request.md) - tested successfully.
3. [Create an issue](docs/examples/create-issue.md) - tested successfully.

## Factory guidance

Worker contracts and verification boundaries live in [docs/factory/](docs/factory/).
Start with [participant approval](docs/factory/participant-approval.md),
[routing](docs/factory/factory-router.md), [triage](docs/factory/issue-triage.md),
[implementation](docs/factory/issue-implementation.md), or [PR review](docs/factory/pr-review.md).
Contributor expectations are in [AGENTS.md](AGENTS.md).
