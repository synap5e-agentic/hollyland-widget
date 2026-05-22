#!/usr/bin/env python3
"""Validate the local Noctalia plugin manifest and entry points."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugin"
MANIFEST_PATH = PLUGIN_DIR / "manifest.json"
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _load_manifest() -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    if not MANIFEST_PATH.exists():
        return None, [f"Missing manifest: {MANIFEST_PATH}"]

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"Invalid JSON in {MANIFEST_PATH}: {exc}"]

    if not isinstance(manifest, dict):
        return None, [f"Manifest root must be an object: {MANIFEST_PATH}"]

    return manifest, errors


def _require_string(manifest: dict[str, object], key: str, errors: list[str]) -> str | None:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"Manifest field `{key}` must be a non-empty string")
        return None
    return value


def _entrypoint_path(raw: str, errors: list[str]) -> Path | None:
    path = (PLUGIN_DIR / raw).resolve()
    plugin_root = PLUGIN_DIR.resolve()
    try:
        path.relative_to(plugin_root)
    except ValueError:
        errors.append(f"Entrypoint escapes plugin directory: {raw}")
        return None
    if not path.exists():
        errors.append(f"Entrypoint file is missing: {raw}")
        return None
    if path.suffix != ".qml":
        errors.append(f"Entrypoint must point to a .qml file: {raw}")
        return None
    return path


def main() -> int:
    manifest, errors = _load_manifest()
    if manifest is None:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    plugin_id = _require_string(manifest, "id", errors)
    name = _require_string(manifest, "name", errors)
    _require_string(manifest, "version", errors)
    _require_string(manifest, "minNoctaliaVersion", errors)
    _require_string(manifest, "description", errors)
    _require_string(manifest, "author", errors)
    _require_string(manifest, "license", errors)

    if plugin_id is not None and not PLUGIN_ID_RE.fullmatch(plugin_id):
        errors.append("Manifest field `id` must match ^[a-z0-9][a-z0-9-]*$")

    tags = manifest.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        errors.append("Manifest field `tags` must be a list of non-empty strings")

    entry_points = manifest.get("entryPoints")
    if not isinstance(entry_points, dict) or not entry_points:
        errors.append("Manifest field `entryPoints` must be a non-empty object")
        entry_points = {}

    resolved_entry_points: list[Path] = []
    for key, raw_path in entry_points.items():
        if not isinstance(key, str) or not key:
            errors.append("Entrypoint keys must be non-empty strings")
            continue
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"Entrypoint `{key}` must be a non-empty string path")
            continue
        resolved = _entrypoint_path(raw_path, errors)
        if resolved is not None:
            resolved_entry_points.append(resolved)

    if len({path.resolve() for path in resolved_entry_points}) != len(resolved_entry_points):
        errors.append("Entrypoint paths must be unique")

    dependencies = manifest.get("dependencies", {})
    if not isinstance(dependencies, dict):
        errors.append("Manifest field `dependencies` must be an object if present")
    else:
        plugins = dependencies.get("plugins", [])
        if not isinstance(plugins, list) or not all(isinstance(item, str) for item in plugins):
            errors.append("Manifest field `dependencies.plugins` must be a list of strings")

    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, dict):
        errors.append("Manifest field `metadata` must be an object if present")
    else:
        default_settings = metadata.get("defaultSettings", {})
        if not isinstance(default_settings, dict):
            errors.append("Manifest field `metadata.defaultSettings` must be an object if present")

    qml_files = sorted(PLUGIN_DIR.rglob("*.qml"))
    if not qml_files:
        errors.append(f"No QML files found in {PLUGIN_DIR}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    display_name = name or plugin_id or "plugin"
    print(
        f"Plugin OK: {display_name} "
        f"({len(resolved_entry_points)} entry points, {len(qml_files)} QML files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
