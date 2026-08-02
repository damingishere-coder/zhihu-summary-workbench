$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Create it in the repository root and install requirements-dev.txt."
}

Set-Location -LiteralPath $RepoRoot
& $Python -m alembic upgrade head
& $Python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
