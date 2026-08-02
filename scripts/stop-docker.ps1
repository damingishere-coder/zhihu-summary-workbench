$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "没有找到 Docker。请先安装并打开 Docker Desktop。"
}

Set-Location -LiteralPath $RepoRoot
docker compose down

if ($LASTEXITCODE -ne 0) {
    throw "Docker 服务停止失败，请确认 Docker Desktop 正在运行。"
}

Write-Output "服务已停止，数据库和上传文件都已保留。"
