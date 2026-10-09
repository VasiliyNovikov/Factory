# Factory event router

[Router](../../.github/workflows/factory-router.yml) uses Copilot to dispatch
workers or skip an event.

Apply the [shared routing policy](routing-policy.md) for eligibility, actionable
work, holds, feedback verification, dispatch, concurrency, and reporting.
[Periodic maintenance](factory-maintenance.md) uses the same policy for missed work.
This guide owns event selection, push fan-out, and event-specific provenance.

## Event selection

### [PR review](pr-review.md)

- A PR is opened, reopened, marked ready, or receives new commits, including
  clean default-branch merges.
- A PR conversation comment requests review or gives new context for reassessment.

### [Issue / PR implementation](issue-implementation.md)

- An issue receives `triaged`.
- An issue or PR conversation has actionable implementation feedback.
- A submitted review contains findings or change requests, including inline findings.
- PR-linked CI fails or times out.

### [Issue triage](issue-triage.md)

- An issue is opened without `triaged`.
- A comment provides clarification or follow-up on an open untriaged issue.

## Default-branch maintenance

- A non-deletion default-branch push routes **all**
  [eligible Factory PRs](routing-policy.md#issue--pr-implementation), not just those
  referenced by pushed commits. No feedback or CI failure is required. Include
  already-current PRs; implementation owns the verified no-op decision.
- Dispatch one implementation worker per PR for
  [PR-scoped base maintenance](issue-implementation.md#default-branch-maintenance).
  Mergeability does not gate routing.
- Include discovery, dispatch verification, and complete/partial reporting in the budget.
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

- `factory-worker-bot[bot]` conversation comments (created or edited) and submitted
  reviews (job-filtered by author, including when someone else edits the comment).
- Approvals (job-filtered for submitted reviews, regardless of author).
- Non-`triaged` issue-label events (job-filtered).
- Fork PR lifecycle events and submitted reviews (job-filtered); fork detection
  for conversation comments remains AI-owned.
- Successful CI without review findings.
- Cancelled runs.
- Router completions and completions triggered by `workflow_dispatch` or `schedule`
  are job-filtered regardless of conclusion, including future non-Factory workflows.
  Other `workflow_run` events require a same-repository head. Source-review findings
  enter through new issues.

Ignoring a completion event does not prevent periodic recovery when the
[shared retry rules](routing-policy.md#dispatch-reconciliation-and-retries) permit it.

## Feedback and event handling

- Created or edited issue/PR conversation comments and submitted reviews trigger routing.
- Standalone inline comments and replies arrive as empty-body `COMMENTED`
  reviews through the existing `pull_request_review: submitted` trigger.
- Edits to inline review comments, review bodies, and issue/PR bodies remain
  unsupported as routing triggers.
- Reviewer-App submissions use `pull_request_review: submitted`, not PR-review
  `workflow_run` events, to avoid duplicate delivery.
- Apply [shared feedback verification](routing-policy.md#feedback-verification)
  before routing reviewer-App findings. If the event arrives before the source
  assessment completes, wait within the job budget for completion.
- Router reruns need the same source attempt to succeed. A worker rerun or
  current-head review request can provide the fresh assessment required by the
  shared policy.

## Dispatch and reporting

Base pushes use the fan-out above; other events dispatch at most one worker.
Follow the [shared dispatch contract](routing-policy.md#dispatch-contract) with
these event-specific `source` fields:

- Conversation-comment edits use `event: "issue_comment"`, `action: "edited"`,
  and the original `comment_id`, without new worker inputs.
- Push maintenance includes `event: "push"`, `ref`, and `after` in `source` for
  provenance, not as live revision checks.

## Accepted risk: router changes can run before merge

- Submitted reviews run the **PR merge revision** of the router, local actions,
  setup scripts, configuration, and guidance.
- That code can use the router's Actions-write token before merge, including for
  unwanted dispatches or other authorized actions. Prompt restrictions and worker
  guards do not isolate it.
- This risk is accepted. Old PRs may have outdated contracts; keep changes small
  and compatible with default-branch workers.

## Execution and verification

- Router events run independently; worker coordination follows the shared policy.
- Router events other than submitted reviews, and all workers, use the default
  branch. Checkouts use `github.workflow_sha`; manual non-default jobs skip in
  versions with the guard.
- Static checks do not establish AI adherence or end-to-end event delivery.
  A PR cannot exercise its changed default-branch push or
  [`issue_comment`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issue_comment)
  triggers. After merge, link an edited test-issue comment to its router run and
  verified worker dispatch or reasoned skip.
