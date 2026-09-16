#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y jq
fi

npm install -g @github/copilot opencode-ai@latest
