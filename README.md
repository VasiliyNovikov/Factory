# Factory

## Agentic Software Factory experiment
Starting with small things:

- [x] Run GitHub Copilot CLI in CI Job
- [x] Have GitHub Copilot CLI on CI read/write repo/issues/PRs
- [x] Review PRs with GitHub Copilot CLI in CI and post comments or approval
- [x] Turn issues and user follow-up comments into PRs or Factory replies

## Factory workflow

The [Factory router](docs/factory/factory-router.md) analyzes events and dispatches triage,
review, or implementation on the default branch. Router runs are independent;
workers own issue/PR concurrency and AI-led freshness checks. Setup checkouts use
the workflow's exact revision. Submitted reviews directly run the PR-revision
router, so router/setup changes can execute before merge; see the
[accepted risk](docs/factory/factory-router.md#accepted-risk-router-changes-can-run-before-merge).

Triage applies the unique `factory-issue-<number>` tracking label before `triaged`
enters routing for implementation. Triage may suggest decomposition in its comment
but creates no issues. Implementation chooses a focused PR or native sub-issues.
A PR carries both labels; a split parent stays open with its existing labels.
Each child enters normal triage and receives its own tracking identity when ready.

**Actors:** Agentic blocks use Copilot in CI; human / bot input can come from a
human or another bot under its own account. Automation denotes CI runs and checks.

**Identities:** Factory = `factory-identity[bot]`; Actions = `github-actions[bot]`.
Running in Actions does not make Factory-created content Actions-authored.

```mermaid
flowchart TD
    issue["Human / bot: new untriaged issue<br/>Author: submitting account"] --> router{"Agentic: Factory router<br/>Default branch except submitted reviews<br/>Independent events; identity: Actions"}
    router -->|Triage| triage{"Agentic: issue triage<br/>Identity: Factory"}
    router -->|Implement| implementation["Agentic: issue implementation<br/>Identity: Factory"]
    router -->|Review| review{"Agentic: PR review<br/>Review author: Actions"}
    router -->|No actionable work| skip["Skip with reason"]
    triage -->|Not ready| clarification["Agentic: clarification or explanation<br/>Comment author: Factory"]
    clarification --> answer["Human / bot: answer or comment<br/>Author: submitting account"]
    answer --> router
    implementation -->|Independent delivery is useful| decomposition["Agentic: plan split; parent stays open and triaged<br/>Identity: Factory; no duplicate parent PR"]
    decomposition --> children["Agentic: create / reuse native sub-issues<br/>Author: Factory for new children"]
    children -->|New child opened| router
    decomposition -->|Human / bot parent follow-up| router
    triage -->|Ready| tracking["Agentic: ready comment, optional split suggestion + factory-issue-NUMBER<br/>Created / applied by: Factory"]
    tracking -->|Factory then applies triaged| router
    implementation -->|Cohesive delivery| pr["Agentic: create / update PR + commits<br/>Author: Factory"]
    implementation -->|Unclear, blocked, or already satisfied| reply["Agentic: reply in triggering conversation<br/>Comment author: Factory"]
    reply -->|New feedback| feedback["Human / bot: issue / PR comments or submitted reviews<br/>Author: submitting account"]
    feedback -->|Comments and submitted reviews| router
    pr -->|PR events| router
    review -->|Workflow completion| router
    review -->|Clean and approval permitted| approval["Agentic: approval<br/>Review author: Actions"]
    pr --> ci["Automation: PR-linked CI<br/>Checks produced by: GitHub Actions"]
    pr -->|Discussion or review| feedback
    ci -->|Failure or timeout| router
```

PR review runs on non-draft, same-repository PRs. Follow-ups require an open,
triaged issue and, when present, a matching open Factory PR. CI must match the
PR's current head or merge revision. Factory does not automatically merge PRs
or close issues. Implementation reuses existing child work on retries and does
not duplicate it in a parent PR. Parent comments resume partial splits through
the same implementation route; see [issue implementation](docs/factory/issue-implementation.md).

## Workflow diagnostics

[Workflow diagnostics](docs/factory/workflow-diagnostics.md) analyzes past workflow runs
separately from the main Factory workflow. New unlabeled findings issues enter the
[Factory workflow](#factory-workflow) through the router and normal issue triage.

```mermaid
flowchart TD
    diagnosticsTrigger["Automation: daily 00:00 UTC or manual<br/>Default branch only"] --> diagnostics{"Agentic: workflow diagnostics<br/>Identity: Factory"}
    diagnostics -->|First invocation| boundary["Agentic: establish boundary only<br/>No analysis or findings"]
    diagnostics -->|Later invocations| workflowAnalysis["Agentic: analyze same-repository runs since previous diagnostics<br/>All workflows / outcomes; include previous run<br/>Parallel read-only Copilot subagents"]
    workflowAnalysis --> findings["Agentic: consolidate findings<br/>Check issues / PRs in all states for duplicates"]
    findings -->|New actionable findings only| diagnosticsIssue["Agentic: new unlabeled issue per finding<br/>Author: Factory"]
    diagnosticsIssue -->|Issue opened| router{"Agentic: Factory router<br/>Default branch; identity: Actions"}
    router -->|Triage| triage{"Agentic: issue triage<br/>Identity: Factory"}
    boundary --> diagnosticsSummary["Agentic: verify actions and summarize results<br/>Job summary and logs"]
    findings --> diagnosticsSummary
    diagnosticsIssue --> diagnosticsSummary
```

## Repository review

[Repository review](docs/factory/repository-review.md) runs daily at 03:17 UTC or manually,
reviewing the whole source snapshot from scratch even on its first invocation.
It checks existing issues/PRs before publishing new actionable findings for triage,
and records the reviewed commit, coverage, issue links, and gaps in the job summary.

```mermaid
flowchart TD
    repositoryReviewTrigger["Automation: daily 03:17 UTC or manual<br/>Default branch only"] --> repositoryReview{"Agentic: full repository review on every invocation<br/>Identity: Factory; source analysis read-only"}
    repositoryReview -->|New findings after duplicate checks| repositoryReviewIssue["Agentic: new unlabeled issue per finding<br/>Author: Factory"]
    repositoryReviewIssue -->|Issue opened| router{"Agentic: Factory router<br/>Default branch; identity: Actions"}
    router -->|Triage| triage{"Agentic: issue triage<br/>Identity: Factory"}
    repositoryReview --> repositoryReviewSummary["Agentic: verify outcomes and record coverage / gaps<br/>Job summary and logs"]
    repositoryReviewIssue --> repositoryReviewSummary
```

## CI examples

The AI setup and issue/PR-creation examples in [docs/examples/](docs/examples/)
are reusable snippets, not installed workflows. The basic examples use this
repository's scripts and require no PAT or custom secret. App-based PR creation uses the
[GitHub App setup](docs/factory/github-app.md) with `FACTORY_CLIENT_ID` and
`FACTORY_PRIVATE_KEY` for automatic downstream runs and distinct PR author/reviewer
identities.

- `scripts/install-tools.sh` installs standalone Copilot CLI and OpenCode via their
  official scripts (no Node.js/npm setup), plus missing `jq`.
- `scripts/ai.sh` reads `.github/model-config.json` and invokes the selected CLI.
- `GITHUB_TOKEN: ${{ github.token }}` authenticates both Copilot model requests and
  the `gh` commands in the basic examples. App-based PR creation sets `GH_TOKEN`
  to the App token and `COPILOT_GITHUB_TOKEN` to the built-in token: three standard
  variable names, two credentials. See [token names and identities](docs/factory/github-app.md#token-names-and-identities)
  for tool precedence and separate Git push authentication.

1. [Install AI tools and run a prompt](docs/examples/ai-tools.md)
2. [Create a pull request](docs/examples/create-pull-request.md) — tested successfully.
3. [Create an issue](docs/examples/create-issue.md) — tested successfully.

## Factory guidance

Active workflow instructions and shared App setup live in [docs/factory/](docs/factory/).

The router dispatches PR review on PR events. Issue triage assesses new
issues and clarification comments; implementation handles triaged issues and
feedback on their Factory PRs. See
[GitHub's Copilot CLI Actions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions).
Workflow diagnostics runs daily at 00:00 UTC or manually. Copilot selects the
same-repository run window, analyzes workflows with parallel subagents, and sends
actionable findings through triage. It verifies its actions and summarizes results
in the job summary and logs.

1. [Factory GitHub App setup](docs/factory/github-app.md)
2. [PR review](docs/factory/pr-review.md) — comment reviews tested successfully; approvals pending.
3. [Triage issues before implementation](docs/factory/issue-triage.md)
4. [Implement a triaged issue or decompose it into sub-issues](docs/factory/issue-implementation.md)
5. [Diagnose workflow runs and create actionable issues](docs/factory/workflow-diagnostics.md)
6. [Route events to default-branch workers](docs/factory/factory-router.md)
7. [Review the whole repository and create actionable issues](docs/factory/repository-review.md)
