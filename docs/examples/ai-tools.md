# Install AI tools and run a prompt

Use this reusable snippet as a starting point for a manually triggered workflow;
it is not an installed workflow in this repository. It checks out the scripts and
model configuration, installs standalone Copilot without Node.js/npm, and runs a
basic prompt.

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

[`scripts/install-tools.sh`](../../scripts/install-tools.sh) uses the official
[Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
and [OpenCode](https://opencode.ai/docs/#install) install scripts to install their
latest stable standalone binaries:

| Command | Installed CLIs |
| --- | --- |
| `./scripts/install-tools.sh copilot` | Copilot only (the example above) |
| `./scripts/install-tools.sh opencode` | OpenCode only |
| `./scripts/install-tools.sh` | Both, preserving direct-install compatibility |

Only the selected CLI is downloaded and version-checked, or both when no argument
is supplied. Unsupported arguments fail before installation. Missing `jq` is still
installed; download, installation, or version-check failures fail the setup.

Copilot installs to `$HOME/.local/bin` and OpenCode to `$HOME/.opencode/bin`.
The installer adds the installed CLI directories to its `PATH` and to `GITHUB_PATH`
for subsequent Actions steps, without relying on shell startup files. For local
use, add the corresponding directories to your calling shell before invoking
`scripts/ai.sh` (both shown here):

```sh
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

To run the same prompt through OpenCode, change the installation argument to
`opencode` and the invocation to `--harness opencode`. Both harnesses read named
profiles from [`.github/model-config.json`](../../.github/model-config.json).
`--profile NAME` defaults to `default`; select `route`, `triage`, `implement`,
`review`, or any other configured name explicitly:

```sh
./scripts/ai.sh --harness copilot --profile route --prompt "Determine whether the event should start issue implementation."
./scripts/ai.sh --harness copilot --profile triage --prompt "Assess whether the issue is ready for implementation."
./scripts/ai.sh --harness copilot --profile implement --prompt "Implement the requested change."
./scripts/ai.sh --harness opencode --profile review --prompt "Review the current diff."
```

Profiles supply `model`, `reasoningEffort`, and `longContext` without schema
validation. `longContext` applies only to Copilot. Unknown names fail rather than
falling back to `default`.

PR review and full-repository review share `review`; changing that profile updates
both reviewers.

## Shared Factory action

Factory workflows use [`.github/actions/ai`](../../.github/actions/ai/action.yml)
to combine tool installation and harness invocation through these same scripts:

```yaml
- name: Run a prompt
  id: worker
  uses: ./.github/actions/ai
  with:
    gh-token: ${{ github.token }}
    prompt: Reply with 'Hello from CI'. Do not use any tools.
```

- Check out the repository before using this local action. Factory callers retain
  their `github.workflow_sha` checkout; implementation retains App authentication
  and full history.
- `prompt` and `gh-token` are required; `profile` defaults to `default`.
  Prompts are passed as data, not shell code. Use Actions expressions for invocation
  values, not shell variable expansion in the input.
- `harness` defaults to `copilot`; the action installs and invokes only that CLI.
  Set `harness: opencode` under `with:` to install and invoke only OpenCode.
  Other values fail setup before installation. Existing Factory callers omit this
  input and continue to use Copilot, without installing OpenCode.
- The caller selects `gh-token`: the built-in token for routing and maintenance,
  `steps.reviewer-token.outputs.token` for PR review, or
  `steps.factory-token.outputs.token` for other App workers. The action exports it as
  `GH_TOKEN` only for invocation, not installation. `GITHUB_TOKEN` and
  `COPILOT_GITHUB_TOKEN` use the built-in token in that same invocation.
- `skipped` forwards the invocation's `GITHUB_OUTPUT` value, preserving
  `steps.worker.outputs.skipped` for triage/review receipt checks. Installation and
  invocation failures fail the action; they are not converted into skips.

Checkout, App permissions/token creation, Git identity, prompts, and receipt checks
remain in the owning workflows.

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
