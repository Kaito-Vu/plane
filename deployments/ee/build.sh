#!/bin/sh
# Build the unmodified core API image, then the EE layer on top.
# Usage: sh deployments/ee/build.sh [prod|dev]   (default prod)
set -e
MODE="${1:-prod}"
cd "$(dirname "$0")/../.."
if [ "$MODE" = "dev" ]; then
  docker build -f apps/api/Dockerfile.dev -t plane-api-core-dev apps/api
  docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml build api
else
  docker build -f apps/api/Dockerfile.api -t plane-api-core apps/api
  docker compose -f docker-compose.yml -f docker-compose-ee.yml build api
fi
