#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
for script in "$repo_root"/scripts/*.sh; do
  bash -n "$script"
done
jq -se 'length == 1 and (.[0] | type == "object")' \
  "$repo_root/.github/model-config.json" > /dev/null || {
  printf 'FAIL: model-config.json must contain one JSON object\n' >&2
  exit 1
}
printf 'PASS: shell syntax and model JSON\n'

profile_references=$(
  yq -o=json -I=0 '
    explode(.) |
    ((select(fileIndex == 0) | .inputs.profile.default),
     (select(fileIndex > 0) | .jobs[].steps[]? |
      select(.uses == "./factory/.github/actions/ai" or .uses == "./.github/actions/ai") |
      .with | select(has("profile")) | .profile)) |
    {"file": filename, "line": line, "profile": .}
  ' "$repo_root/.github/actions/ai/action.yml" "$repo_root"/.github/workflows/*.yml
)
jq -s --slurpfile profiles "$repo_root/.github/model-config.json" '
  .[] | . as $reference |
  if (.profile | type) == "string" and ($profiles[0] | has($reference.profile))
  then empty
  else error("\(.file):\(.line): unknown model profile \(.profile | tojson)")
  end
' <<< "$profile_references"
printf 'PASS: shared AI action default and workflow model profiles\n'

shadow_workflows=$(
  yq -o=json -I=0 'explode(.)' \
    "$repo_root/.github/workflows/owner-feedback-shadow.yml" \
    "$repo_root/.github/workflows/owner-feedback-shadow.lock.yml" | jq -s .
)
jq -e '
  .[0] as $caller | .[1] as $compiled |
  ($caller.on | keys == ["workflow_dispatch"]) and
  ($compiled.on | keys == ["workflow_call"]) and
  ($caller.concurrency == {"group":"owner-feedback","cancel-in-progress":false}) and
  ($caller.jobs.profile.if ==
    "github.ref == format('\''refs/heads/{0}'\'', github.event.repository.default_branch)") and
  ($caller.jobs.shadow.uses == "./.github/workflows/owner-feedback-shadow.lock.yml") and
  ($caller.jobs.shadow.needs == "profile") and
  ($caller.jobs.shadow.with.model == "${{ needs.profile.outputs.model }}") and
  ($caller.jobs.shadow.with.effort == "${{ needs.profile.outputs.effort }}") and
  ($caller.jobs.shadow.with.context == "${{ needs.profile.outputs.context }}") and
  ($caller | tostring | contains("secrets.") | not) and
  all(.[]; all(.jobs[]; .secrets == null and .environment == null)) and
  all(.[]; all((.permissions // {}), (.jobs[].permissions // {});
    type == "object" and
    all(to_entries[]; .value == "read" or .value == "none" or
      (.key == "copilot-requests" and .value == "write")))) and
  ($compiled.jobs.safe_outputs.env.GH_AW_SAFE_OUTPUTS_STAGED == "true") and
  ($compiled.jobs.agent.steps | map(select(.id == "agentic_execution")) | length == 1) and
  ($compiled.jobs.agent.steps[] | select(.id == "agentic_execution") |
    .env.COPILOT_MODEL == "${{ inputs.model }}" and
    .env.SHADOW_REVIEW_EFFORT == "${{ inputs.effort }}" and
    .env.SHADOW_REVIEW_CONTEXT == "${{ inputs.context }}" and
    .env.GH_AW_ENGINE_CWD == "factory" and
    (.run | contains("factory_shadow_harness.cjs")))
' <<< "$shadow_workflows" > /dev/null || {
  printf 'FAIL: shadow admission, secret/permission boundary, staging, or profile binding\n' >&2
  exit 1
}
printf 'PASS: shadow admission, no inherited secrets, read-only permissions and staged outputs\n'

temp_dir=$(mktemp -d)
trap 'rm -rf -- "$temp_dir"' EXIT
mkdir -p "$temp_dir/bin" "$temp_dir/scripts" "$temp_dir/.github"

# Exercise unchanged production code without pinning the live model choices.
cp -- "$repo_root/scripts/ai.sh" "$temp_dir/scripts/ai.sh"
cat > "$temp_dir/.github/model-config.json" <<'JSON'
{
  "default": {
    "model": "fixture-default",
    "reasoningEffort": "medium",
    "longContext": false
  },
  "extended": {
    "model": "fixture-extended",
    "reasoningEffort": "high",
    "longContext": true
  },
  "fusion-standard": {
    "model": "fusion",
    "reasoningEffort": "standard",
    "longContext": false
  },
  "fusion-high": {
    "model": "fusion",
    "reasoningEffort": "high",
    "longContext": true
  },
  "fusion-max": {
    "model": "fusion",
    "reasoningEffort": "max"
  }
}
JSON

cat > "$temp_dir/bin/copilot" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\0' "${0##*/}" "$@" >> "$AI_TEST_ARGS"
if [[ "$AI_TEST_EXIT" != 0 ]]; then
  printf 'fixture CLI failure\n' >&2
fi
exit "$AI_TEST_EXIT"
SH
chmod +x "$temp_dir/bin/copilot"

prompt=$'  "double quotes" and \'single quotes\'\n$HOME $(printf expanded) `printf expanded`; * ? [abc] | & < > \\\n--literal-option\n\n'

fail() {
  printf 'FAIL: %s: %s\n' "$case_name" "$1" >&2
  cat "$temp_dir/output" >&2
  exit 1
}

run_launcher() {
  local cli_status=$1
  shift
  : > "$temp_dir/actual"
  actual_status=0
  PATH="$temp_dir/bin:$PATH" \
    AI_TEST_ARGS="$temp_dir/actual" AI_TEST_EXIT="$cli_status" \
    bash "$temp_dir/scripts/ai.sh" --prompt "$prompt" "$@" \
      > "$temp_dir/output" 2>&1 || actual_status=$?
}

assert_status() {
  [[ "$actual_status" == "$1" ]] \
    || fail "expected exit $1, received $actual_status"
}

assert_args() {
  printf '%s\0' "$@" > "$temp_dir/expected"
  if ! cmp -s "$temp_dir/expected" "$temp_dir/actual"; then
    printf 'Expected arguments:\n' >&2
    jq -Rs 'split("\u0000")[:-1]' "$temp_dir/expected" >&2
    printf 'Received arguments:\n' >&2
    jq -Rs 'split("\u0000")[:-1]' "$temp_dir/actual" >&2
    fail 'CLI arguments differ'
  fi
}

cd -- "$temp_dir"
default_args=(copilot --model fixture-default --reasoning-effort medium
  --context default --disable-builtin-mcps --enable-memory
  --prompt "$prompt" --yolo)
extended_args=(copilot --model fixture-extended --reasoning-effort high
  --context long_context --disable-builtin-mcps --enable-memory
  --prompt "$prompt" --yolo)

case_name='copilot default profile and literal prompt'
run_launcher 0
assert_status 0
assert_args "${default_args[@]}"

case_name='copilot selected profile and literal prompt'
run_launcher 0 --profile extended
assert_status 0
assert_args "${extended_args[@]}"

case_name='copilot CLI failure'
run_launcher 37 --profile extended
assert_status 37
assert_args "${extended_args[@]}"

for selection in 'standard default' 'high long_context' 'max default'; do
  read -r tier context <<< "$selection"
  case_name="copilot Fusion $tier profile and literal prompt"
  run_launcher 0 --profile "fusion-$tier"
  assert_status 0
  assert_args copilot --model fusion --fusion-tier "$tier" \
    --context "$context" --disable-builtin-mcps --enable-memory \
    --prompt "$prompt" --yolo
done

case_name='copilot Fusion CLI failure'
run_launcher 37 --profile fusion-max
assert_status 37
assert_args copilot --model fusion --fusion-tier max \
  --context default --disable-builtin-mcps --enable-memory \
  --prompt "$prompt" --yolo
grep -qx 'fixture CLI failure' "$temp_dir/output" \
  || fail 'CLI error was not preserved'

case_name='copilot unknown profile'
run_launcher 0 --profile missing
(( actual_status != 0 )) || fail 'unknown profile succeeded'
[[ ! -s "$temp_dir/actual" ]] || fail 'unknown profile invoked a CLI'

case_name='copilot unknown argument'
run_launcher 0 --unknown
(( actual_status != 0 )) || fail 'unknown argument succeeded'
[[ ! -s "$temp_dir/actual" ]] || fail 'unknown argument invoked a CLI'

for context in '"false"' null; do
  case_name="copilot invalid context $context"
  jq --argjson context "$context" '.extended.longContext = $context' \
    "$temp_dir/.github/model-config.json" > "$temp_dir/invalid-context.json"
  mv -- "$temp_dir/invalid-context.json" "$temp_dir/.github/model-config.json"
  run_launcher 0 --profile extended
  assert_status 1
  grep -Fq "Invalid model profile 'extended'" "$temp_dir/output" \
    || fail 'invalid context did not name the profile'
  [[ ! -s "$temp_dir/actual" ]] || fail 'invalid context invoked a CLI'
done

printf 'PASS: copilot direct/Fusion profiles, literal prompt, exit status, and invalid arguments\n'

cp "$repo_root/scripts/owner-feedback-shadow.cjs" "$temp_dir/scripts/factory_shadow_harness.cjs"
cat > "$temp_dir/scripts/copilot_harness.cjs" <<'JS'
const { writeFileSync } = require("node:fs");
writeFileSync(process.env.SHADOW_TEST_CAPTURE, JSON.stringify({
  args: process.argv.slice(2),
  budget: process.env.AI_BUDGET_MINUTES,
  deadline: process.env.AI_DEADLINE_UTC,
  now: Date.now(),
}));
process.exit(Number(process.env.SHADOW_TEST_EXIT));
JS
cat > "$temp_dir/bin/timeout" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\0' "$@" > "$SHADOW_TEST_TIMEOUT"
shift 3
exec "$@"
SH
chmod +x "$temp_dir/bin/timeout"

case_name='shadow native harness arguments, deadline and failure propagation'
shadow_status=0
PATH="$temp_dir/bin:$PATH" SHADOW_REVIEW_EFFORT=max SHADOW_REVIEW_CONTEXT=long_context \
  SHADOW_TEST_TIMEOUT="$temp_dir/timeout-args" SHADOW_TEST_CAPTURE="$temp_dir/shadow.json" \
  SHADOW_TEST_EXIT=37 \
  node "$temp_dir/scripts/factory_shadow_harness.cjs" fixture-cli --prompt "$prompt" \
  > "$temp_dir/output" 2>&1 || shadow_status=$?
[[ "$shadow_status" == 37 ]] || fail "native harness exit status was not preserved"
jq -e --arg prompt "$prompt" '
  .args == ["fixture-cli","--reasoning-effort","max","--context","long_context","--prompt",$prompt] and
  .budget == "30" and
  ((.deadline | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601) * 1000 - .now |
    . > 1790000 and . <= 1800000)
' "$temp_dir/shadow.json" > /dev/null || fail 'profile, prompt or absolute deadline changed'
jq -Rse 'split("\u0000")[:3] == ["--verbose","--kill-after=30s","30m"]' \
  "$temp_dir/timeout-args" > /dev/null || fail 'hard timeout or termination grace changed'

case_name='shadow missing profile fails before native invocation'
: > "$temp_dir/timeout-args"
shadow_status=0
PATH="$temp_dir/bin:$PATH" SHADOW_REVIEW_EFFORT= SHADOW_REVIEW_CONTEXT=long_context \
  SHADOW_TEST_TIMEOUT="$temp_dir/timeout-args" \
  node "$temp_dir/scripts/factory_shadow_harness.cjs" fixture-cli \
  > "$temp_dir/output" 2>&1 || shadow_status=$?
(( shadow_status != 0 )) || fail 'missing profile succeeded'
[[ ! -s "$temp_dir/timeout-args" ]] || fail 'missing profile invoked the native harness'
printf 'PASS: shadow profile arguments, absolute deadline, hard timeout and failure propagation\n'
