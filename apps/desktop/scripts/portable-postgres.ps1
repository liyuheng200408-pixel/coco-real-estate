<#
.SYNOPSIS
  Coco 桌面版「本机模式」便携 PostgreSQL 引导脚本（Windows 首发）。

.DESCRIPTION
  在没有管理员权限、不注册系统服务的前提下，为 Coco 本机模式准备一个独立的
  PostgreSQL：下载便携发行包 → 只解出运行必需目录 → initdb → 随机端口 + 随机
  口令 → 只监听回环 → 建业务库 → 写出与 .env.db 约定一致的连接串。

  设计约束（与 Coco 现有部署约定一致，勿随意更改）：
  * 数据层必须 PostgreSQL：agent/real_estate_db.py 缺少 DATABASE_URL 时显式报错，
    禁止静默回退 sqlite（2026-08-12 幽灵库事故的防复发机制）。
  * .env.db 键名/格式与 install.sh 生成的完全一致：
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD / DATABASE_URL。
  * scripts/backup_db.py 与 scripts/healthcheck.py 通过 PATH 直接调
    pg_dump / pg_restore / psql —— 所以后端进程的 PATH 必须含 <DataRoot>\bin。
  * DATABASE_URL 用 127.0.0.1 而不是 localhost：只监听回环 IPv4 时，localhost 可能
    先解析到 ::1 导致连接被拒（Windows 上很常见）。

  幂等：重复执行不重建数据目录、不更换口令、不动已有数据；端口被占用时自动改选
  空闲端口并同步更新 .env.db 的 DATABASE_URL。

  安全：只监听 127.0.0.1；pg_hba 仅放行 127.0.0.1/32 且强制 scram-sha-256；
  selftest 会断言「非回环地址连不上」「错误口令被拒」。

.PARAMETER Action
  setup           首次安装 + 确保在跑（幂等；桌面版每次启动都可调用）
  fetch           只下载并解出便携包（不做 initdb）
  start / stop    启动 / 停止（不安装）
  status          状态 JSON（不含口令），供桌面版展示
  selftest        逐项自检；全部 PASS 返回 0，任一 FAIL 返回 7
  print-env       打印后端进程所需环境变量行（含口令，仅供父进程消费）
  reset-password  凭据丢失时的恢复：临时 trust 回环 → 重置口令 → 复原 hba

.EXAMPLE
  pwsh -File portable-postgres.ps1 -Action setup          # 首次本机安装

.EXAMPLE
  pwsh -File portable-postgres.ps1 -Action selftest       # 自检

.EXAMPLE
  # Linux 等价验证（用系统 PG 的 bin 目录替代便携包，仅测试用）
  pwsh -File portable-postgres.ps1 -Action setup -PgBinDir /usr/lib/postgresql/16/bin `
       -DataRoot /tmp/coco-pg/pgsql -DataDir /tmp/coco-pg/data -EnvFile /tmp/coco-pg/.env.db
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('setup', 'fetch', 'start', 'stop', 'status', 'selftest', 'print-env', 'reset-password')]
    [string]$Action = 'setup',

    # 便携 PG 安装根（内含 bin/ lib/ share/），默认 <HermesHome>\pgsql
    [string]$DataRoot = '',
    # 数据目录（PGDATA），默认 <HermesHome>\pgsql-data
    [string]$DataDir = '',
    # .env.db 路径，默认 <HermesHome>\hermes-agent\.env.db
    [string]$EnvFile = '',
    # 直接用这组 PG 可执行文件（不下载/不解压）；测试与「已有 PG」场景用
    [string]$PgBinDir = '',
    # 指定端口；0 = 自动挑空闲端口
    [int]$Port = 0,
    [string]$DbName = 'hermes_agent',
    [string]$DbUser = 'hermes',
    # 本地 zip（优先于网络源）
    [string]$ZipPath = '',
    # 追加下载源（在默认源之前尝试）
    [string[]]$SourceUrls = @(),
    [switch]$SkipDownload,
    # 删除并重建数据目录（危险，数据全丢）
    [switch]$Force,
    # 不生成 COCO_ENC_KEY（交给 Coco 安装流程负责时用）
    [switch]$NoEncKey,
    [switch]$Json,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# ============================================================================
# 常量
# ============================================================================
$script:PgVersion = '16.4-1'
$script:PgMajor = 16
$script:PgZipName = "postgresql-$($script:PgVersion)-windows-x64-binaries.zip"
# 便携包默认下载源（按顺序回退）。国内分发走 COCO_PG_MIRROR（自建镜像/Release 附件）
# 或 -SourceUrls / -ZipPath，不在此处写未经验证的链接。
$script:DefaultSources = @("https://get.enterprisedb.com/postgresql/$($script:PgZipName)")
$script:BlockBegin = '# >>> coco-managed (portable-postgres.ps1) - do not edit by hand >>>'
$script:BlockEnd = '# <<< coco-managed (portable-postgres.ps1) <<<'
$script:StateName = 'coco-pg.json'
$script:ManagedEnvKeys = @('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DATABASE_URL')

# 退出码：桌面版按码给不同提示文案
$script:Exit = @{
    Ok = 0; Usage = 1; Download = 2; BinMissing = 3; InitDb = 4; Start = 5
    CredLost = 6; SelfTest = 7; Config = 8; Unexpected = 9
}

# ============================================================================
# 输出
# ============================================================================
$script:IsWin = ($env:OS -eq 'Windows_NT')
$script:SelfFails = 0

function Write-Line {
    param([string]$Text, [string]$Color = 'Gray')
    if ($Quiet -and $Color -eq 'Gray') { return }
    if ($Json) { return }
    Write-Host $Text -ForegroundColor $Color
}
function Info([string]$m) { Write-Line "· $m" }
function Ok([string]$m) { Write-Line "  [OK]   $m" 'Green' }
function Warn([string]$m) { Write-Line "  [警告] $m" 'Yellow' }
function Fail([string]$m) { Write-Line "  [失败] $m" 'Red' }
function Step([string]$m) { Write-Line ""; Write-Line "== $m ==" 'Cyan' }

function Die([string]$Message, [int]$Code = 1) {
    Fail $Message
    if ($Json) { [pscustomobject]@{ ok = $false; error = $Message; exitCode = $Code } | ConvertTo-Json -Compress | Write-Output }
    exit $Code
}

function Get-Prop($Obj, [string]$Name) {
    if ($null -eq $Obj) { return $null }
    $p = $Obj.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

# ============================================================================
# 路径 / 随机值
# ============================================================================
function Get-HermesHome {
    if ($env:HERMES_HOME) { return $env:HERMES_HOME }
    if ($script:IsWin) {
        if ($env:LOCALAPPDATA) { return (Join-Path $env:LOCALAPPDATA 'hermes') }
        return (Join-Path $env:USERPROFILE 'AppData\Local\hermes')
    }
    return (Join-Path $HOME '.hermes')
}

function Resolve-Config {
    $homeDir = Get-HermesHome
    if ($DataDir) { $script:RDataDir = $DataDir } else { $script:RDataDir = Join-Path $homeDir 'pgsql-data' }
    if ($DataRoot) { $script:RDataRoot = $DataRoot } else { $script:RDataRoot = Join-Path $homeDir 'pgsql' }
    if ($EnvFile) { $script:REnvFile = $EnvFile } else { $script:REnvFile = Join-Path (Join-Path $homeDir 'hermes-agent') '.env.db' }
    if ($PgBinDir) { $script:RBindir = $PgBinDir; $script:RBinFromPortable = $false }
    else { $script:RBindir = Join-Path $script:RDataRoot 'bin'; $script:RBinFromPortable = $true }
    $script:RState = Join-Path $script:RDataDir $script:StateName
    $script:RLog = Join-Path $script:RDataDir 'coco-postgres.log'
    if ($script:IsWin) { $script:RToolSuffix = '.exe' } else { $script:RToolSuffix = '' }
}

function Get-ToolPath([string]$Name) { return (Join-Path $script:RBindir ($Name + $script:RToolSuffix)) }

function New-RandomPassword([int]$Length = 32) {
    # 只用字母数字：避免在 URL / .env.db / 命令行里需要转义
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'.ToCharArray()
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $bytes) { [void]$sb.Append($chars[$b % $chars.Length]) }
    return $sb.ToString()
}

function New-FernetKey {
    # 32 字节随机 → urlsafe base64，与 cryptography.fernet.Fernet.generate_key() 等价
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

function Test-PortFree {
    # [CmdletBinding()] 不是装饰：没有它时，写错的具名参数（如 -Port 而形参叫 $P）
    # 会被静默收进 $args，形参保持默认值 0 —— 实测踩过，表现为「端口一律判定为空/被占」。
    [CmdletBinding()]
    param([int]$Port, [string]$Address = '127.0.0.1')
    if ($Port -le 0 -or $Port -gt 65535) { return $false }
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse($Address), $Port)
        $listener.Start()
        return $true
    } catch { return $false } finally { if ($listener) { try { $listener.Stop() } catch { } } }
}

function Get-FreeLoopbackPort {
    # 让内核分配空闲端口：绑定 0 号端口读出实际端口后释放
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse('127.0.0.1'), 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port } finally { $listener.Stop() }
}

function Test-TcpReachable {
    [CmdletBinding()]
    param([string]$Address, [int]$Port, [int]$TimeoutMs = 1500)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch { return $false } finally { try { $client.Close() } catch { } }
}

function Get-NonLoopbackIPv4 {
    $out = @()
    try {
        $hosts = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
        foreach ($h in $hosts) {
            if ($h.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not $h.ToString().StartsWith('127.')) {
                $out += $h.ToString()
            }
        }
    } catch { }
    return $out
}

function Protect-SecretFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ($script:IsWin) {
        # chmod 600 的 Windows 等价物：断开继承，只留当前用户
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($r in @($acl.Access)) { [void]$acl.RemoveAccessRule($r) }
        $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($me, 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
    } else {
        & chmod 600 $Path
    }
}

function Write-TextFile([string]$Path, [string]$Text) {
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# ============================================================================
# 便携包：下载 / 解出
# ============================================================================
function Get-PgArchive {
    [CmdletBinding()]
    param([string]$Destination)

    if ($SkipDownload) { Warn '已指定 -SkipDownload，跳过下载'; return $false }

    $sources = New-Object System.Collections.Generic.List[string]
    if ($env:COCO_PG_MIRROR) { $sources.Add(($env:COCO_PG_MIRROR.TrimEnd('/') + '/' + $script:PgZipName)) }
    foreach ($u in $SourceUrls) { $sources.Add($u) }
    foreach ($u in $script:DefaultSources) { $sources.Add($u) }

    $part = "$Destination.part"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { $curl = Get-Command curl -ErrorAction SilentlyContinue }

    $i = 0
    foreach ($url in $sources) {
        $i++
        Info "[$i/$($sources.Count)] $url"
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        if ($curl) {
            # -C - 断点续传：中断后重跑接着下
            $cargs = @('-fSL', '-C', '-', '--retry', '2', '--retry-delay', '3', '--max-time', '3600', '-o', $part, $url)
            $out = & $curl.Source @cargs 2>&1
            if ($LASTEXITCODE -ne 0) {
                $sw.Stop()
                Warn "下载失败（curl 退出码 $LASTEXITCODE）：$(($out | Out-String).Trim())；换下一个源"
                continue
            }
        } else {
            try {
                $oldPref = $ProgressPreference
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -Uri $url -OutFile $part -UseBasicParsing -TimeoutSec 3600
                $ProgressPreference = $oldPref
            } catch {
                $ProgressPreference = 'Continue'
                $sw.Stop()
                Warn "下载失败（$($_.Exception.Message)）；换下一个源"
                continue
            }
        }
        $sw.Stop()

        # 校验：存在 + 魔数 + 体积下限 + 能打开目录（防错误页/半截文件被当安装包）
        $st = Get-ZipStatus -Path $part
        if ($st -ne 'ok') {
            Warn "下载结果不可用（$st）；换下一个源"
            Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
            continue
        }
        $len = (Get-Item -LiteralPath $part -Force).Length
        Move-Item -LiteralPath $part -Destination $Destination -Force
        $mb = [math]::Round($len / 1MB, 1)
        $secs = [math]::Max($sw.Elapsed.TotalSeconds, 0.1)
        Ok "下载完成：$mb MB，用时 $([math]::Round($secs, 1)) 秒（$([math]::Round($mb / $secs, 2)) MB/s）"
        return $true
    }
    return $false
}

function Get-ZipStatus {
    <#
      便携包体检：存在 → 体积下限 → zip 魔数 → 目录能打开 → 含 bin/initdb。
      全是廉价检查（不读全文件），但能挡住三类真实事故：
        ① 下载中断留下的半截包；② 代理/网关返回的错误页（几十字节 HTML）；
        ③ 版本/架构不对的包（解出来才发现没有 initdb.exe，用户已经白等十分钟）。
      只判「文件存在」就解压的写法，会把 .NET 的
      "End of Central Directory record could not be found" 直接甩给用户（实测）。
    #>
    [CmdletBinding()]
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 'missing' }
    try { $len = (Get-Item -LiteralPath $Path -Force).Length } catch { return 'missing' }
    if ($len -lt 150MB) { return "truncated:$([math]::Round($len / 1MB, 1))MB" }
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $sig = New-Object byte[] 2
        if ($fs.Read($sig, 0, 2) -lt 2) { return 'notzip' }
    } finally { $fs.Close() }
    if ($sig[0] -ne 0x50 -or $sig[1] -ne 0x4B) { return 'notzip' }
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
        $z = [System.IO.Compression.ZipFile]::OpenRead($Path)
        try {
            if ($z.Entries.Count -lt 1000) { return "toofew:$($z.Entries.Count)" }
            foreach ($e in $z.Entries) {
                if ($e.FullName -match '(^|/)bin/initdb(\.exe)?$') { return 'ok' }
            }
            return 'noinitdb'
        } finally { $z.Dispose() }
    } catch { return 'corrupt' }
}

function Expand-PgArchive {
    <#
      只解出运行必需目录 bin / lib / share。
      实测 postgresql-16.4-1-windows-x64-binaries.zip（338.7MB / 22649 项）：
        全解 ≈ 906MB，其中 pgAdmin 4 615.9MB、symbols 155.6MB、doc 15.5MB、
        include 12.4MB、StackBuilder 0.7MB —— 运行期都不需要；
        只解 bin+lib+share = 119.7MB，安装体积缩小约 87%。
    #>
    [CmdletBinding()]
    param([string]$ZipFile, [string]$Root)

    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    if (-not (Test-Path -LiteralPath $Root)) { New-Item -ItemType Directory -Path $Root -Force | Out-Null }

    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipFile)
    try {
        $kept = New-Object System.Collections.Generic.List[object]
        foreach ($e in $zip.Entries) {
            if ($e.FullName.EndsWith('/')) { continue }
            $rel = $e.FullName
            if ($rel.StartsWith('pgsql/')) { $rel = $rel.Substring(6) }
            if ($rel.StartsWith('bin/') -or $rel.StartsWith('lib/') -or $rel.StartsWith('share/')) { $kept.Add($e) }
        }
        Info "压缩包 $($zip.Entries.Count) 项 → 只解出 $($kept.Count) 项（bin/lib/share）"
        $done = 0
        $written = 0L
        foreach ($e in $kept) {
            $rel = $e.FullName
            if ($rel.StartsWith('pgsql/')) { $rel = $rel.Substring(6) }
            $target = Join-Path $Root ($rel -replace '/', [System.IO.Path]::DirectorySeparatorChar)
            $tdir = Split-Path -Parent $target
            if ($tdir -and -not (Test-Path -LiteralPath $tdir)) { New-Item -ItemType Directory -Path $tdir -Force | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
            $written += $e.Length
            $done++
            if ($done % 2000 -eq 0) { Info "已解出 $done / $($kept.Count) 项（$([math]::Round($written / 1MB, 1)) MB）" }
        }
        Ok "解压完成：$done 项，$([math]::Round($written / 1MB, 1)) MB → $Root"
    } finally { $zip.Dispose() }
}

function Assert-PortableLayout {
    $need = @('initdb', 'pg_ctl', 'postgres', 'psql', 'pg_dump', 'pg_restore', 'pg_isready')
    $missing = @()
    foreach ($n in $need) { if (-not (Test-Path -LiteralPath (Get-ToolPath $n))) { $missing += $n } }
    if ($missing.Count -gt 0) {
        Die "PostgreSQL 可执行文件缺失（$($script:RBindir)）：$($missing -join ', ')。便携包可能没解压完整，删掉该目录后重跑。" $script:Exit.BinMissing
    }
    $ver = ((& (Get-ToolPath 'psql') '--version') 2>&1 | Out-String).Trim()
    Ok "$ver（$($script:RBindir)）"
    return $ver
}

function Invoke-Fetch {
    Step '准备便携 PostgreSQL'
    New-Item -ItemType Directory -Path $script:RDataRoot -Force | Out-Null

    if ($PgBinDir) { Ok "使用指定的 PG 目录，跳过下载/解压：$PgBinDir"; return }

    if (Test-Path -LiteralPath (Get-ToolPath 'initdb')) {
        Ok "便携包已存在，跳过下载：$($script:RDataRoot)"
        return
    }

    # -ZipPath 优先；其次是 COCO_PG_ZIP（安装包内置分发时用，完全离线）
    $localZip = $ZipPath
    if (-not $localZip -and $env:COCO_PG_ZIP) { $localZip = $env:COCO_PG_ZIP; Info "使用 COCO_PG_ZIP：$localZip" }
    if ($localZip) {
        $st = Get-ZipStatus -Path $localZip
        if ($st -ne 'ok') { Die "指定的压缩包不可用（$st）：$localZip。请重新下载后再试。" $script:Exit.Download }
        $zip = $localZip
        Ok "使用本地压缩包：$zip"
    } else {
        $zip = Join-Path ([System.IO.Path]::GetTempPath()) $script:PgZipName
        # 复用缓存前必须校验：下载中断（国内网络常见）会在 %TEMP% 留下半截文件或错误页
        $st = Get-ZipStatus -Path $zip
        if ($st -eq 'ok') {
            Info "复用已下载的压缩包：$zip（要重新下载请先删除它）"
        } elseif ($st -ne 'missing') {
            Warn "缓存压缩包不可用（$st），删除后重新下载：$zip"
            Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $zip) {
                # 删不掉（被占用 / 权限不足）也不能拿它去解压：换一个新的缓存文件名
                $zip = Join-Path ([System.IO.Path]::GetTempPath()) ("postgresql-$($script:PgVersion)-windows-x64-" + ([Guid]::NewGuid().ToString('N').Substring(0, 8)) + ".zip")
                Warn "原缓存文件删不掉，改用新文件下载：$zip"
            }
        }
        if (-not (Test-Path -LiteralPath $zip)) {
            $ok_ = Get-PgArchive -Destination $zip
            if (-not $ok_) {
                $tried = $script:DefaultSources.Count + $SourceUrls.Count
                if ($env:COCO_PG_MIRROR) { $tried++ }
                Die "便携 PostgreSQL 下载失败（已尝试 $tried 个源）。`n排查：`n  1) 网络能否访问 get.enterprisedb.com；`n  2) 用 COCO_PG_MIRROR 指向自建镜像（或 Release 附件）；`n  3) 或手动下载后用 -ZipPath 指定。" $script:Exit.Download
            }
        }
    }
    Expand-PgArchive -ZipFile $zip -Root $script:RDataRoot
}

# ============================================================================
# 状态文件 / .env.db
# ============================================================================
function Read-State {
    if (Test-Path -LiteralPath $script:RState) {
        try { return (Get-Content -LiteralPath $script:RState -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
    }
    return $null
}

function Write-State {
    param([hashtable]$Values)
    $obj = [ordered]@{}
    $old = Read-State
    if ($old) { foreach ($p in $old.PSObject.Properties) { $obj[$p.Name] = $p.Value } }
    foreach ($k in $Values.Keys) { $obj[$k] = $Values[$k] }
    if (-not $obj.Contains('schemaVersion')) { $obj['schemaVersion'] = 1 }
    $obj['updatedAt'] = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    if (-not $obj.Contains('createdAt')) { $obj['createdAt'] = $obj['updatedAt'] }
    Write-TextFile $script:RState ($obj | ConvertTo-Json -Depth 5)
}

function Read-EnvMap {
    $map = [ordered]@{}
    if (-not (Test-Path -LiteralPath $script:REnvFile)) { return $map }
    foreach ($line in [System.IO.File]::ReadAllLines($script:REnvFile)) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $eq = $t.IndexOf('=')
        if ($eq -lt 1) { continue }
        $map[$t.Substring(0, $eq).Trim()] = $t.Substring($eq + 1)
    }
    return $map
}

function Write-EnvMap {
    <#
      只改我们管理的 6 个键，其余行（COCO_ENC_KEY / COCO_ENABLE_CRON / 模型密钥…）
      原样保留 —— 否则每次启动都会把经纪人的自定义配置抹掉。
    #>
    [CmdletBinding()]
    param([hashtable]$Values)

    $lines = @()
    $nl = [Environment]::NewLine
    if (Test-Path -LiteralPath $script:REnvFile) {
        $raw = [System.IO.File]::ReadAllText($script:REnvFile)
        if ($raw.Contains("`r`n")) { $nl = "`r`n" } else { $nl = "`n" }
        $lines = @([System.IO.File]::ReadAllLines($script:REnvFile))
    } else {
        $lines = @('# 数据库配置（由 apps/desktop/scripts/portable-postgres.ps1 生成/维护）')
    }

    $seen = @{}
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        $t = $line.Trim()
        $eq = $t.IndexOf('=')
        if (-not $t.StartsWith('#') -and $eq -gt 0) {
            $key = $t.Substring(0, $eq).Trim()
            if ($Values.ContainsKey($key)) {
                $out.Add("$key=$($Values[$key])")
                $seen[$key] = $true
                continue
            }
        }
        $out.Add($line)
    }
    foreach ($k in $Values.Keys) {
        if (-not $seen.ContainsKey($k)) { $out.Add("$k=$($Values[$k])") }
    }
    Write-TextFile $script:REnvFile ($out -join $nl)
    Protect-SecretFile $script:REnvFile
}

function Get-ManagedEnvValues {
    param([int]$PgPort, [string]$Password)
    return @{
        DB_HOST      = '127.0.0.1'
        DB_PORT      = "$PgPort"
        DB_NAME      = $DbName
        DB_USER      = $DbUser
        DB_PASSWORD  = $Password
        DATABASE_URL = "postgresql://${DbUser}:${Password}@127.0.0.1:${PgPort}/${DbName}"
    }
}

# ============================================================================
# postgresql.conf / pg_hba.conf（托管块，幂等）
# 两个文件里的注释一律用 ASCII：PG 的 conf 解析对编码敏感，少一个变量。
# ============================================================================
function Get-ConfValue {
    [CmdletBinding()]
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $t = $line.Trim()
        if ($t.StartsWith('#') -or -not $t) { continue }
        if ($t -match ('^\s*' + [regex]::Escape($Key) + '\s*=\s*(.+?)\s*$')) { return $Matches[1].Trim().Trim("'", '"') }
    }
    return $null
}

function Get-ConfBlockCount {
    [CmdletBinding()]
    param([string]$Path, [string]$Key)
    $count = 0
    $inBlock = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $t = $line.Trim()
        if ($t -eq $script:BlockBegin) { $inBlock = $true; continue }
        if ($t -eq $script:BlockEnd) { $inBlock = $false; continue }
        if (-not $inBlock -and $t -and -not $t.StartsWith('#') -and $t -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) { $count++ }
    }
    return $count
}

function Set-ManagedConfBlock {
    [CmdletBinding()]
    param([string]$Path, [int]$PgPort)

    $block = @(
        $script:BlockBegin
        "listen_addresses = '127.0.0.1'"
        "port = $PgPort"
        # 必须写死：不设时 PG 会去系统默认 socket 目录（Linux 上是 /var/run/postgresql）
        # 建锁文件 —— 普通用户没有写权限，服务直接起不来（实测 FATAL: could not create
        # lock file ... Permission denied）。置空 = 完全不用 unix socket，只走 TCP 回环，
        # 且集群不会往数据目录之外的任何地方写文件。
        "unix_socket_directories = ''"
        'password_encryption = scram-sha-256'
        'shared_buffers = 128MB'
        'max_connections = 50'
        'logging_collector = off'
        "unix_socket_directories = ''"
        "log_line_prefix = '%m [%p] '"
        "log_timezone = 'Asia/Shanghai'"
        "timezone = 'Asia/Shanghai'"
        $script:BlockEnd
    ) -join [Environment]::NewLine

    $text = [System.IO.File]::ReadAllText($Path)
    $re = [regex]::Escape($script:BlockBegin) + '[\s\S]*?' + [regex]::Escape($script:BlockEnd)
    if ([regex]::IsMatch($text, $re)) {
        $text = [regex]::Replace($text, $re, [System.Text.RegularExpressions.MatchEvaluator] { param($m) $block })
    } else {
        $text = $text.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block + [Environment]::NewLine
    }
    Write-TextFile $Path $text
}

function Set-PgHba {
    [CmdletBinding()]
    param([string]$Path)
    $content = @(
        '# Generated by apps/desktop/scripts/portable-postgres.ps1'
        '# Loopback only + scram-sha-256 password auth. No trust, no LAN, no public.',
        '# TYPE  DATABASE  USER  ADDRESS       METHOD'
        'local   all       all                 scram-sha-256'
        'host    all       all   127.0.0.1/32  scram-sha-256'
        ''
    ) -join [Environment]::NewLine
    Write-TextFile $Path $content
}

# ============================================================================
# 生命周期
# ============================================================================
function Get-PgStatus {
    $ctl = Get-ToolPath 'pg_ctl'
    if (-not (Test-Path -LiteralPath $ctl)) { return 'missing' }
    if (-not (Test-Path -LiteralPath (Join-Path $script:RDataDir 'PG_VERSION'))) { return 'nodata' }
    & $ctl -D $script:RDataDir status *> $null
    if ($LASTEXITCODE -eq 0) { return 'running' }
    return 'stopped'
}

function Invoke-InitDb {
    [CmdletBinding()]
    param([string]$Password)
    $pwfile = Join-Path ([System.IO.Path]::GetTempPath()) ('coco-pg-pw-' + [Guid]::NewGuid().ToString('N'))
    try {
        Write-TextFile $pwfile $Password
        Protect-SecretFile $pwfile
        Info "initdb → $($script:RDataDir)（UTF8 / locale C / scram-sha-256，跨机可重现）"
        # Windows 上 initdb/pg_ctl 会用受限令牌启动 postgres，管理员账号也不需要 UAC 提权
        $out = & (Get-ToolPath 'initdb') -D $script:RDataDir -U $DbUser -E UTF8 --locale=C -A scram-sha-256 "--pwfile=$pwfile" 2>&1
        if ($LASTEXITCODE -ne 0) { Die "initdb 失败（退出码 $LASTEXITCODE）：`n$(($out | Out-String).Trim())" $script:Exit.InitDb }
        Ok '数据目录初始化完成'
    } finally {
        if (Test-Path -LiteralPath $pwfile) { Remove-Item -LiteralPath $pwfile -Force }
    }
}

function Start-PgServer {
    $status = Get-PgStatus
    if ($status -eq 'running') { Ok 'PostgreSQL 已在运行'; return $true }
    if ($status -eq 'nodata') { Die "数据目录未初始化：$($script:RDataDir)" $script:Exit.Start }
    if ($status -eq 'missing') { Die "找不到 pg_ctl（$($script:RBindir)）" $script:Exit.BinMissing }

    Info "启动 PostgreSQL（PGDATA=$($script:RDataDir)，日志 $($script:RLog)）"
    $out = & (Get-ToolPath 'pg_ctl') -D $script:RDataDir -l $script:RLog -w -t 60 start 2>&1
    if ($LASTEXITCODE -ne 0) {
        $tail = ''
        if (Test-Path -LiteralPath $script:RLog) {
            $tail = (@([System.IO.File]::ReadAllLines($script:RLog)) | Select-Object -Last 15) -join [Environment]::NewLine
        }
        Die "PostgreSQL 启动失败（退出码 $LASTEXITCODE）：`n$(($out | Out-String).Trim())`n日志尾部：`n$tail" $script:Exit.Start
    }
    Ok 'PostgreSQL 已启动'
    return $true
}

function Stop-PgServer {
    $status = Get-PgStatus
    if ($status -ne 'running') { Ok 'PostgreSQL 未在运行，无需停止'; return }
    $out = & (Get-ToolPath 'pg_ctl') -D $script:RDataDir -m fast -w -t 60 stop 2>&1
    if ($LASTEXITCODE -ne 0) { Warn "停止失败：$(($out | Out-String).Trim())" } else { Ok 'PostgreSQL 已停止' }
}

function Invoke-Psql {
    [CmdletBinding()]
    param([string]$Sql, [string]$Password, [int]$PgPort)
    $env:PGPASSWORD = $Password
    try {
        $a = @('-h', '127.0.0.1', '-p', "$PgPort", '-U', $DbUser, '-d', 'postgres', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-c', $Sql)
        $out = & (Get-ToolPath 'psql') @a 2>&1
        return [pscustomobject]@{ Code = $LASTEXITCODE; Out = ($out | Out-String).Trim() }
    } finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
}

function Ensure-Database {
    [CmdletBinding()]
    param([string]$Password, [int]$PgPort)
    $r = Invoke-Psql -Sql "SELECT 1 FROM pg_database WHERE datname = '$DbName'" -Password $Password -PgPort $PgPort
    if ($r.Code -ne 0) { Die "连接数据库失败：`n$($r.Out)" $script:Exit.Start }
    if ($r.Out.Trim() -eq '1') { Ok "业务库已存在：$DbName"; return }
    $r2 = Invoke-Psql -Sql "CREATE DATABASE `"$DbName`"" -Password $Password -PgPort $PgPort
    if ($r2.Code -ne 0) { Die "创建业务库失败：`n$($r2.Out)" $script:Exit.Start }
    Ok "业务库已创建：$DbName"
}

# ============================================================================
# setup：幂等主流程
# ============================================================================
function Invoke-Setup {
    Step 'Coco 本机模式：便携 PostgreSQL'
    Info "安装根   $($script:RDataRoot)"
    Info "数据目录 $($script:RDataDir)"
    Info "配置     $($script:REnvFile)"

    Invoke-Fetch
    Assert-PortableLayout | Out-Null

    $envMap = Read-EnvMap
    $state = Read-State
    $hasData = Test-Path -LiteralPath (Join-Path $script:RDataDir 'PG_VERSION')
    $pwSource = 'reused'

    # ---- 1. 口令：已存在就绝不重生成（否则 .env.db 与库内角色口令不一致，直接锁死）----
    $password = $null
    if ($hasData) {
        $password = $envMap['DB_PASSWORD']
        if (-not $password) { $password = Get-Prop $state 'password' }
        if (-not $password) {
            Die ("数据目录已存在（$($script:RDataDir)）但找不到数据库口令。`n恢复方式：`n" +
                 "  1) 找回 .env.db（含 DB_PASSWORD / DATABASE_URL）放回 $($script:REnvFile)；`n" +
                 "  2) 或执行 -Action reset-password 重设口令（数据不丢）；`n" +
                 "  3) 数据可以丢时才用 -Force 重建。") $script:Exit.CredLost
        }
        Ok '复用已有数据目录与口令（未重新初始化）'
    } else {
        if ($Force -and (Test-Path -LiteralPath $script:RDataDir)) {
            Warn "-Force：删除已存在的数据目录 $($script:RDataDir)"
            Remove-Item -LiteralPath $script:RDataDir -Recurse -Force
        }
        $password = New-RandomPassword
        $pwSource = 'generated'
        Invoke-InitDb -Password $password
    }

    # ---- 2. 端口：服务在跑就沿用配置里的端口；没跑才判空并可能重挑 ----
    $confPath = Join-Path $script:RDataDir 'postgresql.conf'
    $prevConfPort = Get-ConfValue -Path $confPath -Key 'port'
    $status = Get-PgStatus
    $pgPort = 0
    $chosen = $false
    $portNote = ''
    if ($Port -gt 0) {
        # 显式指定：端口空着、或者本来就是我们自己在监听，都算可用
        if (Test-PortFree $Port -or ($status -eq 'running' -and $prevConfPort -eq "$Port")) {
            $pgPort = $Port; $chosen = $true; $portNote = '指定端口'
        } else {
            $explicitOccupied = $true
            Warn "指定端口 $Port 已被其它进程占用，改为自动选择"
        }
    }
    if (-not $chosen -and $status -eq 'running' -and $prevConfPort) {
        # 服务已经在跑：端口由我们自己的实例持有，绝不能再判空重挑（否则每次启动都换端口）
        $pgPort = [int]$prevConfPort; $chosen = $true; $portNote = '沿用（服务运行中）'
    }
    if (-not $chosen) {
        $candidates = @()
        if ($prevConfPort) { $candidates += [int]$prevConfPort }
        $stPort = Get-Prop $state 'port'
        if ($stPort) { $candidates += [int]$stPort }
        if ($envMap['DB_PORT']) { $candidates += [int]$envMap['DB_PORT'] }
        foreach ($c in ($candidates | Select-Object -Unique)) {
            if (Test-PortFree $c) { $pgPort = $c; $chosen = $true; $portNote = '沿用' + $(if ($explicitOccupied) { '（改用旧端口）' } else { '' }); break }
        }
    }
    if (-not $chosen) {
        $pgPort = Get-FreeLoopbackPort
        if (-not (Test-PortFree $pgPort)) { $pgPort = Get-FreeLoopbackPort }   # 释放到启用之间的极小窗口，复检一次
        $portNote = '自动挑选的空闲端口'
    }
    if ($envMap['DB_PORT'] -eq "$pgPort") { $portNote = '沿用' }
    Ok "端口 $pgPort（$portNote）"

    # ---- 3. 配置：只监听回环 ----
    Set-ManagedConfBlock -Path $confPath -PgPort $pgPort
    Set-PgHba -Path (Join-Path $script:RDataDir 'pg_hba.conf')
    $listen = Get-ConfValue -Path $confPath -Key 'listen_addresses'
    if ($listen -ne '127.0.0.1') { Die "listen_addresses 不是 127.0.0.1（实际：$listen）" $script:Exit.Config }
    if ((Get-ConfBlockCount -Path $confPath -Key 'listen_addresses') -gt 0) {
        Die "postgresql.conf 的托管块之外还有生效的 listen_addresses，请清理后再跑（避免监听被放开）" $script:Exit.Config
    }
    Ok "只监听 127.0.0.1:$pgPort（pg_hba 仅回环 + scram-sha-256）"

    # ---- 4. 起服务 + 建库（端口变了就要重启，光改 conf 对已在跑的实例无效）----
    if ($status -eq 'running' -and $prevConfPort -and [int]$prevConfPort -ne $pgPort) {
        Warn "配置端口从 $prevConfPort 变为 $pgPort，重启实例生效"
        Stop-PgServer
    }
    Start-PgServer | Out-Null
    Ensure-Database -Password $password -PgPort $pgPort

    # ---- 5. .env.db（格式与 install.sh 一致；其余键原样保留）----
    Write-EnvMap -Values (Get-ManagedEnvValues -PgPort $pgPort -Password $password)
    Ok "已写入 $($script:REnvFile)（DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD/DATABASE_URL）"

    if (-not $NoEncKey) {
        if (-not (Read-EnvMap)['COCO_ENC_KEY']) {
            Write-EnvMap -Values @{ COCO_ENC_KEY = (New-FernetKey) }
            Ok '已生成 COCO_ENC_KEY（客户手机号/微信加密用，必须随备份一起保存）'
        } else { Ok 'COCO_ENC_KEY 已存在，保持不变' }
    }

    # ---- 6. 建业务表（与 install.sh 的 setup_tables 同一入口）----
    $repo = Split-Path -Parent $script:REnvFile
    $py = $null
    foreach ($cand in @((Join-Path $repo 'venv\Scripts\python.exe'), (Join-Path $repo 'venv\bin\python'), (Join-Path $repo 'venv\bin\python3'))) {
        if (Test-Path -LiteralPath $cand) { $py = $cand; break }
    }
    if ($py) {
        Info "初始化数据表（$py -c init_real_estate_db）"
        $envVars = Get-ManagedEnvValues -PgPort $pgPort -Password $password
        $oldPath = $env:PATH
        $env:DATABASE_URL = $envVars['DATABASE_URL']
        $env:PATH = "$($script:RBindir)$([System.IO.Path]::PathSeparator)$oldPath"
        try {
            $out = & $py -c "from agent.real_estate_db import init_real_estate_db; init_real_estate_db(); print('TABLES_OK')" 2>&1
            if ($LASTEXITCODE -eq 0 -and ($out | Out-String).Contains('TABLES_OK')) { Ok '数据表已就绪' }
            else { Warn "建表未成功（后端首次工具调用会重试）：$(($out | Out-String).Trim())" }
        } catch { Warn "建表异常：$($_.Exception.Message)" }
        finally {
            $env:PATH = $oldPath
            Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
        }
    } else {
        Warn "未找到后端 venv（$repo），跳过建表；后端首次工具调用会自动建表"
    }

    $stateSource = 'portable-zip'
    if ($PgBinDir) { $stateSource = 'system-bin-dir' }
    Write-State -Values @{
        pgMajor = $script:PgMajor; pgVersion = $script:PgVersion; dataDir = $script:RDataDir
        binDir = $script:RBindir; port = $pgPort; dbName = $DbName; dbUser = $DbUser
        envFile = $script:REnvFile; source = $stateSource; passwordSource = $pwSource
    }

    # ---- 7. 收尾自检 ----
    $selfOk = Invoke-SelfTest -Brief
    if (-not $selfOk) { Die '自检未全部通过（详见上面列表）' $script:Exit.SelfTest }

    Step '完成'
    Ok "本机 PostgreSQL 就绪：127.0.0.1:$pgPort/$DbName（用户 $DbUser）"
    Info "后端进程 PATH 需要包含：$($script:RBindir)（备份/体检脚本要 pg_dump、pg_restore、psql）"
    if ($Json) {
        [pscustomobject]@{
            ok = $true; port = $pgPort; dbName = $DbName; dbUser = $DbUser
            dataDir = $script:RDataDir; binDir = $script:RBindir; envFile = $script:REnvFile
            databaseUrl = (Get-ManagedEnvValues -PgPort $pgPort -Password $password)['DATABASE_URL']
        } | ConvertTo-Json -Compress | Write-Output
    }
}

# ============================================================================
# 自检
# ============================================================================
function Invoke-SelfTest {
    param([switch]$Brief)

    $script:SelfFails = 0
    $script:SelfPass = 0
    if (-not $Brief) { Step '自检' }

    function Check([string]$Name, [scriptblock]$Body) {
        try {
            $r = & $Body
            if ($null -eq $r -or $r -eq $true) { Ok $Name; $script:SelfPass++ }
            elseif ($r -is [string]) {
                if ($r.StartsWith('SKIP:')) { Warn "SKIP $Name（$($r.Substring(5))）" }
                else { Ok "$Name — $r"; $script:SelfPass++ }
            } else { Fail $Name; $script:SelfFails++ }
        } catch { Fail "$Name（$($_.Exception.Message)）"; $script:SelfFails++ }
    }

    $conf = Join-Path $script:RDataDir 'postgresql.conf'
    $hba = Join-Path $script:RDataDir 'pg_hba.conf'
    $envMap = Read-EnvMap
    $state = Read-State
    $pgPort = 0
    if ($envMap['DB_PORT']) { $pgPort = [int]$envMap['DB_PORT'] }
    elseif (Get-Prop $state 'port') { $pgPort = [int](Get-Prop $state 'port') }

    Check '可执行文件齐全（initdb/pg_ctl/postgres/psql/pg_dump/pg_restore）' {
        foreach ($n in @('initdb', 'pg_ctl', 'postgres', 'psql', 'pg_dump', 'pg_restore')) {
            if (-not (Test-Path -LiteralPath (Get-ToolPath $n))) { throw "缺少 $n" }
        }
        $true
    }
    Check '数据目录已初始化（PG_VERSION）' {
        $v = Join-Path $script:RDataDir 'PG_VERSION'
        if (-not (Test-Path -LiteralPath $v)) { throw "缺 $v" }
        $major = ([System.IO.File]::ReadAllText($v)).Trim()
        if ($script:RBinFromPortable -and $major -ne "$($script:PgMajor)") { throw "主版本 $major ≠ 预期 $($script:PgMajor)" }
        "主版本 $major"
    }
    Check '只监听 127.0.0.1（且无块外覆盖）' {
        $v = Get-ConfValue -Path $conf -Key 'listen_addresses'
        if ($v -ne '127.0.0.1') { throw "listen_addresses = $v" }
        $c = Get-ConfBlockCount -Path $conf -Key 'listen_addresses'
        if ($c -gt 0) { throw "托管块之外还有 $c 处生效的 listen_addresses" }
        'listen_addresses = 127.0.0.1'
    }
    Check '端口 / 状态文件 / DATABASE_URL 三处自洽' {
        $c = Get-ConfValue -Path $conf -Key 'port'
        if (-not $c) { throw 'postgresql.conf 缺少 port' }
        if (-not $pgPort) { throw '.env.db 缺少 DB_PORT' }
        if ([int]$c -ne $pgPort) { throw "conf=$c 与 env=$pgPort 不一致" }
        $url = $envMap['DATABASE_URL']
        if (-not $url) { throw '.env.db 缺少 DATABASE_URL' }
        if ($url -notmatch '^postgres(ql)?://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)$') { throw "DATABASE_URL 格式不符：$url" }
        if ([int]$Matches[5] -ne $pgPort) { throw "URL 端口 $($Matches[5]) ≠ $pgPort" }
        if ($Matches[4] -ne '127.0.0.1') { throw "URL 主机 $($Matches[4]) ≠ 127.0.0.1" }
        if ($Matches[6] -ne $DbName) { throw "URL 库名 $($Matches[6]) ≠ $DbName" }
        if ($Matches[2] -ne $DbUser) { throw "URL 用户 $($Matches[2]) ≠ $DbUser" }
        "port=$pgPort，URL 可解析且自洽"
    }
    Check 'pg_hba 仅回环 + scram-sha-256' {
        $rows = 0
        $bad = @()
        foreach ($line in [System.IO.File]::ReadAllLines($hba)) {
            $t = $line.Trim()
            if (-not $t -or $t.StartsWith('#')) { continue }
            $rows++
            if ($t -match '0\.0\.0\.0/0|::/0|\btrust\b|^\s*(host|hostssl)\s+\S+\s+\S+\s+all\s') { $bad += $t }
            elseif ($t -match '^(host|hostssl)' -and $t -notmatch '127\.0\.0\.1/32|::1/128') { $bad += $t }
            elseif ($t -match '^(host|hostssl)' -and $t -notmatch 'scram-sha-256') { $bad += $t }
        }
        if ($rows -eq 0) { throw 'pg_hba.conf 没有任何放行规则' }
        if ($bad.Count -gt 0) { throw "存在不安全规则：$($bad -join ' | ')" }
        "$rows 条规则全部是回环 + scram-sha-256"
    }
    Check '服务在运行且 127.0.0.1 可连' {
        if ((Get-PgStatus) -ne 'running') { throw 'pg_ctl status 显示未运行' }
        if (-not (Test-TcpReachable -Address '127.0.0.1' -Port $pgPort)) { throw "127.0.0.1:$pgPort 连不上" }
        $true
    }
    Check '非回环地址连不上（只监听回环的实证）' {
        $ips = @(Get-NonLoopbackIPv4)
        if (-not $ips -or $ips.Count -eq 0) { return 'SKIP:本机没有非回环 IPv4 地址' }
        $reachable = @()
        foreach ($ip in $ips) { if (Test-TcpReachable -Address $ip -Port $pgPort -TimeoutMs 1200) { $reachable += $ip } }
        if ($reachable.Count -gt 0) { throw "以下非回环地址竟能连上：$($reachable -join ', ')" }
        "已试 $($ips.Count) 个非回环地址，均连接失败"
    }
    Check '口令认证生效（正确口令可连 / 错误口令被拒）' {
        $pw = $envMap['DB_PASSWORD']
        if (-not $pw) { throw '.env.db 缺少 DB_PASSWORD' }
        $r = Invoke-Psql -Sql 'SELECT 1' -Password $pw -PgPort $pgPort
        if ($r.Code -ne 0 -or $r.Out -ne '1') { throw "正确口令连接失败：$($r.Out)" }
        $bad = Invoke-Psql -Sql 'SELECT 1' -Password 'definitely-wrong-password' -PgPort $pgPort
        if ($bad.Code -eq 0) { throw '错误口令竟然连接成功（认证没生效）' }
        $true
    }
    Check '业务库存在' {
        $r = Invoke-Psql -Sql "SELECT 1 FROM pg_database WHERE datname = '$DbName'" -Password $envMap['DB_PASSWORD'] -PgPort $pgPort
        if ($r.Code -ne 0 -or $r.Out -ne '1') { throw "库 $DbName 不存在" }
        $true
    }
    Check '.env.db 权限仅当前用户' {
        if ($script:IsWin) {
            $acl = Get-Acl -LiteralPath $script:REnvFile
            if (@($acl.Access).Count -gt 3) { throw "ACL 条目偏多（$(@($acl.Access).Count)），可能仍继承父目录权限" }
            'ACL 已断开继承，仅当前用户'
        } else {
            $mode = (Get-Item -LiteralPath $script:REnvFile -Force).UnixFileMode
            if ($null -eq $mode) { throw '无法读取权限' }
            $str = [Convert]::ToString([int]$mode, 8)
            if ($str -ne '600') { throw "权限 $str（期望 600）" }
            '600'
        }
    }
    Check '备份工具链可用（pg_dump 能连通业务库）' {
        $env:PGPASSWORD = $envMap['DB_PASSWORD']
        try {
            $out = & (Get-ToolPath 'pg_dump') -h 127.0.0.1 -p $pgPort -U $DbUser -d $DbName --schema-only 2>&1
            if ($LASTEXITCODE -ne 0) { throw "pg_dump 失败：$(($out | Out-String).Trim())" }
        } finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
        $true
    }

    if ($script:SelfFails -gt 0) { Fail "$($script:SelfFails) 项未通过（通过 $($script:SelfPass) 项）"; return $false }
    Ok "$($script:SelfPass) 项全部通过"
    return $true
}

# ============================================================================
# reset-password：凭据丢失时的恢复路径（数据不动）
# ============================================================================
function Invoke-ResetPassword {
    Step '重置本机 PostgreSQL 口令'
    Assert-PortableLayout | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $script:RDataDir 'PG_VERSION'))) {
        Die "数据目录未初始化：$($script:RDataDir)" $script:Exit.InitDb
    }
    $confPath = Join-Path $script:RDataDir 'postgresql.conf'
    $hbaPath = Join-Path $script:RDataDir 'pg_hba.conf'
    $pgPort = Get-ConfValue -Path $confPath -Key 'port'
    if (-not $pgPort) { Die 'postgresql.conf 里找不到 port' $script:Exit.Config }
    $pgPort = [int]$pgPort

    Warn '过程中会有几秒「仅本机回环、免密码」窗口，完成后立即复原 hba'
    Stop-PgServer

    $hbaBackup = "$hbaPath.coco-bak"
    [System.IO.File]::WriteAllText($hbaBackup, [System.IO.File]::ReadAllText($hbaPath), (New-Object System.Text.UTF8Encoding($false)))
    Write-TextFile $hbaPath (@('local all all trust', 'host all all 127.0.0.1/32 trust', '') -join [Environment]::NewLine)
    $newPw = $null
    try {
        Start-PgServer | Out-Null
        $newPw = New-RandomPassword
        $r = Invoke-Psql -Sql "ALTER USER `"$DbUser`" WITH PASSWORD '$newPw'" -Password '' -PgPort $pgPort
        if ($r.Code -ne 0) { Die "重置口令失败：$($r.Out)" $script:Exit.Config }
        Ok '口令已重置'
    } finally {
        # 无论成败都复原 hba，绝不把免密状态留在磁盘上
        Copy-Item -LiteralPath $hbaBackup -Destination $hbaPath -Force
        Remove-Item -LiteralPath $hbaBackup -Force -ErrorAction SilentlyContinue
        Stop-PgServer
        Start-PgServer | Out-Null
    }
    if (-not $newPw) { Die '口令重置未完成' $script:Exit.Config }

    Write-EnvMap -Values (Get-ManagedEnvValues -PgPort $pgPort -Password $newPw)
    Ok "新口令已写回 $($script:REnvFile)"
    $ok_ = Invoke-SelfTest -Brief
    if (-not $ok_) { Die '重置后自检未通过' $script:Exit.SelfTest }
    Ok '恢复完成（数据未受影响）'
}

# ============================================================================
# 入口
# ============================================================================
Resolve-Config

try {
switch ($Action) {
    'setup' { Invoke-Setup }
    'fetch' {
        Invoke-Fetch
        if (-not $PgBinDir) { Assert-PortableLayout | Out-Null } else { Ok "使用指定 bin 目录：$PgBinDir" }
    }
    'start' { Assert-PortableLayout | Out-Null; Start-PgServer | Out-Null }
    'stop' { Stop-PgServer }
    'selftest' {
        $r = Invoke-SelfTest
        if (-not $r) { exit $script:Exit.SelfTest }
        if ($Json) { [pscustomobject]@{ ok = $true; action = 'selftest' } | ConvertTo-Json -Compress | Write-Output }
    }
    'status' {
        $st = Get-PgStatus
        $envMap = Read-EnvMap
        $state = Read-State
        $portOut = 0
        if ($envMap['DB_PORT']) { $portOut = [int]$envMap['DB_PORT'] }
        elseif (Get-Prop $state 'port') { $portOut = [int](Get-Prop $state 'port') }
        $listen = $null
        $confPath = Join-Path $script:RDataDir 'postgresql.conf'
        if (Test-Path -LiteralPath $confPath) { $listen = Get-ConfValue -Path $confPath -Key 'listen_addresses' }
        $obj = [pscustomobject]@{
            ok = ($st -eq 'running'); state = $st; port = $portOut
            dataDir = $script:RDataDir; binDir = $script:RBindir; envFile = $script:REnvFile
            dbName = $DbName; dbUser = $DbUser; listen = $listen
        }
        if ($Json) { $obj | ConvertTo-Json -Compress } else { $obj | Format-List }
    }
    'print-env' {
        $envMap = Read-EnvMap
        if (-not $envMap['DATABASE_URL']) { Die '尚未配置（.env.db 无 DATABASE_URL），先跑 -Action setup' $script:Exit.CredLost }
        foreach ($k in $script:ManagedEnvKeys) { if ($envMap[$k]) { "$k=$($envMap[$k])" } }
        "PATH_PREPEND=$($script:RBindir)"
    }
    'reset-password' { Invoke-ResetPassword }
}
} catch {
    Die ("未预期的错误（$($_.Exception.GetType().Name)）：$($_.Exception.Message)`n" +
         "位置：$($_.InvocationInfo.PositionMessage)`n" +
         "请把以上信息发给技术顾问，或删掉 $($script:RDataRoot) 后重跑。") $script:Exit.Unexpected
}
exit $script:Exit.Ok
