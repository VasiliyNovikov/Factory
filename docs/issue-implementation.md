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
workflow completions (GitHub requires a nonempty `workflows` filter). Before
minting an App token, installing tools, or invoking Copilot, the routing job
requires the run's head repository to match this repository and its branch to
start with `factory/issue-`. Fork workflow failures and default-branch push
failures therefore skip routing. Eligible runs must still be linked to an open,
labeled Factory PR at its current head or current synthetic merge commit.
It prefers the run's explicit PR association;
when absent, PR and push runs may resolve through a unique open PR on that branch.
Ambiguous associations, unrelated runs, and completions of triage, implementation,
or workflow diagnostics are skipped. Diagnostics runs only on the default branch;
its next invocation analyzes its predecessor without invoking the PR-feedback router.

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

YAML conditions skip `factory-identity[bot]` comments/reviews, comments or reviews
on closed or untriaged items, unrelated issue labels, approvals, successful non-review
workflows, fork or non-Factory-branch workflow runs, and triage/implementation/diagnostics
completions before starting routing. Keep the early author filter aligned with
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
in the log. There is no separate parser or output validation; an absent
`issue_number` skips implementation, including if routing failed to produce it.
Implementation rechecks live state before changing the PR.

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

Every implementation run must post a new App-authored comment in the triggering
conversation with its outcome, unique run marker, PR link, and addressed/outstanding
feedback with thread links, even after deduplication or mutation failures.

`Verify Factory result` checks only for that comment; a missing comment fails the
job. A green run does not prove correct PR changes or successful thread mutations;
Copilot verifies those separately, including mutation read-backs. PR creation,
updates, and labels remain Copilot's responsibility. Setup failures before Copilot
starts appear only in Actions logs.

**CI status:** Issue-to-PR implementation and addressed-thread resolution have run
in CI. Clarification replies, duplicate-reply prevention, and denied-resolution
handling have not yet been exercised live.
