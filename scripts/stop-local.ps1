$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsRoot = Join-Path $RepoRoot "logs"
$StatePath = Join-Path $LogsRoot "local-state.json"

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Output "未找到本机启动状态：$StatePath"
    exit 0
}

try {
    $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
}
catch {
    throw "无法读取本机启动状态 $StatePath。请不要按端口手动终止进程，先检查该文件。"
}

$ResolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$RecordedRepoRoot = [string]$State.projectRoot
if ($RecordedRepoRoot -ne $ResolvedRepoRoot) {
    throw "状态文件的项目根目录不匹配，已跳过停止以保护其他项目进程。"
}

function Get-TrackedProcessInfo {
    param([int]$ProcessId)

    Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Get-ProcessTreeIds {
    param([int]$RootProcessId)

    $ProcessIds = New-Object 'System.Collections.Generic.List[int]'
    $ProcessIds.Add($RootProcessId)
    $Children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [int]$_.ParentProcessId -eq $RootProcessId })
    foreach ($Child in $Children) {
        foreach ($ChildProcessId in @(Get-ProcessTreeIds -RootProcessId ([int]$Child.ProcessId))) {
            $ProcessIds.Add([int]$ChildProcessId)
        }
    }
    return $ProcessIds.ToArray()
}

function ConvertTo-RecordedUtc {
    param([object]$Value)

    if ($Value -is [DateTimeOffset]) {
        return $Value.UtcDateTime
    }
    if ($Value -is [DateTime]) {
        return $Value.ToUniversalTime()
    }
    return [DateTime]::ParseExact(
        [string]$Value,
        "o",
        [System.Globalization.CultureInfo]::InvariantCulture,
        [System.Globalization.DateTimeStyles]::RoundtripKind
    ).ToUniversalTime()
}

function Test-TrackedProcessIdentity {
    param(
        [object]$Record,
        [object]$ProcessInfo
    )

    if (-not $ProcessInfo) {
        return [pscustomobject]@{
            Live = $false
            Matches = $true
            Failures = @()
        }
    }

    $Failures = New-Object 'System.Collections.Generic.List[string]'
    $CommandLine = [string]$ProcessInfo.CommandLine
    $RootMatches = $CommandLine.IndexOf([string]$Record.root, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $MarkerMatches = $CommandLine.IndexOf([string]$Record.marker, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $Port = 0
    $PortIsValid = [int]::TryParse([string]$Record.port, [ref]$Port) -and $Port -gt 0
    $PortTokenMatches = $false
    if ($PortIsValid) {
        $PortTokenMatches =
            $CommandLine.IndexOf("--port $Port", [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $CommandLine.IndexOf("--port=$Port", [StringComparison]::OrdinalIgnoreCase) -ge 0
    }

    if (-not $RootMatches) { $Failures.Add("项目根目录") }
    if (-not $MarkerMatches) { $Failures.Add("命令标记") }
    if (-not $PortIsValid -or -not $PortTokenMatches) { $Failures.Add("端口 token") }

    $PortOwnerMatches = $false
    if ($PortIsValid) {
        $ProcessTreeIds = @(Get-ProcessTreeIds -RootProcessId ([int]$ProcessInfo.ProcessId))
        $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
        foreach ($Listener in $Listeners) {
            if ($ProcessTreeIds -contains ([int]$Listener.OwningProcess)) {
                $PortOwnerMatches = $true
                break
            }
        }
    }
    if (-not $PortOwnerMatches) { $Failures.Add("端口监听归属") }

    $LiveStartMatches = $false
    try {
        $LiveProcess = Get-Process -Id ([int]$ProcessInfo.ProcessId) -ErrorAction Stop
        $LiveStartUtc = $LiveProcess.StartTime.ToUniversalTime()
        $RecordedStartUtc = ConvertTo-RecordedUtc -Value $Record.startTimeUtc
        $LiveStartMatches = [math]::Abs(($LiveStartUtc - $RecordedStartUtc).TotalSeconds) -le 5
    }
    catch {
        $Failures.Add("启动时间")
    }
    if (-not $LiveStartMatches -and -not ($Failures -contains "启动时间")) {
        $Failures.Add("启动时间")
    }

    return [pscustomobject]@{
        Live = $true
        Matches = $Failures.Count -eq 0
        Failures = @($Failures)
    }
}

function Stop-VerifiedProcessTree {
    param(
        [int]$RootProcessId,
        [object]$Record,
        [switch]$Validated
    )

    if (-not $Validated) { throw "内部错误：停止进程前必须完成身份校验。" }

    $Children = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [int]$_.ParentProcessId -eq $RootProcessId }
    foreach ($Child in $Children) {
        Stop-VerifiedProcessTree -RootProcessId ([int]$Child.ProcessId) -Record $Record -Validated
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
    Write-Output "已停止 $($Record.name)（PID $RootProcessId）"
}

$IdentityMismatch = $false
$InvalidRecord = $false
foreach ($Record in @($State.processes)) {
    $ProcessId = 0
    if ([int]::TryParse([string]$Record.pid, [ref]$ProcessId)) {
        $ProcessInfo = Get-TrackedProcessInfo -ProcessId $ProcessId
        $Identity = Test-TrackedProcessIdentity -Record $Record -ProcessInfo $ProcessInfo
        if (-not $Identity.Live) {
            Write-Output "$($Record.name)（PID $ProcessId）已退出，清理记录。"
            continue
        }
        if (-not $Identity.Matches) {
            $IdentityMismatch = $true
            Write-Warning "PID $ProcessId 的 $($Record.name) 身份校验失败（$($Identity.Failures -join '、')），已跳过且保留状态文件。"
            continue
        }
        Stop-VerifiedProcessTree -RootProcessId $ProcessId -Record $Record -Validated
    }
    else {
        $InvalidRecord = $true
        Write-Warning "状态中的 $($Record.name) PID 无效，已跳过。"
    }
}

if ($IdentityMismatch -or $InvalidRecord) {
    Write-Warning "存在仍运行但身份不匹配或无效的进程记录，状态文件已保留；请确认后再处理。"
    exit 1
}

Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
Write-Output "本机 memory 模式已停止"
