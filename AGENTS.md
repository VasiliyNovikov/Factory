# Repository guidance

- This is an initial scaffold for an agentic software factory experiment.
  `README.md` tracks completed CI access milestones. No application code is
  implemented yet.
- CI examples live in `docs/`. Keep them aligned with the scripts and workflow
  when changing them:
  - [AI tool setup and invocation](docs/ai-tools.md)
  - [PR creation](docs/create-pull-request.md)
  - [Issue creation](docs/create-issue.md)
- `.github/workflows/ci.yml` is a manually triggered (`workflow_dispatch`)
  Copilot PR-creation test. See the linked examples for setup, permissions,
  invocation, and result verification.
- No application toolchain, dependency manifest, or build/test/lint commands are
  configured.
