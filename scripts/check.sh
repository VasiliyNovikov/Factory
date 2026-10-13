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

profile_references=$(awk '
  FILENAME == ARGV[1] {
    if (/^  [^ ]/) profile_input = /^  profile:/
    if (!profile_input || !/^    default:/) next
    found_default = 1
  }
  FILENAME != ARGV[1] && !/^[[:space:]]*profile:/ { next }
  {
    sub(/^[^:]*:[[:space:]]*/, "")
    sub(/[[:space:]]+#.*$/, "")
    sub(/[[:space:]]+$/, "")
    if (/^".*"$/ || /^\047.*\047$/) $0 = substr($0, 2, length($0) - 2)
    printf "%s:%d\t%s\n", FILENAME, FNR, $0
  }
  END {
    if (!found_default) {
      printf "FAIL: %s: missing profile default\n", ARGV[1] > "/dev/stderr"
      exit 1
    }
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
