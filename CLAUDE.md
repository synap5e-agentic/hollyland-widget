# Noctalia Plugin Template

This repo is a reusable starting point for local Noctalia plugins.

## First Steps

- Stamp the sample manifest before real feature work:

```bash
python3 scripts/scaffold_plugin.py \
  --plugin-id my-plugin \
  --name "My Plugin" \
  --description "Short description" \
  --author "Simon"
```

- Configure the local QML import shim once per clone:

```bash
python3 scripts/setup_noctalia_qml_imports.py --checkout /etc/xdg/quickshell/noctalia-shell
```

- If the checkout is a git repo, enable the repo-local hooks:

```bash
scripts/install_git_hooks.sh
```

## Required Checks

Use `scripts/check_all.sh` as the canonical local gate before handing off or committing.

It runs:

- Python syntax compilation for `scripts/`
- `bash -n install.sh`
- `python3 scripts/validate_plugin.py`
- `python3 scripts/lint_qml.py`
- `./install.sh --dry-run`

The `pre-commit` hook calls the same script. Do not add separate ad hoc check paths unless the template grows a new stable requirement and the canonical script is updated with it.

## Editing Conventions

- Keep `plugin/manifest.json` authoritative for the plugin id, metadata, and entry points.
- Keep `install.sh` manifest-driven. Do not hardcode plugin ids in the installer.
- Put shared plugin state in `plugin/Main.qml`, the bar surface in `plugin/BarWidget.qml`, and the expanded UI in `plugin/Panel.qml`.
- If you add new QML entry points like `Settings.qml` or `ControlCenterWidget.qml`, update both `plugin/manifest.json` and `scripts/validate_plugin.py` expectations only if the new shape becomes part of the template contract.

## Hook Notes

- Hooks live in `.githooks/`.
- `scripts/install_git_hooks.sh` sets `git config core.hooksPath .githooks`.
- If commits fail on QML lint because imports are missing, fix the local shim setup instead of bypassing the hook.
