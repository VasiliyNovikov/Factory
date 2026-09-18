#!/usr/bin/env bash
set -euo pipefail

script_dir=$(dirname -- "${BASH_SOURCE[0]}")
filter="$script_dir/validate-work-items.jq"
checks=0

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

check() {
  local name=$1 expected=$2 event=$3 input=$4 output
  if output=$(jq -cse --arg event "$event" -f "$filter" <<< "$input" 2>&1); then
    [[ "$expected" == accept ]] || fail "$name accepted invalid work items: $output"
    jq -en --argjson actual "$output" --argjson expected "$input" \
      '$actual == $expected' >/dev/null || fail "$name changed the accepted matrix"
  else
    [[ "$expected" == reject ]] || fail "$name rejected valid work items: $output"
  fi
  checks=$((checks + 1))
  printf 'PASS: %s\n' "$name"
}

item='{"issue_number":"12","source_pr":"34","reply_number":"34","tracking_label":"factory-issue-12"}'
matrix="[$item]"
issue=$(jq -c 'map(.source_pr = "" | .reply_number = .issue_number)' <<< "$matrix")

check 'PR feedback' accept pull_request_review "$matrix"
check 'issue feedback' accept issue_comment "$issue"
check 'empty skip' accept push '[]'
check 'push item' accept push "$matrix"
check 'newline in issue ID' reject push \
  "$(jq -c 'map(.issue_number += "\n" | .tracking_label += "\n")' <<< "$matrix")"
check 'newline in PR IDs' reject push \
  "$(jq -c 'map(.source_pr += "\n" | .reply_number += "\n")' <<< "$matrix")"
check 'newline aliases bypassing uniqueness' reject push \
  "$(jq -c '. + map(with_entries(.value += "\n"))' <<< "$matrix")"
check 'leading newline in issue ID' reject push \
  "$(jq -c 'map(.issue_number = "\n12" | .tracking_label = "factory-issue-\n12")' <<< "$matrix")"
check 'embedded newline in issue ID' reject push \
  "$(jq -c 'map(.issue_number = "1\n2" | .tracking_label = "factory-issue-1\n2")' <<< "$matrix")"
check 'non-digit issue ID' reject push \
  "$(jq -c 'map(.issue_number = "12 --foo" | .tracking_label = "factory-issue-12 --foo")' <<< "$matrix")"
check 'zero issue ID' reject push \
  "$(jq -c 'map(.issue_number = "0" | .tracking_label = "factory-issue-0")' <<< "$matrix")"
check 'non-string ID' reject push \
  "$(jq -c 'map(.issue_number = 12)' <<< "$matrix")"
check 'extra key' reject push \
  "$(jq -c 'map(.anything = "unvalidated")' <<< "$matrix")"
check 'missing key' reject push \
  "$(jq -c 'map(del(.source_pr))' <<< "$matrix")"
check 'non-object item' reject push '["invalid"]'
check 'non-array output' reject push \
  "$(jq -c '{item: .[0]}' <<< "$matrix")"
check 'duplicate tracking label' reject push \
  "$(jq -c '. + map(.source_pr = "35" | .reply_number = "35")' <<< "$matrix")"
check 'duplicate reply target' reject push \
  "$(jq -c '. + map(.issue_number = "13" | .tracking_label = "factory-issue-13")' <<< "$matrix")"
check 'push without a PR' reject push "$issue"
check 'missing output' reject push ''
check 'malformed output' reject push '['
check 'multiple JSON values' reject push '[] []'
check 'mismatched reply target' reject push \
  "$(jq -c 'map(.reply_number = "35")' <<< "$matrix")"
check 'mismatched tracking label' reject push \
  "$(jq -c 'map(.tracking_label = "factory-issue-99")' <<< "$matrix")"

many=$(jq -cn '[range(1; 258) | tostring | {
  issue_number: ., source_pr: ., reply_number: ., tracking_label: ("factory-issue-" + .)
}]')
check 'multiple ordinary-event items' reject issue_comment \
  "$(jq -c '.[0:2]' <<< "$many")"
check '256 push items' accept push "$(jq -c '.[0:256]' <<< "$many")"
check '257 push items' reject push "$many"

printf '%s work-item checks passed.\n' "$checks"
