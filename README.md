# OpenClaw Skins

OpenClaw Skins is a Windows-first desktop skin host for monitoring and controlling a local OpenClaw gateway. It ships with a reusable skin manifest system and a placeholder crab skin pack that can be replaced with real PNG art at any time.

## Current Features

- Frameless transparent desktop skin window
- Bundled 2-frame skin manifest loader
- Live OpenClaw Gateway WebSocket monitoring
- Busy animation driven by OpenClaw `agent` lifecycle events
- Gateway `Refresh` and `Restart Gateway` controls
- System tray menu for show/hide, refresh, restart, and quit
- Settings file support for gateway URL, token, CLI command, skin selection, and window position

## Quick Start

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv pip install -e .[dev]
python -m openclaw_skins
```

## Settings

The app stores settings at `%LOCALAPPDATA%\OpenClawSkins\settings.json`.

You can override the CLI command to support wrappers such as:

```json
{
  "cli_command": "wsl openclaw"
}
```

## Skin Packs

Skin packs live under `assets\skins\<skin-id>\`.

The bundled crab skin reads its frames from `assets\sourcePNG\openclaw-skin-closed.png` and `assets\sourcePNG\openclaw-skin-open.png`.

If those files are missing, the asset script generates placeholders with those same names. If the files already exist, they are left untouched.

## Tests

```powershell
pytest
```

## Packaging

```powershell
.\scripts\build.ps1
```
