#!/usr/bin/env python3
"""Stamp the sample manifest into a real Noctalia plugin."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "plugin" / "manifest.json"
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_manifest(manifest: dict[str, object]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _parse_tags(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Customize this template's sample manifest")
    parser.add_argument("--plugin-id", required=True, help="Plugin id, e.g. github-feed")
    parser.add_argument("--name", required=True, help="Human-readable plugin name")
    parser.add_argument("--description", required=True, help="Short plugin description")
    parser.add_argument("--author", default=os.environ.get("USER", "Simon"), help="Manifest author field")
    parser.add_argument("--version", default="0.1.0", help="Manifest version")
    parser.add_argument("--license", dest="license_name", help="Manifest license")
    parser.add_argument("--min-noctalia-version", help="Minimum Noctalia version")
    parser.add_argument("--tags", help="Comma-separated tag list")
    parser.add_argument("--bar-label", help="Short label for the sample bar widget")
    parser.add_argument("--panel-message", help="Placeholder text shown in the sample panel")
    args = parser.parse_args()

    if not PLUGIN_ID_RE.fullmatch(args.plugin_id):
        raise SystemExit("plugin id must match ^[a-z0-9][a-z0-9-]*$")

    manifest = _load_manifest()
    manifest["id"] = args.plugin_id
    manifest["name"] = args.name
    manifest["description"] = args.description
    manifest["author"] = args.author
    manifest["version"] = args.version

    if args.license_name:
        manifest["license"] = args.license_name
    if args.min_noctalia_version:
        manifest["minNoctaliaVersion"] = args.min_noctalia_version

    tags = _parse_tags(args.tags)
    if tags is not None:
        manifest["tags"] = tags

    metadata = manifest.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        manifest["metadata"] = metadata
    default_settings = metadata.setdefault("defaultSettings", {})
    if not isinstance(default_settings, dict):
        default_settings = {}
        metadata["defaultSettings"] = default_settings

    if args.bar_label:
        default_settings["barLabel"] = args.bar_label
    else:
        default_settings.pop("barLabel", None)

    if args.panel_message:
        default_settings["panelMessage"] = args.panel_message

    _write_manifest(manifest)

    print(f"Updated {MANIFEST_PATH}")
    print(f"Plugin id: {args.plugin_id}")
    print(f"Plugin name: {args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
