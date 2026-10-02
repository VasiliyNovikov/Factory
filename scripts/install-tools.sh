#!/usr/bin/env bash
set -euo pipefail

harnesses=("$@")
if (( $# == 0 )); then
  harnesses=(copilot opencode)
elif (( $# != 1 )) || [[ "$1" != copilot && "$1" != opencode ]]; then
  printf 'Usage: %s [copilot|opencode]\n' "$0" >&2
  exit 1
fi

timeout_command=$(command -v timeout || command -v gtimeout) || {
  printf 'Error: GNU timeout is required (install coreutils).\n' >&2
  exit 1
}

retry() {
  local description=$1 attempt status delay
  shift

  for attempt in 1 2 3; do
    if "$@"; then
      return 0
    else
      status=$?
    fi

    if (( attempt == 3 )); then
      printf 'Error: %s failed after 3 attempts (exit %s).\n' "$description" "$status" >&2
      return "$status"
    fi

    delay=$((attempt * 5))
    printf '%s failed (exit %s); retrying in %ss (attempt %s/3).\n' \
      "$description" "$status" "$delay" "$((attempt + 1))" >&2
    sleep "$delay"
  done
}

if ! command -v jq >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y jq
fi

installer=$(mktemp)
trap 'rm -f -- "$installer"' EXIT

for harness in "${harnesses[@]}"; do
  case "$harness" in
    copilot)
      bin_dir="$HOME/.local/bin"
      installer_url=https://gh.io/copilot-install
      installer_command=(env PREFIX="$HOME/.local" bash "$installer")
      ;;
    opencode)
      bin_dir="$HOME/.opencode/bin"
      installer_url=https://opencode.ai/install
      installer_command=(bash "$installer" --no-modify-path)
      ;;
  esac

  export PATH="$bin_dir:$PATH"
  : > "$installer"
  retry "$harness bootstrap download" \
    curl -fsSL --connect-timeout 10 --max-time 20 --output "$installer" "$installer_url"
  if [[ ! -s "$installer" ]]; then
    printf 'Error: %s bootstrap download was empty.\n' "$harness" >&2
    exit 1
  fi

  retry "$harness installation" \
    "$timeout_command" --kill-after=5s 60s "${installer_command[@]}"

  "$timeout_command" --kill-after=5s 10s "$harness" --version || {
    status=$?
    printf 'Error: %s version check failed (exit %s).\n' "$harness" "$status" >&2
    exit "$status"
  }

  if [[ -n "${GITHUB_PATH:-}" ]]; then
    printf '%s\n' "$bin_dir" >> "$GITHUB_PATH"
  fi
done
