# Review a pull request

[PR review](../.github/workflows/pr-review.yml) is a separate workflow that runs
when a PR is opened, updated with new commits, reopened, or marked ready for
review. Draft PRs and fork PRs are skipped; the example uses the repository's
write-capable Actions token. New runs cancel older reviews of the same PR.

The workflow uses the shared [AI tool setup](ai-tools.md) with these permissions:

```yaml
permissions:
  contents: read
  pull-requests: write
  copilot-requests: write
```

It checks out the base revision for the installation script, harness, and model
configuration. Copilot reads the proposed changes through `gh pr view`,
`gh pr diff`, and read-only API calls, rather than executing the PR's code.

## Review outcome

- Actionable findings: submit a comment review with file/line references and
  suggested fixes, using inline review comments where possible.
- No actionable findings: submit an approval.
- PR authored by `github-actions[bot]`: submit a comment review even when clean,
  because the same bot identity cannot approve its own PR.
- Incomplete review or API failure: report the error without approving.

The review is attached to the event's head commit. Copilot is instructed to check
that the PR is still open, ready, and at that commit before posting. A final API
check requires a submitted bot review matching that commit and a unique run
marker, so a successful Copilot exit alone does not make the job pass.

## Run and verify

Enable **Settings → Actions → General → Workflow permissions → Allow GitHub
Actions to create and approve pull requests** for approvals.

After the workflow is on `master`, open a non-draft PR from a branch in this
repository. PRs created or updated using `GITHUB_TOKEN`, including the PR-creation
example, require a user with write access to select **Approve workflows to run**
on the PR before their `pull_request` workflows start. See
[GitHub's workflow triggering guide](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

Check **Actions → PR review** and the PR's review timeline. The job's verification
step confirms that a review was posted; it does not independently validate the
quality of Copilot's findings. This example has not yet been tested in CI.
