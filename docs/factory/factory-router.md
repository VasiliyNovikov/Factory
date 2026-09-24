# Factory event router

[Router AI](../../.github/workflows/factory-router.yml) decides which workers an event
needs, or skips it.

- Keep the router simple and AI-driven.
- Apply the [shared routing policy](routing-policy.md) for worker eligibility,
  actionable work, holds, feedback verification, and dispatch reconciliation.
  [Periodic maintenance](factory-maintenance.md) uses the same policy for missed work.
- Workers own execution, freshness checks, and result verification.

## Event selection

### [PR review](pr-review.md)

- A PR is opened, reopened, marked ready, or receives new commits.
- A PR conversation comment requests review or provides clarification requiring
  reviewer reassessment.

### [Issue / PR implementation](issue-implementation.md)

- An issue receives `triaged`.
- An issue or PR conversation contains actionable implementation feedback.
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

- A non-deletion default-branch push routes all eligible Factory PRs, not just PRs
  referenced by the pushed commits. [Implementation eligibility](#implementation-eligibility)
  applies without requiring a comment, review, or CI failure.
- Push maintenance requires an existing PR; the PR-optional issue-only path does
  not apply.
- Each eligible PR gets its own implementation worker. Workers bring only
  their assigned PR up to date with the current default branch, resolving any
  conflicts. Routing does not depend on mergeability or conflict detection.
- The job budget includes discovery, dispatch verification, and reporting of
  complete or partial outcomes.
- Assignments identify existing PRs at their current live heads, not a possibly
  superseded push revision. Maintenance routing never creates issues or PRs.
- The push trigger lists `master`; update that filter if the default branch is
  renamed. Ordinary Factory-branch pushes do not match. This filter is not an
  isolation boundary against actors able to rewrite workflows.

GitHub documents no [mergeability-change event](https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request).
[`synchronize`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
follows PR head updates, not base-only advances. The
[UI/API mergeability calculation](https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database#checking-mergeability-of-pull-requests)
is not a separate trigger; custom dispatch would still need a detector.
Default-branch discovery therefore belongs in coordinators, not in each implementer.

## Skip

The job condition enforces the payload-only skips noted below before checkout
or AI setup. Other skip decisions remain AI-owned.

- `factory-worker-bot[bot]` comments/reviews (job-filtered for conversation
  comments only; submitted reviews still reach AI).
- Approvals.
- Unrelated labels or events (job-filtered for non-`triaged` issue-label events).
- Fork PR lifecycle events and submitted reviews (job-filtered); fork detection
  for conversation comments remains AI-owned.
- Successful CI without review findings.
- Cancelled runs.
- Router, maintenance, triage, implementation, diagnostics, or
  [repository review](repository-review.md) completions (job-filtered).
  Automation must not trigger itself; source-review findings enter through new
  issues instead.
- Failed review-worker completions (job-filtered): these are not PR-code CI
  failures.
- Skipped review-worker completions (job-filtered): these have no findings.

The [shared holds and handled-work rules](routing-policy.md#holds-and-handled-work)
also apply. These event skips do not prevent periodic discovery of an unfinished
handoff or a needed fresh assessment after a failed/cancelled worker.

## Feedback and event handling

- Humans and other bots may provide feedback.
- Main conversation comments and submitted reviews trigger routing.
- Standalone inline replies and edited comments do not trigger routing.
  TODO: Support routing for standalone inline replies and edited comments.
- Reviewer-App submissions use `pull_request_review: submitted`; PR-review
  `workflow_run` events are excluded to avoid duplicate delivery.
- Apply [shared feedback verification](routing-policy.md#feedback-verification)
  before routing reviewer-App findings. If the event arrives before the source
  assessment completes, wait within the job budget for completion.
- Failed, incomplete, or conflicting source verification is a failure, not a skip.
  A router rerun requires that same source attempt to succeed; failed, timed-out,
  or cancelled assessments need a [fresh assessment](pr-review.md#skip-and-report)
  via a review-worker rerun or a current-head review request.

## Dispatch and reporting

- Dispatch on the current default branch. Default-branch pushes may dispatch one
  implementation worker per eligible PR; all other events dispatch at most
  one of the three workers.
- Follow the [shared dispatch contract](routing-policy.md#dispatch-contract).
  `router_run_id` identifies this router run; `source` describes the triggering
  event and its applicable identifiers.
- For push maintenance, include `event: "push"`, `ref`, and `after` in `source` for
  provenance, not as a substitute for workers' live revision checks.
- Apply [shared dispatch reconciliation](routing-policy.md#dispatch-reconciliation-and-retries)
  across router attempts and periodic sweeps, including verified acceptance and
  distinct partial outcomes.
- Reports of incomplete batches must identify recovery through a native rerun of
  the original router run, without depending on another push.
- Follow the shared [boundaries and reporting rules](routing-policy.md#boundaries-and-reporting);
  the router remains dispatch-only with its built-in token.

## Concurrency and freshness

- Router runs are independent.
- Workers coordinate per issue/PR and check freshness before acting.
- Review jobs serialize per PR/head without cancelling the active assessment or
  its posted-review check. Different heads run independently.
- Triage and implementation preserve active jobs.
- Push maintenance and ordinary feedback share the existing per-issue worker
  concurrency.
- Pending jobs can be replaced, so workers consider the latest discussion and
  outstanding feedback.
- AI-owned skips are explained in the job summary.

## Accepted risk: router changes can run before merge

- Submitted reviews execute the router from the **PR merge revision**, including
  its local actions, setup scripts, configuration, and guidance.
- Changes can run before merge with the router's Actions-write token, causing
  broken routing, unwanted dispatches, or other token-authorized actions.
- Prompt restrictions and worker guards do not isolate modified router code.
- Old PRs may have outdated routing or worker contracts.
- This is an accepted tradeoff; keep router changes small and compatible with
  default-branch workers.

## Execution and verification

- Other router events and all workers use the default branch.
- Setup checkouts use `github.workflow_sha` to match the executing workflow.
- Manual jobs skip non-default refs in workflow versions containing the guard.
- Central review dispatch has been verified live. The reviewer-App handoff still
  needs [post-deployment verification](pr-review.md#verification-limits).
- Default-branch fan-out needs post-merge verification; a PR cannot exercise its
  changed default-branch push trigger before deployment.
- Payload-only comment, label, and completion guards need post-merge verification:
  a Factory comment must skip the router job without AI setup, while a `triaged`
  handoff must still dispatch implementation.
- Static checks do not establish AI adherence or end-to-end event delivery.
