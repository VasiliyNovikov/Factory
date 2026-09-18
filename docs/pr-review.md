# PR review

[PR review](../.github/workflows/pr-review.yml) is a separate workflow that runs
when a PR is opened, updated with new commits, reopened, or marked ready for
review. It also reviews actual description edits and Factory's
`factory-review-requested` label, so addressed feedback can receive a fresh
assessment without a new commit. Other edits and labels are ignored.
Draft, closed, and fork PRs are skipped; the example uses the repository's
write-capable Actions token.

Reviews are serialized per PR without cancelling an active review. This keeps a
late duplicate or stale follow-up from cancelling a valid assessment. Before
installing tools, a live API check rejects stale heads, superseded description
edits, and label events whose request has already been consumed. Existing commit
events still schedule review; every submission must match the current head.

The workflow uses the shared [AI tool setup](ai-tools.md) with these permissions:

```yaml
permissions:
  contents: read
  pull-requests: write
  copilot-requests: write
```

It checks out the base revision for the installation script, harness, and model
configuration. Copilot reads the proposed changes through `gh pr view`,
`gh pr diff`, and read-only API calls, rather than executing the PR's code.
The review invocation passes `--profile review` to `scripts/ai.sh`, using the
`review` profile's model, reasoning effort, and context settings from
[`.github/model-config.json`](../.github/model-config.json).

The review job has a 30-minute total timeout, including setup time already elapsed.
Its prompt tells Copilot to budget the remaining time, reserving time for required
GitHub reporting and final verification without relaxing required checks or
approving an incomplete review.

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

The reviewer refreshes the live diff, description, full discussion, reviews, and
threads, and reassesses changes before submitting. A resolved thread, request
label, or implementation-success report is not evidence that the PR is clean.
The review is attached to the event's head commit. Copilot must check that the
PR is still open, ready, in this repository, and at that commit before posting.
A final API check requires exactly one submitted Actions review matching that
commit and the unique run marker, rejects self-approval, and prints its actual
state and URL. A green job can represent COMMENT, not just APPROVE.

## No-commit handoff

Actual description corrections use the native `pull_request.edited` event.
For verified already-addressed feedback with no commit or description change,
the implementer uses the App token to add `factory-review-requested` to the PR.
It creates the repository label only if missing, using existing Issues access.
No new credential or workflow permission is required.

The native `pull_request.labeled` event retains the PR's head/merge association,
so the existing implementation routing still recognizes the review's findings.
Only Factory-authored additions of this label enter review. The reviewer removes
it with the Actions token only if it was present in the triggering event, after
verifying a submitted review and rechecking the live PR, then verifies removal.
A request added during an older review stays pending for its own assessment.
Failed reviews leave the request pending.
API or removal read-back errors fail the job
rather than representing approval or successful acknowledgement.

Pending requests are reused, not removed and re-added. The implementer inspects
the PR timeline and subsequent reviews and does not request another assessment
of identical feedback and unchanged context that has already been re-reviewed.
Unclear, partial, blocked, or disputed feedback gets an explanation, not a
request loop. New substantive corrections may warrant a fresh request.
Approvals do not trigger implementation; request removal is not a review trigger.

## Run and verify

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests** for approvals.

After the workflow is on `master`, open a non-draft PR from a branch in this
repository. PRs created or updated using `GITHUB_TOKEN` require a user with write
access to select **Approve workflows to run**
on the PR before their `pull_request` workflows start. See
[GitHub's workflow triggering guide](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

Check **Actions → PR review** and the PR's review timeline. The job's verification
step confirms that a review was posted; it does not independently validate the
quality of Copilot's findings. The comment-review path was tested successfully:
Copilot identified both deliberate regressions and posted inline findings, and
the verification step passed. The approval path has not yet been tested.

To enable automatic runs and let `github-actions[bot]` approve clean PRs, follow
the [Factory GitHub App setup](github-app.md).
The App creates PRs under a separate identity; the review workflow keeps using
its built-in token.

Focused local checks run with `python -m unittest discover -s tests -v` (Python's
standard library, Bash, and `jq`). They execute the workflow's actual inline
eligibility, result-verification, and acknowledgement steps against a fake `gh`:
unchanged-head follow-ups, stale/ineligible events, duplicate consumed requests,
review state/commit/run-marker matching, and API failures. These mocked checks
do not establish AI review quality, real event delivery, or live approval.
