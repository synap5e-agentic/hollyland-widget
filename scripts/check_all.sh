#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

run_step() {
  echo "==> $1"
  shift
  "$@"
}

cd "$ROOT_DIR"

run_step "Compile Python scripts" python3 -m py_compile scripts/*.py service/hollyland-widget-service
run_step "Parse installer" bash -n install.sh
run_step "Validate plugin manifest" python3 scripts/validate_plugin.py
run_step "Lint QML" python3 scripts/lint_qml.py
run_step "Dry-run installer" ./install.sh --dry-run

echo "All checks passed."
