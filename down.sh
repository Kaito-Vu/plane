#!/usr/bin/env bash
# Wipe everything for a fresh install: containers, images, and the ./data bind mounts
# (redis, rabbitmq, uploads). The external Postgres is NOT touched.
# Usage: ./down.sh [-y]
set -euo pipefail
cd "$(dirname "$0")"

DATA_DIR="${DATA_DIR:-$(grep -E '^DATA_DIR=' .env.prod 2>/dev/null | cut -d= -f2- | tr -d '"\r' || true)}"
DATA_DIR="${DATA_DIR:-./data}"

echo "This will delete: all plane containers + images, and $DATA_DIR (uploads included)."
if [ "${1:-}" != "-y" ]; then
  read -r -p "Type 'yes' to continue: " ans
  [ "$ans" = "yes" ] || { echo "Aborted"; exit 1; }
fi

# --rmi all removes every image referenced by the compose file; TAG must match what was loaded
for t in $(docker images --format '{{.Tag}}' 'plane-api' | sort -u) ; do
  TAG="$t" docker compose -f docker-compose.run.yml --env-file .env.prod down -v --rmi all --remove-orphans || true
done
docker compose -f docker-compose.run.yml --env-file .env.prod down -v --rmi all --remove-orphans || true

# leftovers from other tags
docker images --format '{{.Repository}}:{{.Tag}}' | grep '^plane-' | xargs -r docker rmi -f

rm -rf "$DATA_DIR"
echo "Clean. Load new tarball and run ./run.sh"
