#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! git -C "$ROOT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "Not inside a git repository: $ROOT_DIR" >&2
  exit 1
fi

git -C "$ROOT_DIR" config core.hooksPath .githooks
echo "Configured git hooks for $ROOT_DIR"
echo "Git will now use .githooks/pre-commit"
