param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "没有找到 Docker。请先安装并打开 Docker Desktop。"
}

try {
    docker info | Out-Null
}
catch {
    throw "Docker Desktop 当前没有运行。请打开 Docker Desktop，等待左下角显示 Engine running 后重试。"
}

Set-Location -LiteralPath $RepoRoot
Write-Output "正在构建并启动知乎问题总结工作台，请稍候……"
$env:COMPOSE_PROGRESS = "plain"

docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Docker 构建或启动失败。请查看上方最先出现的 ERROR；常见原因是网络无法下载镜像，或 4173、8000、6379 端口被占用。"
}

$Ready = $false
for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        $Frontend = Invoke-WebRequest -Uri "http://127.0.0.1:4173/" -TimeoutSec 2 -UseBasicParsing
        if ($Health.status -eq "ok" -and $Frontend.StatusCode -eq 200) {
            $Ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $Ready) {
    docker compose ps
    throw "容器已经启动，但网页未在 60 秒内就绪。请运行 docker compose logs 查看具体原因。"
}

Write-Output ""
Write-Output "启动成功！"
Write-Output "网页：http://127.0.0.1:4173"
Write-Output "接口文档：http://127.0.0.1:8000/docs"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:4173"
}
