# Repository guidance

- This is an initial scaffold for an agentic software factory experiment. The
  unchecked items in `README.md` are goals: running GitHub Copilot CLI in CI and
  giving it read/write access to the repository, issues, and PRs. No application
  code is implemented yet.
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  placeholder with a no-op job; Copilot integration is not implemented yet.
- No toolchain, dependency manifest, or build/test/lint commands are configured.
