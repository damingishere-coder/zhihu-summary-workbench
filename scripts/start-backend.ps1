$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Create it in the repository root and install requirements-dev.txt."
}

Set-Location -LiteralPath $RepoRoot
$ExistingListener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ExistingListener) {
    $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($ExistingListener.OwningProcess)" -ErrorAction SilentlyContinue
    throw "端口 8000 已被 PID $($ExistingListener.OwningProcess) 占用。命令：$($Owner.CommandLine)。脚本不会自动停止其他项目进程。"
}
& $Python -m alembic upgrade head
& $Python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
