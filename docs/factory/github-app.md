# Factory GitHub App setup

`factory-worker-bot[bot]` creates PRs, pushes updates, and replies to issues.
[PR review](pr-review.md) uses `factory-reviewer-bot[bot]` so it can approve Factory
PRs without self-approval. Commit names do not change API identities.

App-created PRs and pushes trigger matching workflows without the manual approval
needed for `GITHUB_TOKEN`-generated events. Repository/environment policies still apply.

## Configure the Apps

1. [Register separate GitHub Apps](https://docs.github.com/en/apps/creating-github-apps/setting-up-a-github-app/creating-a-github-app).
   The Factory App needs these repository permissions:

   | Permission | Access | Used for |
   |---|---|---|
   | Contents | Read and write | Reading code and pushing branches |
   | Pull requests | Read and write | Creating and updating PRs |
   | Issues | Read and write | Triage, labels, sub-issues, replies, and diagnostics findings |
   | Workflows | Read and write for issue implementation | Changing `.github/workflows/` files |

   The reviewer App's installation needs Contents read/write for repository
   writer qualification and Pull requests read/write to submit reviews.
   Its workflow token stays at Contents read and Pull requests write; see
   [approval qualification](pr-review.md#approval-qualification).
   Metadata read is automatic; leave other permissions unset. Disable webhooks
   on both Apps; no callback URL or subscriptions are needed.
2. Install each App on this repository.
3. Save each Client ID as a repository Actions variable, and each generated
   private-key PEM as an Actions secret:

   | App | Client ID variable | Private-key secret |
   |---|---|---|
   | Factory | `FACTORY_CLIENT_ID` | `FACTORY_PRIVATE_KEY` |
   | Reviewer | `FACTORY_REVIEWER_CLIENT_ID` | `FACTORY_REVIEWER_PRIVATE_KEY` |

Keep private keys and tokens out of source code, logs, and conversations.

Approve permission changes under **GitHub Settings → Applications → Installed
GitHub Apps → Configure**. Editing the App alone does not update installation grants.

## Use the App in a workflow

For [PR creation](../examples/create-pull-request.md), generate the token before
checkout and use it for persisted push credentials:

```yaml
- name: Create PR App token
  id: pr-app-token
  uses: actions/create-github-app-token@v3
  with:
    client-id: ${{ vars.FACTORY_CLIENT_ID }}
    private-key: ${{ secrets.FACTORY_PRIVATE_KEY }}
    permission-contents: write
    permission-pull-requests: write

- name: Check out repository
  uses: actions/checkout@v6
  with:
    token: ${{ steps.pr-app-token.outputs.token }}
```

Request only the permissions needed by the job, within the installation's grants:

| Job | App token permissions |
|---|---|
| Triage | Contents read, Issues write |
| Implementation | Contents, Pull requests, Issues, and Workflows write |
| PR review | Contents read, Pull requests write |
| Diagnostics, repository review, model profile improvement, and owner feedback learning | Contents/Pull requests read, Issues write |

Workflow changes need Workflows write **before pushing a PR branch**. The
installation must grant it, and the worker's token-generation input must already
be on the default branch.

[Diagnostics](workflow-diagnostics.md) uses built-in `actions: read` for
same-repository runs/jobs/logs; [repository review](repository-review.md) needs no
Actions access. Both create only new unlabeled findings, verified with the App token.

[Model profile improvement](model-profile-improvement.md) and
[owner feedback learning](owner-feedback.md) also create only new unlabeled
findings for triage, never PRs or direct edits. Neither needs Actions or
workflow-write access.

The [router](factory-router.md) and [maintenance](factory-maintenance.md) need no
App token: they use built-in Actions write for dispatch and
Contents/Issues/Pull requests read for analysis. Workers run on the default branch
with their own permissions. Reviewer-App submissions trigger the native router
event without an Actions-write grant.

## Token names and identities

App jobs expose **two credentials through three standard variables**:

| Variable | Value in App-based jobs | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | Built-in `${{ github.token }}` | Workflow access as `github-actions[bot]`; fallback authentication for `gh` when `GH_TOKEN` is unset |
| `COPILOT_GITHUB_TOKEN` | The same built-in token | Explicit authentication for Copilot model requests |
| `GH_TOKEN` | Generated Factory or reviewer App installation token | Preferred authentication for `gh`, acting as `<app-slug>[bot]` |

`GH_TOKEN` selects the GitHub CLI credential, not its type; routing and maintenance
use the built-in token there.

The [shared action](../examples/ai-tools.md#shared-factory-action) sets these
invocation credentials using the caller's `gh-token` input:
`steps.factory-token.outputs.token`, `steps.reviewer-token.outputs.token`, or
`github.token`. Token creation and Git identity stay in callers.
The action also supplies the built-in `GITHUB_TOKEN` for
[Copilot installation](../examples/ai-tools.md#installation-authentication), not OpenCode.

For direct App-based script calls, set these variables and keep the Git identity:

```yaml
GITHUB_TOKEN: ${{ github.token }}
COPILOT_GITHUB_TOKEN: ${{ github.token }}
GH_TOKEN: ${{ steps.pr-app-token.outputs.token }}
```

Git push authentication is separate: checkout's `token` persists App credentials.
Neither `GH_TOKEN` alone nor Git author/committer names configure push authentication.

For PR creation, the built-in token only needs:

```yaml
permissions:
  contents: read
  copilot-requests: write
```

The [token action](https://github.com/actions/create-github-app-token) defaults to
this repository and revokes its token at job end. Generate a fresh token per job.

## API evidence credentials

[Diagnostics](workflow-diagnostics.md) and [implementation](issue-implementation.md),
including their read-only analysis subprocesses, follow these rules from the first
GitHub lookup. Each workflow's guide still owns source eligibility, permissions,
and allowed mutations.

- For read-only Actions endpoints (`repos/.../actions/...`, including runs,
  attempts, jobs, and logs), use command-scoped `GH_TOKEN="$GITHUB_TOKEN"`.
  For example, the first own-run metadata lookup uses:

  ```sh
  GH_TOKEN="${GITHUB_TOKEN:?built-in Actions token is required}" \
    gh api "repos/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
  ```

- All other repository/issue/PR operations, including permission checks and
  verification, keep App `GH_TOKEN` unchanged. This includes Checks (`check-runs`,
  `check-suites`), commit statuses (`status`, `statuses`), and GraphQL check/status
  queries. CI-related evidence is not necessarily an Actions endpoint.
- Use `gh api` with explicit endpoints for Actions reads: `gh run view` summaries
  also read PRs and Checks. Never switch credentials globally or apply an
  Actions-token override to a subprocess that also makes non-Actions calls.
  A denied request is a failure to report, not permission to try another
  credential or widen access.
- Keep `COPILOT_GITHUB_TOKEN` bound to the built-in token for model requests.

Retain non-secret API invocation evidence in the run log and summary: exercised
workflow revision, endpoint/operation, credential role, and outcome, including the
first Actions lookup. Use variable names or role labels, never token values.
Report any credential-role deviation and its corrective reread separately.
A successful request or static inspection alone does not prove live adherence.

## Review identity and approvals

Posting an approval and qualifying for required reviews are different:
[required approving reviewers need repository write access](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-a-pull-request-before-merging).
The installation's access and a job's narrower token scope are separate.
Keep reviewed source unchanged, follow the
[review execution rules](pr-review.md#local-checks), and retain all repository
review protections.

See [approval qualification](pr-review.md#approval-qualification) for the verified
correction and remaining limits.
