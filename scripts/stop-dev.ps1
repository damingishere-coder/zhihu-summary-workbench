$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsRoot = Join-Path $RepoRoot "logs"

function Stop-TrackedProcessTree {
    param([int]$TrackedProcessId)

    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$TrackedProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in $Children) {
        Stop-TrackedProcessTree -TrackedProcessId ([int]$Child.ProcessId)
    }
    Stop-Process -Id $TrackedProcessId -Force -ErrorAction SilentlyContinue
}

foreach ($Name in @("frontend", "worker", "backend")) {
    $PidFile = Join-Path $LogsRoot "$Name.pid"
    if (Test-Path -LiteralPath $PidFile) {
        $ProcessId = Get-Content -LiteralPath $PidFile | Select-Object -First 1
        if ($ProcessId -match "^\d+$") {
            Stop-TrackedProcessTree -TrackedProcessId ([int]$ProcessId)
            Write-Output "Stopped $Name (PID $ProcessId)"
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

Set-Location -LiteralPath $RepoRoot
docker compose stop redis
Write-Output "Development services stopped"
