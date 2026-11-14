# Install the external export toolchain on Windows.
# Usage:  pwsh -File scripts/install-tools.ps1

$ErrorActionPreference = "Stop"

Write-Host "Installing pandoc via winget..."
winget install --id JohnMacFarlane.Pandoc --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity

$tectonicVersion = "0.17.0"
$tectonicDir = Join-Path $env:LOCALAPPDATA "Tectonic"
$zip = Join-Path $env:TEMP "tectonic-$tectonicVersion.zip"
$url = "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40$tectonicVersion/tectonic-$tectonicVersion-x86_64-pc-windows-msvc.zip"

if (-not (Test-Path (Join-Path $tectonicDir "tectonic.exe"))) {
  Write-Host "Downloading tectonic $tectonicVersion..."
  Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
  New-Item -ItemType Directory -Force -Path $tectonicDir | Out-Null
  Expand-Archive -Path $zip -DestinationPath $tectonicDir -Force
  Remove-Item $zip -ErrorAction SilentlyContinue
}

& (Join-Path $tectonicDir "tectonic.exe") --version
Write-Host "pandoc: $((Get-Command pandoc -ErrorAction SilentlyContinue).Source)"
Write-Host "tectonic: $(Join-Path $tectonicDir 'tectonic.exe')"
