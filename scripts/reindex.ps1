# Rebuild FTS5 search index and Markdown-derived link table.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
& $Python (Join-Path $PSScriptRoot "reindex.py")
