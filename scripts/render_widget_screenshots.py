#!/usr/bin/env python3
"""Render Hollyland widget screenshots from the live local service payload."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT_ROOT_FILE = ROOT / ".cache" / "noctalia-qml-import-root"
DEFAULT_SERVICE_URL = "http://127.0.0.1:8791/api/current"
DEFAULT_NOCTALIA_SETTINGS_FILE = Path.home() / ".config" / "noctalia" / "settings.json"
DEFAULT_NOCTALIA_COLORS_FILE = Path.home() / ".config" / "noctalia" / "colors.json"
DEFAULT_PANEL_OUTPUT = ROOT / "docs" / "screenshots" / "hollyland-panel.png"
DEFAULT_BAR_OUTPUT = ROOT / "docs" / "screenshots" / "hollyland-bar.png"
DEFAULT_PANEL_WIDTH = 820
DEFAULT_PANEL_HEIGHT = 0
DEFAULT_PANEL_EXTRA_HEIGHT = 40
DEFAULT_BAR_WIDTH = 220
DEFAULT_BAR_HEIGHT = 36
DEFAULT_NOCTALIA_COLORS = {
    "mPrimary": "#fff59b",
    "mOnPrimary": "#0e0e43",
    "mSecondary": "#a9aefe",
    "mOnSecondary": "#0e0e43",
    "mTertiary": "#9BFECE",
    "mOnTertiary": "#0e0e43",
    "mError": "#FD4663",
    "mOnError": "#0e0e43",
    "mSurface": "#070722",
    "mOnSurface": "#f3edf7",
    "mSurfaceVariant": "#11112d",
    "mOnSurfaceVariant": "#7c80b4",
    "mOutline": "#21215F",
    "mShadow": "#070722",
    "mHover": "#9BFECE",
    "mOnHover": "#0e0e43",
}
DEFAULT_NOCTALIA_SETTINGS = {
    "general": {
        "animationDisabled": False,
        "animationSpeed": 1,
        "iRadiusRatio": 1,
        "radiusRatio": 1,
        "scaleRatio": 1,
        "shadowOffsetX": 2,
        "shadowOffsetY": 3,
    },
    "ui": {
        "boxBorderEnabled": False,
        "fontDefault": "Sans Serif",
        "fontDefaultScale": 1,
        "fontFixed": "monospace",
        "fontFixedScale": 1,
        "panelBackgroundOpacity": 0.93,
        "translucentWidgets": False,
    },
    "colorSchemes": {
        "darkMode": True,
        "predefinedScheme": "Noctalia-default",
    },
    "bar": {
        "capsuleColorKey": "none",
        "capsuleOpacity": 1.0,
        "density": "default",
        "fontScale": 1.0,
        "position": "top",
        "screenOverrides": [],
        "showCapsule": True,
        "showOutline": False,
    },
}


def _import_root() -> Path | None:
    env_root = os.environ.get("NOCTALIA_QML_IMPORT_ROOT")
    if env_root:
        path = Path(env_root).expanduser()
        return path if path.exists() else None
    if DEFAULT_IMPORT_ROOT_FILE.exists():
        configured = DEFAULT_IMPORT_ROOT_FILE.read_text(encoding="utf-8").strip()
        if configured:
            path = Path(configured).expanduser()
            return path if path.exists() else None
    return None


def _source_root(import_root: Path | None) -> Path | None:
    if import_root is None:
        return None
    source_marker = import_root / "source-root.txt"
    if not source_marker.exists():
        return None
    configured = source_marker.read_text(encoding="utf-8").strip()
    if not configured:
        return None
    source = Path(configured).expanduser()
    return source if source.exists() else None


def _qmltestrunner() -> str | None:
    configured = os.environ.get("QML_TESTRUNNER")
    if configured:
        path = Path(configured)
        return configured if path.exists() else shutil.which(configured)
    fallback = Path("/usr/lib/qt6/bin/qmltestrunner")
    if fallback.exists():
        return str(fallback)
    for candidate in ("qmltestrunner6", "qmltestrunner"):
        discovered = shutil.which(candidate)
        if discovered:
            return discovered
    return None


def _qml_url(path: Path) -> str:
    return path.resolve().as_uri()


def _load_payload(service_url: str) -> tuple[dict[str, object], str]:
    with urlopen(service_url, timeout=2) as response:
        return json.load(response), "service"


def _redact_payload(payload: dict[str, object]) -> dict[str, object]:
    """Replace receiver-identifying fields with placeholders for shareable screenshots."""
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary["rx_sn"] = "XXXXXXXXXXX"
        summary["rx_mac"] = "XX:XX:XX:XX:XX:XX"
        usb_list = summary.get("usb")
        if isinstance(usb_list, list):
            for entry in usb_list:
                if isinstance(entry, dict):
                    entry["usb_dev"] = "/dev/bus/usb/00X/0XX"
                    entry["serial"] = "Wireless Microphone"
    state = payload.get("state")
    if isinstance(state, dict):
        rx = state.get("rx")
        if isinstance(rx, dict):
            rx["sn"] = "XXXXXXXXXXX"
            rx["mac"] = "XX:XX:XX:XX:XX:XX"
            rx["usb_dev"] = "/dev/bus/usb/00X/0XX"
    return payload


def _resolve_output_path(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return ROOT / path


def _manifest_description() -> str:
    manifest = _read_json_file(ROOT / "plugin" / "manifest.json")
    description = manifest.get("description") if manifest else None
    if isinstance(description, str) and description.strip():
        return description
    return "Bar widget and panel for the Hollyland wireless receiver"


def _online_transmitters(state: dict[str, object]) -> list[dict[str, object]]:
    transmitters = state.get("transmitters")
    if not isinstance(transmitters, list):
        return []
    return [tx for tx in transmitters if isinstance(tx, dict) and tx.get("online") is True]


def _short_tx_label(tx: dict[str, object] | None) -> str:
    if not tx:
        return "TX"
    tx_id = tx.get("id")
    if tx_id is None:
        return "TX"
    tx_name = str(tx_id).strip()
    return tx_name.upper() if tx_name else "TX"


def _transmitter_battery_compact_text(tx: dict[str, object] | None) -> str:
    if not tx:
        return "-"
    if tx.get("online") is False:
        return "Off"
    battery = tx.get("battery")
    if battery is None or battery == "":
        return "-"
    try:
        numeric = float(battery)
    except (TypeError, ValueError):
        return str(battery)
    return str(round(numeric))


def _bar_transmitter_items(state: dict[str, object]) -> list[dict[str, str]]:
    transmitters = state.get("transmitters")
    if isinstance(transmitters, list):
        clipped = transmitters[:2]
    else:
        clipped = []
    items: list[dict[str, str]] = []
    for tx in clipped:
        data = tx if isinstance(tx, dict) else {}
        tx_id = str(data.get("id") or "")
        items.append(
            {
                "id": tx_id,
                "label": _short_tx_label(data),
                "valueText": _transmitter_battery_compact_text(data),
            }
        )
    return items


def _bar_primary_text(state: dict[str, object]) -> str:
    online = _online_transmitters(state)
    if len(online) == 2:
        return "+".join(_short_tx_label(tx) for tx in online)
    if len(online) > 2:
        return f"{len(online)}TX"
    primary = state.get("primary_tx")
    if isinstance(primary, dict):
        label = primary.get("label")
        if label:
            return str(label)
    if state.get("connected"):
        return "RX"
    return "HL"


def _bar_secondary_text(state: dict[str, object]) -> str:
    online = _online_transmitters(state)
    if len(online) == 2:
        return "/".join(_transmitter_battery_compact_text(tx) for tx in online)
    if len(online) > 2:
        return f"{len(online)} on"
    primary = state.get("primary_tx")
    if isinstance(primary, dict):
        return _transmitter_battery_compact_text(primary)
    if state.get("connected"):
        return "LIVE"
    if state.get("device_present"):
        return "USB"
    return ""


def _status_color(state: dict[str, object], colors: dict[str, object]) -> str:
    if state.get("service_error"):
        return str(colors.get("mError", "#FD4663"))
    if state.get("connected"):
        return str(colors.get("mPrimary", "#fff59b"))
    if state.get("device_present"):
        return str(colors.get("mTertiary", "#9BFECE"))
    return str(colors.get("mOnSurfaceVariant", "#7c80b4"))


def _payload_state(payload: dict[str, object]) -> dict[str, object]:
    state = payload.get("state")
    return state if isinstance(state, dict) else {}


def _payload_section(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _bar_props(payload: dict[str, object], colors: dict[str, object], width: int, height: int) -> dict[str, object]:
    state = _payload_state(payload)
    return {
        "width": width,
        "height": height,
        "labelText": _bar_primary_text(state),
        "secondaryText": _bar_secondary_text(state),
        "accent": _status_color(state, colors),
        "txItems": _bar_transmitter_items(state),
        "isVertical": False,
        "capsuleHeight": 27,
        "barFontSize": 10,
    }


def _panel_props(payload: dict[str, object], width: int, height: int, plugin_description: str) -> dict[str, object]:
    updated_at = payload.get("updated_at")
    return {
        "width": width,
        "height": height,
        "state": _payload_state(payload),
        "summary": _payload_section(payload, "summary"),
        "backend": _payload_section(payload, "backend"),
        "updatedAt": str(updated_at or ""),
        "bannerText": "",
        "bannerIsError": False,
        "actionBusy": False,
        "pendingAction": "",
        "voiceLevelMin": 0,
        "voiceLevelMax": 5,
        "pluginName": "Hollyland",
        "pluginDescription": plugin_description,
    }


def _read_json_file(path: Path) -> dict[str, object] | None:
    try:
        if not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _deep_merge(defaults: dict[str, object], overrides: dict[str, object] | None) -> dict[str, object]:
    merged: dict[str, object] = {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            merged[key] = _deep_merge(value, None)
        elif isinstance(value, list):
            merged[key] = list(value)
        else:
            merged[key] = value

    if not overrides:
        return merged

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _compact_settings(raw_settings: dict[str, object] | None) -> dict[str, object]:
    merged = _deep_merge(DEFAULT_NOCTALIA_SETTINGS, raw_settings)
    compact: dict[str, object] = {}
    for section_name, defaults in DEFAULT_NOCTALIA_SETTINGS.items():
        section = merged.get(section_name, {})
        if not isinstance(section, dict) or not isinstance(defaults, dict):
            continue
        compact[section_name] = {key: section.get(key, fallback) for key, fallback in defaults.items()}
    return compact


def _load_scheme_colors(source_root: Path | None, settings: dict[str, object]) -> dict[str, object] | None:
    if source_root is None:
        return None
    color_settings = settings.get("colorSchemes")
    if not isinstance(color_settings, dict):
        return None
    scheme = str(color_settings.get("predefinedScheme") or "Noctalia-default")
    mode = "dark" if color_settings.get("darkMode", True) else "light"
    scheme_file = source_root / "Assets" / "ColorScheme" / scheme / f"{scheme}.json"
    data = _read_json_file(scheme_file)
    if not data:
        return None
    colors = data.get(mode)
    if not isinstance(colors, dict):
        return None
    return {key: value for key, value in colors.items() if key.startswith("m")}


def _load_theme(settings_file: Path, colors_file: Path, source_root: Path | None) -> tuple[dict[str, object], dict[str, object], str]:
    settings = _compact_settings(_read_json_file(settings_file))
    colors = _read_json_file(colors_file)
    if colors:
        return settings, {**DEFAULT_NOCTALIA_COLORS, **colors}, "local"

    scheme_colors = _load_scheme_colors(source_root, settings)
    if scheme_colors:
        return settings, {**DEFAULT_NOCTALIA_COLORS, **scheme_colors}, "scheme"

    return settings, dict(DEFAULT_NOCTALIA_COLORS), "fallback"


def _write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).strip() + "\n", encoding="utf-8")


def _write_preview_imports(root: Path, settings: dict[str, object], colors: dict[str, object], source_root: Path | None) -> Path:
    import_root = root / "noctalia-preview-imports"
    settings_json = json.dumps(settings, sort_keys=True)
    colors_json = json.dumps(colors, sort_keys=True)
    font_file = ""
    if source_root is not None:
        candidate = source_root / "Assets" / "Fonts" / "tabler" / "noctalia-tabler-icons.ttf"
        if candidate.exists():
            font_file = candidate.resolve().as_uri()

    _write_text(
        import_root / "Quickshell" / "qmldir",
        """
        module Quickshell
        ShellScreen 1.0 ShellScreen.qml
        """,
    )
    _write_text(
        import_root / "Quickshell" / "ShellScreen.qml",
        """
        import QtQuick

        QtObject {
          property string name: ""
        }
        """,
    )
    _write_text(
        import_root / "Quickshell" / "Io" / "qmldir",
        """
        module Quickshell.Io
        FileView 1.0 FileView.qml
        IpcHandler 1.0 IpcHandler.qml
        """,
    )
    _write_text(
        import_root / "Quickshell" / "Io" / "FileView.qml",
        """
        import QtQuick

        QtObject {
          property string path: ""
          property bool printErrors: true
          property bool watchChanges: false
          signal loaded()
          signal loadFailed(var error)
          signal fileChanged()
          property string text: ""
          function reload() { loaded(); }
        }
        """,
    )
    _write_text(
        import_root / "Quickshell" / "Io" / "IpcHandler.qml",
        """
        import QtQuick

        QtObject {
          property string target: ""
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "qmldir",
        """
        module qs.Commons
        singleton Logger 1.0 Logger.qml
        singleton Settings 1.0 Settings.qml
        singleton Style 1.0 Style.qml
        singleton Color 1.0 Color.qml
        singleton Icons 1.0 Icons.qml
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "Logger.qml",
        """
        import QtQuick

        pragma Singleton
        QtObject {
          function d() {}
          function i() {}
          function w() {}
          function e() {}
          function callStack() {}
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "Settings.qml",
        f"""
        import QtQuick

        pragma Singleton
        QtObject {{
          readonly property var data: ({settings_json})

          function _findScreenOverride(screenName) {{
            const overrides = data.bar.screenOverrides || [];
            if (!screenName || overrides.length === undefined) return null;
            for (let i = 0; i < overrides.length; i++) {{
              if (overrides[i] && overrides[i].name === screenName) return overrides[i];
            }}
            return null;
          }}

          function getBarPositionForScreen(screenName) {{
            const override = _findScreenOverride(screenName);
            if (override && override.enabled !== false && override.position !== undefined) return override.position;
            return data.bar.position || "top";
          }}

          function getBarDensityForScreen(screenName) {{
            const override = _findScreenOverride(screenName);
            if (override && override.enabled !== false && override.density !== undefined) return override.density;
            return data.bar.density || "default";
          }}
        }}
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "Color.qml",
        f"""
        import QtQuick
        import qs.Commons

        pragma Singleton
        QtObject {{
          readonly property bool isTransitioning: false
          readonly property var _colors: ({colors_json})

          readonly property color mPrimary: _colors.mPrimary
          readonly property color mOnPrimary: _colors.mOnPrimary
          readonly property color mSecondary: _colors.mSecondary
          readonly property color mOnSecondary: _colors.mOnSecondary
          readonly property color mTertiary: _colors.mTertiary
          readonly property color mOnTertiary: _colors.mOnTertiary
          readonly property color mError: _colors.mError
          readonly property color mOnError: _colors.mOnError
          readonly property color mSurface: _colors.mSurface
          readonly property color mOnSurface: _colors.mOnSurface
          readonly property color mSurfaceVariant: _colors.mSurfaceVariant
          readonly property color mOnSurfaceVariant: _colors.mOnSurfaceVariant
          readonly property color mOutline: _colors.mOutline
          readonly property color mShadow: _colors.mShadow
          readonly property color mHover: _colors.mHover
          readonly property color mOnHover: _colors.mOnHover

          function resolveColorKey(key) {{
            if (key === "primary") return mPrimary;
            if (key === "secondary") return mSecondary;
            if (key === "tertiary") return mTertiary;
            if (key === "error") return mError;
            return mOnSurface;
          }}

          function adaptiveOpacity(baseOpacity) {{
            return Settings.data.colorSchemes.darkMode ? baseOpacity : Math.pow(baseOpacity, 1.5);
          }}

          function smartAlpha(baseColor, minAlpha) {{
            const minimum = minAlpha === undefined ? 0.4 : minAlpha;
            if (!Settings.data.ui.translucentWidgets) return baseColor;
            const alpha = Math.max(adaptiveOpacity(Settings.data.ui.panelBackgroundOpacity), minimum);
            const resultAlpha = Math.max(0, baseColor.a - (1.0 - alpha));
            return Qt.alpha(baseColor, resultAlpha);
          }}
        }}
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "Style.qml",
        """
        import QtQuick
        import qs.Commons

        pragma Singleton
        QtObject {
          readonly property real uiScaleRatio: Settings.data.general.scaleRatio || 1

          readonly property real fontSizeXXS: 8
          readonly property real fontSizeXS: 9
          readonly property real fontSizeS: 10
          readonly property real fontSizeM: 11
          readonly property real fontSizeL: 13
          readonly property real fontSizeXL: 16
          readonly property real fontSizeXXL: 18
          readonly property real fontSizeXXXL: 24

          readonly property int fontWeightRegular: 400
          readonly property int fontWeightMedium: 500
          readonly property int fontWeightSemiBold: 600
          readonly property int fontWeightBold: 700

          readonly property int radiusXXXS: Math.round(3 * Settings.data.general.radiusRatio)
          readonly property int radiusXXS: Math.round(4 * Settings.data.general.radiusRatio)
          readonly property int radiusXS: Math.round(8 * Settings.data.general.radiusRatio)
          readonly property int radiusS: Math.round(12 * Settings.data.general.radiusRatio)
          readonly property int radiusM: Math.round(16 * Settings.data.general.radiusRatio)
          readonly property int radiusL: Math.round(20 * Settings.data.general.radiusRatio)

          readonly property int iRadiusXXXS: Math.round(3 * Settings.data.general.iRadiusRatio)
          readonly property int iRadiusXXS: Math.round(4 * Settings.data.general.iRadiusRatio)
          readonly property int iRadiusXS: Math.round(8 * Settings.data.general.iRadiusRatio)
          readonly property int iRadiusS: Math.round(12 * Settings.data.general.iRadiusRatio)
          readonly property int iRadiusM: Math.round(16 * Settings.data.general.iRadiusRatio)
          readonly property int iRadiusL: Math.round(20 * Settings.data.general.iRadiusRatio)

          readonly property int borderS: Math.max(1, Math.round(1 * uiScaleRatio))
          readonly property int borderM: Math.max(1, Math.round(2 * uiScaleRatio))
          readonly property int borderL: Math.max(1, Math.round(3 * uiScaleRatio))

          readonly property int marginXXXS: Math.round(1 * uiScaleRatio)
          readonly property int marginXXS: Math.round(2 * uiScaleRatio)
          readonly property int marginXS: Math.round(4 * uiScaleRatio)
          readonly property int marginS: Math.round(6 * uiScaleRatio)
          readonly property int marginM: Math.round(9 * uiScaleRatio)
          readonly property int marginL: Math.round(13 * uiScaleRatio)
          readonly property int marginXL: Math.round(18 * uiScaleRatio)

          readonly property real baseWidgetSize: 33
          readonly property real animationFast: Settings.data.general.animationDisabled ? 0 : Math.round(150 / Settings.data.general.animationSpeed)
          readonly property real animationNormal: Settings.data.general.animationDisabled ? 0 : Math.round(300 / Settings.data.general.animationSpeed)

          readonly property real barHeight: getBarHeightForDensity(Settings.data.bar.density, Settings.data.bar.position === "left" || Settings.data.bar.position === "right")
          readonly property real capsuleHeight: getCapsuleHeightForDensity(Settings.data.bar.density, barHeight)
          readonly property real _barBaseFontSize: Math.max(1, (barHeight / capsuleHeight) * fontSizeXXS)
          readonly property real barFontSize: (Settings.data.bar.position === "left" || Settings.data.bar.position === "right") ? _barBaseFontSize * 0.9 * Settings.data.bar.fontScale : _barBaseFontSize * Settings.data.bar.fontScale

          readonly property color capsuleColor: Settings.data.bar.showCapsule ? Qt.alpha(Settings.data.bar.capsuleColorKey !== "none" ? Color.resolveColorKey(Settings.data.bar.capsuleColorKey) : Color.mSurfaceVariant, Settings.data.bar.capsuleOpacity) : "transparent"
          readonly property color capsuleBorderColor: Settings.data.bar.showOutline ? Color.mPrimary : "transparent"
          readonly property int capsuleBorderWidth: Settings.data.bar.showOutline ? borderS : 0
          readonly property color boxBorderColor: Settings.data.ui.boxBorderEnabled ? Color.mOutline : "transparent"

          function pixelAlignCenter(containerSize, contentSize) {
            return Math.round((containerSize - contentSize) / 2);
          }

          function toOdd(n) {
            return Math.floor(n / 2) * 2 + 1;
          }

          function getBarHeightForDensity(density, isVertical) {
            let h;
            switch (density) {
            case "mini": h = isVertical ? 23 : 21; break;
            case "compact": h = isVertical ? 27 : 25; break;
            case "comfortable": h = isVertical ? 39 : 37; break;
            case "spacious": h = isVertical ? 49 : 47; break;
            default: h = isVertical ? 33 : 31; break;
            }
            return toOdd(h);
          }

          function getCapsuleHeightForDensity(density, barHeight) {
            let h;
            switch (density) {
            case "mini": h = Math.round(barHeight * 0.90); break;
            case "compact": h = Math.round(barHeight * 0.85); break;
            case "comfortable": h = Math.round(barHeight * 0.75); break;
            case "spacious": h = Math.round(barHeight * 0.65); break;
            default: h = Math.round(barHeight * 0.82); break;
            }
            return toOdd(h);
          }

          function getBarFontSizeForDensity(barHeight, capsuleHeight, isVertical) {
            const baseFontSize = Math.max(1, (barHeight / capsuleHeight) * fontSizeXXS);
            return isVertical ? baseFontSize * 0.9 * Settings.data.bar.fontScale : baseFontSize * Settings.data.bar.fontScale;
          }

          function getBarHeightForScreen(screenName) {
            const density = Settings.getBarDensityForScreen(screenName);
            const position = Settings.getBarPositionForScreen(screenName);
            return getBarHeightForDensity(density, position === "left" || position === "right");
          }

          function getCapsuleHeightForScreen(screenName) {
            return getCapsuleHeightForDensity(Settings.getBarDensityForScreen(screenName), getBarHeightForScreen(screenName));
          }

          function getBarFontSizeForScreen(screenName) {
            const barHeight = getBarHeightForScreen(screenName);
            const capsuleHeight = getCapsuleHeightForScreen(screenName);
            const position = Settings.getBarPositionForScreen(screenName);
            return getBarFontSizeForDensity(barHeight, capsuleHeight, position === "left" || position === "right");
          }
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Commons" / "Icons.qml",
        f"""
        import QtQuick

        pragma Singleton
        QtObject {{
          readonly property var aliases: ({{ "close": "x" }})
          readonly property var icons: ({{
            "default": "",
            "sparkles": "\\u{{f6d7}}",
            "x": "\\u{{eb55}}"
          }})
          readonly property string defaultIcon: "default"
          readonly property string fontSource: {json.dumps(font_file)}
          readonly property string fontFamily: fontLoader.status === FontLoader.Ready ? fontLoader.name : ""

          property FontLoader fontLoader: FontLoader {{
            source: fontSource
          }}

          function get(iconName) {{
            let name = iconName || defaultIcon;
            if (aliases[name] !== undefined) name = aliases[name];
            if (icons[name] !== undefined) return icons[name];
            return icons[defaultIcon];
          }}
        }}
        """,
    )
    _write_text(
        import_root / "qs" / "Widgets" / "qmldir",
        """
        module qs.Widgets
        NBox 1.0 NBox.qml
        NText 1.0 NText.qml
        NIcon 1.0 NIcon.qml
        NIconButton 1.0 NIconButton.qml
        """,
    )
    _write_text(
        import_root / "qs" / "Widgets" / "NBox.qml",
        """
        import QtQuick
        import qs.Commons

        Item {
          id: root
          property color color: Color.mSurfaceVariant
          property bool forceOpaque: false
          property alias radius: bg.radius
          property alias border: bg.border

          Rectangle {
            id: bg
            anchors.fill: parent
            radius: Style.radiusM
            border.color: Style.boxBorderColor
            border.width: Style.borderS
            color: root.forceOpaque ? root.color : Color.smartAlpha(root.color)
          }
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Widgets" / "NText.qml",
        """
        import QtQuick
        import qs.Commons

        Text {
          id: root
          property bool richTextEnabled: false
          property bool markdownTextEnabled: false
          property string family: Settings.data.ui.fontDefault
          property real pointSize: Style.fontSizeM
          property bool applyUiScale: true
          property real fontScale: (family === Settings.data.ui.fontDefault ? Settings.data.ui.fontDefaultScale : Settings.data.ui.fontFixedScale) * (applyUiScale ? Style.uiScaleRatio : 1)
          property var features: ({})

          opacity: enabled ? 1.0 : 0.6
          font.family: root.family
          font.weight: Style.fontWeightMedium
          font.pointSize: Math.max(1, root.pointSize * fontScale)
          font.features: root.features
          color: Color.mOnSurface
          elide: Text.ElideRight
          wrapMode: Text.NoWrap
          verticalAlignment: Text.AlignVCenter
          textFormat: root.richTextEnabled ? Text.RichText : (root.markdownTextEnabled ? Text.MarkdownText : Text.PlainText)
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Widgets" / "NIcon.qml",
        """
        import QtQuick
        import qs.Commons

        Text {
          id: root
          property string icon: Icons.defaultIcon
          property real pointSize: Style.fontSizeL
          property bool applyUiScale: true

          visible: icon !== undefined && icon !== ""
          text: Icons.get(icon)
          font.family: Icons.fontFamily
          font.pointSize: Math.max(1, applyUiScale ? root.pointSize * Style.uiScaleRatio : root.pointSize)
          color: Color.mOnSurface
          verticalAlignment: Text.AlignVCenter
          horizontalAlignment: Text.AlignHCenter
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Widgets" / "NIconButton.qml",
        """
        import QtQuick
        import qs.Commons
        import qs.Widgets

        Item {
          id: root
          property real baseSize: Style.baseWidgetSize
          property string icon: ""
          property alias border: visualButton.border
          property alias radius: visualButton.radius
          property alias color: visualButton.color
          signal clicked()

          readonly property real buttonSize: Style.toOdd(baseSize * Style.uiScaleRatio)
          implicitWidth: buttonSize
          implicitHeight: buttonSize

          Rectangle {
            id: visualButton
            width: root.buttonSize
            height: root.buttonSize
            anchors.centerIn: parent
            color: Color.smartAlpha(Color.mSurfaceVariant)
            radius: Math.min(Style.iRadiusL, width / 2)
            border.color: Color.mOutline
            border.width: Style.borderS

            NIcon {
              icon: root.icon
              pointSize: Style.toOdd(visualButton.width * 0.48)
              color: Color.mPrimary
              anchors.centerIn: parent
            }
          }

          MouseArea {
            anchors.fill: parent
            onClicked: root.clicked()
          }
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Services" / "UI" / "qmldir",
        """
        module qs.Services.UI
        TooltipService 1.0 TooltipService.qml
        BarService 1.0 BarService.qml
        """,
    )
    _write_text(
        import_root / "qs" / "Services" / "UI" / "TooltipService.qml",
        """
        import QtQuick

        QtObject {
          function show() {}
          function hide() {}
        }
        """,
    )
    _write_text(
        import_root / "qs" / "Services" / "UI" / "BarService.qml",
        """
        import QtQuick

        QtObject {
          function getTooltipDirection() { return "top"; }
        }
        """,
    )
    return import_root


def _render_test_source(component_path: Path, props: dict[str, object], output: Path, width: int, height: int, component_kind: str) -> str:
    props_json = json.dumps(props, sort_keys=True)
    component_url = _qml_url(component_path)
    wait_ms = 300 if component_kind == "panel" else 150
    object_props = "testRoot.props"
    if component_kind == "panel":
        object_props = """Object.assign({}, testRoot.props, {
      runActionFn: function(_payload) {},
      setBooleanActionFn: function(_action, _on, _extras) {},
      setVoiceLevelFn: function(_value) {},
      refreshStateFn: function() {}
    })"""
    return f"""
import QtQuick
import QtTest
import qs.Commons

TestCase {{
  id: testRoot
  name: "HollylandWidgetRender"
  when: windowShown
  width: {width}
  height: {height}

  property bool renderDone: false
  property bool renderOk: false
  property var props: ({props_json})

  function test_render_fixture() {{
    const component = Qt.createComponent("{component_url}");
    compare(component.status, Component.Ready, component.errorString());
    const item = component.createObject(testRoot, {object_props});
    verify(item !== null);
    wait({wait_ms});
    item.grabToImage(function(result) {{
      testRoot.renderOk = result.saveToFile({json.dumps(str(output))});
      testRoot.renderDone = true;
    }});
    tryCompare(testRoot, "renderDone", true, 5000);
    verify(renderOk);
    item.destroy();
  }}
}}
""".strip()


def _measure_test_source(component_path: Path, props: dict[str, object], width: int, height: int, component_kind: str) -> str:
    props_json = json.dumps(props, sort_keys=True)
    component_url = _qml_url(component_path)
    object_props = "testRoot.props"
    if component_kind == "panel":
        object_props = """Object.assign({}, testRoot.props, {
      runActionFn: function(_payload) {},
      setBooleanActionFn: function(_action, _on, _extras) {},
      setVoiceLevelFn: function(_value) {},
      refreshStateFn: function() {}
    })"""
    return f"""
import QtQuick
import QtTest
import qs.Commons

TestCase {{
  id: testRoot
  name: "HollylandWidgetMeasure"
  when: windowShown
  width: {width}
  height: {height}

  property var props: ({props_json})

  function test_measure_fixture() {{
    const component = Qt.createComponent("{component_url}");
    compare(component.status, Component.Ready, component.errorString());
    const item = component.createObject(testRoot, {object_props});
    verify(item !== null);
    wait(50);
    const result = {{
      preferredWidth: Number(item.contentPreferredWidth || item.implicitWidth || item.width || 0),
      preferredHeight: Number(item.contentPreferredHeight || item.implicitHeight || item.height || 0)
    }};
    console.log("MEASURE:" + JSON.stringify(result));
    item.destroy();
  }}
}}
""".strip()


def _render(
    runner: str,
    import_roots: list[Path],
    platform: str,
    component_path: Path,
    props: dict[str, object],
    output: Path,
    width: int,
    height: int,
    tmp_path: Path,
    component_kind: str,
) -> None:
    test_file = tmp_path / f"tst_render_{component_path.stem}.qml"
    test_file.write_text(_render_test_source(component_path, props, output, width, height, component_kind) + "\n", encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = platform
    env.setdefault("QML_DISABLE_DISK_CACHE", "1")
    env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("QT_STYLE_OVERRIDE", "Fusion")
    env.pop("QT_QPA_PLATFORMTHEME", None)
    cmd = [
        runner,
        "-platform",
        platform,
    ]
    for import_root in import_roots:
        cmd += ["-import", str(import_root)]
    cmd += ["-input", str(test_file)]
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    if not output.exists():
        raise RuntimeError(f"Renderer completed without writing {output}")


def _measure(
    runner: str,
    import_roots: list[Path],
    platform: str,
    component_path: Path,
    props: dict[str, object],
    width: int,
    height: int,
    tmp_path: Path,
    component_kind: str,
) -> tuple[int, int]:
    test_file = tmp_path / f"tst_measure_{component_path.stem}.qml"
    test_file.write_text(_measure_test_source(component_path, props, width, height, component_kind) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = platform
    env.setdefault("QML_DISABLE_DISK_CACHE", "1")
    env.setdefault("QT_QUICK_BACKEND", "software")
    env.setdefault("QT_STYLE_OVERRIDE", "Fusion")
    env.pop("QT_QPA_PLATFORMTHEME", None)
    cmd = [
        runner,
        "-platform",
        platform,
    ]
    for import_root in import_roots:
        cmd += ["-import", str(import_root)]
    cmd += ["-input", str(test_file)]
    result = subprocess.run(cmd, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    measured = None
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        marker = "MEASURE:"
        if marker in line:
            measured = json.loads(line.split(marker, 1)[1])
            break
    if measured is None:
        raise RuntimeError(f"Measurement completed without emitting preferred size for {component_path}")
    measured_width = int(round(float(measured.get("preferredWidth") or width)))
    measured_height = int(round(float(measured.get("preferredHeight") or height)))
    return max(1, measured_width), max(1, measured_height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", default=DEFAULT_SERVICE_URL, help="Payload URL, defaults to local /api/current")
    parser.add_argument("--panel-output", default=str(DEFAULT_PANEL_OUTPUT.relative_to(ROOT)), help="Rendered panel PNG path")
    parser.add_argument("--bar-output", default=str(DEFAULT_BAR_OUTPUT.relative_to(ROOT)), help="Rendered bar PNG path")
    parser.add_argument("--panel-width", type=int, default=DEFAULT_PANEL_WIDTH)
    parser.add_argument("--panel-height", type=int, default=DEFAULT_PANEL_HEIGHT, help="Panel height in px; use 0 to auto-size from contentPreferredHeight")
    parser.add_argument("--bar-width", type=int, default=DEFAULT_BAR_WIDTH)
    parser.add_argument("--bar-height", type=int, default=DEFAULT_BAR_HEIGHT)
    parser.add_argument("--platform", default=os.environ.get("QML_RENDER_PLATFORM", "offscreen"), help="Qt platform plugin for qmltestrunner")
    parser.add_argument("--noctalia-settings-file", default=str(DEFAULT_NOCTALIA_SETTINGS_FILE), help="Noctalia settings.json used for preview sizing/theme")
    parser.add_argument("--noctalia-colors-file", default=str(DEFAULT_NOCTALIA_COLORS_FILE), help="Noctalia colors.json used for preview colors")
    parser.add_argument("--no-redact", action="store_true", help="Skip redaction of receiver serial/MAC/USB path; default redacts for shareable screenshots")
    args = parser.parse_args()

    runner = _qmltestrunner()
    if runner is None:
        print("Widget render unavailable: install Qt 6 qmltestrunner or set QML_TESTRUNNER.", file=sys.stderr)
        return 2
    import_root = _import_root()
    source_root = _source_root(import_root)
    settings, colors, theme_source = _load_theme(
        Path(args.noctalia_settings_file).expanduser(),
        Path(args.noctalia_colors_file).expanduser(),
        source_root,
    )

    payload, source = _load_payload(args.service_url)
    if not args.no_redact:
        payload = _redact_payload(payload)
    print(f"Using payload source: {source}")
    print(f"Using Noctalia theme source: {theme_source}")

    panel_component = ROOT / "plugin" / "qml" / "HollylandPanel.qml"
    bar_component = ROOT / "plugin" / "qml" / "HollylandBar.qml"
    for component in (panel_component, bar_component):
        if not component.exists():
            print(f"Widget render unavailable: missing {component}", file=sys.stderr)
            return 2

    panel_output = _resolve_output_path(args.panel_output)
    bar_output = _resolve_output_path(args.bar_output)
    plugin_description = _manifest_description()

    with tempfile.TemporaryDirectory(prefix="widget-render-") as tmp:
        tmp_path = Path(tmp)
        preview_import_root = _write_preview_imports(tmp_path, settings, colors, source_root)
        import_roots = [preview_import_root]
        panel_width = args.panel_width
        panel_height = args.panel_height
        if panel_height <= 0:
            panel_measure_props = _panel_props(payload, panel_width, 4096, plugin_description)
            _, measured_panel_height = _measure(
                runner,
                import_roots,
                args.platform,
                panel_component,
                panel_measure_props,
                panel_width,
                4096,
                tmp_path,
                "panel",
            )
            panel_height = measured_panel_height + DEFAULT_PANEL_EXTRA_HEIGHT

        panel_props = _panel_props(payload, panel_width, panel_height, plugin_description)
        bar_props = _bar_props(payload, colors, args.bar_width, args.bar_height)

        _render(
            runner,
            import_roots,
            args.platform,
            panel_component,
            panel_props,
            panel_output,
            panel_width,
            panel_height,
            tmp_path,
            "panel",
        )
        _render(
            runner,
            import_roots,
            args.platform,
            bar_component,
            bar_props,
            bar_output,
            args.bar_width,
            args.bar_height,
            tmp_path,
            "bar",
        )

    print(f"panel: {panel_output} ({panel_width}x{panel_height})")
    print(f"bar: {bar_output} ({args.bar_width}x{args.bar_height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
