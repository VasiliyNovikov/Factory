---
name: Owner feedback shadow analysis
description: Manual, read-only gh-aw comparison; findings are previews, never issues.
on:
  workflow_call:
    inputs:
      expected_sha:
        required: true
        type: string
      window_end:
        required: true
        type: string
      model:
        required: true
        type: string
      effort:
        required: true
        type: string
      context:
        required: true
        type: string
  github-token: ${{ secrets.GITHUB_TOKEN }}
  reaction: none
  status-comment: false
if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
permissions:
  contents: read
  issues: read
  pull-requests: read
  copilot-requests: write
concurrency:
  group: owner-feedback-shadow-native
  cancel-in-progress: false
features:
  group-concurrency-queue: false
engine:
  id: copilot
  cwd: factory
  model: ${{ inputs.model }}
  args:
    - --disable-builtin-mcps
    - --enable-memory
  harness:
    use: factory_shadow_harness.cjs
    max-retries: 0
  env:
    GH_AW_HARNESS_STARTUP_RETRIES: "0"
    SHADOW_REVIEW_EFFORT: ${{ inputs.effort }}
    SHADOW_REVIEW_CONTEXT: ${{ inputs.context }}
  concurrency:
    group: owner-feedback-shadow-engine
    cancel-in-progress: false
timeout-minutes: 35
checkout:
  repository: ${{ github.repository }}
  ref: ${{ github.workflow_sha }}
  path: factory
  github-token: ${{ secrets.GITHUB_TOKEN }}
  pull-request: false
sandbox:
  agent:
    model-fallback: false
    token-steering: false
network:
  allowed:
    - defaults
    - github
    - developers.openai.com
    - platform.openai.com
    - platform.claude.com
    - docs.anthropic.com
    - www.anthropic.com
    - claude.com
tools:
  bash: [":*"]
  edit: false
  github:
    mode: gh-proxy
    github-token: ${{ secrets.GITHUB_TOKEN }}
    allowed-repos: ["vasiliynovikov/factory"]
    min-integrity: none
safe-outputs:
  github-token: ${{ secrets.GITHUB_TOKEN }}
  staged: true
  report-failure-as-issue: false
  report-failed-jobs: false
  noop:
    report-as-issue: false
  report-missing-tool:
    create-issue: false
  report-missing-data:
    create-issue: false
  report-incomplete:
    create-issue: false
  threat-detection:
    report-as-issue: false
    continue-on-error: false
  create-issue:
    max: 1
    labels: []
    max-issue-artifacts: 0
steps:
  - name: Set Factory target context
    uses: ./factory/.github/actions/target-context
    with:
      target-repository: ${{ github.repository }}
pre-agent-steps:
  - name: Bind comparison revision and deadline harness
    env:
      GH_TOKEN: ${{ github.token }}
      EXPECTED_SHA: ${{ inputs.expected_sha }}
      WINDOW_END: ${{ inputs.window_end }}
    run: |
      set -euo pipefail
      if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] ||
        [[ ! "$WINDOW_END" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] ||
        [[ "$(date -u -d "$WINDOW_END" +%FT%TZ)" != "$WINDOW_END" ]] ||
        (( $(date -u -d "$WINDOW_END" +%s) > $(date -u +%s) )); then
        echo "::error::Provide a full default SHA and a valid, non-future UTC window end."
        exit 1
      fi
      default_branch=$(gh api "repos/$TARGET_REPOSITORY" --jq .default_branch)
      live_sha=$(gh api "repos/$TARGET_REPOSITORY/commits/$default_branch" --jq .sha)
      if [[ "$live_sha" != "$EXPECTED_SHA" ]]; then
        echo "::error::Comparison default revision changed; choose a fresh matched baseline."
        exit 1
      fi
      {
        printf 'SHADOW_TARGET_SHA=%s\n' "$live_sha"
        printf 'SHADOW_WINDOW_END=%s\n' "$WINDOW_END"
        printf 'SHADOW_WINDOW_START=%s\n' "$(date -u -d "$WINDOW_END -90 days" +%FT%TZ)"
      } >> "$GITHUB_ENV"
      cp "$FACTORY_ROOT/scripts/owner-feedback-shadow.cjs" \
        "$RUNNER_TEMP/gh-aw/actions/factory_shadow_harness.cjs"
---

Read AGENTS.md and the **Staged shadow experiment** section of
docs/factory/owner-feedback.md in FACTORY_ROOT. Assess the supplied
SHADOW_WINDOW_START / SHADOW_WINDOW_END window at SHADOW_TARGET_SHA using the
current `review` profile. This is a read-only comparison, not publication authority.

Complete the assessment and retain the full report in GITHUB_STEP_SUMMARY and
the final CLI response before AI_DEADLINE_UTC. Only after finishing the report and
any native tasks, preview at most one genuinely new, unlabeled finding with
`create_issue`; use `noop` for complete coverage with no new finding, or
`report_incomplete` for missing evidence or failures. A staged output is not a
created issue or a verified isolation result.
