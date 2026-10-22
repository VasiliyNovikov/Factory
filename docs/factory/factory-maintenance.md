# Periodic Factory recovery

[Maintenance AI](../../.github/workflows/factory-maintenance.yml) recovers unattended
issue/PR lifecycle work using the [shared routing policy](routing-policy.md).
It dispatches existing workers, not repairs, findings issues, or another router.

Follow the [host/target contract](target-context.md). Use API-only target context
and keep the executing Factory checkout unchanged.

## Invocation and scope

- Run every six hours at **00:00, 06:00, 12:00, and 18:00 UTC** (`0 */6 * * *`),
  or through **Actions -> Factory maintenance -> Run workflow** on the default
  branch. GitHub may delay scheduled runs; this is not a recovery-time guarantee.
- Both entry points use the host's default branch. Checkout uses `github.workflow_sha`
  in `factory/`; target validation precedes AI setup. The pinned shared AI action
  uses the existing `route` profile, and active sweeps are serialized without
  cancellation.
- Use only the built-in token with Actions write for dispatch and
  Contents/Issues/Pull requests read for discovery, plus Copilot model access.
  No App token, new secret, or repository/App setting change is required.
- This is recovery orchestration, distinct from [workflow diagnostics](workflow-diagnostics.md)
  and [repository review](repository-review.md). Do not implement work, post comments,
  change labels, approve requests, or create issues/PRs.

## Discovery and decisions

- Discover current open issues and same-repository PRs through paginated native
  APIs. Inspect each relevant discussion, labels, ownership, revisions, native
  children/dependencies, and workflow outcomes. Use all-state branch/PR/child
  history when needed to avoid reviving delivered or deliberately split work.
- Do not limit discovery to recently updated targets or the interval since the
  last sweep: missed events can leave old work untouched. Earlier sweep evidence
  helps reconcile actions but is not a watermark excluding unresolved work.
- Establish an actionable lifecycle gap, not merely an old `updated_at`:
  - An open untriaged issue lacks an assessment, has a new answer/request awaiting
    triage, or has an incomplete ready-comment/tracking-label handoff.
  - An eligible ready issue has no active/completed implementation, or verified
    partial work needs recovery rather than another response to an unchanged hold.
  - An eligible PR lacks a successful assessment covering its current head and
    [review context](pr-review.md#review-coverage), including after a failed/skipped
    assessment or a verified same-head correction without an explicit review request.
  - An eligible Factory PR has outstanding implementation feedback, applicable
    current-revision CI failures, or lacks the current default-branch revision.
- Apply shared eligibility, feedback-source verification, human holds, and duplicate
  checks, including the [unsuccessful-recovery retry gate](routing-policy.md#dispatch-reconciliation-and-retries),
  before selecting a worker. Skipped/stale runs require reassessment of current
  need; their conclusion alone does not justify another dispatch.
- For base recovery, compare the exact live PR head/default-branch ancestry;
  GitHub mergeability, an old push SHA, or the PR's age is not evidence of currency.
  Assign base-only maintenance to that existing PR with the implementation
  worker's restricted scope.
- Recover multiple independent targets, but select only the next needed stage for
  each issue/PR lifecycle. Do not send both issue-only and PR implementation for
  the same issue, or review a head already selected for implementation/base updates.
  Defer dependent stages until their prerequisites produce verifiable state.
- A `triaged` issue with invalid tracking labels has no eligible triage or
  implementation handoff. Report the blocker; the coordinator cannot repair it.
- If pagination, required reads, or coverage cannot finish within the
  [invocation budget](../examples/ai-tools.md#invocation-budget), identify unexamined
  targets/pages and remaining work. Never describe incomplete discovery as no work.

## Dispatch provenance and recovery

- Follow the [shared dispatch contract and reconciliation rules](routing-policy.md#dispatch-contract);
  recheck against ordinary router/worker activity before each dispatch.
- Set `router_run_id` to this maintenance run's ID. In `source`, use:
  - The actual invocation `event`: `schedule` or `workflow_dispatch`.
  - `action: "recover"`, `coordinator_workflow: "factory-maintenance.yml"`, and
    `coordinator_run_attempt` for this attempt.
  - The target IDs and a `reason` describing the outstanding gap. Identify a
    base-only assignment explicitly as default-branch-only maintenance, with the
    observed default `ref` and `after` revision.
  - Original comment/review/CI identifiers when applicable; reviewer-App
    `run_id`/`run_attempt` remain the verified source assessment's identifiers.
- Do not fabricate an `issues`, `pull_request_review`, or `push` event to make the
  sweep look like the original trigger. The expected PR head is current context,
  not a claim that an older finding was reviewed at that head.
- For an incomplete sweep, recovery is a native rerun of the originating
  maintenance run or a later sweep after reconciling its accepted/uncertain work.
  Do not cancel other runs or add durable markers, labels, or a custom queue.

## Reporting and verification

- Append a job summary covering examined issues/PRs and history, coverage gaps,
  target repository/head/default revisions separately from the Factory revision,
  source evidence, chosen workers, verified host acceptance/run links,
  skipped/blocked reasons, and outstanding work.
- The router ignores maintenance completions; worker events retain their ordinary
  routing. There is no receipt/report workflow or new feedback loop.

Use these representative decisions for focused manual verification of the shared
policy and entry-point wiring, not a wording-only test suite:

| Evidence | Decision |
|---|---|
| Ready comment and matching tracking label, no `triaged`, interrupted triage, no active equivalent | Dispatch triage to reassess and finish the handoff; do not label directly. |
| Ready issue, no branch/PR/child-owned work or active implementation | Dispatch issue-only implementation. |
| Review posted but source assessment failed its receipt check; retry gate permits recovery | Dispatch a fresh current-head review if still needed; do not forward its findings. |
| Current successful review covers the current code and review-relevant context | No review dispatch, including repeated reports of an already-assessed correction. |
| Successful `COMMENTED` review, then a verified relevant description correction at the same head | Dispatch review if no equivalent work is active; an explicit human request is unnecessary. |
| Factory PR reply demonstrates a finding was already satisfied; that evidence has not been reassessed | Verify the evidence and dispatch review, not another implementation or an approval. |
| Description edit and Factory reply describe the same correction; an equivalent review is active | No duplicate dispatch; head equality alone is insufficient to establish equivalence. |
| Cosmetic metadata edit or routine Factory report with no uncovered review context | No review dispatch. |
| Same-head follow-up on a closed, draft, or fork PR, or only unapproved external scope | No review dispatch; preserve eligibility and owner-decision holds. |
| Matching current assignment queued/running under the ordinary router | No equivalent recovery dispatch. |
| Recovery failed/timed out/cancelled; same worker, target, revisions, and request in a later scheduled/manual sweep | Record the blocker and failed run links; no equivalent dispatch. |
| After failed recovery, relevant revision or actionable feedback changes, or a human explicitly requests retry | Reassess eligibility, partial outcomes, and active work before dispatching remaining work. |
| Unanswered Factory question, pending owner decision, rejection, or parent awaiting children | Record the hold; no recovery dispatch without changed evidence. |
| Factory PR missing the live default revision, otherwise eligible and unblocked | Dispatch PR-scoped implementation for a base update, not issue creation. |
| Batch accepted A, response for B uncertain, C not attempted | Reconcile A/B before retries; dispatch C only if still eligible. Report partial recovery. |
| Page/API failure after examining only some targets | Report incomplete coverage and actual accepted work, not a clean no-work result. |

Static/contract checks and these manual decisions do not prove AI adherence, race
freedom, or live GitHub recovery. No live schedule is exercised by a PR alone.
