# Create a pull request

This PR-creation example was tested successfully and is retained as a reusable
documentation snippet, not an installed workflow.
Copilot creates a unique branch, commits a small Markdown file, pushes it, and
opens a PR titled `test` against `master`.

The basic example below uses `GITHUB_TOKEN`.

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests**. Without this setting, the branch
push succeeds but PR creation is rejected even with `pull-requests: write`.

Keep the setup steps from [Install AI tools and run a prompt](ai-tools.md) and
replace the job permissions with:

```yaml
permissions:
  contents: write
  pull-requests: write
  copilot-requests: write
```

Replace the basic prompt step with:

```yaml
- name: Create test PR with Copilot
  env:
    GITHUB_TOKEN: ${{ github.token }}
    GIT_AUTHOR_NAME: factory[bot]
    GIT_AUTHOR_EMAIL: 41898282+github-actions[bot]@users.noreply.github.com
    GIT_COMMITTER_NAME: factory[bot]
    GIT_COMMITTER_EMAIL: 41898282+github-actions[bot]@users.noreply.github.com
  run: >-
    ./scripts/ai.sh
    --harness copilot
    --prompt "Create a test pull request in repository ${GITHUB_REPOSITORY}.
    Fetch origin master and create branch ci/test-pr-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT} from origin/master.
    Create or update ci-pr-test.md with a short note and this run URL: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}.
    Commit only that file with message 'Added CI PR creation test'.
    Push the new branch to origin, then use gh pr create to open exactly one PR against master with title 'test' and a body containing the run URL.
    Use the provided Git author and committer environment variables.
    Do not push to master or merge the PR.
    Actually create the PR and report its URL; report any failure accurately."
```

`contents: write` permits branch pushes; `pull-requests: write` permits PR
creation; `copilot-requests: write` permits model requests. Checkout persists
credentials by default so Copilot's `git push` can authenticate.

The commit author and committer names are `factory[bot]`, but the noreply email
still links to `github-actions[bot]`. The PR author is `github-actions[bot]`, as
determined by the token.

## Verify the result

Copilot can report a tool failure and still exit successfully. A green workflow
run alone does not prove the PR was created. Check the reported URL with
`gh pr view <URL>`, or add an explicit CI existence check.

For automatic downstream workflow runs and a separate PR author/reviewer identity,
follow the [Factory GitHub App setup](../factory/github-app.md).
