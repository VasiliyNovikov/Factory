# Repository guidance

- This is an initial scaffold for an agentic software factory experiment. The
  unchecked items in `README.md` are goals: running GitHub Copilot CLI in CI and
  giving it read/write access to the repository, issues, and PRs. No application
  code is implemented yet.
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  Copilot CLI smoke test. Auth uses built-in `GITHUB_TOKEN` with
  `copilot-requests: write` and a recent CLI; no PAT needed. See
  [GitHub's Actions guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions).
- No application toolchain, dependency manifest, or build/test/lint commands are
  configured.
- `.github/model-config.json` supplies model and reasoning defaults to both CI
  tools; `longContext` applies only to Copilot CLI (`true`: long, `false`: default).
- Run either installed CLI with `./scripts/ai.sh --harness opencode
  --prompt "..."` (or `--harness copilot`); model settings come from the JSON.
- Install both CLIs with `./scripts/install-tools.sh` (requires Node.js/npm;
  CI uses Node.js 24). Missing `jq` is installed via `sudo apt-get`.
