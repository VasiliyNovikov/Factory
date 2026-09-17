#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -r -- "$test_dir"' EXIT
mkdir -p "$test_dir/repo/scripts" "$test_dir/repo/.github" "$test_dir/bin"
cp "$repo_dir/scripts/ai.sh" "$test_dir/repo/scripts/ai.sh"
config="$test_dir/repo/.github/model-config.json"
source_config="$repo_dir/.github/model-config.json"
cp "$source_config" "$config"

cat > "$test_dir/bin/copilot" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
jq -cn --arg harness "$(basename -- "$0")" \
  --arg config "${OPENCODE_CONFIG_CONTENT:-}" --args \
  '{harness: $harness, config: $config, args: $ARGS.positional}' -- "$@" > "$AI_TEST_OUTPUT"
printf '%s\n' 'stub output'
exit "${AI_TEST_EXIT_CODE:-0}"
STUB
cp "$test_dir/bin/copilot" "$test_dir/bin/opencode"
chmod +x "$test_dir/bin/copilot" "$test_dir/bin/opencode"
export PATH="$test_dir/bin:$PATH"
export AI_TEST_OUTPUT="$test_dir/invocation.json"
unset OPENCODE_CONFIG_CONTENT AI_TEST_EXIT_CODE
prompt=$'--leading prompt "quotes"\nsecond line \\ literal $HOME'
checks=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  cat "$test_dir/stderr" >&2
  exit 1
}

run_ai() {
  rm -f -- "$AI_TEST_OUTPUT"
  bash "$test_dir/repo/scripts/ai.sh" "$@" > "$test_dir/stdout" 2> "$test_dir/stderr"
}

assert_invocation() {
  jq -e --arg harness "$1" --arg model "$2" --arg reasoning "$3" \
    --arg context "$4" --arg prompt "$prompt" '
      .harness == $harness and .args == (
        if $harness == "copilot" then
          ["--model", $model, "--reasoning-effort", $reasoning,
           "--context", $context, "--prompt", $prompt, "--yolo"]
        else
          ["run", "--model", ("github-copilot/" + $model),
           "--variant", $reasoning, "--auto", "--", $prompt]
        end
      )
    ' "$AI_TEST_OUTPUT" >/dev/null || fail "Incorrect $1 arguments"
  checks=$((checks + 1))
}

expect_failure() {
  local message=$1
  shift
  if run_ai "$@"; then
    fail "Expected failure: $message"
  fi
  [[ ! -e "$AI_TEST_OUTPUT" ]] || fail 'A harness was invoked for invalid input'
  grep -Fq -- "$message" "$test_dir/stderr" || fail "Missing error: $message"
  checks=$((checks + 1))
}

for harness in copilot opencode; do
  cp "$source_config" "$config"
  run_ai --harness "$harness" --prompt "$prompt"
  assert_invocation "$harness" gpt-6-astra high long_context
  cp "$AI_TEST_OUTPUT" "$test_dir/default.json"

  run_ai --harness "$harness" --prompt "$prompt" --profile default
  cmp -s "$AI_TEST_OUTPUT" "$test_dir/default.json" || fail 'Explicit default differs from omission'
  checks=$((checks + 1))

  run_ai --profile implement --harness "$harness" --prompt "$prompt"
  assert_invocation "$harness" gpt-6-astra max long_context
  run_ai --harness "$harness" --profile review --prompt "$prompt"
  assert_invocation "$harness" claude-opus-5 max long_context

  custom_profile='custom.profile "quoted"'
  jq --arg name "$custom_profile" '
    .[$name] = {model: "custom/model", reasoningEffort: "low", longContext: false}
  ' "$source_config" > "$config"
  run_ai --harness "$harness" --prompt "$prompt" --profile "$custom_profile"
  assert_invocation "$harness" custom/model low default

  expect_failure 'unknown model profile: missing' \
    --harness "$harness" --prompt "$prompt" --profile missing
  expect_failure 'Missing value for --profile' --harness "$harness" --prompt "$prompt" --profile
  expect_failure 'Missing value for --profile' --harness "$harness" --prompt "$prompt" --profile ''
  expect_failure 'Missing value for --profile' --harness "$harness" --profile --prompt "$prompt"
  expect_failure 'Missing value for --profile' --profile --harness "$harness" --prompt "$prompt"
  expect_failure 'Missing value for --profile' --harness "$harness" --prompt "$prompt" --profile -h

  jq 'del(.default)' "$source_config" > "$config"
  expect_failure 'missing default model profile' \
    --harness "$harness" --prompt "$prompt" --profile implement

  for value in null false 42 '""' '"text"' '[]' '{}'; do
    jq --argjson value "$value" '.default = $value' "$source_config" > "$config"
    expect_failure 'invalid default model profile' \
      --harness "$harness" --prompt "$prompt" --profile implement
    jq --argjson value "$value" '.implement = $value' "$source_config" > "$config"
    expect_failure 'invalid model profile: implement' \
      --harness "$harness" --prompt "$prompt" --profile implement
  done

  for field in model reasoningEffort longContext; do
    jq --arg field "$field" 'del(.implement[$field])' "$source_config" > "$config"
    expect_failure 'invalid model profile: implement' \
      --harness "$harness" --prompt "$prompt" --profile implement
    for value in null 42 '""' '[]' '{}'; do
      jq --arg field "$field" --argjson value "$value" \
        '.implement[$field] = $value' "$source_config" > "$config"
      expect_failure 'invalid model profile: implement' \
        --harness "$harness" --prompt "$prompt" --profile implement
    done
  done
  jq '.implement.longContext = "false"' "$source_config" > "$config"
  expect_failure 'invalid model profile: implement' \
    --harness "$harness" --prompt "$prompt" --profile implement
  jq '.implement.model = true' "$source_config" > "$config"
  expect_failure 'invalid model profile: implement' \
    --harness "$harness" --prompt "$prompt" --profile implement
  jq '.implement.reasoningEffort = false' "$source_config" > "$config"
  expect_failure 'invalid model profile: implement' \
    --harness "$harness" --prompt "$prompt" --profile implement

  for invalid_json in '{' '' 'null' '[]' '"text"' '{} {}'; do
    printf '%s\n' "$invalid_json" > "$config"
    expect_failure 'Invalid model configuration:' --harness "$harness" --prompt "$prompt"
  done
  cat "$source_config" "$source_config" > "$config"
  expect_failure 'expected one object of named model profiles' \
    --harness "$harness" --prompt "$prompt"
  rm -- "$config"
  expect_failure 'Invalid model configuration:' --harness "$harness" --prompt "$prompt"

  jq '.unused = null' "$source_config" > "$config"
  run_ai --harness "$harness" --prompt "$prompt"
  assert_invocation "$harness" gpt-6-astra high long_context
done

cp "$source_config" "$config"
run_ai --harness opencode --prompt "$prompt"
jq -e '.config | fromjson ==
  {provider: {"github-copilot": {options: {headers: {"Copilot-Integration-Id": "copilot-developer-cli"}}}}}
' "$AI_TEST_OUTPUT" >/dev/null || fail 'Default OpenCode header was not added'
checks=$((checks + 1))

for headers in '{"X-Test":"keep"}' '{"X-Test":"keep","Copilot-Integration-Id":"custom"}'; do
  existing_config=$(jq -cn --argjson headers "$headers" '
    {theme: "test", provider: {"github-copilot": {options: {headers: $headers, timeout: 123}}}}
  ')
  OPENCODE_CONFIG_CONTENT="$existing_config" run_ai \
    --harness opencode --profile review --prompt "$prompt"
  assert_invocation opencode claude-opus-5 max long_context
  jq -e --argjson existing "$existing_config" '
    (.config | fromjson) == (
      $existing |
      .provider["github-copilot"].options.headers["Copilot-Integration-Id"] //= "copilot-developer-cli"
    )
  ' "$AI_TEST_OUTPUT" >/dev/null || fail 'Existing OpenCode configuration was not preserved'
  checks=$((checks + 1))
done

for harness in copilot opencode; do
  if AI_TEST_EXIT_CODE=23 run_ai --harness "$harness" --prompt "$prompt"; then
    fail 'Harness failure was hidden'
  else
    status=$?
  fi
  [[ $status -eq 23 ]] || fail 'Harness exit status was changed'
  [[ $(cat "$test_dir/stdout") == 'stub output' ]] || fail 'Harness stdout was changed'
  checks=$((checks + 1))
done

expect_failure 'harness must be opencode or copilot' --harness other --prompt "$prompt"
expect_failure 'prompt is required' --harness copilot
expect_failure 'Unknown argument: --other' --other
printf '{\n' > "$config"
for help in --help -h; do
  run_ai "$help"
  [[ ! -e "$AI_TEST_OUTPUT" ]] || fail 'Help invoked a harness'
  grep -Fq -- '[--profile NAME]' "$test_dir/stdout" || fail 'Help omits the profile selector'
  grep -Fq -- 'default: default' "$test_dir/stdout" || fail 'Help omits the default profile'
  grep -Fq -- '--harness copilot --prompt "PROMPT"' "$test_dir/stdout" || fail 'Help omits default usage'
  grep -Fq -- '--profile review' "$test_dir/stdout" || fail 'Help omits named-profile usage'
  checks=$((checks + 1))
done

printf 'Passed %s wrapper checks (stubbed CLIs; no live model requests).\n' "$checks"
