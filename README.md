# Hollyland Noctalia Widget

Local Noctalia bar widget and panel for the Hollyland wireless receiver.

![Hollyland bar widget](docs/screenshots/hollyland-bar.png)

![Hollyland panel](docs/screenshots/hollyland-panel.png)

## Screenshots

Regenerate the checked-in screenshots with:

```bash
python3 scripts/render_widget_screenshots.py
```

This requires the local service running on `127.0.0.1:8791` and Qt 6
`qmltestrunner` at `/usr/lib/qt6/bin/qmltestrunner`, or a `QML_TESTRUNNER`
environment variable pointing to it.

The plugin talks to a tiny local HTTP service in `service/hollyland-widget-service`. That service
imports `~/agentic/hollyland/hollyland_api.py` directly and uses the same code path as the CLI,
rather than spawning `hollyland_cli.py` as a subprocess. HTTP is still the simpler boundary for the
QML side because the widget is request/poll oriented rather than stream oriented.

## What It Shows

- receiver presence and probe status
- RX version, serial, MAC, USB path
- transmitter online/offline state, battery, mute
- current audio settings from `summary`
- common write actions: noise, performance, light, identify, TX mute, voice mode, signal mode,
  EQ, shutdown time, and voice level

## Layout

| Path | Purpose |
|---|---|
| `plugin/manifest.json` | Noctalia plugin metadata and entry points |
| `plugin/Main.qml` | Shared plugin state, HTTP polling, action dispatch |
| `plugin/BarWidget.qml` | Compact bar surface |
| `plugin/Panel.qml` | Expanded controls and live state |
| `service/hollyland-widget-service` | Local HTTP wrapper around the Hollyland Python API |
| `systemd/hollyland-widget.service` | Optional user service unit |
| `scripts/check_all.sh` | Canonical local verification gate |
| `install.sh` | Symlink the plugin tree into Noctalia and register it |

## Run The Service

The plugin expects the service on `127.0.0.1:8791` by default.

Run it directly:

```bash
./service/hollyland-widget-service
```

Or link/start the user unit:

```bash
systemctl --user link ~/agentic/hollyland-widget/systemd/hollyland-widget.service
systemctl --user enable --now hollyland-widget.service
systemctl --user status hollyland-widget.service
```

Useful overrides:

```bash
HOLLYLAND_PROJECT_ROOT=~/agentic/hollyland
HOLLYLAND_WIDGET_HOST=127.0.0.1
HOLLYLAND_WIDGET_PORT=8791
```

Quick checks:

```bash
curl -s http://127.0.0.1:8791/health | python3 -m json.tool
curl -s http://127.0.0.1:8791/api/current | python3 -m json.tool
curl -s -X POST http://127.0.0.1:8791/api/action \
  -H 'content-type: application/json' \
  -d '{"action":"refresh"}' | python3 -m json.tool
```

## Install The Plugin

Install the QML into `~/.config/noctalia/plugins/hollyland/` and register it in
`~/.config/noctalia/plugins.json`:

```bash
./install.sh
```

Use `./install.sh --restart` to restart Noctalia after install, or `./install.sh --dry-run` to
inspect what would happen.

## Checks

Run the full local gate with:

```bash
scripts/check_all.sh
```

That runs:

- Python syntax compilation for `scripts/` and `service/`
- `bash -n install.sh`
- manifest and entry-point validation
- QML linting
- installer dry-run validation

QML linting expects a configured import shim. Set it up once per clone:

```bash
python3 scripts/setup_noctalia_qml_imports.py --checkout /etc/xdg/quickshell/noctalia-shell
```
