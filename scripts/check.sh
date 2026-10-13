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

# Read the block-style action inputs used in this repository, not prompt text.
profile_references=$(awk '
  function value(line) {
    sub(/^[^:]*:[[:space:]]*/, "", line)
    if (line ~ /^#/) return ""
    sub(/[[:space:]]+#.*$/, "", line)
    sub(/[[:space:]]+$/, "", line)
    if (line ~ /^".*"$/ || line ~ /^\047.*\047$/)
      line = substr(line, 2, length(line) - 2)
    return line
  }
  function finish_step() {
    if (action == "./factory/.github/actions/ai" || action == "./.github/actions/ai") {
      if (inline_inputs != "") {
        printf "FAIL: %s: shared AI inputs must use block-style YAML: %s\n", file, inline_inputs > "/dev/stderr"
        failed = 1
      }
      if (has_profile)
        printf "%s:%d\t%s\n", file, profile_line, profile
    }
  }
  FNR == 1 {
    finish_step()
    file = FILENAME
    step_indent = property_indent = with_indent = -1
    action = profile = inline_inputs = ""
    has_profile = 0
  }
  /^[[:space:]]*($|#)/ { next }
  {
    match($0, /[^ ]/)
    indent = RSTART - 1
    line = substr($0, RSTART)
  }
  FILENAME == ARGV[1] {
    if (indent == 0) {
      inputs = (line ~ /^inputs:/)
      metadata_indent = -1
      profile_input = 0
      next
    }
    if (!inputs) next
    if (metadata_indent < 0) metadata_indent = indent
    if (indent == metadata_indent) {
      profile_input = (line ~ /^profile:/)
      default_indent = -1
    } else if (profile_input) {
      if (default_indent < 0) default_indent = indent
      if (indent == default_indent && line ~ /^default:/) {
        printf "%s:%d\t%s\n", FILENAME, FNR, value(line)
        found_default = 1
      }
    }
    next
  }
  {
    if (indent <= step_indent) {
      finish_step()
      step_indent = property_indent = with_indent = -1
      action = profile = inline_inputs = ""
      has_profile = 0
    }
    if (step_indent < 0 && line ~ /^-( |$)/) {
      step_indent = indent
      match(line, /^- */)
      indent += RLENGTH
      line = substr(line, RLENGTH + 1)
      if (line ~ /^($|#)/) next
    }
    if (step_indent < 0) next
    if (property_indent < 0) property_indent = indent
    if (indent == property_indent && line ~ /^uses:/) action = value(line)
    if (indent <= with_indent) with_indent = -1
    if (indent == property_indent && line ~ /^with:/) {
      with_indent = indent
      input_indent = -1
      inline_inputs = value(line)
    } else if (with_indent >= 0) {
      if (input_indent < 0) input_indent = indent
      if (indent == input_indent && line ~ /^profile:/) {
        profile = value(line)
        profile_line = FNR
        has_profile = 1
      }
    }
  }
  END {
    finish_step()
    if (!found_default) {
      printf "FAIL: %s: missing profile default\n", ARGV[1] > "/dev/stderr"
      failed = 1
    }
    if (failed) exit 1
  }
' "$repo_root/.github/actions/ai/action.yml" "$repo_root"/.github/workflows/*.yml)

while IFS=$'\t' read -r reference profile; do
  jq -e --arg profile "$profile" 'has($profile)' \
    "$repo_root/.github/model-config.json" > /dev/null || {
    printf "FAIL: %s: unknown model profile '%s'\n" "$reference" "$profile" >&2
    exit 1
  }
done <<< "$profile_references"
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
cp -- "$temp_dir/bin/copilot" "$temp_dir/bin/opencode"
chmod +x "$temp_dir/bin/copilot" "$temp_dir/bin/opencode"

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
    OPENCODE_CONFIG_CONTENT='{}' \
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
for harness in copilot opencode; do
  case "$harness" in
    copilot)
      default_args=(copilot --model fixture-default --reasoning-effort medium
        --context default --enable-memory --prompt "$prompt" --yolo)
      extended_args=(copilot --model fixture-extended --reasoning-effort high
        --context long_context --enable-memory --prompt "$prompt" --yolo)
      ;;
    opencode)
      default_args=(opencode run --model github-copilot/fixture-default
        --variant medium --auto -- "$prompt")
      extended_args=(opencode run --model github-copilot/fixture-extended
        --variant high --auto -- "$prompt")
      ;;
  esac

  case_name="$harness default profile and literal prompt"
  run_launcher 0 --harness "$harness"
  assert_status 0
  assert_args "${default_args[@]}"

  case_name="$harness selected profile and literal prompt"
  run_launcher 0 --harness "$harness" --profile extended
  assert_status 0
  assert_args "${extended_args[@]}"

  case_name="$harness CLI failure"
  run_launcher 37 --harness "$harness" --profile extended
  assert_status 37
  assert_args "${extended_args[@]}"

  case_name="$harness unknown profile"
  run_launcher 0 --harness "$harness" --profile missing
  (( actual_status != 0 )) || fail 'unknown profile succeeded'
  [[ ! -s "$temp_dir/actual" ]] || fail 'unknown profile invoked a CLI'

  printf 'PASS: %s profiles, literal prompt, exit status, and unknown profile\n' "$harness"
done
