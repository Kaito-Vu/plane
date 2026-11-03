#!/usr/bin/env bash
# Run on prod: load all image tarballs next to this script, then start the stack.
# Usage: ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env.prod ] || { echo "Missing .env.prod (copy from .env.prod.example)" >&2; exit 1; }

shopt -s nullglob
tars=(plane-images-*.tar.gz plane-images-*.tar)
[ ${#tars[@]} -gt 0 ] || { echo "No plane-images-*.tar[.gz] found" >&2; exit 1; }

for t in "${tars[@]}"; do
  echo "Loading $t"
  docker load -i "$t"
done

docker compose -f docker-compose.run.yml --env-file .env.prod up -d
