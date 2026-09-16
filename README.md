# Factory

## Agentic Software Factory experiment
Starting with small things:

- [x] Run GitHub Copilot CLI in CI Job
- [x] Have GitHub Copilot CLI on CI read/write repo/issues/PRs
- [ ] Review PRs with GitHub Copilot CLI in CI and post comments or approval

## CI examples

The basic examples use this repository's scripts and require no PAT or custom secret.
The optional [GitHub App setup](docs/create-pull-request.md#use-a-github-app-for-automatic-runs-and-approvals)
uses App credentials to enable automatic runs and distinct PR author/reviewer identities.

- `scripts/install-tools.sh` installs Copilot CLI, OpenCode, and missing `jq`.
- `scripts/ai.sh` reads `.github/model-config.json` and invokes the selected CLI.
- `GITHUB_TOKEN: ${{ github.token }}` authenticates both Copilot model requests and
  the `gh` commands it executes.

Run the manual examples from **Actions → CI → Run workflow** once the workflow is
on the default branch. The PR-review workflow runs on PR events. See
[GitHub's Copilot CLI Actions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions).

1. [Install AI tools and run a prompt](docs/ai-tools.md)
2. [Create a pull request](docs/create-pull-request.md) — tested successfully.
3. [Create an issue](docs/create-issue.md) — tested successfully.
4. [Review a pull request](docs/review-pull-request.md) — comment reviews tested successfully; approvals pending.
