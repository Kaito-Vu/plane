#!/usr/bin/env bash
# Build prod images, pull third-party images used by docker-compose.run.yml,
# and export all of them to one tarball to copy to the (offline) prod server.
# Usage: ./build.sh [tag]   (default: prod)
set -euo pipefail
cd "$(dirname "$0")"

export TAG="${1:-prod}"
OUT="plane-images-${TAG}.tar.gz"
IMAGES=(plane-web plane-admin plane-space plane-live plane-api plane-proxy)
IMAGES=("${IMAGES[@]/%/:$TAG}")

DOCKER_BUILDKIT=1 docker compose -f docker-compose.yml build

# third-party images = literal (non-${...}) image: lines in the run compose file
mapfile -t EXTERNAL < <(grep -E '^\s+image:' docker-compose.run.yml | awk '{print $2}' | grep -v '\$' | tr -d '\r')
for i in "${EXTERNAL[@]}"; do docker pull --platform linux/amd64 "$i"; done

docker save "${IMAGES[@]}" "${EXTERNAL[@]}" | gzip > "$OUT"
echo "Done: $OUT"
echo "Copy to prod: $OUT docker-compose.run.yml .env.prod run.sh, then ./run.sh"
