# Install AI tools and run a prompt

Use this reusable snippet as a starting point for a manually triggered workflow;
it is not an installed workflow in this repository. It checks out the scripts and
model configuration, installs the standalone tools without Node.js/npm, and runs a
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

[`scripts/install-tools.sh`](../../scripts/install-tools.sh) uses the official
[Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
and [OpenCode](https://opencode.ai/docs/#install) install scripts to install their
latest stable standalone binaries. It retains missing-`jq` installation and
checks both CLI versions; download, installation, or version-check failures fail
the setup.

Copilot installs to `$HOME/.local/bin` and OpenCode to `$HOME/.opencode/bin`.
The installer adds both to its `PATH` and to `GITHUB_PATH` for subsequent Actions
steps, without relying on shell startup files. For local use, add those directories
to your calling shell before invoking `scripts/ai.sh`:

```sh
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

Use `--harness opencode` to run the same prompt through OpenCode. Both harnesses
read named profiles from [`.github/model-config.json`](../../.github/model-config.json).
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

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
