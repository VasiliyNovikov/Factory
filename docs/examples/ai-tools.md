# Install AI tools and run a prompt

This reusable snippet installs standalone Copilot without Node.js/npm and runs a
prompt. It is not an installed workflow. Direct script calls make one setup
attempt; use the [shared Factory action](#shared-factory-action) for setup retries.

```yaml
name: CI

on:
  workflow_dispatch:

jobs:
  ai:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      copilot-requests: write
    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Install Copilot
        run: ./scripts/install-tools.sh copilot

      - name: Run a prompt
        timeout-minutes: 5
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

Bootstrap scripts run only after a successful, nonempty download.

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
schema validation. Unknown profiles fail, with no fallback. PR review, repository
review, model profile improvement,
[owner feedback learning](../factory/owner-feedback.md), and
[implementation self-review](../factory/issue-implementation.md#internal-self-review)
share `review`. Implementation stays on `implement` and invokes the same runner
with `--profile review` for its internal pre-publication pass; it does not install
another CLI or replace independent PR review.

[Model profile improvement](../factory/model-profile-improvement.md) evaluates
every caller weekly and files evidence-backed, unlabeled issues for triage. Its
evaluator owns live model discovery and compatibility checks; ordinary
invocations remain unchanged.

## Shared Factory action

Factory workflows use [`.github/actions/ai`](../../.github/actions/ai/action.yml)
to install and invoke a CLI. The installation step retries failures; AI invocation
is not retried and runs only after setup succeeds. Settings live in the action and
[installer](../../scripts/install-tools.sh). Only bootstrap downloads have a time
limit; a hung vendor installer or version check waits for the caller's job timeout.

```yaml
- name: Run a prompt
  id: worker
  uses: ./.github/actions/ai
  with:
    gh-token: ${{ github.token }}
    budget: 5
    prompt: Reply with 'Hello from CI'. Do not use any tools.
```

- Check out the repository first. Factory callers use `github.workflow_sha`;
  implementation also needs App-authenticated checkout and full history.
- `prompt`, `gh-token`, and `budget` are required; `profile` defaults to `default`.
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

### Invocation budget

Set `budget` to a whole number of minutes from 1 to 360. The action starts this
budget immediately before invoking the harness, after installation. It exports
`AI_BUDGET_MINUTES` and the absolute `AI_DEADLINE_UTC` (UTC ISO 8601). One short
budget/deadline notice is shared by the prompt and Actions log; the task and
subtask rules stay in this guide. Child processes inherit the environment
variables; coordinators must also pass the remaining time and an earlier deadline
to delegated tasks, reserving time to integrate results.

Finish all AI-owned work, including checks, publication, reporting, and outcome
verification, before `AI_DEADLINE_UTC`. Subtasks, including implementation's
internal review, share that deadline rather than receiving a fresh budget.
Do not weaken required checks to meet it; report incomplete work accurately.

The action uses GNU `timeout` around `scripts/ai.sh`: expiry sends `TERM`, with
`KILL` after a further 30 seconds if needed. The command's exit status passes
directly to GitHub Actions; nonzero means step failure, including on timeout.
For diagnostics, use the notice's Actions timestamp as the invocation start,
and the invocation step's completion time and exit status from Actions. A hard
timeout is not a skip or permission to omit reporting; the killed agent cannot
finish its report. Direct `scripts/ai.sh` calls do not start a new budget or timeout.

Factory jobs omit `timeout-minutes`, restoring GitHub's
[default job limit](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes).
Checkout, token creation, harness installation, and post-invocation receipt checks
are outside the AI budget, but remain subject to the job/runner limits. Any shorter
enclosing limit still wins. The invocation boundary is inside the composite
action so installation does not consume the AI budget.

Build on this setup to [create a pull request](create-pull-request.md) or
[create an issue](create-issue.md).
