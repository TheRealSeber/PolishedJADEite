#!/usr/bin/env bash
# Run the JADE test suite inside a Linux container where symlinks work.
# Usage: ./scripts/run-tests-docker.sh [pytest-args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="jade-tests:latest"

docker build -f "$ROOT/Dockerfile.test" -t "$IMAGE" "$ROOT"

docker run --rm \
  -v "$ROOT:/workspace" \
  -w /workspace \
  "$IMAGE" \
  python -m pytest tests/ "$@"