#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: ./scripts/ai.sh --prompt "PROMPT" [--profile NAME]' \
    '  --profile NAME  Select a named model profile (default: default).' \
    '' \
    'Examples:' \
    '  ./scripts/ai.sh --prompt "PROMPT"' \
    '  ./scripts/ai.sh --profile review --prompt "PROMPT"'
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

prompt=
profile=default
while (( $# > 0 )); do
  case "$1" in
    --prompt)
      [[ $# -ge 2 && -n "$2" ]] || fail "Missing value for $1"
      prompt=$2
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

[[ -n "$prompt" ]] || fail 'prompt is required'
command -v jq >/dev/null || fail 'jq is required'
command -v copilot >/dev/null || fail 'copilot is not installed'

script_dir=$(dirname -- "${BASH_SOURCE[0]}")
config="$script_dir/../.github/model-config.json"
profile_config=$(jq -ce --arg profile "$profile" '.[$profile]' "$config") \
  || fail "Cannot load model profile '$profile' from $config"

model=$(jq -r '.model' <<< "$profile_config")
reasoning=$(jq -r '.reasoningEffort' <<< "$profile_config")
context=$(jq -r 'if .longContext then "long_context" else "default" end' <<< "$profile_config")

exec copilot --model "$model" --reasoning-effort "$reasoning" \
  --context "$context" --enable-memory --prompt "$prompt" --yolo
