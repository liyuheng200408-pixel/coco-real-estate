<#
.SYNOPSIS
  本机模式的每日备份：把便携 PostgreSQL 里的业务数据与密钥文件备份到用户目录。

.DESCRIPTION
  本机模式下数据在所有者的电脑上，**备份是唯一的安全网**（服务器版由服务器上的
  每日 cron 兜底，这里没有别人替你兜）。所以装好数据库之后就注册一条用户级计划任务，
  每天跑一次，并在登录时补一次（笔记本中午常常是关机/合盖状态）。

  备份内容（与服务器版的约定一致，便于同一套恢复流程）：
    · 业务库 dump —— 调仓库里的 `scripts/backup_db.py backup`（pg_dump -Fc），
      落到 `~/backups/real_estate/*.dump`
    · `enc_key.txt` —— 客户手机号/微信的加密密钥（丢了就永久解不开）
    · `env.db.bak` —— 整个 .env.db（含数据库口令），恢复时不用再猜
  不做删除：由 `backup_db.py` 自己的保留策略处理，避免这里再多一套删数据的逻辑。

.PARAMETER Action
  register    注册计划任务（幂等），并立刻跑一次备份
  unregister  删除计划任务（不动已有备份文件）
  run         只跑一次备份（计划任务就是这么调的）
  status      看计划任务与最近一次备份的情况

.EXAMPLE
  pwsh -File local-backup.ps1 -Action register

.EXAMPLE
  pwsh -File local-backup.ps1 -Action run -PgBinDir D:\hermes\pgsql\bin
#>
[CmdletBinding()]
param(
    [ValidateSet('register', 'unregister', 'run', 'status')]
    [string]$Action = 'run',

    [string]$InstallDir = '',
    [string]$DataRoot = '',
    [string]$BackupDir = '',
    # 便携 PG 的 bin（备份要 pg_dump/pg_restore/psql）
    [string]$PgBinDir = '',
    # 计划任务名（一个账号一份，含中文会被 schtasks 正常接受）
    [string]$TaskName = 'Coco-LocalDatabase-Backup',
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
$script:IsWin = ($env:OS -eq 'Windows_NT')
$script:Exit = @{ Ok = 0; Config = 8; Failed = 1 }

function Say([string]$Text, [string]$Color = 'Gray') {
    if (-not $Quiet -or $Color -ne 'Gray') { Write-Host $Text -ForegroundColor $Color }
}
function Step([string]$m) { Say '' ; Say "== $m ==" 'Cyan' }

$home_ = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }
if (-not $InstallDir) { $InstallDir = Join-Path $home_ 'hermes-agent' }
if (-not $DataRoot) { $DataRoot = Join-Path $home_ 'pgsql' }
if (-not $PgBinDir) { $PgBinDir = Join-Path $DataRoot 'bin' }
if (-not $BackupDir) { $BackupDir = Join-Path $env:USERPROFILE 'backups\real_estate' }
$envFile = Join-Path $InstallDir '.env.db'
$logFile = Join-Path $BackupDir 'local-backup.log'

function Write-Log([string]$Message) {
    if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null }
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    Say "  $Message"
}

function Get-EnvValue([string]$Key) {
    if (-not (Test-Path -LiteralPath $envFile)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($envFile)) {
        $t = $line.Trim()
        if ($t -match ('^' + [regex]::Escape($Key) + '=(.*)$')) { return $Matches[1] }
    }
    return $null
}

function Get-VenvPython {
    $candidates = if ($script:IsWin) {
        @((Join-Path $InstallDir 'venv\Scripts\python.exe'), (Join-Path $InstallDir 'venv\bin\python'))
    } else {
        @((Join-Path $InstallDir 'venv\bin\python'), (Join-Path $InstallDir 'venv\bin\python3'), (Join-Path $InstallDir 'venv\Scripts\python.exe'))
    }
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return $c } }
    return $null
}

function Invoke-Backup {
    Step '备份本机数据库'
    if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null }

    if (-not (Test-Path -LiteralPath $envFile)) {
        Write-Log "失败：找不到配置文件 $envFile（本机模式还没装好？）"
        return $script:Exit.Config
    }

    $url = Get-EnvValue 'DATABASE_URL'
    if (-not $url) {
        Write-Log "失败：$envFile 里没有 DATABASE_URL"
        return $script:Exit.Config
    }

    $python = Get-VenvPython
    $backupScript = Join-Path (Join-Path $InstallDir 'scripts') 'backup_db.py'
    if (-not $python -or -not (Test-Path -LiteralPath $backupScript)) {
        Write-Log "失败：找不到后端 venv 或备份脚本（python=$python, script=$backupScript）"
        return $script:Exit.Config
    }

    # 备份脚本调裸命令名 pg_dump/pg_restore/psql —— 必须把便携 PG 的 bin 放最前
    $oldPath = $env:PATH
    $oldUtf8 = $env:PYTHONUTF8
    $oldIoEnc = $env:PYTHONIOENCODING
    $env:PATH = "$PgBinDir$([System.IO.Path]::PathSeparator)$oldPath"
    $env:DATABASE_URL = $url
    # 强制 Python 走 UTF-8：Windows 上 stdout 默认跟随控制台代码页（cp1252/GBK），
    # 脚本一打印中文就 UnicodeEncodeError 崩掉（实测真机 CI：计划任务注册成功、
    # 备份一跑就失败）。后端进程本来就有 PYTHONUTF8=1，这里对备份脚本做同样的事。
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    try {
        # 明确把备份目录交给 backup_db.py：它默认写 ~/backups/real_estate，
        # 而我们可能被调用方指定了别的位置（不传就会出现「备份成功但目录里没有」）。
        $out = & $python $backupScript backup --backup-dir $BackupDir 2>&1 | Out-String
        $code = $LASTEXITCODE
        foreach ($line in ($out -split "`r?`n")) { if ($line.Trim()) { Write-Log "  $line" } }
        if ($code -ne 0) {
            Write-Log "失败：backup_db.py 退出码 $code"
            return $script:Exit.Failed
        }
    } finally {
        $env:PATH = $oldPath
        Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
        if ($null -eq $oldUtf8) { Remove-Item Env:\PYTHONUTF8 -ErrorAction SilentlyContinue } else { $env:PYTHONUTF8 = $oldUtf8 }
        if ($null -eq $oldIoEnc) { Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue } else { $env:PYTHONIOENCODING = $oldIoEnc }
    }

    # 密钥单独留一份（服务器版也是这么做的）：丢了就再也解不开客户手机号/微信
    $key = Get-EnvValue 'COCO_ENC_KEY'
    if ($key) {
        Set-Content -LiteralPath (Join-Path $BackupDir 'enc_key.txt') -Value "COCO_ENC_KEY=$key" -Encoding UTF8
        Write-Log '已备份密钥到 enc_key.txt'
    } else {
        Write-Log '注意：.env.db 里没有 COCO_ENC_KEY（旧安装或已损坏）'
    }

    # 整个 .env.db 也留一份：本机模式的口令只在这里，恢复时省得猜
    Copy-Item -LiteralPath $envFile -Destination (Join-Path $BackupDir 'env.db.bak') -Force
    Write-Log '已备份 .env.db → env.db.bak'

    $newest = Get-ChildItem -LiteralPath $BackupDir -Filter '*.dump' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) {
        Write-Log ("完成：最新备份 {0}（{1:N1} MB，{2}）" -f $newest.Name, ($newest.Length / 1MB), $newest.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))
    } else {
        Write-Log '失败：备份目录里没有 dump 文件'
        return $script:Exit.Failed
    }

    return $script:Exit.Ok
}

function Get-TaskXml {
    # 用 XML 而不是 schtasks 命令行参数：只有 XML 才设得上 StartWhenAvailable
    # （笔记本中午关机是常态，错过的时间点要在机器醒来后补跑）。
    $user = "$env:USERDOMAIN\$env:USERNAME"
    # 路径里可能有空格/& —— 点出 XML 的特殊字符，避免任务注册后跑不起来
    $scriptArg = [System.Security.SecurityElement]::Escape($PSCommandPath)
    @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Coco 本机模式：每天备份便携 PostgreSQL 的数据与密钥（用户级任务，不需要管理员权限）</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$(Get-Date -Format 'yyyy-MM-dd')T12:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>pwsh</Command>
      <Arguments>-NoLogo -NoProfile -ExecutionPolicy Bypass -File &quot;$scriptArg&quot; -Action run</Arguments>
    </Exec>
  </Actions>
</Task>
"@
}

function Register-Task {
    if (-not $script:IsWin) {
        Say '计划任务只在 Windows 上注册（其它平台请用 cron 调 -Action run）' 'Yellow'
        return $script:Exit.Config
    }

    Step '注册每日备份计划任务'
    $xmlPath = Join-Path ([System.IO.Path]::GetTempPath()) ('coco-backup-' + [Guid]::NewGuid().ToString('N') + '.xml')
    try {
        [System.IO.File]::WriteAllText($xmlPath, (Get-TaskXml), (New-Object System.Text.UnicodeEncoding))
        $out = & schtasks.exe /Create /TN $TaskName /XML $xmlPath /F 2>&1 | Out-String
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            Say "注册失败（schtasks 退出码 $code）：$($out.Trim())" 'Red'
            return $script:Exit.Failed
        }
        Say "已注册计划任务：$TaskName（每天 12:00 + 每次登录，用户级、不需要管理员）" 'Green'
    } finally {
        Remove-Item -LiteralPath $xmlPath -Force -ErrorAction SilentlyContinue
    }

    # 立刻跑一次：注册完就有第一份备份，不用等到明天
    return (Invoke-Backup)
}

function Unregister-Task {
    if (-not $script:IsWin) { Say '非 Windows 平台没有计划任务可删' 'Yellow'; return $script:Exit.Config }
    $out = & schtasks.exe /Delete /TN $TaskName /F 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Say "删除失败：$($out.Trim())" 'Red'; return $script:Exit.Failed }
    Say "已删除计划任务：$TaskName（备份文件保留在 $BackupDir）" 'Green'
    return $script:Exit.Ok
}

function Get-Status {
    Step '本机备份状态'
    Say "备份目录：$BackupDir"
    $envState = if (Test-Path -LiteralPath $envFile) { '存在' } else { '缺失' }
    Say "配置文件：$envFile（$envState）"
    if (Test-Path -LiteralPath $BackupDir) {
        $dumps = @(Get-ChildItem -LiteralPath $BackupDir -Filter '*.dump' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        Say "备份数量：$($dumps.Count)"
        if ($dumps.Count -gt 0) { Say "最新备份：$($dumps[0].Name)（$([math]::Round($dumps[0].Length / 1MB, 1)) MB，$($dumps[0].LastWriteTime)）" }
        foreach ($f in @('enc_key.txt', 'env.db.bak')) {
            $state = if (Test-Path -LiteralPath (Join-Path $BackupDir $f)) { '有' } else { '缺' }
            Say "$f：$state"
        }
    }
    if ($script:IsWin) {
        $out = & schtasks.exe /Query /TN $TaskName 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { Say "计划任务：已注册（$TaskName）" 'Green' } else { Say "计划任务：未注册（$TaskName）" 'Yellow' }
    }
    $stale = $false
    if (Test-Path -LiteralPath $BackupDir) {
        $newest = Get-ChildItem -LiteralPath $BackupDir -Filter '*.dump' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $newest) { $stale = $true } elseif (((Get-Date) - $newest.LastWriteTime).TotalHours -gt 48) { $stale = $true }
    } else { $stale = $true }
    if ($stale) { Say '结论：超过 48 小时没有新备份（或从来没有），请跑 -Action register' 'Yellow'; return $script:Exit.Failed }
    Say '结论：备份正常' 'Green'
    return $script:Exit.Ok
}

switch ($Action) {
    'run' { exit (Invoke-Backup) }
    'register' { exit (Register-Task) }
    'unregister' { exit (Unregister-Task) }
    'status' { exit (Get-Status) }
}
