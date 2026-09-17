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
The optional `--profile NAME` selects an entry by name; omitting it is equivalent
to `--profile default`, so existing workflow commands remain valid.

| Profile | Model | Reasoning effort | Long context |
| --- | --- | --- | --- |
| `default` | `gpt-6-astra` | `high` | `true` |
| `implement` | `gpt-6-astra` | `max` | `true` |
| `review` | `claude-opus-5` | `max` | `true` |

```sh
# Use the default profile.
./scripts/ai.sh --harness copilot --prompt "Summarize the repository."

# Select a named profile with either harness.
./scripts/ai.sh --harness copilot --profile implement --prompt "Implement the requested change."
./scripts/ai.sh --harness opencode --profile review --prompt "Review the current diff."
```

Additional names can be added to the configuration without changing the script.
Each profile is a complete object with nonempty string `model` and
`reasoningEffort` fields and a boolean `longContext`; profiles do not inherit
values. A valid `default` profile is required even when another name is selected.
Missing selector values, unknown names, malformed configuration, and invalid
default or selected entries fail before either CLI is invoked. Unknown names
never fall back to `default`. Workflows do not automatically choose profiles.

Copilot receives the selected model and reasoning effort, with `longContext`
mapped to `--context long_context` when true and `--context default` when false.
OpenCode uses the selected model with the `github-copilot/` prefix and the
reasoning effort as its variant; it ignores `longContext`. Its existing
`OPENCODE_CONFIG_CONTENT` settings are preserved, including a supplied
`Copilot-Integration-Id` header (otherwise `copilot-developer-cli` is added).

Run the wrapper's regression checks with `bash scripts/test-ai.sh`. They require
only Bash, `jq`, and standard Unix utilities, use temporary configuration copies
and stubbed CLIs, and make no live model requests.

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
