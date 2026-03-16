$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

& $python scripts\generate_assets.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m openclaw_skins
exit $LASTEXITCODE

