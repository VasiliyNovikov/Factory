# Create an issue

This tested snippet creates one new `test` issue per run. It is not an installed
workflow. Keep the [AI setup](ai-tools.md) and use these job permissions:

```yaml
permissions:
  contents: read
  issues: write
  copilot-requests: write
```

Replace the basic prompt step with:

```yaml
- name: Create test issue with Copilot
  env:
    GITHUB_TOKEN: ${{ github.token }}
  run: >-
    ./scripts/ai.sh
    --harness copilot
    --prompt "Use the GitHub CLI (gh issue create) to create exactly one new issue in repository ${GITHUB_REPOSITORY}
    with the title 'test' and body 'Created by Copilot CLI in CI. Run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}'.
    Actually create the issue, then report its URL. If creation fails, report the error."
```

`contents: read` allows checkout; `issues: write` allows creation. The tested
workflow used `persist-credentials: false` on checkout because it does not push.

## Verify the result

A successful Copilot exit does not prove creation. Check the reported URL with
`gh issue view <URL>`, or add a CI existence check.
