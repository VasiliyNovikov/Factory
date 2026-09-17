# Install AI tools and run a prompt

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
read named profiles from [`.github/model-config.json`](../.github/model-config.json).
`--profile NAME` defaults to `default`; select `triage`, `implement`, `review`, or any
other configured name explicitly:

```sh
./scripts/ai.sh --harness copilot --profile triage --prompt "Assess whether the issue is ready for implementation."
./scripts/ai.sh --harness copilot --profile implement --prompt "Implement the requested change."
./scripts/ai.sh --harness opencode --profile review --prompt "Review the current diff."
```

Profiles supply `model`, `reasoningEffort`, and `longContext` without schema
validation. `longContext` applies only to Copilot. Unknown names fail rather than
falling back to `default`.

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
