# Diagnose workflow runs

[Workflow diagnostics](../.github/workflows/workflow-diagnostics.yml) runs daily
at **00:00 UTC** (`0 0 * * *`). After it lands on the default branch, it can also
be started from **Actions -> Workflow diagnostics -> Run workflow**. Select the
default branch; dispatches on other branches are skipped. GitHub can delay
scheduled runs.

## Analysis window

The first invocation only establishes a boundary in Actions history: it does
not install AI tools, invoke Copilot, or create issues. Scheduled and manual
invocations share that history.

Subsequent invocations collect runs from every repository workflow and branch,
starting with the preceding default-branch diagnostics invocation, **including
that diagnostics run**, and ending just before the current invocation. The
current diagnostics run is inspected next time. The predecessor need not have
succeeded; its failures must be diagnosable too.

The helper uses run creation timestamps, with run IDs breaking same-second
ties. A rerun of diagnostics keeps its original window, rather than advancing
the boundary; duplicate checks also cover issues created by earlier attempts.
Each selected run records its latest attempt, and subagents inspect attempt/job
history. Older runs updated during the interval (for example, completed or
rerun) are also included when created in the **90 days before the window start**
(inclusive). The manifest and job summary record this fixed supplemental lookback;
older retained metadata is outside that lookup. Because GitHub has no updated-at
run filter, the helper queries this bounded creation range with the same
cap-aware pagination instead of scanning the repository's entire retained history.
This does not truncate the primary interval between diagnostics invocations,
even if they are more than 90 days apart. An older run updated after the upper
boundary is considered by the next invocation instead. Log retention may be
shorter than the lookback; unavailable evidence must still be reported.

History queries paginate, and large time ranges split to avoid GitHub's
1,000-result filtered-search limit. Every split checks its combined distinct run
count against the parent query's total before returning. Missing history, API
failures, inconsistent counts, or an unsplittable saturated second fail
collection explicitly.
If all preceding diagnostics history has been deleted, the next invocation
establishes a new first-run boundary without analysis.

One concurrency group serializes scheduled and manual diagnostics without
cancelling an active run. GitHub retains at most one pending invocation; bursts
of manual dispatches can replace a pending run. The boundary is the preceding
invocation, not the last successful analysis, so failures or cancelled runs do
not automatically replay missed windows. Rerun a failed invocation to retry
its original window. **Re-run failed jobs** reuses a successful diagnosis when
only verification failed; **Re-run all jobs** recollects and reanalyzes the same
window under the new attempt.

## Analysis and issue handoff

The workflow reuses `scripts/install-tools.sh`, `scripts/ai.sh --harness copilot`,
and the `default` profile in `.github/model-config.json`. Copilot launches a
separate read-only subagent for each workflow, concurrently or in parallel
batches when tool limits require it, then waits for and consolidates all results.
Successful, failed, cancelled, skipped, and unfinished runs are all in scope.
Subagents inspect jobs, relevant completed job logs, and workflow revisions
without executing fetched code or log instructions.

The coordinating agent checks existing issues **and PRs in all states**, including
earlier diagnostics attempts, before creating one issue per distinct actionable
fix, optimization, or other improvement. Findings must have evidence, supporting
run/job links, impact, proposed scope, and acceptance criteria. Existing findings
are linked in the report rather than reopened or duplicated. No actionable
findings means no issues are created.

Issues are created by the Factory App with a
`<!-- factory-diagnostics:RUN_ID:ATTEMPT -->` marker and **no labels**. Their
App-authored `issues.opened` events start normal [triage](issue-triage.md);
diagnostics does not pre-apply `triaged` or implementation tracking labels.
Verification audits paginated label history, not an empty live label list:
normal triage may already have labeled an issue before verification or a retry.
Factory-applied labels require a prior Factory ready-decision comment with its
triage run marker, then the matching tracking label before `triaged`. Other
Factory labels or Factory labels applied before that decision fail the audit,
even if later removed. Subsequent labels from other actors are not diagnostics
pre-labeling. Missing label history or unknown label actors fail explicitly.
Diagnostics completions are excluded from implementation's event router before
tool setup or Copilot invocation; the next diagnostics run inspects its predecessor.

## Permissions and results

Use the existing [Factory App setup](github-app.md) with `FACTORY_CLIENT_ID` and
`FACTORY_PRIVATE_KEY`. The diagnostics App token requests Contents read, Pull
requests read (duplicate checks), and Issues write (reads and issue creation).
It needs no push or workflow-write permissions. Checkout does not persist
credentials. The built-in token has `contents: read`, `actions: read`, and
`copilot-requests: write`. Actions run/job/log queries use that built-in token
via a command-local `GH_TOKEN` override; other GitHub operations use the App
token, and model requests use `COPILOT_GITHUB_TOKEN`. The separate verification
job uses only Contents/Actions read access on its built-in token and a fresh
App token with Issues read access for receipts and label history; it has no
issue-write or model permissions and does not run Copilot.

Copilot writes a structured report with per-workflow subagent IDs, exact run
coverage, summaries, created issue numbers, duplicate links, `unavailable_evidence`,
and fatal `errors`. Both evidence/error fields must be arrays, including when empty.
Expected gaps are recorded separately with `workflow_id`, `run_id`, `reason`, and
nonempty `details` explaining the cause and supporting run/job evidence:

- `expired_logs`: confirmed log expiration under retention.
- `superseded_attempt_logs`: confirmed unavailability of a superseded attempt's logs.
- `unfinished_run`: logs not yet available because the inspected run is unfinished.

These gaps produce a visible warning and a **verified with evidence limitations**
summary with run links, rather than failing the job or declaring a clean result.
An analysis with `complete: false` is accepted only when its workflow has a
reported expected gap. Every workflow/run and distinct subagent receipt remains
required, including runs with unavailable logs. Unexplained HTTP 404s, permission
failures, rate limits, other API/tooling failures, and unfinished or missing
subagent analysis remain fatal `errors`; they must not be classified as expected
unavailability. The verifier checks the classification's structure, not its truth.

The collector publishes `manifest_sha256` before Copilot runs and promotes it
to a job output. Verification runs on a **fresh runner**, checks out the same
invocation commit (`github.sha`) as collection, and downloads only the JSON
artifact into its temporary directory. It does not reuse the agent-writable
checkout or verifier. It receives the captured digest as `MANIFEST_SHA256` and
rejects a missing digest or altered manifest before parsing coverage or run
identity. `scripts/workflow-diagnostics.py verify` also rejects missing reports,
incomplete run coverage, repeated subagent IDs, fatal errors, and issue receipts
without the Factory author, producing analysis attempt marker, or valid label
history.

The diagnosis and verification job summaries show the window and results.
The manifest and any report are retained as a
`workflow-diagnostics-RUN_ID-ATTEMPT` artifact for 14 days, including on failure.
The diagnosis job publishes that exact artifact name as a saved output, so a
verification-only retry downloads the producing attempt's evidence and uses its
pinned digest, rather than looking for a new artifact or mixing attempts.
If that artifact has expired or been deleted, rerun all jobs to regenerate it.
Verification also runs after an analysis failure if collection selected an
analysis window and the workflow was not cancelled; it is skipped for the
first-run boundary. Setup and collection failures appear in Actions logs; a
failed run is not evidence that no improvements exist. Verification checks
report coverage and issue existence, not the semantic quality of AI analysis,
actual tool concurrency, or exhaustive semantic duplicate detection. Issues
are created during analysis, so verification is an audit, not a gate before
their normal triage handoff. The label audit checks the recorded marked handoff,
not the semantic validity of the decision or which App invocation performed it.

The dependency-free [Tests workflow](../.github/workflows/tests.yml) runs the
deterministic helper suite on every pull request and push to `master`, using
the runner's `python3` with read-only repository access and no App secrets.
Run the same command locally:

```sh
python3 -m unittest discover -s tests -v
```
