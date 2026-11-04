#!/usr/bin/env bash
# Run on prod: load all image tarballs next to this script, then start the stack.
# Usage: ./run.sh [tag]   (default: tag taken from the newest plane-images-<tag>.tar.gz)
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

if [ -z "${1:-}" ]; then
  newest=$(ls -t "${tars[@]}" | head -1)
  set -- "$(basename "$newest" | sed -E 's/^plane-images-(.*)\.tar(\.gz)?$/\1/')"
fi
# exported var overrides TAG in .env.prod for compose interpolation
export TAG="$1"
echo "Using TAG=$TAG"

mkdir -p "${DATA_DIR:-./data}"/{redis,rabbitmq,uploads}
docker compose -f docker-compose.run.yml --env-file .env.prod up -d
