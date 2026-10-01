#!/usr/bin/env bash
set -euo pipefail

if (( $# == 0 )); then
  printf 'Usage: %s COMMAND [ARG...]\n' "$0" >&2
  exit 1
fi

exec env \
  -u GH_TOKEN \
  -u GITHUB_TOKEN \
  -u COPILOT_GITHUB_TOKEN \
  -u GITHUB_OUTPUT \
  -u GITHUB_ENV \
  -u GITHUB_PATH \
  -u GITHUB_STATE \
  -u GITHUB_STEP_SUMMARY \
  -- "$@"
