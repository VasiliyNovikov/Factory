# Install AI tools and run a prompt

This reusable snippet installs standalone Copilot without Node.js/npm and runs a
prompt. It is not an installed workflow.

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

      - name: Install Copilot
        run: ./scripts/install-tools.sh copilot

      - name: Run a prompt
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: >-
          ./scripts/ai.sh
          --harness copilot
          --prompt "Reply with 'Hello from CI'. Do not use any tools."
```

[`install-tools.sh`](../../scripts/install-tools.sh) uses the official
[Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
and [OpenCode](https://opencode.ai/docs/#install) scripts for their latest stable
standalone binaries:

| Command | Installed CLIs |
| --- | --- |
| `./scripts/install-tools.sh copilot` | Copilot only |
| `./scripts/install-tools.sh opencode` | OpenCode only |
| `./scripts/install-tools.sh` | Both |

The installer downloads and version-checks the selected CLIs and installs missing
`jq`. Unsupported arguments fail before installation; download, install, or
version-check errors fail setup.

Copilot installs to `$HOME/.local/bin` and OpenCode to `$HOME/.opencode/bin`.
The installer updates its `PATH` and Actions' `GITHUB_PATH`, not shell startup
files. For local use, add the installed directories to your shell (both shown):

```sh
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

For OpenCode, install `opencode` and invoke `--harness opencode`. Both CLIs use
[model profiles](../../.github/model-config.json). `--profile NAME` defaults to
`default`; select other configured names explicitly:

```sh
./scripts/ai.sh --harness copilot --profile route --prompt "Determine whether the event should start issue implementation."
./scripts/ai.sh --harness copilot --profile triage --prompt "Assess whether the issue is ready for implementation."
./scripts/ai.sh --harness copilot --profile implement --prompt "Implement the requested change."
./scripts/ai.sh --harness opencode --profile review --prompt "Review the current diff."
```

Profiles supply `model`, `reasoningEffort`, and Copilot-only `longContext`, without
schema validation. Unknown profiles fail, with no fallback. PR and repository
review share `review`.

## Shared Factory action

Factory workflows use [`.github/actions/ai`](../../.github/actions/ai/action.yml)
to install and invoke a CLI through these scripts:

```yaml
- name: Run a prompt
  id: worker
  uses: ./.github/actions/ai
  with:
    gh-token: ${{ github.token }}
    prompt: Reply with 'Hello from CI'. Do not use any tools.
```

- Check out the repository first. Factory callers use `github.workflow_sha`;
  implementation also needs App-authenticated checkout and full history.
- `prompt` and `gh-token` are required; `profile` defaults to `default`.
- Prompts are data, not shell code. Use Actions expressions for runtime values,
  not shell variable expansion in the input.
- `harness` defaults to `copilot`, as used by current callers. Set
  `harness: opencode` to select OpenCode. Only that CLI is installed and invoked;
  other values fail before installation.
- The caller chooses `gh-token`: built-in for routing, reviewer App for PR review,
  Factory App for other workers. Only invocation receives it as `GH_TOKEN`;
  `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` use the built-in token.
- `skipped` forwards the invocation's `GITHUB_OUTPUT` value for triage/review
  receipt checks. Install and invocation errors fail the action, not skip it.

Checkout, App permissions/token creation, Git identity, prompts, and receipt checks
remain in the owning workflows.

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
