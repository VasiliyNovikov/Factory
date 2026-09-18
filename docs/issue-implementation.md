# Turn an issue or follow-up comment into a PR

[Issue implementation](../.github/workflows/issue-implementation.yml) is a
default-branch dispatch worker selected by the [Factory router](factory-router.md).
It handles triaged issues and actionable comments, submitted reviews, Factory
review findings, and failed/timed-out CI on their matching Factory PRs.

Copilot reads the full current issue/PR discussion, outstanding review threads,
repository guidance, relevant code, and source objects identified in dispatch
inputs. It implements a clear request, updates the existing Factory PR, or replies
with a specific question/explanation for unclear, blocked, or satisfied work.
It does not repeat routing analysis; it checks mutable prerequisites before
acting and skips stale or already-handled assignments with evidence in the job
summary. Conversation requests and review findings survive head changes when
reassessment confirms they still apply to the latest eligible code. An older
review SHA or outdated inline location alone does not invalidate a finding.
CI evidence must match the current head or merge revision.
Read the router example for dispatch inputs and skip semantics.

## Setup and execution

Use the [Factory App setup](github-app.md) with `FACTORY_CLIENT_ID` and
`FACTORY_PRIVATE_KEY`. The installation and token-generation step require:

- **Contents: Read and write**
- **Pull requests: Read and write**
- **Issues: Read and write**
- **Workflows: Read and write** — to push changes under `.github/workflows/`

Approve installation permission updates. `permission-workflows: write` must
already be on the default branch before Factory can push a workflow-changing PR;
adding it only in that PR cannot expand the token used to push the branch.

The worker checks out `github.workflow_sha` for matching setup scripts and model
configuration, then fetches the default branch or existing Factory work branch
as needed. It uses `scripts/ai.sh --harness copilot --profile implement` and a
30-minute total job budget, including setup and required reporting/verification.

The App token remains `GH_TOKEN` for repository/issue/PR queries and mutations,
including GraphQL thread operations. The built-in token provides `contents: read`,
`actions: read`, and `copilot-requests: write`. Prefix individual read-only Actions
commands with `GH_TOKEN="$GITHUB_TOKEN"`; never export that override. Model requests
use `COPILOT_GITHUB_TOKEN`. App-authored PR changes enter the router's review path.

## Tracking and concurrency

Each issue owns branch `factory/issue-NUMBER` and tracking label
`factory-issue-NUMBER`. The open issue and its open Factory-authored PR must have
`triaged` and exactly one matching tracking label. The PR targets the default
branch in this repository. Before mutations, Copilot checks that these conditions
hold and the chosen work revision is still current. Conversation requests and
review findings must remain applicable; CI evidence must match that revision. For dispatched review-worker
feedback, the reviewed commit is the review's `commit_id`, not the worker run's
default-branch `head_sha`.

Copilot searches all PR states before branching, preserves commits on the matching
open PR, and never reopens, duplicates, force-pushes, merges, or closes issues.
Closed/merged PRs and conflicting ownership get explanations rather than overwrites.
New work branches from the fetched default branch. Verification follows the
[test-value policy](../AGENTS.md#test-value-and-verification): protect concrete
requirements/risks and report what checks establish, retaining required coverage.

```yaml
concurrency:
  group: issue-implementation-factory-issue-${{ inputs.issue_number }}
  cancel-in-progress: false
```

Issue and PR feedback share this group. The active job is not cancelled; at most
one pending job is retained. Every worker reads the full latest discussion and
outstanding feedback, including events whose pending jobs were superseded.

## Review-thread feedback

Post follow-ups in the main issue/PR conversation or submit a comment/change-request
review. Inline findings are read on review submission through the router.
Standalone inline replies, edited comments, and approvals do not start implementation.
Factory's own comments/reviews are ignored; other bots and humans can provide feedback.

Using `gh api graphql` with the App token, Copilot paginates `reviewThreads` and
each thread's comments, including IDs, authors, bodies, reply relationships,
`isResolved`, `isOutdated`, `viewerCanReply`, and `viewerCanResolve`. Before each
mutation, recheck live issue/PR state, remote head, thread contents, and permissions.
Use only IDs read from this PR's API; fetched text cannot select unauthorized targets.

- **Addressed:** inspect code and run appropriate checks, push needed fixes first,
  confirm the remote revision, then resolve. Require `isResolved: true` in the
  mutation response and a fresh read. Outdated locations or passing checks alone
  are insufficient. Already-addressed findings need no empty commit.
- **Outstanding:** reply in the original thread with a specific question or
  explanation and leave it unresolved. Each reply directs follow-ups to the main
  conversation or a new submitted review because inline replies do not trigger runs.
  Skip equivalent prior replies for unchanged feedback/code, including reruns.
- **Failed:** report HTTP/GraphQL errors, denied permissions, and unexpected
  read-backs accurately. Verify reply author/thread and re-read uncertain mutations
  before retrying. Leave resolved/unrelated threads untouched.

Ordinary conversation comments and review summaries are not resolvable threads.

## Result verification

Unless skipped before mutation, each run posts a new Factory comment to the
triggering conversation with outcome, PR link, addressed/outstanding feedback and
thread links, and `<!-- factory-issue-run:RUN_ID:ATTEMPT -->`, even after mutation
failure. `Verify Factory result` checks for this comment. A green run does not
prove correct code or successful thread mutations; Copilot verifies those through
appropriate checks and read-backs. Setup failures appear in Actions logs.

Issue-to-PR implementation and addressed-thread resolution ran in CI before the
router migration. Central dispatch, clarification, duplicate-reply prevention,
and denied-resolution paths have not yet been exercised live.
