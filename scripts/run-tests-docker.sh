#!/usr/bin/env bash
# Run the JADE test suite inside a Linux container where symlinks work.
# Usage: ./scripts/run-tests-docker.sh [pytest-args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="jade-tests:latest"

docker build -f "$ROOT/Dockerfile.test" -t "$IMAGE" "$ROOT"

# In a git worktree, $ROOT/.git is a FILE pointing at the main checkout's
# .git/worktrees/<name>. Mounting only $ROOT leaves that target outside the
# container, and every test that shells out to git dies with
# "fatal: not a git repository". Mount the real git dir at the same absolute
# path the pointer names, so those tests behave as they do in a plain clone.
GIT_MOUNT=()
if [ -f "$ROOT/.git" ]; then
  COMMON_DIR="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
  GIT_MOUNT=(-v "$COMMON_DIR:$COMMON_DIR")
fi

docker run --rm \
  -v "$ROOT:/workspace" \
  "${GIT_MOUNT[@]}" \
  -w /workspace \
  "$IMAGE" \
  python -m pytest tests/ "$@"
