#!/usr/bin/env bash
set -euo pipefail

output_file=

error() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

unverified() {
  if [[ -n "$output_file" ]]; then
    if grep -qx 'review_attempted=true' "$output_file"; then
      error "$1 Retry reconciliation only; do not resubmit or skip."
    fi
    printf 'review_receipt_required=true\n' >> "$output_file"
  fi
  error "$1 Retry the read-only checks; do not skip."
}

fail() {
  if [[ -n "$output_file" ]]; then
    printf 'review_failed=true\n' >> "$output_file"
  fi
  error "$1"
}

[[ $# == 3 && "${1:-}" == publish ]] \
  || error 'Usage: review-publication.sh publish REQUEST_JSON OUTPUT_FILE'
request_file=$2
output_file=$3
: >> "$output_file"

[[ -n "${GITHUB_REPOSITORY:-}" ]] || fail 'GITHUB_REPOSITORY is required'
[[ -n "${PR_NUMBER:-}" ]] || fail 'PR_NUMBER is required'
[[ -n "${PR_HEAD_SHA:-}" ]] || fail 'PR_HEAD_SHA is required'
[[ -n "${REVIEW_MARKER:-}" ]] || fail 'REVIEW_MARKER is required'
[[ -n "${REVIEWER_LOGIN:-}" ]] || fail 'REVIEWER_LOGIN is required'
endpoint="repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER"

load_reviews() {
  reviews=$(gh api --paginate --slurp "$endpoint/reviews") \
    || unverified 'Could not read reviews.'
}

jq -e --arg sha "$PR_HEAD_SHA" --arg marker "$REVIEW_MARKER" '
  type == "object" and .commit_id == $sha and
  (.event == "COMMENT" or .event == "APPROVE") and
  (.body | type == "string" and contains($sha) and contains($marker)) and
  ((has("comments") | not) or (.comments | type == "array"))
' "$request_file" >/dev/null || error 'Request must include the expected SHA, marker, body, review event, and optional comments array.'

find_related_reviews() {
  load_reviews
  related_reviews=$(jq -c --arg login "$REVIEWER_LOGIN" --arg marker "$REVIEW_MARKER" '
    [.[][] | select(.user.login == $login and
      (((.body // "") | contains($marker)) or .state == "PENDING"))]
  ' <<< "$reviews") || unverified 'Invalid review reconciliation response.'
}

matches_request() {
  jq -e --arg sha "$PR_HEAD_SHA" --slurpfile request "$request_file" '
    length == 1 and
    .[0].commit_id == $sha and .[0].body == $request[0].body and
    .[0].state == (if $request[0].event == "APPROVE" then "APPROVED" else "COMMENTED" end)
  ' <<< "$related_reviews" >/dev/null
}

report_review() {
  printf 'Verified review: %s\n' "$(jq -r '.[0].html_url' <<< "$related_reviews")"
}

find_related_reviews
if [[ "$related_reviews" != '[]' ]]; then
  printf 'review_attempted=true\n' >> "$output_file"
  matches_request || fail 'Existing or pending review needs reconciliation; no new review was submitted.'
  report_review
  if grep -qx 'review_failed=true' "$output_file"; then
    fail 'Review reconciled, but an earlier API or reconciliation failure remains unresolved.'
  fi
  exit 0
fi
if grep -qx 'review_failed=true' "$output_file"; then
  fail 'An earlier API or reconciliation failure prevents publication in this attempt.'
fi
if grep -qx 'review_attempted=true' "$output_file"; then
  unverified 'An earlier submission attempt has no verified review.'
fi

if jq -e '(.comments // []) | length > 0' "$request_file" >/dev/null; then
  files=$(gh api --paginate --slurp "$endpoint/files") \
    || unverified 'Could not read PR files for inline comment validation.'
  printf '%s\n' "$files" |
    python3 "$(dirname -- "${BASH_SOURCE[0]}")/validate-review-comments.py" "$request_file" \
    || error 'Correct the inline comments or move the findings into the review body before publication.'
fi

pr=$(gh api "$endpoint") || unverified 'Could not read live PR eligibility.'
eligible=$(jq -er --arg repo "$GITHUB_REPOSITORY" --arg sha "$PR_HEAD_SHA" '
  if ((.state == "open" or .state == "closed") and
      (.draft | type == "boolean") and (.head.sha | type == "string") and
      (.head | has("repo")) and
      (.head.repo == null or (.head.repo.full_name | type == "string")) and
      (.base.repo.full_name | type == "string") and
      (.user.login | type == "string"))
  then (.state == "open" and .draft == false and
        .head.repo.full_name == $repo and .base.repo.full_name == $repo and
        .head.sha == $sha) | tostring
  else error("Incomplete PR eligibility response")
  end
' <<< "$pr") || unverified 'Could not establish live PR eligibility.'
if [[ "$eligible" != true ]]; then
  if grep -qx 'review_receipt_required=true' "$output_file"; then
    error 'PR is no longer eligible after a read failure; publication remains incomplete, not skipped.'
  fi
  printf 'skipped=true\n' >> "$output_file"
  printf 'Skipped: PR is no longer open, non-draft, same-repository, and at the assigned head.\n'
  exit 0
fi
if [[ "$(jq -r .event "$request_file")" == APPROVE &&
      "$(jq -r .user.login <<< "$pr")" == "$REVIEWER_LOGIN" ]]; then
  error 'The reviewer cannot approve its own PR; use COMMENT.'
fi

# Record the attempt before POST, even if GitHub rejects it without creating a review.
printf 'review_attempted=true\n' >> "$output_file"
post_failed=false
if ! gh api --method POST "$endpoint/reviews" --input "$request_file" >/dev/null; then
  post_failed=true
  printf 'review_failed=true\n' >> "$output_file"
fi
find_related_reviews
if [[ "$post_failed" == true ]]; then
  if matches_request; then
    report_review
  else
    printf 'No matching submitted review verified after the failed request.\n' >&2
  fi
  fail 'Review API request failed; reconciliation is not a skip or permission to resubmit.'
fi
[[ "$related_reviews" != '[]' ]] \
  || unverified 'Submission returned success but its review is not visible.'
matches_request || fail 'Submission returned success but its exact review could not be verified.'
report_review
