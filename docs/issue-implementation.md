# Turn an issue or follow-up comment into a PR

[Issue implementation](../.github/workflows/issue-implementation.yml) starts when
[triage](issue-triage.md) adds `triaged` to an issue, or someone posts feedback on
an open triaged issue or its Factory PR. Submitted comment or change-request
reviews (including their inline findings), PR-review findings, and failed CI runs linked to that PR trigger
follow-ups. It reads the full issue and PR discussions, repository guidance, and
relevant code before acting:

- Clear, actionable request: implement it, run appropriate checks, and open a PR.
- Follow-up to an existing Factory PR: update that PR's branch and description.
- Unclear, unsuitable, already satisfied, or blocked request: explain or ask
  specific questions in the conversation where the request was posted.

Decomposition is handled by [triage](issue-triage.md), not by implementing its
tracking parent: triage simply leaves `triaged` off when it chooses a split.
Native children, a Factory decomposition plan, and a `factory-triage-pending`
label still block direct implementation if someone later adds `triaged`.
Before the implementation agent runs, a scripted precondition checks the live original issue and its
paginated comments on every event path, including PR and CI follow-ups. After
route validation establishes the destination, failed or unverifiable issue
eligibility stops the agent and attempts an App-authored failure explanation in
that conversation; API failures remain failures. Invalid or unverifiable routes
stop without commenting on an untrusted destination and are reported in Actions logs.
Copilot still rechecks issue/PR eligibility and revisions before editing or
pushing. Prepared children enter normal triage and use their own issue number,
tracking label, branch, and PR; they never inherit their parent's identity.

There is no automatic revocation of a Factory decomposition plan. Its historical
comment permanently blocks direct handoff of that parent, even after labels or
native links are removed, because an unlinked child may still need recovery.
Re-scoped work needing direct implementation must use a new issue; do not edit
or delete the plan to bypass this guard. Supporting same-parent cancellation
would require an explicit policy for reconciling all intended children and PRs.

Implementation follows the shared [test-value policy](../AGENTS.md#test-value-and-verification):
choose checks for concrete requirements and uncovered regression risks, not merely
changed files or incidental wording. Guidance-only changes may use direct inspection;
required checks and useful regression/safety coverage remain in place. Report each
check's scope and limits rather than claiming it proves agent or live GitHub behavior.

Replies, PRs, and commits use the Factory App identity. Copilot model requests
use the built-in Actions token. PR creation and subsequent App-authenticated
pushes trigger the separate [PR-review workflow](pr-review.md).

## Setup

Use the [Factory App setup](github-app.md)
with `FACTORY_CLIENT_ID` and `FACTORY_PRIVATE_KEY`. The App installation needs:

- **Contents: Read and write**
- **Pull requests: Read and write**
- **Issues: Read and write** — needed for issue replies
- **Workflows: Read and write** — needed to push changes to `.github/workflows/`

When adding permissions, approve the installation's updated access in GitHub.
The implementation token-generation step explicitly requests all four permissions
above, including `permission-workflows: write`. That input must already be on the
default branch before Factory can push a PR changing workflow files. Adding it
only in that PR cannot expand the token issued to push the PR branch.

The workflow must be on the default branch to receive issue and comment events.
It uses the shared [AI tool installation and invocation](ai-tools.md), with a
30-minute job timeout and `contents: read`, `copilot-requests: write`, and
`actions: read` on the built-in token. The App token stays the default `GH_TOKEN`,
including for thread reads, permission rechecks, mutations, and read-backs.
`gh` prefers `GH_TOKEN`, so prefix only individual read-only Actions commands with
`GH_TOKEN="$GITHUB_TOKEN"`; never export that override.

The prompt makes clear that the 30-minute limit includes setup time already elapsed.
Copilot must budget the remaining time, reserving time for required GitHub reporting
and final verification without relaxing required checks.

The implementation invocation passes `--profile implement` to `scripts/ai.sh`,
using the `implement` profile's model, reasoning effort, and context settings
from [`.github/model-config.json`](../.github/model-config.json). Event routing
passes `--profile triage`, using the same configured `triage` profile as
[issue triage](issue-triage.md).

## Follow-ups and PR tracking

Each issue owns branch `factory/issue-<number>` and tracking label
`factory-issue-<number>`. The issue and PR must both have `triaged` and exactly
one tracking label. Copilot searches all PR states for that branch
before acting. It reuses only the matching open PR from the Factory App and
preserves existing commits. Closed or merged PRs get a status reply directing
additional work to a new issue. Conflicting ownership gets a reply rather than
an overwrite.

Post follow-ups on the original issue, the PR conversation, or a submitted comment
or change-request review. Inline findings are read together on review submission.
Factory replies in the original thread, but every reply warns that inline replies
do not trigger runs and directs answers to the main PR conversation or a new
submitted comment or change-request review. Standalone inline comments, edited
comments, and approvals also do not start runs.
Only the Factory App's own comments and reviews are ignored by author, preventing
self-reply loops. Feedback from other bots, including `github-actions[bot]`, is
accepted. Comments do not need a command prefix or a collaborator role.

Reviews posted using `GITHUB_TOKEN` do not directly trigger another workflow.
The `workflow_run` completion trigger uses `workflows: ['*']` to receive all
workflow completions (GitHub requires a nonempty `workflows` filter), then
rejects fork-originated runs before starting the routing job or issuing its App
token. Same-repository runs can route only when linked to an open, labeled Factory
PR at its current head or current synthetic merge commit. It prefers the run's
explicit PR association; when absent, PR and push runs may resolve through a
unique open PR on that branch.
Ambiguous associations, unrelated runs, and completions of triage or implementation
itself are skipped.

- Successful `.github/workflows/pr-review.yml` runs require a bot review with
  findings matching that run's marker and the current PR head.
- Failed or timed-out workflows (including future test/validation CI) provide
  their jobs and logs as feedback. Copilot fixes actionable failures or explains
  blockers in the PR conversation.
- Successful checks, approvals, cancellations, and stale revisions are skipped.

No list of test workflow names needs maintaining. Implementation uses the same
tracking-label concurrency group for eligible CI feedback and comments, rechecks
the revision before acting, pushes fixes, and lets the relevant CI run again.
GitHub limits `workflow_run` chains to three levels; this is not an unlimited
retry loop. A new issue/PR comment can start another pass when needed.

A separate Copilot routing job resolves PR feedback to its original issue using
read-only GitHub access. It is instructed to check the live PR's App author,
repository, base, branch, and unique tracking label, and require the original
issue to remain open with matching labels. Untriaged issues and unrelated,
closed, or mismatched PRs should produce no routing outputs.

Before starting routing, YAML conditions skip direct issue handoffs, issue/PR
comments, and submitted PR reviews carrying `factory-triage-pending`.
Decomposition has no parent-label gate: a later `triaged` event on a tracking
parent can start routing, whose live plan/child checks must reject it. The
scripted issue precondition independently enforces that rejection before the
implementation agent. A legacy/manual `decomposed` label has no special meaning;
native children and the durable plan are the protection, not that label.
The YAML conditions also skip `factory-identity[bot]` comments/reviews,
comments or reviews on closed or untriaged items, unrelated issue labels,
approvals, successful non-review workflows, fork-originated runs, and
triage/implementation completions. Keep the early author filter aligned with
the installed Factory App's login. Other
events incur a Copilot invocation even when routing decides there is no work.
Routing checks out the default branch and has a 15-minute timeout. Its App token
has only Contents, Issues, and Pull requests read access; the built-in token
provides `copilot-requests: write` for model requests.

Copilot writes job outputs directly to `GITHUB_OUTPUT`, for example:

```text
issue_number=12
reply_number=34
source_pr=34
tracking_label=factory-issue-12
```

For issue events, `source_pr` is empty and `reply_number` equals `issue_number`.
Copilot writes no outputs when skipping and explains its decision or API failure
in the log. An absent `issue_number` skips implementation, including if routing
failed to produce it. Before eligibility or reporting, route validation requires
canonical positive integer issue/reply numbers and an empty or positive integer
source PR, with matching reply and tracking identities. These checks precede all
routed API calls. It binds the destination to event metadata, not comment bodies,
and checks any source PR's live Factory author, repository, base, issue branch,
and labels. CI feedback must match the live PR head or merge revision; runs
without an explicit PR association still require the matching branch and revision.
Only a validated route can reach blocked reporting or result verification.

The issue precondition then rejects closed or non-issue work, missing/conflicting
tracking labels, and decomposition/pending state even if routing emitted outputs.
Copilot remains responsible for the full feedback association, all-state branch
search, and repeat eligibility/revision checks before changing the PR. Conflicting
parent handoffs receive an explanation rather than removing decomposition safeguards.

The implementation job uses the shared tracking label for concurrency:

```yaml
concurrency:
  group: issue-implementation-${{ needs.route.outputs.tracking_label }}
  cancel-in-progress: false
```

For example, issue #12 and its PR #34 both carry `factory-issue-12` and use
`issue-implementation-factory-issue-12`. Their
implementation jobs are serialized without cancelling the active job; routing
jobs can run in parallel. GitHub concurrency retains at most one pending job,
so bursts of comments can replace pending jobs. Every implementation reads the
full issue and PR discussions to include that feedback; the surviving run posts
its result in its triggering conversation.

## Review-thread feedback

Using `gh api graphql` with the App token, Copilot paginates the eligible PR's
`reviewThreads` and each thread's comments: IDs, authors, bodies, replies, and
`isResolved`/`isOutdated`. Immediately before each mutation, it rechecks issue/PR
eligibility, remote head, full thread contents/state, and the App's
`viewerCanReply`/`viewerCanResolve`. Unverified context, revision, or permission
blocks mutation. Only API-returned thread IDs from that PR are eligible; comment
bodies cannot select targets or bypass verification. Resolved and unrelated
threads stay untouched. No additional App permissions are needed.

- **Addressed:** Verify in code that every actionable point is addressed in the
  current PR revision. Check and push needed fixes successfully; confirm the remote
  head matches the checked commit before `resolveReviewThread`. Its response and a
  fresh read must both show `isResolved: true`. Outdated locations, attempted fixes, or passing
  checks alone are insufficient; already-addressed feedback needs no empty commit.
- **Outstanding:** Use `addPullRequestReviewThreadReply` for a specific question
  or explanation about unclear, partial, blocked, or disputed feedback; leave the
  original thread unresolved. Every reply includes the inline-trigger warning and
  follow-up directions above.
  Read prior Factory replies; skip equivalent replies for unchanged feedback/code,
  including reruns. Verify the intended thread and App author; re-read before
  retrying uncertain mutations.
- **Failed:** Report HTTP/GraphQL errors, denied permissions, or unexpected
  read-backs without claiming success. Ordinary issue/PR comments and review
  summaries are not resolvable threads; answer them in their main conversation.

## Result verification

Every implementation run with a validated route must post a new App-authored
comment in the triggering conversation with its outcome, unique run marker,
PR link, and addressed/outstanding feedback with thread links, even after
deduplication or mutation failures.

`Verify Factory result` requires successful route validation and checks for that
comment, including after a failed issue-eligibility precondition; a missing comment
fails the job. A blocked run stays failed even when its explanation was posted and
verified. The precondition is a
point-in-time check, not continuous enforcement. A green run does not prove
correct PR changes or successful thread mutations; Copilot verifies those
separately, including mutation read-backs. PR creation, updates, and labels remain
Copilot's responsibility. Other setup failures before eligibility is checked
appear only in Actions logs.

**CI status:** Issue-to-PR implementation and addressed-thread resolution have run
in CI. Clarification replies, duplicate-reply prevention, and denied-resolution
handling have not yet been exercised live.
