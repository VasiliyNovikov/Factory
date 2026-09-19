#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y jq
fi

export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"

curl -fsSL https://gh.io/copilot-install | PREFIX="$HOME/.local" bash
curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path

copilot --version
opencode --version

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$HOME/.local/bin" "$HOME/.opencode/bin" >> "$GITHUB_PATH"
fi
