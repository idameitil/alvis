#!/usr/bin/env bash
# Build the prod image and (re)start the alvis container.
# Invoked by .github/workflows/deploy.yml on every push to main,
# and by humans for manual redeploys after editing on the VM.
#
# Assumes the working tree is already at the revision you want to deploy
# (the caller is responsible for `git pull`).

set -euo pipefail

cd "$(dirname "$0")/.."

docker compose -f deployment/docker-compose.prod.yml up -d --build
docker image prune -f
