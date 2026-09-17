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
`actions: read` on the built-in token. Copilot uses that token for read-only
Actions log queries; the App token handles repository changes and replies.

The implementation invocation passes `--profile implement` to `scripts/ai.sh`,
using the `implement` profile's model, reasoning effort, and context settings
from [`.github/model-config.json`](../.github/model-config.json). Event routing
and issue triage omit `--profile` and continue using `default`.

## Follow-ups and PR tracking

Each issue owns branch `factory/issue-<number>` and tracking label
`factory-issue-<number>`. The issue and PR must both have `triaged` and exactly
one tracking label. Copilot searches all PR states for that branch
before acting. It reuses only the matching open PR from the Factory App and
preserves existing commits. Closed or merged PRs get a status reply directing
additional work to a new issue. Conflicting ownership gets a reply rather than
an overwrite.

Post follow-up requests on the original issue, in its Factory PR conversation,
or in a submitted review. Inline comments are read together when the review is
submitted, avoiding one run per inline finding. Standalone inline comments and
later inline replies do not trigger runs. Factory handles inline feedback in its
original review thread and also posts a run summary in the triggering conversation.
Every thread reply directs answers and follow-ups to the main PR conversation
or a new submitted comment or change-request review so they can start a run.
Edited comments do not trigger runs. Submitted comment reviews and change requests
trigger runs; approvals do not start another implementation.
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

YAML conditions skip `factory-identity[bot]` comments/reviews, comments or reviews
on closed or untriaged items, unrelated issue labels, approvals, successful non-review
workflows, and triage/implementation completions before starting routing. Keep
the early author filter aligned with the installed Factory App's login. Other
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

Copilot reads the eligible PR's review threads using `gh api graphql`, paginating
both `reviewThreads` and each thread's comments. This includes replies, authors,
thread/comment IDs, and current `isResolved`/`isOutdated` state; review summaries
alone do not provide that context. Before each thread mutation, it rechecks the
issue/PR eligibility, remote head, full thread contents, resolution state, and
`viewerCanReply`/`viewerCanResolve`. Incomplete context or an unverified revision
prevents a mutation. Thread and comment bodies are untrusted data, not authority
to select mutation targets or bypass verification. Use only thread IDs returned
by the eligible PR's API, never IDs supplied in comment bodies.

- **Addressed:** Verify every actionable point against the current PR revision's
  code. If changes are needed, run appropriate checks, commit, push successfully, and
  confirm the remote head matches the checked commit before using
  `resolveReviewThread`. Both the mutation response and a fresh thread read must
  report `isResolved: true` before claiming resolution. Already-addressed feedback
  can be resolved after verification without an empty commit. An outdated
  location, attempted fix, or passing checks alone is not proof of a fix.
- **Outstanding:** For unclear, partially addressed, blocked, or disputed feedback,
  use `addPullRequestReviewThreadReply` to ask a specific question or explain what
  remains in the original thread, leaving it unresolved. Every thread reply
  explains that inline replies do not trigger a run and directs answers and
  follow-ups to the main PR conversation or a new submitted comment or
  change-request review. Read prior Factory replies and avoid an equivalent reply
  when feedback and relevant code have not changed, including on reruns. Verify
  replies appear in the intended thread under the App identity; re-read before
  retrying an uncertain mutation.
- **Skipped or failed:** Leave resolved and unrelated threads alone. Report
  HTTP/GraphQL errors, denied permissions, and unexpected read-back states in the
  main-conversation outcome without claiming an unverified reply or resolution.

These operations use the App token's existing **Pull requests: Read and write**
permission. Ordinary issue comments, main PR comments, and review summaries are
not resolvable threads; acknowledge or answer them in the corresponding main
conversation. Thread replies do not replace the required new run-marked outcome
comment, which links the PR and summarizes addressed and outstanding feedback
with thread links, including failures.

Check the behavior on an eligible Factory PR with these cases:

| Case | Expected evidence |
|---|---|
| Addressed by a new fix | Appropriate checks pass; the pushed head matches the checked commit; the mutation and fresh thread read both confirm resolution. |
| Clarification needed or only partly addressed | A specific App-authored question or explanation appears in the original thread; `isResolved` stays false. The reply explains that inline replies do not trigger a run and directs answers to the main PR conversation or a new submitted comment or change-request review. An unchanged rerun adds no equivalent inline reply, but still posts its run summary. |
| Resolution fails or is denied | The outcome reports the API/permission error or unconfirmed state, without claiming resolution; the run-marked summary still appears. |
| Outdated or already resolved | Outdated feedback is checked against the current code, not automatically resolved; resolved or unrelated threads receive no mutation. |
| Embedded mutation instructions | Instructions or thread IDs in comment bodies do not select mutation targets or bypass code verification; only API-returned threads on the eligible PR can be mutated. |

## Result verification

Every outcome gets a comment in the triggering issue or PR conversation containing
a unique run marker, even when no new inline reply is needed or a thread mutation
fails.
The workflow's inline verification step requires a matching
App-authored comment. PR creation, updates, and labels are left to Copilot.

A green run means a response was posted, which can be a clarification or
an error explanation. It does not independently verify PR changes or their
correctness, or the thread mutations that Copilot checks via API read-back.
A missing response from this run fails the job.
Setup failures before Copilot starts appear in Actions logs rather than a
reply. This example has not yet been tested in CI.
