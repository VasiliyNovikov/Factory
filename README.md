# Factory

## Agentic Software Factory experiment
Starting with small things:

- [x] Run GitHub Copilot CLI in CI Job
- [x] Have GitHub Copilot CLI on CI read/write repo/issues/PRs
- [ ] Review PRs with GitHub Copilot CLI in CI and post comments or approval
- [ ] Turn issues and user follow-up comments into PRs or Factory replies

## Factory workflow

The [Factory router](docs/factory-router.md) analyzes events and dispatches triage,
review, or implementation on the default branch. Router runs are independent;
workers own issue/PR concurrency and AI-led freshness checks. Setup checkouts use
the workflow's exact revision. Submitted reviews directly run the PR-revision
router, so router/setup changes can execute before merge; see the
[accepted risk](docs/factory-router.md#accepted-risk-router-changes-can-run-before-merge).

Triage applies the unique `factory-issue-<number>` tracking label before `triaged`
enters routing for implementation. The resulting Factory PR carries both labels.

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
    triage -->|Ready| tracking["Agentic: ready comment + factory-issue-NUMBER<br/>Created / applied by: Factory"]
    tracking -->|Factory then applies triaged| router
    implementation -->|Actionable| pr["Agentic: create / update PR + commits<br/>Author: Factory"]
    implementation -->|Unclear, blocked, or already satisfied| reply["Agentic: reply in triggering conversation<br/>Comment author: Factory"]
    reply -->|New feedback| feedback["Human / bot: issue / PR comments or submitted reviews<br/>Author: submitting account"]
    feedback -->|Comments and submitted reviews| router
    pr -->|PR events| router
    review -->|Workflow completion| router
    review -->|Clean and approval permitted| approval["Agentic: approval<br/>Review author: Actions"]
    pr --> ci["Automation: PR-linked CI<br/>Checks produced by: GitHub Actions"]
    pr -->|Discussion or review| feedback
    ci -->|Failure or timeout| router
    base["Human / bot: default-branch update"] --> router
    implementation -->|Confirmed merge conflicts| repair["Agentic: verified conflict repair<br/>Own PR only; preserve both histories"]
    repair --> pr

    diagnosticsTrigger["Automation: daily 00:00 UTC or manual<br/>Default branch only"] --> diagnostics{"Agentic: workflow diagnostics<br/>Identity: Factory"}
    diagnostics -->|First invocation| boundary["Agentic: establish boundary only<br/>No analysis or findings"]
    diagnostics -->|Later invocations| workflowAnalysis["Agentic: analyze same-repository runs since previous diagnostics<br/>All workflows / outcomes; include previous run<br/>Parallel read-only Copilot subagents"]
    workflowAnalysis --> findings["Agentic: consolidate findings<br/>Check issues / PRs in all states for duplicates"]
    findings -->|New actionable findings only| diagnosticsIssue["Agentic: new unlabeled issue per finding<br/>Author: Factory"]
    diagnosticsIssue --> router
    boundary --> diagnosticsSummary["Agentic: verify actions and summarize results<br/>Job summary and logs"]
    findings --> diagnosticsSummary
    diagnosticsIssue --> diagnosticsSummary
```

PR review runs on non-draft, same-repository PRs. Follow-ups require an open,
triaged issue and, when present, a matching open Factory PR. CI must match the
PR's current head or merge revision.

Default-branch updates and ordinary follow-ups check eligible Factory PRs for
merge conflicts; each implementer handles only its assigned PR. Verified repairs
preserve both histories and intended changes. Clean/behind branches get no
conflict-repair commit; clean maintenance checks without outstanding feedback,
errors, or blockers skip without PR comments. Ambiguous resolutions get a blocker
on the PR. Factory does not automatically merge PRs or close issues.

## CI examples

The basic examples use this repository's scripts and require no PAT or custom secret.
The PR-creation CI uses the [GitHub App setup](docs/github-app.md)
with `FACTORY_CLIENT_ID` and `FACTORY_PRIVATE_KEY` to enable automatic runs and
distinct PR author/reviewer identities.

- `scripts/install-tools.sh` installs standalone Copilot CLI and OpenCode via their
  official scripts (no Node.js/npm setup), plus missing `jq`.
- `scripts/ai.sh` reads `.github/model-config.json` and invokes the selected CLI.
- `GITHUB_TOKEN: ${{ github.token }}` authenticates both Copilot model requests and
  the `gh` commands in the basic examples. App-based PR creation sets `GH_TOKEN`
  to the App token and `COPILOT_GITHUB_TOKEN` to the built-in token.

Run the manual examples from **Actions → CI → Run workflow** once the workflow is
on the default branch; select that branch (other refs skip). The router dispatches
PR review on PR events. Issue triage assesses new
issues and clarification comments; implementation handles triaged issues and
feedback on their Factory PRs. See
[GitHub's Copilot CLI Actions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions).
Workflow diagnostics runs daily at 00:00 UTC or manually. Copilot selects the
same-repository run window, analyzes workflows with parallel subagents, and sends
actionable findings through triage. It verifies its actions and summarizes results
in the job summary and logs.

1. [Install AI tools and run a prompt](docs/ai-tools.md)
2. [Create a pull request](docs/create-pull-request.md) — tested successfully.
3. [Create an issue](docs/create-issue.md) — tested successfully.
4. [PR review](docs/pr-review.md) — comment reviews tested successfully; approvals pending.
5. [Triage issues before implementation](docs/issue-triage.md)
6. [Turn a triaged issue or follow-up comment into a PR](docs/issue-implementation.md)
7. [Diagnose workflow runs and create actionable issues](docs/workflow-diagnostics.md)
8. [Route events to default-branch workers](docs/factory-router.md)
