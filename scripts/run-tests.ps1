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
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }

Set-Location -LiteralPath $FrontendRoot
& npm.cmd run typecheck
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run typecheck:extension
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run test:extension
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run build:extension
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run test:run
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }
& npm.cmd run test:sites
if ($LASTEXITCODE -ne 0) { throw "Validation command failed (exit $LASTEXITCODE)" }

Write-Output "All automated tests passed"
