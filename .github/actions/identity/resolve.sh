#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '::error::%s\n' "$1" >&2
  exit 1
}

[[ ${FACTORY_USER_ID:-} =~ ^[1-9][0-9]*$ ]] ||
  fail 'FACTORY_USER_ID must be a positive decimal bot user ID'
[[ ${REVIEWER_USER_ID:-} =~ ^[1-9][0-9]*$ ]] ||
  fail 'REVIEWER_USER_ID must be a positive decimal bot user ID'
[[ "$FACTORY_USER_ID" != "$REVIEWER_USER_ID" ]] ||
  fail 'Factory and reviewer must have distinct bot user IDs'
[[ -n ${GH_TOKEN:-} ]] || fail 'gh-token is required'

resolve_login() {
  local user_id=$1
  gh api "user/${user_id}" |
    jq -er --arg id "$user_id" '
      select((.id | type) == "number" and (.id | tostring) == $id and .type == "Bot") |
      .login | select(type == "string" and test("^[A-Za-z0-9-]+\\[bot\\]$"))
    '
}

factory_login=$(resolve_login "$FACTORY_USER_ID") ||
  fail 'Cannot resolve FACTORY_USER_ID to a bot account'
reviewer_login=$(resolve_login "$REVIEWER_USER_ID") ||
  fail 'Cannot resolve REVIEWER_USER_ID to a bot account'

case "${APP_ROLE:-}" in
  factory)
    [[ -n ${APP_SLUG:-} && "$factory_login" == "${APP_SLUG}[bot]" ]] ||
      fail 'Factory token App does not match FACTORY_USER_ID'
    ;;
  reviewer)
    [[ -n ${APP_SLUG:-} && "$reviewer_login" == "${APP_SLUG}[bot]" ]] ||
      fail 'Reviewer token App does not match REVIEWER_USER_ID'
    ;;
  router)
    [[ -z ${APP_SLUG:-} ]] || fail 'Router must use the built-in token, not an App slug'
    ;;
  *) fail 'app-role must be factory, reviewer, or router' ;;
esac

{
  printf 'FACTORY_USER_ID=%s\n' "$FACTORY_USER_ID"
  printf 'REVIEWER_USER_ID=%s\n' "$REVIEWER_USER_ID"
  printf 'FACTORY_LOGIN=%s\n' "$factory_login"
  printf 'REVIEWER_LOGIN=%s\n' "$reviewer_login"
} >> "$GITHUB_ENV"
