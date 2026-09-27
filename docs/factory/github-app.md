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

   The reviewer needs only Contents read and Pull requests read/write. Metadata
   read is automatic; leave other permissions unset. Disable webhooks on both
   Apps; no callback URL or subscriptions are needed.
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
| Diagnostics and repository review | Contents/Pull requests read, Issues write |

Workflow changes need Workflows write **before pushing a PR branch**. The
installation must grant it, and the worker's token-generation input must already
be on the default branch.

[Diagnostics](workflow-diagnostics.md) uses built-in `actions: read` for
same-repository runs/jobs/logs; [repository review](repository-review.md) needs no
Actions access. Both create only new unlabeled findings, verified with the App token.

The [router](factory-router.md) needs no App token: it uses built-in Actions write
for dispatch and Contents/Issues/Pull requests read for analysis. Workers run on
the default branch with their own permissions. Reviewer-App submissions trigger
the native router event without an Actions-write grant.

## Token names and identities

App jobs expose **two credentials through three standard variables**:

| Variable | Value in App-based jobs | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | Built-in `${{ github.token }}` | Workflow access as `github-actions[bot]`; fallback authentication for `gh` when `GH_TOKEN` is unset |
| `COPILOT_GITHUB_TOKEN` | The same built-in token | Explicit authentication for Copilot model requests |
| `GH_TOKEN` | Generated Factory or reviewer App installation token | Preferred authentication for `gh`, acting as `<app-slug>[bot]` |

`GH_TOKEN` selects the GitHub CLI credential, not its type; the router uses the
built-in token there.

The [shared action](../examples/ai-tools.md#shared-factory-action) sets these
variables only during AI invocation, using the caller's `gh-token` input:
`steps.factory-token.outputs.token`, `steps.reviewer-token.outputs.token`, or
`github.token`. Token creation and Git identity stay in callers.

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

## Review identity and approvals

Approvals need reviewer Pull requests write and must follow repository policies.
Use `COMMENT`, not `APPROVE`, when the PR author equals `REVIEWER_LOGIN`; existing
PR authors do not change. Factory App PR creation is tested; reviewer authentication,
approvals, and native delivery still need [live verification](pr-review.md#verification-limits).
