# Turn an issue or follow-up comment into a PR

[Issue implementation](../.github/workflows/issue-implementation.yml) starts when
[triage](issue-triage.md) adds `triaged` to an issue, or someone posts feedback on
an open triaged issue or its Factory PR. Inline comments, submitted comment or
change-request reviews, PR-review findings, and failed CI runs linked to that PR trigger
follow-ups. It reads the full issue and PR discussions, repository guidance, and
relevant code before acting:

- Clear, actionable request: implement it, run appropriate checks, and open a PR.
- Follow-up to an existing Factory PR: update that PR's branch and description.
- Unclear, unsuitable, already satisfied, or blocked request: explain or ask
  specific questions in the conversation where the request was posted.

Replies, PRs, and commits use the Factory App identity. Copilot model requests
use the built-in Actions token. PR creation and subsequent App-authenticated
pushes trigger the separate [PR-review workflow](pr-review.md).

## Setup

Use the [Factory App setup](github-app.md)
with `FACTORY_CLIENT_ID` and `FACTORY_PRIVATE_KEY`. The App installation needs:

- **Contents: Read and write**
- **Pull requests: Read and write**
- **Issues: Read and write** — needed for issue replies

When adding permissions, approve the installation's updated access in GitHub.
Requests to change `.github/workflows/` also need the App's **Workflows: Read and
write** permission and `permission-workflows: write` in the token-generation
step. The workflow currently requests only the three permissions above.

The workflow must be on the default branch to receive issue and comment events.
It uses the shared [AI tool installation and invocation](ai-tools.md), with a
30-minute job timeout and `contents: read`, `copilot-requests: write`, and
`actions: read` on the built-in token. Copilot uses that token for read-only
Actions log queries; the App token handles repository changes and replies.

## Follow-ups and PR tracking

Each issue owns branch `factory/issue-<number>` and tracking label
`factory-issue-<number>`. The issue and PR must both have `triaged` and exactly
one tracking label. Copilot searches all PR states for that branch
before acting. It reuses only the matching open PR from the Factory App and
preserves existing commits. Closed or merged PRs get a status reply directing
additional work to a new issue. Conflicting ownership gets a reply rather than
an overwrite.

Post follow-up requests on the original issue, in its Factory PR conversation,
or as inline review comments. Replies to PR feedback are posted in the PR's main
conversation. Edited comments do not trigger runs. Submitted comment reviews
and change requests trigger runs; approvals do not start another implementation.
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

YAML conditions skip unrelated issue labels, approvals, successful non-review
workflows, and triage/implementation completions before starting routing. Other
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

## Result verification

Every outcome gets a comment in the triggering issue or PR conversation containing
a unique run marker.
The workflow's inline verification step requires a matching
App-authored comment. PR creation, updates, and labels are left to Copilot.

A green run means a response was posted, which can be a clarification or
an error explanation. It does not independently verify PR changes or their
correctness. A missing response from this run fails the job.
Setup failures before Copilot starts appear in Actions logs rather than a
reply. This example has not yet been tested in CI.
