#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: ./scripts/ai.sh --harness opencode|copilot --prompt "PROMPT" [--profile NAME]' \
    '  --profile NAME  Select a named model profile (default: default).' \
    '' \
    'Examples:' \
    '  ./scripts/ai.sh --harness copilot --prompt "PROMPT"' \
    '  ./scripts/ai.sh --harness opencode --profile review --prompt "PROMPT"'
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

harness=
prompt=
profile=default
while (( $# > 0 )); do
  case "$1" in
    --harness|--prompt)
      [[ $# -ge 2 && -n "$2" ]] || fail "Missing value for $1"
      case "$1" in
        --harness) harness=$2 ;;
        --prompt) prompt=$2 ;;
      esac
      shift 2
      ;;
    --profile)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || fail "Missing value for $1"
      profile=$2
      shift 2
      ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; fail "Unknown argument: $1" ;;
  esac
done

case "$harness" in
  opencode|copilot) ;;
  *) fail 'harness must be opencode or copilot' ;;
esac
[[ -n "$prompt" ]] || fail 'prompt is required'
command -v jq >/dev/null || fail 'jq is required'
command -v "$harness" >/dev/null || fail "$harness is not installed"

script_dir=$(dirname -- "${BASH_SOURCE[0]}")
config="$script_dir/../.github/model-config.json"
profile_config=$(jq -ces --arg profile "$profile" '
  def valid_profile:
    type == "object" and
    (.model | type == "string" and length > 0) and
    (.reasoningEffort | type == "string" and length > 0) and
    (.longContext | type == "boolean");

  if length != 1 or (.[0] | type != "object") then
    error("expected one object of named model profiles")
  elif (.[0] | has("default") | not) then
    error("missing default model profile")
  elif (.[0].default | valid_profile | not) then
    error("invalid default model profile")
  elif (.[0] | has($profile) | not) then
    error("unknown model profile: \($profile)")
  elif (.[0][$profile] | valid_profile | not) then
    error("invalid model profile: \($profile)")
  else .[0][$profile]
  end
' "$config") || fail "Invalid model configuration: $config"

model=$(jq -r '.model' <<< "$profile_config")
reasoning=$(jq -r '.reasoningEffort' <<< "$profile_config")
context=$(jq -r 'if .longContext then "long_context" else "default" end' <<< "$profile_config")

case "$harness" in
  copilot)
    exec copilot --model "$model" --reasoning-effort "$reasoning" \
      --context "$context" --prompt "$prompt" --yolo
    ;;
  opencode)
    model="github-copilot/$model"
    opencode_config=${OPENCODE_CONFIG_CONTENT:-'{}'}
    OPENCODE_CONFIG_CONTENT=$(jq -c '
      .provider["github-copilot"].options.headers["Copilot-Integration-Id"] //= "copilot-developer-cli"
    ' <<< "$opencode_config")
    export OPENCODE_CONFIG_CONTENT
    exec opencode run --model "$model" --variant "$reasoning" --auto -- "$prompt"
    ;;
esac
