# Triage issues before implementation

[Issue triage](../.github/workflows/issue-triage.yml) handles newly opened issues,
new comments on open untriaged issues, and removal of `factory-triage-pending`
after a sub-issue is prepared. Pending children are skipped, including on comments.
PR comments go to the separate [implementation workflow](issue-implementation.md).
Only Factory's own comments are ignored by author; other bots and humans can
provide clarification. Factory's child-release label events are not ignored.

The workflow runs `scripts/ai.sh --harness copilot --profile triage`, using the
`triage` profile's model, reasoning effort, and context settings from
[`.github/model-config.json`](../.github/model-config.json).

Copilot reads the issue, full discussion, repository guidance, relevant code,
decomposition plans, and existing child work. It chooses one of three outcomes:

- **Ready:** summarize a cohesive implementation's scope and acceptance criteria,
  then hand it off with `<!-- factory-triage:ready -->`.
- **Decomposed:** autonomously split a larger request into native sub-issues when
  independent delivery is useful, with `<!-- factory-triage:decomposed -->`
  only after their setup is verified. Do not split tightly coupled work just to
  create more issues.
- **Reply:** ask specific questions or explain why the request is unsuitable,
  already satisfied, blocked, or only partially decomposed, with
  `<!-- factory-triage:reply -->`. A later comment can trigger reassessment or recovery.

`triaged` means **ready for implementation**, not just inspected. This workflow
does not implement code or open PRs.

## Direct implementation handoff

Copilot rechecks that the issue is open and untriaged, with no pending label,
decomposition plan, native children, or `decomposed` label. For a ready decision, it:

1. Creates repository labels if needed.
2. Posts the agreed scope and acceptance criteria in a marked decision comment.
3. Adds `factory-issue-<issue-number>` to the issue and verifies it.
4. Adds `triaged` in a separate API request, emitting the implementation handoff event.

The labels are applied using the Factory App token so the `issues: labeled`
event starts the implementation workflow. Copilot is instructed to reply about a conflicting
`factory-issue-*` label instead of assigning multiple identities. Retrying a partially completed
handoff reuses the existing tracking label. Both labels are later copied onto
the PR; the shared tracking label becomes its implementation concurrency key.

## Decomposition and recovery

The parent remains open and untriaged. `decomposed` reserves it for child work;
it protects both completed splits and partial attempts, not just successful runs.
It must never be directly implemented, even if a later comment requests work or
someone also adds `triaged`. Implementation routing rechecks this guard, including
when feedback arrives through a PR or CI run.

Copilot uses this sequence rather than a separate scripted planning engine:

1. Persist a Factory-authored `<!-- factory-decomposition-plan -->` comment with
   stable child keys, bounded scopes, acceptance criteria, context, and dependencies.
   Add and verify `decomposed` before creating children. Preserve unrelated labels;
   do not add `triaged` or a new parent tracking label.
2. Read native children and paginate repository issues in **all states** before
   creating missing work. Each new child includes
   `<!-- factory-child:OWNER/REPO#PARENT_NUMBER:KEY -->` in its body and
   `factory-triage-pending` in its creation request. It has a parent link,
   actionable scope, acceptance criteria, relevant context, and explicit dependencies.
   No parent tracking label or ready/decomposed state is copied.
3. Create or reuse the native relationship using GitHub's
   [sub-issue API](https://docs.github.com/en/rest/issues/sub-issues).
   `POST .../issues/PARENT_NUMBER/sub_issues` takes the child's integer database
   `id` as `sub_issue_id`, not its issue number. Verify every intended child in
   the paginated native list and check its `GET .../issues/CHILD_NUMBER/parent`.
   For a verified accessible child, that endpoint's HTTP 404 with message
   `No parent issue found` means it is not linked yet: link and re-check it.
   Other 404s, permission errors, and ambiguous failures are not proof of missing
   parentage. Never replace an existing different parent.
4. Once **all** intended relationships, scopes, and dependency references are
   verified, remove `factory-triage-pending` from open pending children with the
   App token. A closed pending child still blocks completed setup: preserve its
   state and labels and post a reply explaining the blocker, not a completed
   decomposition marker. Removing the label from an open child emits the
   `issues: unlabeled` event that starts ordinary child triage.
   Each child can need clarification or further decomposition; only its own
   ready path applies its own tracking label before `triaged`.
5. Verify the parent remains open with `decomposed` and without `triaged`, all
   intended links exist, and no child is pending. Post the completed split,
   child links, and dependencies with the decomposed decision marker.

The pending label prevents the child's `opened` event racing ahead of native
linking or dependency setup. Only removal of that label is an extra triage
trigger; arbitrary label changes do not retriage issues.

On retries, reconcile the durable plan, its recorded child URLs, existing native
children, and exact child markers from the Factory identity before creating
anything. All-state listing also finds a child whose creation succeeded but
whose response or subsequent linking failed; search indexing alone is insufficient.
Reuse intended children and links, and release only remaining prepared children.
Do not re-add pending to released children, duplicate closed work, reopen children,
or overwrite conflicting ownership or parentage.

An uncertain API outcome that cannot be resolved gets an explicit reply, not a
blind retry. Partial failures retain the plan and protective labels and report
created links, errors, and unfinished steps. A later non-Factory parent comment
resumes reconciliation. Already-decomposed parents stay on this path; they never
fall back to direct handoff. This is not automatic completion tracking, merging,
or parent/child closure.

Triage runs are serialized per issue using `issue-triage-<number>`. Live state is
checked after waiting so a comment queued before handoff does not retriage an
already-ready issue or release pending work. Direct handoff ends triage;
decomposed parent comments remain eligible for recovery. Implementation has its
own shared issue/PR concurrency group. GitHub retains at most one pending run
per group, so each assessment reads the full discussion.

## Setup and verification

Use the [Factory App credentials](github-app.md)
`FACTORY_CLIENT_ID` and `FACTORY_PRIVATE_KEY`. Triage requests **Contents: Read**
and **Issues: Read and write**. Copilot uses the built-in token with
`copilot-requests: write`. The workflow must be on the default branch.

Triage uses `gh` with the existing `GH_TOKEN` (Factory App token) for repository
and issue reads, discussion refreshes, replies, and labels. The built-in
`GITHUB_TOKEN` has no Issues access; substituting it for `GH_TOKEN` can cause
HTTP 403 on issue reads. `COPILOT_GITHUB_TOKEN` authenticates model requests.

See the shared setup for approving installation permission updates.

For requests changing workflow files, the implementation token must already
request `permission-workflows: write` on the default branch and the installation
must grant it. GitHub checks this permission when pushing the PR branch, before
merge. After resolving a blocked prerequisite, post a new issue comment to
trigger reassessment.

A read-only verification step requires exactly one Factory comment with this run's
marker and exactly one decision marker. Ready results must match live open-issue
state, the unique tracking label, `triaged`, and no decomposition/pending state.
An existing Factory decomposition plan also rejects a ready result.
Decomposed results require an open protected parent, a persisted Factory
decomposition plan, native children, and no pending or inherited child tracking
labels; ready children need their own tracking identity. Missing comments,
inconsistent success claims, and API failures fail the step. Reply results also
read the live issue and require `triaged` to be absent; `decomposed` and partial
setup state remain allowed. A conflicting handoff fails verification rather
than removing independently changed labels. A reply can describe a partial
failure; a green reply run does not mean decomposition or handoff succeeded.

Scope quality, the complete intended child set, dependency correctness, and API
mutations remain Copilot's responsibility. The verifier checks live postconditions,
not the quality of its decisions or completion of child implementation.
See [issue implementation](issue-implementation.md) for the next stage.

End-to-end verification requires live CI runs after these workflows are on the
default branch. Exercise ready and clarification paths, decomposition and child
triage, parent follow-ups, partial-attempt recovery, and closed or conflicting
work. Inspect native links, parent/child labels, Factory-authored decision
comments, and individual triage runs rather than treating a successful agent
response or a single green job as proof of the whole flow.
