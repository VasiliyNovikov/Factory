# Local checks during reviews

[PR review](pr-review.md#local-checks) and
[repository review](repository-review.md#review-scope), plus
[implementation self-review](issue-implementation.md#internal-reviewer-contract),
set what may run. All use these safeguards:

- Inspect each check and its invoked code first. Reject credential access,
  destructive actions, and external mutations. Unsafe or inconclusive checks
  and checks needing GitHub authentication are evidence gaps; never supply tokens.
- Prefer existing tools. Use temporary workspaces, preserve the checkout,
  guidance, and reviewed source, and clean up afterwards.
- Use `env -u` to remove `GH_TOKEN`, `GITHUB_TOKEN`,
  `COPILOT_GITHUB_TOKEN`, `GITHUB_OUTPUT`, `GITHUB_ENV`, `GITHUB_PATH`,
  `GITHUB_STATE`, and `GITHUB_STEP_SUMMARY` from every check and its descendants.
  This includes static validators, copied/adapted snippets, synthetic probes,
  and permitted dependency downloads and installs.
  Never pass credentials or command-file paths through arguments or files, or
  reintroduce them inside a check.
- Keep ordinary source/evidence reads, authenticated GitHub operations, model
  access, publication, and reporting in the coordinator. Do not source the
  check shell or strip the coordinator's environment globally.

For example, after inspecting the checks, run them from the source workspace:

```sh
(
  exec env -u GH_TOKEN -u GITHUB_TOKEN -u COPILOT_GITHUB_TOKEN \
    -u GITHUB_OUTPUT -u GITHUB_ENV -u GITHUB_PATH -u GITHUB_STATE \
    -u GITHUB_STEP_SUMMARY \
    bash -euo pipefail -c 'bash -n scripts/ai.sh; shellcheck scripts/ai.sh'
)
```

Adapt the example to the review; the commands are illustrative, but all eight
exclusions are required. The subshell keeps `exec` from replacing the coordinator.
For compound commands, pipelines, and installation steps, strip variables from
the entire shell, not just the first command or pipeline stage.

Removing variables prevents accidental inheritance, not same-runner access to
credentials or runner files. These are behavioral rules, not a sandbox.
