#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
for script in "$repo_root"/scripts/*.sh; do
  bash -n "$script"
done

check_model_config() {
  jq -se 'length == 1 and (.[0] | type == "object")' "$1" > /dev/null || {
    printf 'FAIL: model-config.json must contain one JSON object\n' >&2
    return 1
  }
  jq '
    [
      to_entries[] |
      select(.value | type == "object") |
      select(.value.longContext | type != "boolean") |
      .key
    ] |
    if length == 0 then empty
    else error("model-config.json: invalid profiles \(map(tojson) | join(", ")); " +
      "expected boolean longContext")
    end
  ' "$1"
}
check_model_config "$repo_root/.github/model-config.json"
printf 'PASS: shell syntax, model JSON, and boolean context settings\n'

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
  }
}
JSON

cat > "$temp_dir/bin/copilot" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\0' "${0##*/}" "$@" >> "$AI_TEST_ARGS"
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

case_name='copilot unknown profile'
run_launcher 0 --profile missing
(( actual_status != 0 )) || fail 'unknown profile succeeded'
[[ ! -s "$temp_dir/actual" ]] || fail 'unknown profile invoked a CLI'

case_name='copilot unknown argument'
run_launcher 0 --unknown
(( actual_status != 0 )) || fail 'unknown argument succeeded'
[[ ! -s "$temp_dir/actual" ]] || fail 'unknown argument invoked a CLI'

printf 'PASS: copilot profiles, literal prompt, exit status, and invalid arguments\n'

case_name='model context validation'
jq 'del(.default.model, .default.reasoningEffort) |
  .default.extra = "allowed" | .["non-object"] = false' \
  "$temp_dir/.github/model-config.json" > "$temp_dir/accepted-profiles.json"
check_model_config "$temp_dir/accepted-profiles.json" > "$temp_dir/output" 2>&1 \
  || fail 'valid contexts or fields left to runtime were rejected'

jq '.default as $profile | {
  "string-context": ($profile | .longContext = "false"),
  "number-context": ($profile | .longContext = 0),
  "missing-context": ($profile | del(.longContext)),
  "null-context": ($profile | .longContext = null)
}' "$temp_dir/.github/model-config.json" > "$temp_dir/invalid-profiles.json"
if check_model_config "$temp_dir/invalid-profiles.json" > "$temp_dir/output" 2>&1; then
  fail 'invalid contexts were accepted'
fi
while IFS= read -r profile; do
  grep -Fq -- "\"$profile\"" "$temp_dir/output" \
    || fail "invalid profile $profile was not named"
done < <(jq -r 'keys[]' "$temp_dir/invalid-profiles.json")
printf 'PASS: context validation and profile-specific diagnostics\n'
