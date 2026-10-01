#!/bin/sh
# Fails when the branch changes files outside the allowlist(s). Usage:
#   BASE=origin/preview sh deployments/ee/check-core-untouched.sh
# Allowlists: deployments/ee/core-allowlist.txt (always) and deployments/ee/fork-divergence.txt (optional: edits
# this fork intentionally keeps against upstream, e.g. fork-wide Docker/Caddy changes).
set -eu
cd "$(dirname "$0")/../.."
BASE="${BASE:-origin/preview}"
base_commit="$(git merge-base "$BASE" HEAD)" || { echo "cannot resolve BASE=$BASE (fetch it, with enough history)" >&2; exit 2; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# --no-renames: a rename would otherwise list only the new path and hide the deletion of a core file.
# quotepath=off and a file (not word splitting) keep paths with spaces / non-ASCII intact.
git -c core.quotepath=off diff --name-only --no-renames "$base_commit" HEAD > "$tmp/changed"
cat deployments/ee/core-allowlist.txt > "$tmp/allow"
if [ -f deployments/ee/fork-divergence.txt ]; then cat deployments/ee/fork-divergence.txt >> "$tmp/allow"; fi
: > "$tmp/bad"
while IFS= read -r f; do
  ok=0
  while IFS= read -r pat; do
    pat="${pat%"$(printf '\r')"}" # tolerate CRLF checkouts of the allowlist
    case "$pat" in ""|"#"*) continue ;; esac
    # shellcheck disable=SC2254
    case "$f" in $pat) ok=1; break ;; esac
  done < "$tmp/allow"
  if [ "$ok" -ne 1 ]; then printf '%s\n' "$f" >> "$tmp/bad"; fi
done < "$tmp/changed"
if [ -s "$tmp/bad" ]; then
  echo "Files changed outside the EE allowlist (relative to $BASE):" >&2
  cat "$tmp/bad" >&2
  echo "Move the change into plugin-owned paths, or add it deliberately to core-allowlist.txt (seam edits) or fork-divergence.txt (fork-wide edits)." >&2
  exit 1
fi
echo "OK: only plugin-owned and allow-listed files changed."
