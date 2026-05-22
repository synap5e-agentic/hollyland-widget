#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$SCRIPT_DIR/plugin"
MANIFEST_PATH="$PLUGIN_ROOT/manifest.json"
PLUGINS_DIR="${NOCTALIA_PLUGINS_DIR:-$HOME/.config/noctalia/plugins}"
PLUGINS_JSON="${NOCTALIA_PLUGINS_JSON:-$HOME/.config/noctalia/plugins.json}"
DRY_RUN=0
RESTART_NOCTALIA=0

usage() {
  echo "Usage: $0 [--dry-run] [--restart]" >&2
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

read_manifest_field() {
  local field="$1"
  python3 - "$MANIFEST_PATH" "$field" <<'PY'
import json
import sys

path, field = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
value = data
for part in field.split("."):
    value = value[part]
print(value)
PY
}

find_noctalia_pids() {
  ps -C qs -o pid=,args= | awk '/qs -c noctalia-shell$/ { print $1 }'
}

register_plugin() {
  DRY_RUN="$DRY_RUN" python3 - "$PLUGINS_JSON" "$PLUGIN_ID" <<'PY'
import json
import os
import sys
from pathlib import Path

plugins_json = Path(sys.argv[1]).expanduser()
plugin_id = sys.argv[2]
dry_run = os.environ.get("DRY_RUN") == "1"

if plugins_json.exists():
    data = json.loads(plugins_json.read_text(encoding="utf-8"))
else:
    data = {"sources": [], "states": {}, "version": 2}

states = data.setdefault("states", {})
existing = states.get(plugin_id)
desired = {"enabled": True, "sourceUrl": "local"}

if existing == desired:
    print(f"Plugin already registered in {plugins_json}")
    raise SystemExit(0)

states[plugin_id] = desired
data.setdefault("sources", [])
data.setdefault("version", 2)

if dry_run:
    print(f"Would register {plugin_id} in {plugins_json}")
else:
    plugins_json.parent.mkdir(parents=True, exist_ok=True)
    plugins_json.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"Registered {plugin_id} in {plugins_json}")
PY
}

restart_noctalia() {
  local existing_qs_pids
  existing_qs_pids="$(find_noctalia_pids)"

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ -n "$existing_qs_pids" ]; then
      printf '[dry-run] kill %s\n' "$existing_qs_pids"
    fi
    echo "[dry-run] systemctl --user stop --no-block noctalia-manual.service"
    echo "[dry-run] setsid qs -c noctalia-shell >/dev/null 2>&1 &"
    return 0
  fi

  if [ -n "$existing_qs_pids" ]; then
    kill $existing_qs_pids
    for _ in $(seq 1 20); do
      if [ -z "$(find_noctalia_pids)" ]; then
        break
      fi
      sleep 0.25
    done
  fi

  systemctl --user stop --no-block noctalia-manual.service >/dev/null 2>&1 || true
  setsid qs -c noctalia-shell >/dev/null 2>&1 &

  for _ in $(seq 1 20); do
    local noctalia_pids
    noctalia_pids="$(find_noctalia_pids)"
    if [ -n "$noctalia_pids" ]; then
      echo "Restarted Noctalia:"
      printf '%s\n' "$noctalia_pids"
      return 0
    fi
    sleep 0.5
  done

  echo "Failed to restart Noctalia. Verify with: ps -C qs -o pid=,args= | awk '/qs -c noctalia-shell/'" >&2
  return 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --restart)
      RESTART_NOCTALIA=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
  shift
done

python3 "$SCRIPT_DIR/scripts/validate_plugin.py"

PLUGIN_ID="$(read_manifest_field id)"
PLUGIN_NAME="$(read_manifest_field name)"
TARGET_DIR="$PLUGINS_DIR/$PLUGIN_ID"

echo "Installing $PLUGIN_NAME ($PLUGIN_ID)..."

run mkdir -p "$PLUGINS_DIR" "$TARGET_DIR"

while IFS= read -r -d '' dir; do
  rel="${dir#$PLUGIN_ROOT/}"
  run mkdir -p "$TARGET_DIR/$rel"
done < <(find "$PLUGIN_ROOT" -mindepth 1 -type d -print0 | sort -z)

declare -A EXPECTED
while IFS= read -r -d '' path; do
  rel="${path#$PLUGIN_ROOT/}"
  EXPECTED["$rel"]=1
  run mkdir -p "$(dirname "$TARGET_DIR/$rel")"
  run ln -sfn "$path" "$TARGET_DIR/$rel"
done < <(find "$PLUGIN_ROOT" -mindepth 1 \( -type f -o -type l \) -print0 | sort -z)

# Prune managed symlinks under TARGET_DIR that no longer have a source.
# "Managed" = symlink pointing into PLUGIN_ROOT. We refuse to touch anything else,
# so user-created files or links to other locations survive untouched.
if [ -d "$TARGET_DIR" ]; then
  while IFS= read -r -d '' link; do
    rel="${link#$TARGET_DIR/}"
    [ -n "${EXPECTED[$rel]:-}" ] && continue
    target="$(readlink "$link" 2>/dev/null || true)"
    case "$target" in
      "$PLUGIN_ROOT"/*) run rm -f "$link" ;;
    esac
  done < <(find "$TARGET_DIR" -mindepth 1 -type l -print0)
  # Remove empty directories left behind by the prune.
  while IFS= read -r -d '' dir; do
    run rmdir "$dir" 2>/dev/null || true
  done < <(find "$TARGET_DIR" -mindepth 1 -depth -type d -empty -print0)
fi

register_plugin

if [ "$RESTART_NOCTALIA" -eq 1 ]; then
  restart_noctalia
elif [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete."
else
  echo "Done. Restart Noctalia to load the plugin."
fi
