# Create an issue

This issue-creation example was tested successfully. Keep the setup steps from
[Install AI tools and run a prompt](ai-tools.md) and replace the job permissions
with:

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

`contents: read` is enough for checkout; `issues: write` allows issue creation.
The historical workflow also set `persist-credentials: false` on checkout,
because this test does not push commits. Each run creates a new `test` issue.

## Verify the result

Copilot can report a tool failure and still exit successfully. A green workflow
run alone does not prove the issue was created. Check the reported URL with
`gh issue view <URL>`, or add an explicit CI existence check.
