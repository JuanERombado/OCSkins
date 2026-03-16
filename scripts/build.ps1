$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$buildName = "OpenClaw Skins"

& $python scripts\generate_assets.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name $buildName `
  --icon assets\icons\openclaw-skins.ico `
  --add-data "assets;assets" `
  --collect-submodules openclaw_skins `
  src\openclaw_skins\__main__.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

