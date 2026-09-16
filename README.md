# Factory

## Agentic Software Factory experiment
Starting with small things:

- [x] Run GitHub Copilot CLI in CI Job
- [x] Have GitHub Copilot CLI on CI read/write repo/issues/PRs

## CI examples

These examples use this repository's scripts and require no PAT or custom secret:

- `scripts/install-tools.sh` installs Copilot CLI, OpenCode, and missing `jq`.
- `scripts/ai.sh` reads `.github/model-config.json` and invokes the selected CLI.
- `GITHUB_TOKEN: ${{ github.token }}` authenticates both Copilot model requests and
  the `gh` commands it executes.

Once the workflow is on the default branch, run it from **Actions → CI → Run
workflow**. See [GitHub's Copilot CLI Actions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions).

### Install AI tools and run a prompt

Start with this manually triggered workflow. It checks out the scripts and model
configuration, installs the tools with Node.js 24, and runs a basic prompt.

```yaml
name: CI

on:
  workflow_dispatch:

jobs:
  ai:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      copilot-requests: write
    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Set up Node.js
        uses: actions/setup-node@v7
        with:
          node-version: '24'

      - name: Install AI tools
        run: ./scripts/install-tools.sh

      - name: Run a prompt
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: >-
          ./scripts/ai.sh
          --harness copilot
          --prompt "Reply with 'Hello from CI'. Do not use any tools."
```

Use `--harness opencode` to run the same prompt through OpenCode. Both harnesses
read model and reasoning defaults from `.github/model-config.json`; `longContext`
applies only to Copilot CLI.

### Create a pull request

The current [CI workflow](.github/workflows/ci.yml) has been tested successfully.
Copilot creates a unique branch, commits a small Markdown file, pushes it, and
opens a PR titled `test` against `master`.

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests**. Without this setting, the branch
push succeeds but PR creation is rejected even with `pull-requests: write`.

Keep the setup steps above and replace the job permissions with:

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

### Create an issue

This issue-creation example was tested successfully. Keep the setup steps above and replace
the job permissions with:

```yaml
permissions:
  contents: read
  issues: write
  copilot-requests: write
```

Replace the basic prompt step with:

```yaml
- name: Create test issue with Copilot
  env:
    GITHUB_TOKEN: ${{ github.token }}
  run: >-
    ./scripts/ai.sh
    --harness copilot
    --prompt "Use the GitHub CLI (gh issue create) to create exactly one new issue in repository ${GITHUB_REPOSITORY}
    with the title 'test' and body 'Created by Copilot CLI in CI. Run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}'.
    Actually create the issue, then report its URL. If creation fails, report the error."
```

`contents: read` is enough for checkout; `issues: write` allows issue creation.
The historical workflow also set `persist-credentials: false` on checkout,
because this test does not push commits. Each run creates a new `test` issue.

### Verify the result

Copilot can report a tool failure and still exit successfully. A green workflow
run alone does not prove an issue or PR was created. Check the reported URL with
`gh issue view <URL>` or `gh pr view <URL>`, or add an explicit CI existence check.
