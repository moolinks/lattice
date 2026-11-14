# backup wrapper
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
& $Python (Join-Path $PSScriptRoot "backup.py") --archive
