$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"

if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    throw "Missing frontend node_modules. Run npm install in the frontend directory."
}

Set-Location -LiteralPath $FrontendRoot
& npm.cmd run dev -- --host 127.0.0.1 --port 4173 --strictPort
