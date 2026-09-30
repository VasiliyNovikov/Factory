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
- For read-only history inspection in a bare clone, explicitly select its Git
  directory for every command with `git --git-dir="$bare_repo" ...` or
  command-scoped `GIT_DIR`, not implicit discovery via `cd` or `git -C` alone.
  This works with `safe.bareRepository=explicit`; do not weaken that setting.
  Read the exact reviewed commit. A separate normal clone/worktree is also valid.
- Use `env -u` to remove `GH_TOKEN`, `GITHUB_TOKEN`, and `COPILOT_GITHUB_TOKEN`
  from every check subprocess, including permitted dependency installs. Also
  remove `GITHUB_OUTPUT`, `GITHUB_ENV`, `GITHUB_PATH`, `GITHUB_STATE`, and
  `GITHUB_STEP_SUMMARY`. Never pass credentials or command-file paths through
  arguments or files; leave the coordinator's environment unchanged.

Removing variables prevents accidental inheritance, not same-runner access to
credentials or runner files. These are behavioral rules, not a sandbox.

## Verification limits

For bare-clone history inspection, link a later live PR review and its checked
guidance revision showing the expected reviewed head was read without
implicit-access failures or retries. This remains pending until observed; a
focused Git check proves command behavior, not AI adherence.
