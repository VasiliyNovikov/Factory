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
- Run every check through
  [`scripts/review-check.sh`](../../scripts/review-check.sh) from the trusted
  workflow checkout, not the reviewed candidate's copy. This includes static
  validators, copied/adapted snippets, synthetic probes, and permitted dependency
  downloads and installs. Do not reconstruct an exclusion prefix for each command.
- The launcher uses `env -u` to remove `GH_TOKEN`, `GITHUB_TOKEN`,
  `COPILOT_GITHUB_TOKEN`, `GITHUB_OUTPUT`, `GITHUB_ENV`, `GITHUB_PATH`,
  `GITHUB_STATE`, and `GITHUB_STEP_SUMMARY` from the command and its descendants.
  Never pass credentials or command-file paths through arguments or files, or
  reintroduce them inside a check.
- Keep ordinary source/evidence reads, authenticated GitHub operations, model
  access, publication, and reporting in the coordinator. Do not source the
  launcher or strip the coordinator's environment globally.

Save the launcher's absolute path while in the trusted workflow checkout, before
entering a temporary source or check workspace:

```sh
review_check="$PWD/scripts/review-check.sh"
"$review_check" bash -n "$source_checkout/scripts/ai.sh"
"$review_check" bash -c 'set -euo pipefail; cd -- "$1"; bash -n scripts/ai.sh; shellcheck scripts/ai.sh' bash "$source_checkout"
```

Wrap the entire shell for compound commands, pipelines, or installation steps,
not just the first command or pipeline stage. Inspect those commands first, too.
An unavailable launcher or a check that cannot run under it is an evidence gap,
not permission to run unwrapped.

The focused launcher regression check uses existing Python and shell tools:
`"$review_check" python3 "$source_checkout/scripts/test-review-check.py"`.
It checks all eight names with non-secret fixtures, including a local installation
and an unchanged coordinator; it does not prove review-agent adherence.

Removing variables prevents accidental inheritance, not same-runner access to
credentials or runner files. These are behavioral rules, not a sandbox.
