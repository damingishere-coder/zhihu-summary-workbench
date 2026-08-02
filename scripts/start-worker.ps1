$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Create the Python environment and install requirements-dev.txt."
}

Set-Location -LiteralPath $RepoRoot
& $Python -m backend.app.worker.main
