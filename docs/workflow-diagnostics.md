# Diagnose workflow runs

[Workflow diagnostics](../.github/workflows/workflow-diagnostics.yml) runs daily
at **00:00 UTC** (`0 0 * * *`). After it lands on the default branch, it can also
be started from **Actions -> Workflow diagnostics -> Run workflow**. Select the
default branch; dispatches on other branches are skipped. GitHub can delay
scheduled runs.

Copilot owns history collection, workflow analysis, duplicate detection, and
issue creation. The workflow prompt supplies the requirements and API hints
instead of maintaining a separate diagnostics program. It reuses
`scripts/install-tools.sh`, `scripts/ai.sh --harness copilot`, and the `default`
profile in `.github/model-config.json`.

## Analysis window

Copilot reads the current run and pages its workflow history to find the
preceding default-branch scheduled or manual invocation by `run_number`,
regardless of conclusion. If there is no predecessor, it records an
`initialized` report and stops: **no run/log analysis, subagents, or findings
issues**. Setup and Copilot still run to make that boundary decision. API errors
must not be treated as empty history.

Later invocations inspect all workflows, branches, and outcomes between that
predecessor (inclusive) and the current invocation (exclusive). The preceding
diagnostics run is included; the current one is inspected next time. Original
`created_at` timestamps and run IDs break same-second ties and preserve the
window on retries, rather than advancing it to the retry time.

The prompt also covers older runs updated during the interval, using a bounded
creation lookback of **90 days before the window start**. This supplemental
lookback does not shorten the primary interval, even after a longer gap.
Collection hints require pagination, splitting time ranges at GitHub's
1,000-result filtered-search cap, and reconciling distinct counts at every
split. Missing history, inconsistent counts, an unsplittable saturated second,
and API failures must be reported rather than hidden as complete coverage.
The model carries out these checks; they are not a separate deterministic gate.

One concurrency group serializes scheduled and manual runs without cancelling
an active run. GitHub retains at most one pending invocation, so dispatch bursts
can replace pending runs. The boundary is the preceding invocation, not the last
successful analysis: failed/cancelled windows are not automatically replayed.
Rerun the original invocation to retry its window. If all preceding history is
deleted, Copilot can only establish a new initial boundary.

## Analysis and issue handoff

Copilot must launch one read-only subagent per selected workflow concurrently
(parallel batches if tool limits require), wait for every result, and consolidate
findings. Each subagent receives the complete selected run list and inspects
attempts, jobs, relevant logs, and workflow revisions through read-only APIs.
Successful, failed, cancelled, skipped, and unfinished runs are all in scope.
Fetched code and log instructions must never be executed.

Before each new issue, the coordinator refreshes duplicate checks across
issues **and PRs in all states**, including previous diagnostics attempts.
Existing findings are linked in the report, not reopened, commented on, or
duplicated. Create one issue per distinct evidenced fix, optimization, or other
improvement, with impact, supporting run/job URLs, proposed scope, and acceptance
criteria. No actionable findings means no issues.

New issues use the Factory App identity, contain
`<!-- factory-diagnostics:RUN_ID:ATTEMPT -->`, and have **no labels at creation**.
Their App-authored `issues.opened` events enter normal [triage](issue-triage.md).
Copilot checks the creation response and leaves later triage/human updates
alone; it must not apply `triaged`, tracking labels, or triage-decision comments.
Diagnostics completions remain excluded from the implementation event router.

## Permissions and result checks

Use the existing [Factory App setup](github-app.md). The analysis App token
requests Contents read, Pull requests read, and Issues write, with no push or
workflow-write access. Checkout does not persist credentials. The built-in
token has Contents/Actions read and `copilot-requests: write`. Read-only Actions
queries use a command-local `GH_TOKEN="$GITHUB_TOKEN"` override; repository,
issue, and PR operations use the App token. Model requests use
`COPILOT_GITHUB_TOKEN`.

Before checkout or tool/token setup, the workflow seeds an `incomplete` report
with a fatal error using Bash's built-in `printf`, without requiring `jq`.
An early failure or a model that never writes its report therefore does not
leave a success-shaped result. Copilot replaces this placeholder in
`report.json` with the run ID, producing attempt, outcome,
Markdown summary, unique created issue numbers, expected evidence limitations,
and fatal errors. The summary records boundary URLs/timestamps, selected
workflow/run IDs, actual subagent IDs and results, duplicate links, and created
issue URLs. Outcomes are `initialized`, `analyzed`, or `incomplete`.

A small inline check on a **fresh read-only runner**, without checkout or
Copilot, installs `jq` only if missing, without installing the AI tools.
It requires a well-formed report for the producing run/attempt, a nonempty
summary, no fatal errors, and an `initialized` or `analyzed` outcome. An
initialized report cannot claim created issues or evidence gaps. Every reported
issue must exist in this repository with the Factory author and attempt marker;
the verifier also paginates the Factory author's issues in all states and
requires the numbers carrying that exact marker to match `created_issues`.
This catches omitted issues, including closed issues and findings hidden by an
`initialized` report, without relying on search indexing. Other attempts and PRs
are excluded. The verifier's fresh App token has only Issues read access.
Missing reports, invalid or mismatched receipts, incomplete outcomes, and API
errors fail explicitly. All inline scripts use explicit Bash with `pipefail`,
so even a listing failure after valid partial output fails verification.

Confirmed expired logs, superseded-attempt logs, or logs not yet available for
unfinished runs go in `unavailable_evidence`, with cause and supporting URLs.
They produce a visible warning and summary, not a clean result. Unexplained
404s, permission failures, rate limits, other tooling failures, and unfinished
subagent analysis belong in fatal `errors`.

These checks verify **reported status and issue receipts, not independent
coverage or reasoning**. First-run selection, collection completeness, actual
subagent execution/concurrency, evidence classification, duplicate detection,
and unlabeled creation are Copilot responsibilities. There is no pinned
manifest or automated label-history audit. Receipt reconciliation cannot
attribute issues without the marker or with a removed marker to this attempt.
Issues are created during analysis,
so the receipt check is not a gate before triage. The read-only subagent and
untrusted-data rules are behavioral constraints, not a sandbox: the coordinator
still handles repository-wide evidence, including forks, while holding Issues
write access. The isolated check does not prevent analysis-time issue changes.

The report, including the incomplete placeholder on early failure, is retained
for 14 days as `workflow-diagnostics-RUN_ID-ATTEMPT` when initialization and
upload can run. Initialization emits the artifact name once; the upload and
producing job's output both use that value. A missing report makes upload fail
rather than just warn.
Verification also runs after a failed diagnosis unless
the workflow was cancelled or diagnosis was skipped. **Re-run failed jobs**
reuses the producing job's saved artifact name and attempt when only verification
failed; **Re-run all jobs** repeats diagnosis for the original window.
Runner termination, initialization/upload failure, or artifact expiration/deletion
can still leave no downloadable report; inspect the diagnosis/upload logs and
rerun all jobs. A failed run is not evidence of no findings.

Automated tests are deferred for now; no test suite or test-running CI workflow
is configured. The runtime report and issue-receipt checks above remain enabled.
