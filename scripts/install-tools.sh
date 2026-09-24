#!/usr/bin/env bash
set -euo pipefail

harnesses=("$@")
if (( $# == 0 )); then
  harnesses=(copilot opencode)
elif (( $# != 1 )) || [[ "$1" != copilot && "$1" != opencode ]]; then
  printf 'Usage: %s [copilot|opencode]\n' "$0" >&2
  exit 1
fi

if ! command -v jq >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y jq
fi

for harness in "${harnesses[@]}"; do
  case "$harness" in
    copilot)
      bin_dir="$HOME/.local/bin"
      export PATH="$bin_dir:$PATH"
      curl -fsSL https://gh.io/copilot-install | PREFIX="$HOME/.local" bash
      ;;
    opencode)
      bin_dir="$HOME/.opencode/bin"
      export PATH="$bin_dir:$PATH"
      curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path
      ;;
  esac

  "$harness" --version

  if [[ -n "${GITHUB_PATH:-}" ]]; then
    printf '%s\n' "$bin_dir" >> "$GITHUB_PATH"
  fi
done
