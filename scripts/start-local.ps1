$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$FrontendRoot = Join-Path $RepoRoot "frontend"
$FrontendConfig = Join-Path $FrontendRoot "vite.config.mjs"
$LogsRoot = Join-Path $RepoRoot "logs"
$StatePath = Join-Path $LogsRoot "local-state.json"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "缺少项目 .venv。请先运行 .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt。"
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
    throw "缺少 frontend\node_modules。请先进入 frontend 运行 npm install。"
}
if (-not (Test-Path -LiteralPath $FrontendConfig)) {
    throw "缺少 frontend\vite.config.mjs，无法启动 Vite。"
}

New-Item -ItemType Directory -Path $LogsRoot -Force | Out-Null

function Stop-ProcessTree {
    param([int]$RootProcessId)

    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in $Children) {
        Stop-ProcessTree -RootProcessId ([int]$Child.ProcessId)
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

$ExpectedRevision = (& $Python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config(r'$RepoRoot/alembic.ini')).get_current_head())").Trim()
if ($LASTEXITCODE -ne 0) { throw "无法确定数据库目标版本" }

foreach ($RequiredPort in @(8002, 4173)) {
    $ExistingListener = Get-NetTCPConnection -State Listen -LocalPort $RequiredPort -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ExistingListener) {
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($ExistingListener.OwningProcess)" -ErrorAction SilentlyContinue
        throw "端口 $RequiredPort 已被 PID $($ExistingListener.OwningProcess) 占用。命令：$($Owner.CommandLine)。脚本不会自动停止其他项目进程。"
    }
}

$HadQueueBackend = Test-Path -LiteralPath Env:QUEUE_BACKEND
$OriginalQueueBackend = $env:QUEUE_BACKEND
$StartedProcesses = @()

try {
    Set-Location -LiteralPath $RepoRoot
    $env:QUEUE_BACKEND = "memory"

    $Backend = Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "backend.app.runtime", "--app-dir", $RepoRoot, "--port", "8002") `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogsRoot "local-backend.log") `
        -RedirectStandardError (Join-Path $LogsRoot "local-backend-error.log") `
        -PassThru
    $StartedProcesses += $Backend

    $Frontend = Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev", "--", "--config", $FrontendConfig, "--host", "127.0.0.1", "--port", "4173", "--strictPort") `
        -WorkingDirectory $FrontendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogsRoot "local-frontend.log") `
        -RedirectStandardError (Join-Path $LogsRoot "local-frontend-error.log") `
        -PassThru
    $StartedProcesses += $Frontend

    $BackendReady = $false
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/health" -TimeoutSec 2
            if ($Health.app_id -ne "zhihu-summary-workbench") {
                throw "8002 端口返回了其他应用：$($Health.app_id)"
            }
            if ($Health.database_revision -ne $ExpectedRevision) {
                throw "数据库版本不正确：$($Health.database_revision)"
            }
            $BackendReady = $true
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $BackendReady) {
        throw "FastAPI 未能在 30 秒内启动，请检查 logs\local-backend-error.log。"
    }

    $FrontendReady = $false
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        $FrontendListener = Get-NetTCPConnection -State Listen -LocalPort 4173 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($FrontendListener) {
            $FrontendReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $FrontendReady) {
        throw "Vite 未能在 30 秒内启动，请检查 logs\local-frontend-error.log。"
    }

    $StartedAt = (Get-Date).ToUniversalTime().ToString("o")
    $State = [ordered]@{
        schemaVersion = 1
        projectRoot = $RepoRoot
        startedAtUtc = $StartedAt
        processes = @(
            [ordered]@{
                name = "backend"
                pid = $Backend.Id
                root = $RepoRoot
                port = 8002
                marker = "backend.app.runtime"
                startTimeUtc = $Backend.StartTime.ToUniversalTime().ToString("o")
            }
            [ordered]@{
                name = "frontend"
                pid = $Frontend.Id
                root = $FrontendRoot
                port = 4173
                marker = "vite.config.mjs"
                startTimeUtc = $Frontend.StartTime.ToUniversalTime().ToString("o")
            }
        )
    }
    $State | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatePath -Encoding UTF8

    Write-Output "本机 memory 模式已启动（未启动 Docker 和独立 Worker）"
    Write-Output "前端: http://127.0.0.1:4173"
    Write-Output "API 文档: http://127.0.0.1:8002/docs"
    Write-Output "运行状态: $StatePath"
}
catch {
    foreach ($StartedProcess in $StartedProcesses) {
        if ($StartedProcess -and (Get-Process -Id $StartedProcess.Id -ErrorAction SilentlyContinue)) {
            Stop-ProcessTree -RootProcessId ([int]$StartedProcess.Id)
        }
    }
    throw
}
finally {
    if ($HadQueueBackend) {
        $env:QUEUE_BACKEND = $OriginalQueueBackend
    }
    else {
        Remove-Item -LiteralPath Env:QUEUE_BACKEND -ErrorAction SilentlyContinue
    }
}
