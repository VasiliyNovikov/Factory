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

1. [Install AI tools and run a prompt](docs/ai-tools.md)
2. [Create a pull request](docs/create-pull-request.md) — tested successfully.
3. [Create an issue](docs/create-issue.md) — tested successfully.
