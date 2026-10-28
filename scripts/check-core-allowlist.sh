#!/usr/bin/env bash
# Fail if the diff vs <base> touches core files outside EE paths and the allowlist.
base="${1:-preview}"
root="$(git rev-parse --show-toplevel)"
bad=$(git diff --name-only "$base" | grep -Ev '^(apps/api/plane/ee/|apps/web/ee/|docs/|deployments/ee/|scripts/|tests/)' | grep -vxFf "$root/deployments/ee/core-allowlist.txt")
if [ -n "$bad" ]; then echo "Core files outside allowlist:"; echo "$bad"; exit 1; fi
