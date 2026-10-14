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

check_inline_bash() {
  local steps step source
  steps=$(
    yq -o=json -I=0 '
      explode(.) |
      (.defaults.run.shell // "") as $workflow_shell |
      ((.runs | {"scope": "action", "steps": .steps, "shell": ""}),
       (.jobs | to_entries[] |
        {"scope": ("job " + .key), "steps": .value.steps,
         "shell": (.value.defaults.run.shell // $workflow_shell),
         "runner": .value.runs-on, "container": .value.container})) |
      . as $group | .steps | to_entries[] | select(.value | has("run")) |
      {"file": filename, "line": (.value.run | line),
       "scope": $group.scope, "index": .key,
       "name": (.value.name // .value.id // "unnamed"),
       "shell": (.value.shell // $group.shell),
       "runner": $group.runner, "container": $group.container, "run": .value.run}
    ' "$@" |
      jq -sc '
        .[] |
        select((.shell | test("^([^[:space:]]*/)?bash([[:space:]]|$)")) or
          (.shell == "" and .container == null and
           ([.runner | if type == "object" then .labels else . end] | flatten |
            any(type == "string" and
                (ascii_downcase | test("^(ubuntu-|macos-)|^linux$"))))))
      '
  ) || return
  [[ -n "$steps" ]] || return 0
  while IFS= read -r step; do
    source=$(jq -r '.run' <<< "$step") || return
    if ! bash -n <<< "$source"; then
      jq -r '"FAIL: \(.file):\(.line): \(.scope) step \(.index + 1) (\(.name)): Bash syntax"' \
        <<< "$step" >&2
      return 1
    fi
  done <<< "$steps"
}

check_inline_bash "$repo_root"/.github/actions/*/action.yml "$repo_root"/.github/workflows/*.yml
printf 'PASS: inline Bash syntax\n'

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

cat > "$temp_dir/inline-action.yml" <<'YAML'
runs:
  using: composite
  steps:
    - name: explicit Bash
      shell: bash
      run: exit 9
    - name: other action shell
      shell: python
      run: if
YAML
cat > "$temp_dir/inline-workflow.yml" <<'YAML'
jobs:
  default:
    runs-on: ubuntu-latest
    steps:
      - name: Linux default
        run: exit 9
  override:
    runs-on: windows-latest
    defaults: {run: {shell: pwsh}}
    steps:
      - name: custom Bash
        shell: /bin/bash --noprofile {0}
        run: exit 9
      - name: other job shell
        run: if
  inherited:
    runs-on: ubuntu-latest
    defaults: {run: {shell: bash}}
    steps:
      - name: job Bash default
        run: exit 9
      - name: other step shell
        shell: sh
        run: if
  windows:
    runs-on: windows-latest
    steps: [{run: if}]
  container:
    runs-on: ubuntu-latest
    container: ubuntu:latest
    steps: [{run: if}]
YAML

case_name='inline Bash selection without execution'
check_inline_bash "$temp_dir/inline-action.yml" "$temp_dir/inline-workflow.yml" \
  > "$temp_dir/output" 2>&1 || fail 'valid Bash or non-Bash steps rejected'

for fixture in 'action:explicit Bash' 'workflow:Linux default' \
  'workflow:custom Bash' 'workflow:job Bash default'; do
  step_name=${fixture#*:}
  case_name="inline syntax failure: $step_name"
  cp -- "$temp_dir/inline-${fixture%%:*}.yml" "$temp_dir/broken.yml"
  INLINE_STEP="$step_name" yq -i '
    ((.runs.steps[]?, .jobs[].steps[]?) |
     select(.name == strenv(INLINE_STEP)) | .run) = "if true; then"
  ' "$temp_dir/broken.yml"
  if check_inline_bash "$temp_dir/broken.yml" > "$temp_dir/output" 2>&1; then
    fail 'invalid Bash succeeded'
  fi
  grep -Fq -- "$temp_dir/broken.yml" "$temp_dir/output" &&
    grep -Fq -- "$step_name" "$temp_dir/output" || fail 'missing file or step'
done

case_name='inline shell selection failure'
cp -- "$temp_dir/inline-action.yml" "$temp_dir/broken.yml"
yq -i '.runs.steps[0].shell = ["bash"]' "$temp_dir/broken.yml"
if check_inline_bash "$temp_dir/broken.yml" "$temp_dir/inline-workflow.yml" \
  > "$temp_dir/output" 2>&1; then
  fail 'invalid shell selection succeeded'
fi

case_name='workflow shell default and job override'
yq -i '.defaults.run.shell = "pwsh" | .jobs.default.steps[0].run = "if"' \
  "$temp_dir/inline-workflow.yml"
check_inline_bash "$temp_dir/inline-workflow.yml" > "$temp_dir/output" 2>&1 \
  || fail 'workflow shell default ignored'
yq -i '.defaults.run.shell = "bash" | .jobs.default.steps[0].run = "exit 9"' \
  "$temp_dir/inline-workflow.yml"
if check_inline_bash "$temp_dir/inline-workflow.yml" > "$temp_dir/output" 2>&1; then
  fail 'workflow Bash default ignored'
fi
printf 'PASS: inline Bash selection, syntax failures, and shell defaults\n'

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
