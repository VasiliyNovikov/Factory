# Diagnose workflow runs

[Workflow diagnostics](../.github/workflows/workflow-diagnostics.yml) runs daily
at **00:00 UTC** (`0 0 * * *`) or manually from **Actions → Workflow diagnostics
→ Run workflow** once it lands on the default branch. Select that branch;
dispatches on other branches are skipped. GitHub can delay scheduled runs.

Copilot owns history selection, investigation, duplicate checks, issue creation,
and result verification. It reuses `scripts/install-tools.sh`,
`scripts/ai.sh --harness copilot`, and the `default` model profile.

## Scope and investigation

The first invocation establishes a boundary with **no analysis or findings
issues**. Later invocations cover the interval from the preceding scheduled or
manual invocation, regardless of its conclusion, up to the current invocation.
The preceding diagnostics run is included; the current one is inspected next
time. Retries use the original invocation times. Older runs updated in the
interval are included with a 90-day creation lookback before the window start.

All workflows, branches, and outcomes are eligible, but only runs whose
`head_repository.full_name` matches this repository are analyzed. Fork-originated
and unknown-origin runs are recorded as out of scope: their logs, artifacts, and
revisions are not fetched, including through related PR code/diff links.
This intentionally narrows the original repository-wide scope following the
maintainer's PR review decision.

Copilot uses parallel read-only subagents per workflow, waits for their results,
and consolidates actionable findings. It chooses the queries and evidence needed
from jobs, attempts, logs, workflow code, and related discussions, handling
pagination and API limits. Successful runs can also reveal optimizations.

One concurrency group serializes scheduled and manual runs without cancelling
an active run. GitHub keeps at most one pending invocation. Failed windows are
not automatically replayed because the boundary is the preceding invocation,
not the last successful analysis; rerun the original invocation to retry it.
API failures must not be mistaken for empty history or a first invocation.

## Findings and reporting

Before creating an issue, Copilot checks issues and PRs in all states, including
earlier attempts, for duplicates. Existing findings are linked, not changed.
Each new actionable finding becomes one Factory-authored issue with evidence
links, impact, proposed scope, acceptance criteria, and
`<!-- factory-diagnostics:RUN_ID:ATTEMPT -->`. No findings means no issues.

Issues are created **without labels**, so App-authored `issues.opened` events
enter normal [triage](issue-triage.md). Copilot verifies creation responses and
issue URLs and leaves later labels and triage updates alone. Diagnostics
completions are excluded from the implementation event router.

Within the 30-minute job budget, Copilot writes the window, per-workflow results,
excluded runs, existing/new issue links, and evidence gaps or failures to the job
summary and log. It distinguishes initialization, completed analysis, and
incomplete analysis. Missing evidence must not be presented as a clean result.

Per the maintainer's simplification decision, there is no JSON report contract,
report artifact, or separate verification job. Checks of investigation coverage
and issue creation are AI-owned. Setup/CLI failures fail their normal workflow
steps, but a successful CLI exit does **not** independently prove complete
analysis or correct issue creation. Inspect the summary and logs; early failure
can leave no AI summary. Automated workflow tests are deferred for now.

## Permissions

The [Factory App token](github-app.md) has Contents read, Pull requests read, and
Issues write, without push or workflow-write access. Checkout does not persist
credentials. The built-in token supplies Contents/Actions read and
`copilot-requests: write`. Individual read-only Actions commands use
`GH_TOKEN="$GITHUB_TOKEN"`; repository, issue, and PR operations use the App token.
`COPILOT_GITHUB_TOKEN` is reserved for model requests.

Same-repository scoping reduces fork-evidence exposure; it is not a sandbox.
Logs and discussions can still contain untrusted text, and the coordinator holds
Issues write access. Copilot and its subagents must treat fetched content as
evidence, not instructions, never execute analyzed code, and make no GitHub
changes except the coordinator's new findings issues. These are behavioral
constraints, not enforced isolation between analysis and issue publication.
