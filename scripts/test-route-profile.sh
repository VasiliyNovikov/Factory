#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python3 - "$root/.github/model-config.json" <<'PY'
import json
import sys

def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result

with open(sys.argv[1]) as config:
    json.load(config, object_pairs_hook=unique_keys)
print("PASS: configuration keys are unique")
PY

temp_dir=$(mktemp -d)
trap 'rm -r -- "$temp_dir"' EXIT

checkout="$temp_dir/default-branch"
mkdir -p "$checkout/scripts" "$checkout/.github" "$temp_dir/bin"
cp "$root/scripts/ai.sh" "$checkout/scripts/ai.sh"
config="$checkout/.github/model-config.json"
launcher="$checkout/scripts/ai.sh"

cat > "$temp_dir/bin/copilot" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\0' "$@" > "$CAPTURE"
STUB
chmod +x "$temp_dir/bin/copilot"
export PATH="$temp_dir/bin:$PATH"
export CAPTURE="$temp_dir/arguments"
prompt=$'Route this review event.\nPreserve "quoted" arguments.'

expect_route() {
  rm -f -- "$CAPTURE"
  "$launcher" --harness copilot --profile route --prompt "$prompt"
  printf '%s\0' --model gpt-6-astra --reasoning-effort high \
    --context default --prompt "$prompt" --yolo > "$temp_dir/expected"
  cmp "$temp_dir/expected" "$CAPTURE"
}

expect_missing_profile() {
  local profile=$1
  rm -f -- "$CAPTURE"
  if "$launcher" --harness copilot --profile "$profile" --prompt "$prompt" \
    > "$temp_dir/stdout" 2> "$temp_dir/stderr"; then
    printf 'FAIL: missing profile %s was accepted\n' "$profile" >&2
    exit 1
  fi
  if [[ -e "$CAPTURE" ]]; then
    printf 'FAIL: Copilot was invoked for missing profile %s\n' "$profile" >&2
    exit 1
  fi
  grep -F -- "Cannot load model profile '$profile'" "$temp_dir/stderr" >/dev/null
}

# A review-event workflow can request route before its configuration is merged.
jq 'del(.route)' "$root/.github/model-config.json" > "$config"
expect_missing_profile route
printf 'PASS: reproduced missing route on the old default-branch configuration\n'

cp "$root/.github/model-config.json" "$config"
expect_route
printf 'PASS: pre-merge route consumer starts with the compatibility configuration\n'

# The later triage upgrade must not change routing's arguments.
jq '.triage.reasoningEffort = "max" | .triage.longContext = true' \
  "$root/.github/model-config.json" > "$config"
expect_route
printf 'PASS: matching-revision routing remains independent of stronger triage\n'

expect_missing_profile missing-profile
printf 'PASS: unknown profiles still fail before invoking Copilot\n'
