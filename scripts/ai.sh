#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' 'Usage: ./scripts/ai.sh --harness opencode|copilot --prompt "PROMPT"'
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

harness=
prompt=
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
jq -e '
  (.model | type == "string" and length > 0) and
  (.reasoningEffort | type == "string" and length > 0) and
  (.longContext | type == "boolean")
' "$config" >/dev/null || fail "Invalid model configuration: $config"

model=$(jq -r '.model' "$config")
reasoning=$(jq -r '.reasoningEffort' "$config")
context=$(jq -r 'if .longContext then "long_context" else "default" end' "$config")

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
