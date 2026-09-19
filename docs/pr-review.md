# PR review

[PR review](../.github/workflows/pr-review.yml) is dispatched on the default branch
by the [Factory router](factory-router.md) for PR opened, synchronize, reopened,
ready-for-review, and actual description-edit events, or conversation comments
requesting review/reassessment, including explicit
[Factory no-commit requests](factory-router.md#no-commit-review-requests).
The router uses `pull_request_target` for PR changes and selects
open, non-draft, same-repository PRs. New worker jobs cancel older reviews of the
same PR and head SHA. Different heads cannot cancel each other; stale-head workers
skip before posting. The reviewer keeps the repository's write-capable Actions token.

The workflow uses the shared [AI tool setup](ai-tools.md) with these permissions:

```yaml
permissions:
  contents: read
  pull-requests: write
  copilot-requests: write
```

It checks out `github.workflow_sha` for the installation script, harness, and model
configuration. Copilot reads the proposed changes through `gh pr view`,
`gh pr diff`, and read-only API calls, rather than executing the PR's code.
The review invocation passes `--profile review` to `scripts/ai.sh`, using the
`review` profile's model, reasoning effort, and context settings from
[`.github/model-config.json`](../.github/model-config.json).

The review job has a 30-minute total timeout, including setup time already elapsed.
Its prompt tells Copilot to budget the remaining time, reserving time for required
GitHub reporting and final verification without relaxing required checks or
approving an incomplete review.

## Same-head reassessment

- A description correction or new request needs assessment even if the head was
  previously reviewed. Skip only when a current-head review demonstrably covers
  the corrected context/request, not merely because that SHA has a review.
- Refresh the live diff, description, full discussion, reviews, and thread history
  before assessment and again before submission. Reassess intervening changes.
- Account for pending requests in the live discussion, not only the dispatched
  source; a newer same-head worker can replace or cancel an earlier request's job.
  Recheck coverage before posting to avoid duplicate assessments.
- Verify a source comment's membership in this PR through the API. Link the
  request being assessed in the submitted review so later workers can establish
  coverage without relying on job success.
- Independently verify addressed findings. A request, resolved thread, or
  implementation-success report does not establish that the PR is clean.
- Read back the submitted review's author, commit, state, run marker, and URL.
  This completes a request without label removal or another acknowledgement.
  Failed/cancelled reviews leave the handoff incomplete, with no automatic retry
  guarantee.

## Review outcome

Reviews follow the shared [test-value policy](../AGENTS.md#test-value-and-verification).
A missing-test finding must identify a concrete uncovered risk, the observable
behavior to check, and why existing coverage is insufficient. Do not demand tests
just because files changed or to preserve incidental wording; justified contract
checks, real-logic mocked tests, and necessary regression/safety coverage remain useful.

- Actionable findings: submit a comment review with file/line references and
  suggested fixes, using inline review comments where possible.
- No actionable findings: submit an approval.
- PR authored by `github-actions[bot]`: submit a comment review even when clean,
  because the same bot identity cannot approve its own PR.
- Incomplete review or API failure: report the error without approving.

The review is attached to the dispatched expected head commit. Copilot is instructed to check
that the PR is still open, ready, and at that commit before posting. A final API
check requires a submitted bot review matching that commit, its full SHA visibly
included in the review body, and a unique run
marker, so a successful Copilot exit alone does not make the job pass. A stale or
already-covered assignment skips before posting, with AI-recorded evidence in the
job summary and `skipped=true`; the posted-review check then skips too. The worker
does not repeat the router's eligibility analysis.

Successful completion wakes the router, which can dispatch implementation for
findings still applicable to the current code, even if the PR advanced after posting.
It correlates the review's run marker and `commit_id`;
the dispatched workflow's own `head_sha` is the default-branch revision.

## Run and verify

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests** for approvals.

After the router and workers are on the default branch, open a non-draft PR from
a branch in this repository using a user or App token. PR changes made using
`GITHUB_TOKEN` do not start the router's `pull_request_target` path. See
[GitHub's workflow triggering guide](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

Check **Actions → PR review** and the PR's review timeline. The job's verification
step confirms that a review was posted; it does not independently validate the
quality of Copilot's findings. Before the router migration, the comment-review path was tested successfully:
Copilot identified both deliberate regressions and posted inline findings, and
the verification step passed. Central dispatch and the approval path have not yet been tested live.

To enable automatic runs and let `github-actions[bot]` approve clean PRs, follow
the [Factory GitHub App setup](github-app.md).
The App creates PRs under a separate identity; the review workflow keeps using
its built-in token.

The no-commit handoff needs live verification after reaching the default branch:
confirm the source edit/request, accepted dispatch, and submitted review's state,
commit, and run marker. Static inspection cannot establish AI adherence, event
delivery, queue ordering, or approval.
