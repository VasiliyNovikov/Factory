# Turn an issue or follow-up comment into a PR

[Issue implementation](../.github/workflows/issue-implementation.yml) starts when
[triage](issue-triage.md) adds `triaged` to an issue, or someone posts feedback on
an open triaged issue or its Factory PR. Submitted comment or change-request
reviews (including their inline findings), PR-review findings, and failed CI runs linked to that PR trigger
follow-ups. Default-branch pushes also check eligible Factory PRs for merge conflicts.
It reads the full issue and PR discussions, repository guidance, and relevant code before acting:

- Clear, actionable request: implement it, run appropriate checks, and open a PR.
- Follow-up to an existing Factory PR: update that PR's branch and description.
- Default-branch push: repair confirmed merge conflicts in existing Factory PRs,
  without implementing unrelated requests or updating merely behind branches.
- Unclear, unsuitable, already satisfied, or blocked request: explain or ask
  specific questions in the conversation where the request was posted.

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
routes only runs linked to an open, labeled Factory PR at its current head or
current synthetic merge commit. It prefers the run's explicit PR association;
when absent, PR and push runs may resolve through a unique open PR on that branch.
Ambiguous associations, unrelated runs, and completions of triage or implementation
itself are skipped.

- Successful `.github/workflows/pr-review.yml` runs require a bot review with
  findings matching that run's marker and the current PR head.
- Failed or timed-out workflows (including future test/validation CI) provide
  their jobs and logs as feedback. Copilot fixes actionable failures or explains
  blockers in the PR conversation.
- Successful checks, approvals, cancellations, and stale revisions are skipped.

Before minting an App token or invoking Copilot, the routing job requires a
workflow completion's `head_repository.full_name` to match `github.repository`.
Fork or missing-head-repository completions do not start routing, even on failure.
Fork PRs still receive the separate read-only PR-head validator checks in CI.

No list of test workflow names needs maintaining. Implementation uses the same
tracking-label concurrency group for eligible CI feedback and comments, rechecks
the revision before acting, pushes fixes, and lets the relevant CI run again.
GitHub limits `workflow_run` chains to three levels; this is not an unlimited
retry loop. A new issue/PR comment can start another pass when needed.

A separate Copilot routing job resolves PR feedback to its original issue using
read-only GitHub access. It is instructed to check the live PR's App author,
repository, base, branch, and unique tracking label, and require the original
issue to remain open with matching labels. Untriaged issues and unrelated,
closed, or mismatched PRs are excluded from the routing result.

YAML conditions skip `factory-identity[bot]` comments/reviews, comments or reviews
on closed or untriaged items, unrelated issue labels, approvals, successful non-review
workflows, triage/implementation completions, and non-default-branch or deletion
pushes before starting routing. Keep the early author filter aligned with the
installed Factory App's login. Other
events incur a Copilot invocation even when routing decides there is no work.
Routing checks out the default branch and has a 15-minute timeout. Its App token
has only Contents, Issues, and Pull requests read access; the built-in token
provides `copilot-requests: write` for model requests.
Push routing uses a ref-scoped job-level concurrency group with cancellation, so
a later push supersedes an older routing pass only for the same ref. Feedback
routing uses run-specific groups and is not cancelled by pushes; already-running
implementers are unaffected.

Copilot writes one compact JSON array to `GITHUB_OUTPUT`, for example:

```text
work_items=[{"issue_number":"12","reply_number":"34","source_pr":"34","tracking_label":"factory-issue-12"}]
```

For issue events, `source_pr` is empty and `reply_number` equals `issue_number`.
Ordinary events produce at most one item. A default-branch push enumerates all
pages of open PRs and produces one item per eligible Factory PR, with the PR as
`source_pr` and `reply_number`, even if mergeability is clean or unknown.
Implementation, not the router, checks the latest head/base for conflicts.
Only the read-only router enumerates repository-wide candidates. Each matrix item
starts a separate implementer invocation scoped to one issue and its own PR;
that invocation must not maintain other issues' PRs.

A verified skip produces `work_items=[]`. Missing or malformed output fails the
JSON contract check rather than silently skipping implementation. The check
requires objects with exactly the four documented keys, whole-string positive
numeric IDs (no whitespace or newlines), matching
tracking labels/reply targets, and unique issue labels and reply targets,
preventing separate issue jobs from targeting the same PR; push items must
include a nonempty PR number. Extra keys are rejected, not passed through as
unvalidated matrix variables. The matrix supports up to 256 items (GitHub's job
limit); incomplete enumeration, API failures, or more items
must be reported without emitting a partial matrix. Validation checks the output
shape, not live eligibility or the completeness of the agent's enumeration.
Implementation rechecks live state before changing a PR.

The workflow and `./scripts/test-work-items.sh` use the same
[`validate-work-items.jq`](../scripts/validate-work-items.jq) filter. Routing runs
these Bash/jq checks before invoking Copilot. [CI](../.github/workflows/ci.yml)
also runs them at the exact PR head, with read-only Contents access, no persisted
checkout credentials, and no App token or AI invocation. The separate PR-creation
job remains manual. Run the script locally to check
accepted matrices, non-array output, newline aliases, mismatched tracking labels/reply
targets, duplicate targets, malformed output, and matrix limits. They verify the
output contract, not AI routing or live GitHub behavior.

Each matrix job uses the shared tracking label for concurrency; `fail-fast: false`
keeps a failure for one issue from cancelling other issues. `max-parallel: 4`
limits each workflow run to four implementer jobs at a time, without changing
each invocation's single-PR scope. This is a per-run limit, not an account-wide
quota:

```yaml
concurrency:
  group: issue-implementation-${{ matrix.tracking_label }}
  cancel-in-progress: false
```

For example, issue #12 and its PR #34 both carry `factory-issue-12` and use
`issue-implementation-factory-issue-12`. Their
implementation jobs are serialized without cancelling the active job; routing
jobs can run in parallel. GitHub concurrency retains at most one pending job,
so bursts of comments can replace pending jobs. Every implementation reads the
full issue and PR discussions to include that feedback; the surviving run posts
its result in its triggering conversation (the PR for a push-triggered check).
Push-triggered jobs also handle unaddressed feedback within the existing issue
scope, even if the conflict probe is clean, so they do not drop feedback from a
replaced pending job. Outcomes for that absorbed feedback also go to the
conversation where it was raised, in addition to the required result on the PR,
and are read back there.
They must not expand the issue scope or create a new PR.

## Merge-conflict maintenance

GitHub documents no [mergeability-change event](https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request).
[`synchronize`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
follows PR head updates, not base-only advances affecting other PRs. The
[UI/API mergeability calculation](https://docs.github.com/en/rest/guides/using-the-rest-api-to-interact-with-your-git-database#checking-mergeability-of-pull-requests)
does not provide a separate trigger. A custom `repository_dispatch` would still
need a detector to send it, so it would add orchestration rather than replace
default-branch discovery. Each implementer remains scoped to one issue/PR.

Default-branch pushes fan out to eligible Factory PRs using the same issue
concurrency groups as comments and CI feedback. The push trigger explicitly lists
`master`; update that literal filter if the repository's default branch is renamed.
The job condition also checks the live default-branch name and excludes deletions.
Ordinary Factory branch pushes do not trigger this workflow.
The trigger filter and ref-scoped routing group prevent unintended runs and
cross-ref cancellation by unchanged workflow copies; they are not a security
boundary against an actor able to rewrite workflow files.
Factory-authored comments and implementation workflow completions are already
ignored, preventing self-triggered repair loops. Ordinary implementation and
follow-up runs also check for conflicts, including after their own changes.

Copilot fetches the current PR head and default branch and records their OIDs.
It probes those exact revisions without changing the working tree, for example
with `git merge-tree --write-tree <head> <base>`: exit 0 is clean, exit 1 with
conflict details confirms conflicts, and anything else (including exit 1 without
conflict details) is a failure. A merely
behind branch, failed checks, or a blocked merge state is not a conflict.
GitHub's `UNKNOWN`/null mergeability is pending; retry briefly or use the local
probe rather than treating it as clean or conflicting. Clean/behind branches
get no base merge or conflict-repair commit.

For confirmed conflicts, the agent merges the checked default-branch revision
into the existing PR branch without rebasing or rewriting history. It resolves
each conflict from both sides' intent, repository guidance, and the issue/PR
context, rather than blindly choosing ours/theirs. Ambiguous intent, a required
product decision, or an unverifiable resolution means aborting the local merge
and explaining the blocker on the PR, not pushing a speculative/partial repair.
Prior results are read to avoid repeating the same blocked attempt for unchanged
revisions and feedback.

Before each mutation, eligibility and both live head/base OIDs are rechecked.
Changed revisions require reassessment and fresh checks, not overwriting another
commit. The combined result receives appropriate checks before a normal push.
After pushing, Copilot verifies the remote head, ancestry of both the previous
PR head and integrated base, and a clean probe against the current default branch.
It must also obtain GitHub's mergeable result for the same revisions before
claiming resolution; pending, stale, denied, and failed verification are reported
explicitly. No force-push, default-branch push, PR merge, issue closure, changed
permissions, or relaxed required checks is authorized.

Each result comment includes the checked head/base, conflict classification,
changes or blockers, and verification limits. An issue-triggered run that cannot
resolve a conflict also explains the blocker on the existing PR.

For a default-branch push with a verified clean probe, no repository changes,
no handled or pending feedback, and no errors or blockers, Copilot updates a
dedicated Factory-authored conflict-status comment instead of adding a comment
on every push. It creates that comment only if absent, using
`<!-- factory-conflict-status:<tracking_label> -->` as its stable marker.
Before editing, it re-reads the comment from that PR's API results and verifies
its conversation, App author, and marker; multiple matches are a blocker.
Ordinary result comments are never reused. The refreshed status retains its
stable marker and includes the current checked revisions, outcome, limits, PR
link, and current run marker. All other outcomes still require a new comment.

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

Every implementation job must report in an App-authored comment in the triggering
conversation with its outcome, PR link, and addressed/outstanding feedback with
thread links. Its marker is scoped to both the run attempt and matrix item:
`<!-- factory-issue-run:<run_id>:<run_attempt>:<tracking_label> -->`.
One matrix item's comment cannot satisfy another item's result check.
A new comment is required even after deduplication or mutation failures, except
for the clean no-op push status update described above.

`Verify Factory result` checks for the App-authored comment containing that exact
job marker, whether newly posted or updated in place; a missing result fails the
job. It does not verify additional replies to absorbed feedback in other
conversations, which Copilot must read back separately. A green run does not prove
correct PR changes, successful conflict repair, or successful thread mutations;
Copilot verifies those separately, including
mutation read-backs. PR creation,
updates, and labels remain Copilot's responsibility. Setup failures before Copilot
starts appear only in Actions logs.

**CI status:** Issue-to-PR implementation and addressed-thread resolution have run
in CI. Clarification replies, duplicate-reply prevention, and denied-resolution
handling have not yet been exercised live. Default-branch fan-out and conflict
repair, in-place no-op status updates, and absorbed-feedback replies also require
live event-to-PR verification after deployment; local Git probes and workflow
checks do not establish AI resolution quality or live routing.
