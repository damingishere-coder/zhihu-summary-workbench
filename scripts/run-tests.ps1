$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$FrontendRoot = Join-Path $RepoRoot "frontend"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Install backend dependencies first."
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    throw "Missing frontend dependencies. Run npm install in the frontend directory."
}

Set-Location -LiteralPath $RepoRoot
& $Python -m pytest --cov=backend.app --cov-report=term-missing

Set-Location -LiteralPath $FrontendRoot
& npm.cmd run typecheck
& npm.cmd run test:run
& npm.cmd run build
& npm.cmd run test:sites

Write-Output "All automated tests passed"
