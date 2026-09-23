# Router split options

**Recommendation: keep one router for now.** If maintenance fan-out becomes hard
to operate within its budget, split only default-branch pushes into a dedicated
job. Splitting by target worker adds coordination where comments can request
different kinds of work.

This is the documentation-only investigation for [#72](https://github.com/VasiliyNovikov/Factory/issues/72),
not a change to active routing instructions. The baseline is
[`f80aa5d`](https://github.com/VasiliyNovikov/Factory/commit/f80aa5d3b3ce2a892f61a69aa5c3767062323ee3),
inspected on 2026-09-23. No workflows, permissions, settings, or approval policy
are changed.

## Current boundary

[`factory-router.yml`](../../.github/workflows/factory-router.yml) has six event
families and one independent, 30-minute AI routing job. Its native condition
excludes non-default/deletion pushes, fork PRs, foreign-repository workflow runs,
and router/review-worker completions. Other skip decisions belong to its
[guidance](factory-router.md), not that condition.

Workers already separate execution by responsibility:
[triage](../../.github/workflows/issue-triage.yml),
[review](../../.github/workflows/pr-review.yml), and
[implementation](../../.github/workflows/issue-implementation.yml).
The remaining question is how to partition event interpretation, not whether to
split the workers again.

## Options

| Option | Responsibilities and native partition | Net tradeoff |
| --- | --- | --- |
| **A. One router** | Keep all current subscriptions in one job. Optional payload-only skip conditions can avoid unnecessary AI starts without introducing another owner. | Least setup/guidance duplication and no migration. Broadest routing context; one workflow's history mixes event families. |
| **B. Trigger-family routers** | Three exclusive jobs: **conversation/lifecycle** for issues, comments, and PR lifecycle; **feedback** for submitted reviews and CI completions; **maintenance** for default-branch pushes. Select by `github.event_name`. | Smaller task-specific context and clearer job outcomes. More caller configuration and guidance boundaries; feedback still has two different provenance rules. Moderate migration. |
| **C. Target-worker routers** | Triage owns issue intake; review owns PR lifecycle; implementation owns handoffs, findings, CI failures, and pushes. Shared comments need one arbiter before selecting a target. | Matches worker names but duplicates their existing separation. Native conditions cannot classify comment intent; an arbiter retains the central decision or adds another stage. Highest coordination/migration cost. |
| **D. Push-only hybrid** | Keep A for non-push events; one maintenance job exclusively owns `push`. Complementary job conditions prevent overlap. | Isolates the only one-to-many route and its recovery budget with little duplicated logic. Ordinary routing remains broad; a second job still needs setup and reporting. Smallest useful split. |

For B or D, prefer jobs in the existing workflow before separate workflow files:
they expose distinct job results without multiplying subscriptions and router
paths. Separate files improve workflow-level filtering and independent evolution,
but duplicate checkout/permissions/prompt wiring and expand completion exclusions.
Neither layout changes the submitted-review execution boundary described below.

Each admitted event still needs one routing AI invocation under A, B, or D.
Smaller context might help, but splitting alone saves neither tool installation
nor model starts. C can start competing models or add a classifier invocation.
All options should reuse the [shared AI action](../examples/ai-tools.md#shared-factory-action)
and authoritative dispatch guidance rather than copy them or add orchestration.
No latency, cost, or routing-error improvement has been measured here.

## Event ownership and outcomes

The selectors below preserve the current subscriptions. Every outcome remains
subject to live eligibility and may instead be a documented skip or failure.
A owns every row; D moves only the last row to maintenance.

| Event / native selector | Possible worker outcome | B owner | C owner |
| --- | --- | --- | --- |
| `issues: opened, labeled` | Untriaged opened issue: triage. Matching `triaged` label handoff: implementation. Other labels: skip. | Conversation | Triage or implementation, partitioned by activity/label |
| `issue_comment: created`; `github.event.issue.pull_request` distinguishes PRs | Issue: triage or implementation. PR: review reassessment or implementation. Non-actionable/handled comments: skip. | Conversation | **One shared arbiter**, then one target |
| `pull_request_target: opened, synchronize, reopened, ready_for_review` | Review a current, open, non-draft, same-repository PR. | Conversation | Review |
| `pull_request_review: submitted` | Implementation for actionable findings/change requests; approvals and Factory-worker reviews skip. Reviewer-App findings require successful source verification. | Feedback | Implementation |
| `workflow_run: completed`, `workflows: ['*']` | Implementation for PR-linked failed/timed-out CI at the current head or merge revision. Non-failures and Factory workflow completions skip. | Feedback | Implementation |
| `push: branches: [master]`; non-deletion and current-default-ref guard | One implementation dispatch per eligible Factory PR, or no work. | Maintenance | Implementation |

### Native conditions versus AI decisions

- `on.<event>.types` selects activities, not issue label names, review states, or
  CI conclusions. Those can use [`jobs.<id>.if`](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)
  before checkout/AI setup. A skipped job can still appear in workflow history.
- Candidate early skips include unrelated issue labels, approvals, Factory-worker
  comments/reviews, and non-failing CI completions. Preserve Factory-created
  issues, label handoffs, PR updates, and reviewer-App submissions; a blanket
  bot exclusion would break them. These refinements are possible under A too.
- Keep both issue and PR conversation intent with one owner. An issue/PR flag
  separates object types, not a request to implement from a request to reassess.
  Live labels, ownership, discussion, and review evidence still need evaluation.
- Do not let review and implementation independently consume the same PR comment.
  Worker concurrency coordinates execution, not routing arbitration, and cannot
  establish the at-most-one-dispatch contract.

### Avoiding gaps and loops

Keep the [existing skip and retry rules](factory-router.md#skip) shared. Exclude
completions of **every** router plus triage, implementation, diagnostics,
repository review, and PR review. Failed review workers are not PR-code CI
failures; successful reviewer findings arrive through submitted reviews, never
a second `workflow_run` route.

App-generated issues, labels, pushes, and reviews intentionally produce downstream
events. [GitHub's token-trigger behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)
is not a replacement for these exclusions. Retain `workflow_dispatch`, not a new
chain of completion-triggered routers. Edited comments and standalone inline
replies remain unsupported triggers; a split must not silently promise coverage.

## Contracts every option must preserve

- **Dispatch and recovery:** Keep the current default-branch worker YAML/input
  contracts, including `source`, `router_run_id`, and paired implementation
  `source_pr`/`head_sha`. Non-push events dispatch at most one worker. Pushes retain
  per-PR fan-out, verified acceptance, partial-outcome reporting, and native-rerun
  recovery without duplicating accepted work. Acceptance is not worker completion.
- **Freshness and concurrency:** Routers remain independent. Workers own live
  eligibility, current revisions, outstanding feedback, and existing per-issue
  or per-PR/head concurrency without cancelling active work. No global router lock
  or deterministic stale-payload substitute is needed.
- **Review provenance:** Preserve the [successful source-assessment check](factory-router.md#feedback-and-event-handling):
  PR membership, reviewer identity, run/attempt marker, and full reviewed SHA
  matching that attempt's `PR_HEAD_SHA`. Wait within budget for successful,
  non-skipped completion including its posted-review check. Neither a later
  review API `commit_id` nor the worker run's default-branch `head_sha` substitutes
  for it. Still-applicable findings survive head drift; failed/unverifiable
  assessment evidence is a failure, not a skip.
- **Execution and tokens:** Per [GitHub's event reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
  issues, comments, PR-target events, and workflow completions use default-branch
  context; this repository restricts pushes to that branch. Submitted reviews
  use the **PR merge revision**, including local router actions, scripts, and
  guidance, with the router's Actions-write token. This
  [accepted pre-merge risk](factory-router.md#accepted-risk-router-changes-can-run-before-merge)
  remains under every split, even separate files. Preserve `github.workflow_sha`
  setup checkouts and default-branch worker dispatch compatibility.
- **Authority:** Routers use the built-in token for dispatch and permitted reads,
  not App credentials or other mutations. Workers keep their existing Factory/
  reviewer App boundaries; model credentials stay separate from repository
  operations. Fetched content remains untrusted data, not authorization.

### Adjacent owner-approval work

[#69](https://github.com/VasiliyNovikov/Factory/issues/69)'s
[latest owner decision](https://github.com/VasiliyNovikov/Factory/issues/69#issuecomment-5792690954)
accepts **AI-managed owner approval**, superseding its original pre-Copilot gate
proposal. At this snapshot, [#71](https://github.com/VasiliyNovikov/Factory/pull/71)
is open and unmerged: external issues may reach router/triage to request scoped
approval; approval resumes readiness assessment rather than granting `triaged`.
External feedback needs its own applicable authorization.

A later router change should reuse the adopted shared approval policy, not
reinvent it per event family or treat a native event filter as a trust decision.
This investigation neither implements #69 nor depends on its merge. Splitting
routers does not provide a spending limit or an isolation boundary.

## Decision and bounded follow-up

Choose **A now**: there is no demonstrated operational problem that outweighs
extra routing owners. If fan-out duration/recovery or mixed-context mistakes
become a concrete problem, choose **D before B**. Reject C unless a future request
provides a genuinely exclusive target-selection contract; adding a classifier
merely to make this split work is not simplification.

Open choices for a later issue are whether observed run evidence justifies a
split, jobs versus separate files, and which payload-only skips are worthwhile.
No new issues or implementation are needed to complete this comparison.

For a selected split, bound a follow-up to the following outcomes:

1. **Exclusive ownership:** Move only the selected event family in one cohesive
   change; keep shared contracts in one place. Inspect default-branch and eligible
   PR merge revisions, including older router copies, so cutover/rollback does
   not activate both owners or lose events. Reconcile already accepted dispatches.
2. **Static verification:** Check actual subscriptions/job conditions against the
   table, worker input compatibility, token permissions, and all completion
   exclusions. Exercise any changed condition with representative payloads.
   Cover shared comments, unrelated labels, fork/draft PRs, approvals/findings,
   failed/skipped source reviews, current/stale CI, and default/non-default pushes.
3. **Live verification after deployment:** Record source events, exact revisions,
   router attempts, accepted dispatches, and worker links. Verify one owner and
   at most one worker for non-push events; multi-PR fan-out and partial-rerun
   recovery for pushes; source-review completion races and no duplicate feedback.
   Preserve explicit failures and outstanding work in summaries.

This document is based on source/discussion inspection and GitHub documentation,
not executed alternative routers. The existing guidance still records pending
[reviewer-App handoff](pr-review.md#verification-limits) and
[fan-out verification](factory-router.md#execution-and-verification). Static
checks cannot establish live event delivery, AI adherence, or performance gains.
