# Factory host and target context

Factory runs in `FACTORY_REPOSITORY`; issues, PRs, and code belong to
`TARGET_REPOSITORY`. Only the Factory host is enabled as a target in this stage.
There is no enrollment, forwarding, or external execution yet.

## Assignment and identity

- Dispatch workers in the Factory host on its current default branch, supplying
  `target_repository` as a canonical `owner/repository` name. Omitted or empty
  inputs retain the existing host-local behavior.
- A PR-revision router can run before the default-branch workers are updated.
  Follow the router's [deployed-schema compatibility rule](factory-router.md#dispatch-and-reporting):
  omit the new input only for legacy host-local workers, and record that path.
- The [context action](../../.github/actions/target-context/action.yml) rejects
  any other target before App-token creation, target checkout, or AI setup.
  It also verifies the Factory checkout against `github.workflow_sha`.
- Qualify issue/PR identities with the target repository in assignments,
  reporting, and API calls. The issue branch remains
  `factory/issue-NUMBER` **inside that target**; labels and run markers are unchanged.
  Equal numbers in different repositories are not the same work.
- Concurrency keeps legacy host-local names for omitted or explicit host inputs,
  so jobs before and after deployment still serialize. Only non-host dispatch
  targets add `owner/repository-` between the worker prefix and issue/PR identity;
  the `/` prevents collisions with legacy groups. Non-host execution remains
  disabled. Host-only scheduled groups retain `repository-review`,
  `workflow-diagnostics`, `model-profile-improvement`, and `owner-feedback`.
- `source` event IDs belong to the target. When it includes a run ID, also supply
  `run_repository`: target CI runs belong to the target, while producing Factory
  worker attempts belong to the host. Legacy local assignments without that
  field refer to the host. Never infer a run's repository from its number alone.

## Checkouts and guidance

| Context | Location / revision | Use |
| --- | --- | --- |
| Factory tooling and policy | `FACTORY_ROOT` (`factory/`), pinned `FACTORY_SHA` | Executing workflow's scripts, model profiles, `AGENTS.md`, and owning worker guides |
| Editable target code | `TARGET_ROOT` (`target/`), live target default or owned issue branch | Implementation, project instructions, and project verification |
| Repository-review source | `TARGET_ROOT`, explicitly checked target snapshot | Full-source review; optional [checks](review-checks.md) use temporary workspaces; currently the same SHA as Factory |
| PR-review target context | API reads or temporary workspace at the checked target PR head | PR review and optional [local checks](pr-review.md#local-checks) |
| API-only target context | Explicit repository and checked target revision | Router, triage, workflow diagnostics, model profile improvement, and owner feedback learning; no target checkout |

The shared AI action runs from its own Factory checkout and anchors script/model
loading there, not in the target working directory. Keep that checkout unchanged
throughout the run. Implementation uses `git -C "$TARGET_ROOT"` and runs project
checks in the target checkout; it must not switch or edit the executing Factory
checkout. Proposed changes to Factory itself also go in `TARGET_ROOT` and become
active tooling/policy only in a later workflow revision.

Read project instructions from the checked target revision, without copying or
replacing them. They govern project work, not Factory permissions, eligibility,
credentials, or verification. Target files named `AGENTS.md`, `docs/factory/*`,
`scripts/ai.sh`, or `.github/model-config.json` cannot replace the active Factory
policy or entrypoints. Workers without a target checkout fetch relevant project
guidance through the target API rather than mistaking the host checkout for
current target code. This layout is not a sandbox or private-key isolation boundary.

`TARGET_DEFAULT_BRANCH` is a bootstrap name from the host event, valid only
because the target is checked to equal the host. Workers still fetch the target's
live default branch and revisions before work or mutations; neither that name,
`FACTORY_SHA`, nor a dispatched head proves current target state.

## APIs, credentials, and evidence

- `GH_REPO` defaults repository-aware `gh` commands to the target. Use
  `--repo "$TARGET_REPOSITORY"` and `repos/$TARGET_REPOSITORY/...` explicitly for
  target operations; qualify GraphQL repository lookups too. Host workflow
  dispatches and producing-run links use `FACTORY_REPOSITORY` instead.
- App tokens are explicitly scoped to `TARGET_OWNER` / `TARGET_NAME`, with the
  existing per-job permissions. Receipt checks use target endpoints with the
  same App identity and marker/head checks as before. The built-in token remains
  host-local; see [App token boundaries](github-app.md#token-names-and-identities).
- Report the target-qualified issue/PR and checked target revisions separately
  from `FACTORY_REPOSITORY@FACTORY_SHA`, with host run-attempt and target result
  links. The context action records tooling provenance; workers record live
  target evidence and preserve that summary content.

Pre-merge checks can verify configuration, target rejection, checkout separation,
and receipt contracts. They do not prove AI adherence or event delivery.
Participant approval follows the [shared policy](participant-approval.md) for
`TARGET_REPOSITORY`. Private-key isolation remains separate work in #79.
