#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  printf 'Usage: %s\n' "$0" >&2
  exit 1
fi

if ! command -v jq >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y jq
fi

installer=$(mktemp)
trap 'rm -f -- "$installer"' EXIT

bin_dir="$HOME/.local/bin"
export PATH="$bin_dir:$PATH"
curl -fsSL --max-time 60 --output "$installer" https://gh.io/copilot-install
if [[ ! -s "$installer" ]]; then
  printf 'Error: Copilot bootstrap download was empty.\n' >&2
  exit 1
fi

env PREFIX="$HOME/.local" bash "$installer"
copilot --version

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$bin_dir" >> "$GITHUB_PATH"
fi
