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
  --context default --enable-memory --prompt "$prompt" --yolo)
extended_args=(copilot --model fixture-extended --reasoning-effort high
  --context long_context --enable-memory --prompt "$prompt" --yolo)

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
    --context "$context" --enable-memory --prompt "$prompt" --yolo
done

case_name='copilot Fusion CLI failure'
run_launcher 37 --profile fusion-max
assert_status 37
assert_args copilot --model fusion --fusion-tier max \
  --context default --enable-memory --prompt "$prompt" --yolo
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
