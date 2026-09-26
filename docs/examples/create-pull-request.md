# Create a pull request

This tested snippet creates a unique branch, commits a Markdown file, and opens
a `test` PR against `master` using `GITHUB_TOKEN`. It is not an installed workflow.

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests**. Without this setting, the branch
push succeeds but PR creation is rejected even with `pull-requests: write`.

Keep the [AI setup](ai-tools.md) and use these job permissions:

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

The permissions allow branch pushes, PR creation, and model requests.
Checkout persists credentials for `git push` by default.

The commit names are `factory[bot]`, but the email links to `github-actions[bot]`.
The token makes `github-actions[bot]` the PR author.

## Verify the result

A successful Copilot exit does not prove creation. Check the reported URL with
`gh pr view <URL>`, or add a CI existence check.

For automatic downstream workflow runs and a separate PR author/reviewer identity,
follow the [Factory GitHub App setup](../factory/github-app.md).
