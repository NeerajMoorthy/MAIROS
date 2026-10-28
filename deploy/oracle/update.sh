#!/usr/bin/env bash
# Update the MAIROS API on the VM to the latest main and restart it.
#
#   bash deploy/oracle/update.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then DOCKER="sudo docker"; fi

git -C "$ROOT" pull --ff-only origin main
cd "$ROOT/deploy/oracle"
$DOCKER compose up -d --build
$DOCKER compose ps
