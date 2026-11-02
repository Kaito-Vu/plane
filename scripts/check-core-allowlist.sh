#!/usr/bin/env bash
# Fail if the diff vs <base> touches core files outside EE paths and the allowlist.
base="${1:-preview}"
git rev-parse --verify -q "$base" >/dev/null || { echo "Unknown base: $base"; exit 2; }
root="$(git rev-parse --show-toplevel)"
allow="$(tr -d '\r' < "$root/deployments/ee/core-allowlist.txt")"
bad=$(git diff --name-only "$base"...HEAD | grep -Ev '^(apps/api/plane/ee/|apps/(web|admin|space)/ee/|docs/|deployments/ee/|scripts/)|(^|/)tests/' | grep -vxFf <(printf '%s\n' "$allow"))
if [ -n "$bad" ]; then echo "Core files outside allowlist:"; echo "$bad"; exit 1; fi
