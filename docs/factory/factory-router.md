# Factory event router

[Router](../../.github/workflows/factory-router.yml) uses Copilot to dispatch
workers or skip an event. Keep routing simple and AI-led; workers own execution,
freshness checks, and result verification.

Apply the [shared routing policy](routing-policy.md) for eligibility, actionable
work, holds, feedback verification, and dispatch reconciliation.
[Periodic maintenance](factory-maintenance.md) uses the same policy for missed work.

## Event selection

### [PR review](pr-review.md)

- A PR is opened, reopened, marked ready, or receives new commits.
- A PR conversation comment requests review or gives new context for reassessment.

### [Issue / PR implementation](issue-implementation.md)

- An issue receives `triaged`.
- An issue or PR conversation has actionable implementation feedback.
- A submitted review contains findings or change requests, including inline findings.
- PR-linked CI fails or times out at the current head or merge revision.

#### Implementation eligibility

Use the [shared implementation eligibility rules](routing-policy.md#issue--pr-implementation).
The issue-only path remains PR-optional; push maintenance requires an existing PR.

### [Issue triage](issue-triage.md)

- An issue is opened without `triaged`.
- A comment provides clarification or follow-up on an open untriaged issue.
- PR conversations are not issue triage.

## Default-branch maintenance

- A non-deletion default-branch push routes **all** [eligible](#implementation-eligibility)
  Factory PRs, not just those referenced by pushed commits. No feedback or CI failure
  is required; an existing PR is.
- Dispatch one implementation worker per eligible PR to merge the current default
  branch and resolve conflicts in that PR only. Mergeability does not gate routing.
- Include discovery, dispatch verification, and complete/partial reporting in the budget.
- Assign each PR's live head, not a superseded push revision. Never create issues or PRs.
- The push trigger lists `master`; update that filter if the default branch is
  renamed. Ordinary Factory-branch pushes do not match. This filter is not an
  isolation boundary against actors able to rewrite workflows.

GitHub has no documented [mergeability-change event](https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request);
[`synchronize`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
follows head, not base, updates. [Mergeability calculation](https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database#checking-mergeability-of-pull-requests)
is not a trigger, so base-update discovery belongs in coordinators, not in each implementer.

## Skip

The job condition makes the noted payload-only skips zero-step jobs, before
checkout or AI setup. Copilot decides the rest.

- `factory-worker-bot[bot]` conversation comments and submitted reviews (job-filtered).
- Approvals (job-filtered for submitted reviews, regardless of author).
- Unrelated labels or events (job-filtered for non-`triaged` issue-label events).
- Fork PR lifecycle events and submitted reviews (job-filtered); fork detection
  for conversation comments remains AI-owned.
- Successful CI without review findings.
- Cancelled runs.
- Router, maintenance, triage, implementation, diagnostics, [repository review](repository-review.md),
  and [model profile improvement](model-profile-improvement.md)
  completions (job-filtered). Source-review findings enter through new issues,
  not self-triggered automation.
- Failed review-worker completions (job-filtered): these are not PR-code CI
  failures.
- Skipped review-worker completions (job-filtered): these have no findings.

The [shared holds and handled-work rules](routing-policy.md#holds-and-handled-work)
also apply. These event skips do not prevent periodic discovery of an unfinished
handoff or a needed fresh assessment after a failed/cancelled worker.

## Feedback and event handling

- Read worker-discovery, PR-review, and required provenance collections completely,
  following the [shared pagination guidance](../../AGENTS.md#github-cli-pagination).
- Humans and other bots may provide feedback.
- Main conversation comments and submitted reviews trigger routing.
- Standalone inline comments and replies arrive as empty-body `COMMENTED`
  reviews through the existing `pull_request_review: submitted` trigger.
  - Assess non-Factory inline comments and replies like other submitted reviews.
  - Read the review's inline comments and complete relevant thread history
    before deciding; an empty review body alone is not a reason to skip
    actionable feedback.
- Edited comments do not trigger routing.
  TODO: Support routing for edited comments.
- Reviewer-App submissions use `pull_request_review: submitted`, not PR-review
  `workflow_run` events, to avoid duplicate delivery.
- Apply [shared feedback verification](routing-policy.md#feedback-verification)
  before routing reviewer-App findings. If the event arrives before the source
  assessment completes, wait within the job budget for completion.
- Failed, incomplete, or conflicting source verification is failure, not a skip.
  Router reruns need the same source attempt to succeed. Failed, timed-out, or
  cancelled assessments need a [fresh assessment](pr-review.md#skip-and-report)
  from a worker rerun or current-head review request.

## Dispatch and reporting

- Dispatch on the current default branch: one implementation worker per eligible
  PR for base pushes, at most one worker for other events.
- Follow the [shared dispatch contract](routing-policy.md#dispatch-contract).
  `router_run_id` identifies this router run; `source` describes the triggering
  event and its applicable identifiers.
- Push maintenance includes `event: "push"`, `ref`, and `after` in `source` for
  provenance, not as live revision checks.
- Apply [shared dispatch reconciliation](routing-policy.md#dispatch-reconciliation-and-retries)
  across router attempts and periodic sweeps, including verified acceptance and
  distinct partial outcomes.
- Report recovery for incomplete batches through a native rerun of the original
  router run, without waiting for another push.
- Follow the shared [boundaries and reporting rules](routing-policy.md#boundaries-and-reporting);
  the router remains dispatch-only with its built-in token.

## Concurrency and freshness

- Router runs are independent; workers coordinate per issue/PR and check freshness.
- Review jobs serialize per PR/head, preserving the active assessment and its
  receipt check. Different heads run independently.
- Triage and implementation also preserve active jobs. Push maintenance and ordinary
  feedback share per-issue concurrency.
- Pending jobs can be replaced, so workers check the latest discussion and
  outstanding feedback. Explain AI-owned skips in the job summary.

## Accepted risk: router changes can run before merge

- Submitted reviews run the **PR merge revision** of the router, local actions,
  setup scripts, configuration, and guidance.
- That code can use the router's Actions-write token before merge, including for
  unwanted dispatches or other authorized actions. Prompt restrictions and worker
  guards do not isolate it.
- This risk is accepted. Old PRs may have outdated contracts; keep changes small
  and compatible with default-branch workers.

## Execution and verification

- Other router events and all workers use the default branch. Checkouts use
  `github.workflow_sha`; manual non-default jobs skip in versions with the guard.
- Static checks do not establish AI adherence or end-to-end event delivery.
  A PR cannot exercise its changed default-branch push trigger.
