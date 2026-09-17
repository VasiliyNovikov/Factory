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
its original window.

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
token, and model requests use `COPILOT_GITHUB_TOKEN`.

Copilot writes a structured report with per-workflow subagent IDs, exact run
coverage, summaries, created issue numbers, duplicate links, and errors.
The collector publishes `manifest_sha256` as a step output before Copilot runs.
Verification receives that captured digest as `MANIFEST_SHA256` and rejects a
missing digest or altered manifest before parsing its coverage or run identity.
`scripts/workflow-diagnostics.py verify` rejects missing reports, incomplete
coverage, repeated subagent IDs, reported evidence/API errors, and issue receipts
without the Factory author and current attempt marker. Missing or unfinished
evidence must be reported as incomplete, not a clean result.

The Actions job summary shows the window and verified results. The manifest and
any report are retained as a `workflow-diagnostics-RUN_ID-ATTEMPT` artifact for
14 days, including on failure. Setup and collection failures appear in Actions
logs; a failed run is not evidence that no improvements exist. Verification
checks report coverage and issue existence, not the semantic quality of AI
analysis, actual tool concurrency, or exhaustive semantic duplicate detection.

Run the deterministic helper tests locally with:

```sh
python3 -m unittest discover -s tests -v
```
