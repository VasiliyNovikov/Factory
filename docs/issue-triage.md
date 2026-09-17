# Triage issues before implementation

[Issue triage](../.github/workflows/issue-triage.yml) handles newly opened issues
and new comments on open issues that do not have `triaged`. PR comments go to
the separate [implementation workflow](issue-implementation.md). Only Factory's own comments are
ignored by author; other bots and humans can provide clarification.

Copilot reads the issue, full discussion, repository guidance, and relevant code.
It then posts a Factory comment with one of two outcomes:

- **Ready:** summarize the scope and acceptance criteria.
- **Reply:** ask specific questions or explain why the request is unsuitable,
  already satisfied, or blocked. The issue stays untriaged; a later comment
  triggers another assessment.

`triaged` means **ready for implementation**, not just inspected. This workflow
does not implement code or open PRs.

## Label handoff

Copilot rechecks that the issue is open and untriaged. For a ready decision, it:

1. Creates repository labels if needed.
2. Posts the agreed scope and acceptance criteria in a marked decision comment.
3. Adds `factory-issue-<issue-number>` to the issue and verifies it.
4. Adds `triaged` in a separate API request, emitting the implementation handoff event.

The labels are applied using the Factory App token so the `issues: labeled`
event starts the implementation workflow. Copilot is instructed to reply about a conflicting
`factory-issue-*` label instead of assigning multiple identities. Retrying a partially completed
handoff reuses the existing tracking label. Both labels are later copied onto
the PR; the shared tracking label becomes its implementation concurrency key.

Triage runs are serialized per issue using `issue-triage-<number>`. Live state is
checked after waiting so a comment queued before handoff does not retriage an
already-ready issue. Label handoff ends triage; implementation has its own shared
issue/PR concurrency group. GitHub retains at most one pending run per group,
so each assessment reads the full discussion.

## Setup and verification

Use the [Factory App credentials](github-app.md)
`FACTORY_CLIENT_ID` and `FACTORY_PRIVATE_KEY`. Triage requests **Contents: Read**
and **Issues: Read and write**. Copilot uses the built-in token with
`copilot-requests: write`. The workflow must be on the default branch.

Triage uses `gh` with the existing `GH_TOKEN` (Factory App token) for repository
and issue reads, discussion refreshes, replies, and labels. The built-in
`GITHUB_TOKEN` has no Issues access; substituting it for `GH_TOKEN` can cause
HTTP 403 on issue reads. `COPILOT_GITHUB_TOKEN` authenticates model requests.

See the shared setup for approving installation permission updates.

For requests changing workflow files, the implementation token must already
request `permission-workflows: write` on the default branch and the installation
must grant it. GitHub checks this permission when pushing the PR branch, before
merge. After resolving a blocked prerequisite, post a new issue comment to
trigger reassessment.

A short read-only verification step confirms that Factory posted a comment
with this run's marker. Label assignment and decision content are left to
Copilot. A green triage run confirms a response, not a successful label handoff
or completed implementation; check the issue labels for handoff readiness.
See [issue implementation](issue-implementation.md) for the next stage.
Triage has not yet been tested end-to-end in CI.
