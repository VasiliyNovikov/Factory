# Local checks during reviews

[PR review](pr-review.md#local-checks) and
[repository review](repository-review.md#review-scope) set what may run. Both use
these safeguards:

- Inspect each check and its invoked code first. Reject credential access,
  destructive actions, and external mutations. Unsafe or inconclusive checks
  and checks needing GitHub authentication are evidence gaps; never supply tokens.
- Prefer existing tools. Use temporary workspaces, preserve the checkout,
  guidance, and reviewed source, and clean up afterwards.
- Use `env -u` to remove `GH_TOKEN`, `GITHUB_TOKEN`, and `COPILOT_GITHUB_TOKEN`
  from every check subprocess, including permitted dependency installs. Also
  remove `GITHUB_OUTPUT`, `GITHUB_ENV`, `GITHUB_PATH`, `GITHUB_STATE`, and
  `GITHUB_STEP_SUMMARY`. Never pass credentials or command-file paths through
  arguments or files; leave the coordinator's environment unchanged.

Removing variables prevents accidental inheritance, not same-runner access to
credentials or runner files. These are behavioral rules, not a sandbox.
