$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$FrontendRoot = Join-Path $RepoRoot "frontend"
$LogsRoot = Join-Path $RepoRoot "logs"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Create the Python environment and install requirements-dev.txt."
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    throw "Missing frontend dependencies. Run npm install in the frontend directory."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install and start Docker Desktop."
}

New-Item -ItemType Directory -Path $LogsRoot -Force | Out-Null
Set-Location -LiteralPath $RepoRoot

docker compose up -d redis
if ($LASTEXITCODE -ne 0) {
    throw "Redis container failed to start. Check Docker Desktop and network access."
}
$RedisReady = $false
for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    $Ping = docker compose exec -T redis redis-cli ping 2>$null
    if ($LASTEXITCODE -eq 0 -and $Ping -match "PONG") {
        $RedisReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $RedisReady) {
    throw "Redis container did not become healthy within 20 seconds."
}
Write-Output "Redis is ready"

& $Python -m alembic upgrade head
Write-Output "Database migration completed"

foreach ($RequiredPort in @(8000, 4173)) {
    $ExistingListener = Get-NetTCPConnection -State Listen -LocalPort $RequiredPort -ErrorAction SilentlyContinue
    if ($ExistingListener) {
        $FirstListener = $ExistingListener | Select-Object -First 1
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($FirstListener.OwningProcess)" -ErrorAction SilentlyContinue
        throw "端口 $RequiredPort 已被 PID $($FirstListener.OwningProcess) 占用。命令：$($Owner.CommandLine)。脚本不会自动停止其他项目进程。"
    }
}

$Backend = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsRoot "backend.log") `
    -RedirectStandardError (Join-Path $LogsRoot "backend-error.log") `
    -PassThru

$Worker = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "backend.app.worker.main") `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsRoot "worker.log") `
    -RedirectStandardError (Join-Path $LogsRoot "worker-error.log") `
    -PassThru

$Frontend = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "4173", "--strictPort") `
    -WorkingDirectory $FrontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsRoot "frontend.log") `
    -RedirectStandardError (Join-Path $LogsRoot "frontend-error.log") `
    -PassThru

Set-Content -LiteralPath (Join-Path $LogsRoot "backend.pid") -Value $Backend.Id
Set-Content -LiteralPath (Join-Path $LogsRoot "worker.pid") -Value $Worker.Id
Set-Content -LiteralPath (Join-Path $LogsRoot "frontend.pid") -Value $Frontend.Id

Start-Sleep -Seconds 2
try {
    $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 10
    if ($Health.app_id -ne "zhihu-summary-workbench") {
        throw "8000 端口返回了其他应用：$($Health.app_id)"
    }
    if ($Health.database_revision -ne "20260823_0005") {
        throw "数据库版本不正确：$($Health.database_revision)"
    }
}
catch {
    throw "Backend failed to start. Check logs\backend-error.log. Error: $($_.Exception.Message)"
}

Write-Output "Backend, worker, and frontend started"
Write-Output "Frontend: http://127.0.0.1:4173"
Write-Output "API docs: http://127.0.0.1:8000/docs"
Write-Output "Logs: $LogsRoot"
