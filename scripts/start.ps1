# Lattice — one-command local start
# Usage:  pwsh -File scripts/start.ps1 [-Build] [-Port 8000]

param(
  [switch]$Build,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$DataDir = Join-Path $HOME "research-data"

if (-not (Test-Path $DataDir)) {
  New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
}

Write-Host "LATTICE / local research workbench" -ForegroundColor DarkYellow
Write-Host "data: $DataDir"
Write-Host "url:  http://127.0.0.1:$Port"

Set-Location $Backend
if (-not (Test-Path (Join-Path $Backend ".venv"))) {
  uv sync
}

$staticIndex = Join-Path $Backend "app/static/index.html"
if ($Build -or -not (Test-Path $staticIndex)) {
  Write-Host "building frontend..." -ForegroundColor DarkGray
  Push-Location $Frontend
  pnpm.cmd install
  pnpm.cmd build
  Pop-Location
}

$env:RESEARCH_DATA_DIR = $DataDir
uv run uvicorn app.main:app --host 127.0.0.1 --port $Port
