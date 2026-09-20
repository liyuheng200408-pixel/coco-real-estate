<#
.SYNOPSIS
  本机模式便携 PostgreSQL 的 Windows 自检（给真机用，双击或一行命令即可跑）。

.DESCRIPTION
  做三件事，然后把结论连同日志路径一起打印出来，方便把输出直接发回给技术顾问：
    1. 跑一遍引导脚本的 setup（幂等：已经装好/已在跑就只做「确保在跑」）
    2. 跑引导脚本的 selftest（11 项：二进制、数据目录、只监听回环、端口自洽、pg_hba、
       回环可连、非回环连不上、口令认证生效、业务库存在、.env.db 权限、pg_dump 链路）
    3. 用 .env.db 里的 DATABASE_URL 直接连一次库，确认连接串真的可用

  它不修改系统：不装服务、不改注册表、不需要管理员权限；数据都在用户目录下。

.PARAMETER SkipDownload
  跳过下载（已内置便携包或用 -ZipPath 指了本地包时用）。

.PARAMETER ZipPath
  本地便携包路径（离线/内置分发）。

.PARAMETER KeepGoing
  即使 setup 失败也继续跑自检（默认失败即停，避免在半成品状态上得出误导结论）。

.EXAMPLE
  pwsh -File apps\desktop\scripts\tests\portable-postgres-windows-selfcheck.ps1
#>
[CmdletBinding()]
param(
    [string]$DataRoot = '',
    [string]$DataDir = '',
    [string]$EnvFile = '',
    [string]$ZipPath = '',
    [switch]$SkipDownload,
    [switch]$KeepGoing
)

$ErrorActionPreference = 'Continue'
$script:Problems = 0
$self = $PSCommandPath
$bootstrap = Join-Path (Split-Path -Parent (Split-Path -Parent $self)) 'portable-postgres.ps1'

if (-not (Test-Path -LiteralPath $bootstrap)) {
    Write-Host "找不到引导脚本：$bootstrap" -ForegroundColor Red
    exit 1
}

$home_ = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }
if (-not $DataRoot) { $DataRoot = Join-Path $home_ 'pgsql' }
if (-not $DataDir) { $DataDir = Join-Path $home_ 'pgsql-data' }
if (-not $EnvFile) { $EnvFile = Join-Path (Join-Path $home_ 'hermes-agent') '.env.db' }
$logDir = Join-Path $home_ 'pgsql-logs'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$report = Join-Path $logDir "selfcheck-$stamp.txt"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Say([string]$Text, [string]$Color = 'Gray') {
    Write-Host $Text -ForegroundColor $Color
    Add-Content -LiteralPath $report -Value $Text -Encoding UTF8
}

Say "Coco 本机数据库自检  $stamp" 'Cyan'
Say "系统      : $([System.Environment]::OSVersion.VersionString) / PowerShell $($PSVersionTable.PSVersion)"
Say "Hermes 目录: $home_"
Say "数据目录  : $DataDir"
Say "配置      : $EnvFile"
Say ""

$commonArgs = @('-DataRoot', $DataRoot, '-DataDir', $DataDir, '-EnvFile', $EnvFile)
if ($ZipPath) { $commonArgs += @('-ZipPath', $ZipPath) }
if ($SkipDownload) { $commonArgs += '-SkipDownload' }

Say "== [1/3] 准备数据库（setup，幂等）==" 'Cyan'
# 实时透传子进程输出（同时写进报告）：下载进度必须看得见，不能等它跑完才吐出来
& pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File $bootstrap @commonArgs -Action setup 2>&1 |
    Tee-Object -FilePath $report -Append | ForEach-Object { Write-Host "  $_" }
$setupCode = $LASTEXITCODE
Say "  退出码：$setupCode"
if ($setupCode -ne 0) {
    $script:Problems++
    Say "  setup 未成功 —— 请看上面的失败项与下面的日志路径" 'Red'
    if (-not $KeepGoing) {
        Say ""
        Say "完整输出已存到：$report" 'Yellow'
        Say "日志文件      ：$(Join-Path $DataDir 'coco-postgres.log')"
        Say "把这两行里的路径对应的文件发回给技术顾问即可。" 'Yellow'
        exit 1
    }
}

Say ""
Say "== [2/3] 自检（selftest）==" 'Cyan'
& pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File $bootstrap @commonArgs -Action selftest 2>&1 |
    Tee-Object -FilePath $report -Append | ForEach-Object { Write-Host "  $_" }
$selfCode = $LASTEXITCODE
Say "  退出码：$selfCode"
if ($selfCode -ne 0) { $script:Problems++ }

Say ""
Say "== [3/3] 用 .env.db 里的连接串直连一次 ==" 'Cyan'
if (Test-Path -LiteralPath $EnvFile) {
    $line = (Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1)
    if ($line) {
        $url = $line.Substring('DATABASE_URL='.Length).Trim()
        $psql = Join-Path (Join-Path $DataRoot 'bin') 'psql.exe'
        if (Test-Path -LiteralPath $psql) {
            $probe = & $psql $url -t -A -c 'select current_user, current_database(), inet_server_port(), current_setting(''listen_addresses'')' 2>&1
            $probeCode = $LASTEXITCODE
            Say "  psql 输出：$probe"
            Say "  退出码  ：$probeCode"
            if ($probeCode -ne 0) { $script:Problems++ }
        } else {
            $script:Problems++
            Say "  找不到 $psql（便携包不完整）" 'Red'
        }
    } else {
        $script:Problems++
        Say "  .env.db 里没有 DATABASE_URL" 'Red'
    }
} else {
    $script:Problems++
    Say "  找不到 .env.db：$EnvFile" 'Red'
}

Say ""
if ($script:Problems -eq 0) {
    Say "结论：全部通过，本机数据库可用。" 'Green'
    Say "后端需要的 3 件事：DATABASE_URL 来自上面这个 .env.db；PATH 里要有 $(Join-Path $DataRoot 'bin')；服务由 pg_ctl 常驻（电脑关机就下线）。"
} else {
    Say "结论：有 $($script:Problems) 项未通过，请把本报告发回给技术顾问。" 'Red'
}
Say "报告文件：$report"
Say "数据库日志：$(Join-Path $DataDir 'coco-postgres.log')"

exit $script:Problems
