/**
 * 本机模式的便携 PostgreSQL 接线。
 *
 * COCO-PATCH（Coco 房产智能体）：
 * 官方桌面版在本机跑后端时不需要数据库（会话/记忆走自带存储），所以官方代码里没有
 * 「本机数据库」这一环。Coco 的数据层强制 PostgreSQL —— `agent/real_estate_db.py`
 * 的 `init_real_estate_db()` 在缺少 `DATABASE_URL` 时直接抛错拒绝初始化（禁止静默
 * 回退 sqlite，那是 2026-08-12 幽灵库事故的根因）。所以「本机模式」必须自带一个
 * 数据库进程：由 `apps/desktop/scripts/portable-postgres.ps1` 负责下载、初始化、
 * 以随机端口/口令只监听回环地跑起来，并把连接串写进 `.env.db`。
 *
 * 这个模块只做两件事（都是纯函数，另有 fs/spawn 的薄封装）：
 *   1. 把 `<HermesHome>/pgsql/bin` 提供给后端 PATH（backup_db.py / healthcheck.py
 *      调的是裸命令名 `pg_dump` / `pg_restore` / `psql`，只能靠 PATH 找）；
 *   2. 从 `<InstallDir>/.env.db` 读出权威连接串并注入后端环境（端口会因冲突漂移，
 *      唯一权威是文件，不要在 Electron 侧自己拼）。
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

function pathModuleForPlatform(platform = process.platform) {
  return platform === 'win32' ? path.win32 : path.posix
}

/** 脚本相对仓库根的位置（随 apps/desktop 一起分发）。 */
const SCRIPT_RELATIVE_PATH = path.join('apps', 'desktop', 'scripts', 'portable-postgres.ps1')

/** 引导脚本的退出码 → 用户可读提示（与 docs/DESKTOP_LOCAL_PG.md 的分流表一致）。 */
const SETUP_EXIT_MESSAGES = Object.freeze({
  1: '便携数据库脚本的调用参数不正确（内部错误，请把日志发给技术顾问）。',
  2: '本机数据库组件下载失败。请检查网络后重试；长期失败可改用「连接服务器」模式。',
  3: '本机数据库组件不完整，请点「修复安装」重新补齐。',
  4: '本机数据库初始化失败。请点「打开日志」把最后几行发给我们。',
  5: '本机数据库无法启动。请点「打开日志」把最后几行发给我们。',
  6: '检测到已有数据库，但凭据文件缺失。请从备份恢复 .env.db，或点「重置口令」（数据不会丢）。',
  7: '本机数据库自检未通过。为避免数据错乱，已停止启动机器人。',
  8: '本机数据库配置有误（监听地址或端口被改动过），请点「修复安装」。',
  9: '本机数据库组件出现未预期的错误。请点「打开日志」把最后几行发给我们。'
})

function portablePostgresRoot(hermesHome: any, { pathModule = path }: any = {}) {
  return hermesHome ? pathModule.join(String(hermesHome), 'pgsql') : null
}

/**
 * 便携 PostgreSQL 的可执行文件目录（内含 psql/pg_dump/pg_restore/pg_ctl）。
 * 与 `hermesManagedNodePathEntries` 同一套路：hermesHome 为空时返回空数组，
 * 让调用方原样拼 PATH。
 */
function hermesManagedPostgresPathEntries(hermesHome: any, { platform = process.platform, pathModule = path }: any = {}) {
  const root = portablePostgresRoot(hermesHome, { pathModule })

  return root ? [pathModule.join(root, 'bin')] : []
}

function portablePostgresScriptPath(repoRoot: any) {
  return repoRoot ? path.join(String(repoRoot), SCRIPT_RELATIVE_PATH) : null
}

/** 解析 dotenv 风格文本：忽略空行与注释，去掉包裹引号，允许 `export` 前缀。 */
function parseEnvText(text: any) {
  const out: Record<string, string> = {}

  for (const rawLine of String(text ?? '').split(/\r?\n/)) {
    const line = rawLine.trim()

    if (!line || line.startsWith('#')) {
      continue
    }

    const withoutExport = line.startsWith('export ') ? line.slice(7).trim() : line
    const eq = withoutExport.indexOf('=')

    if (eq <= 0) {
      continue
    }

    const key = withoutExport.slice(0, eq).trim()
    let value = withoutExport.slice(eq + 1).trim()

    if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) {
      value = value.slice(1, -1)
    }

    if (key) {
      out[key] = value
    }
  }

  return out
}

/**
 * 只接受「本机回环 + postgres 协议」的连接串。其余（空、sqlite、远程主机）一律
 * 返回 null —— 本机模式注入错了地址，比不注入更难排查。
 */
function isLoopbackPostgresUrl(value: any) {
  if (typeof value !== 'string' || !value.trim()) {
    return false
  }

  const trimmed = value.trim()

  if (!/^postgres(ql)?:\/\//i.test(trimmed)) {
    return false
  }

  const host = String(trimmed.replace(/^postgres(ql)?:\/\//i, '').split('@').pop() || '').split('/')[0].replace(/:\d+$/, '')

  return host === '127.0.0.1' || host === 'localhost' || host === '[::1]'
}

function readDatabaseUrlFromEnvFile(envFilePath: any, { readFileSync = fs.readFileSync }: any = {}) {
  if (!envFilePath) {
    return null
  }

  try {
    const url = parseEnvText(readFileSync(envFilePath, 'utf8')).DATABASE_URL

    return isLoopbackPostgresUrl(url) ? String(url).trim() : null
  } catch {
    return null
  }
}

function describeSetupExitCode(exitCode: any) {
  if (exitCode === 0) {
    return '本机数据库已就绪。'
  }

  const messages: Record<string, string> = SETUP_EXIT_MESSAGES as any

  return messages[exitCode] || `本机数据库初始化失败（退出码 ${exitCode}）。请把日志发给技术顾问。`
}

/** 只有 Windows 支持内置便携 PostgreSQL（macOS 二期，Linux 走文档里的安装脚本）。 */
function isLocalPostgresSupported({ platform = process.platform }: any = {}) {
  return platform === 'win32'
}

/**
 * 调用引导脚本。幂等：已经在跑就立刻返回 0，端口与口令都不动，所以应用每次启动
 * 都可以安全地调一次。
 */
function runLocalPostgresSetup({
  hermesHome,
  installDir,
  repoRoot,
  platform = process.platform,
  timeoutMs = 20 * 60 * 1000,
  spawnImpl = spawn,
  existsSync = fs.existsSync
}: any = {}) {
  const script = portablePostgresScriptPath(repoRoot)

  if (!isLocalPostgresSupported({ platform })) {
    return Promise.resolve({ ok: false, exitCode: null, stdout: '', stderr: '', message: '当前系统暂不支持内置本机数据库。' })
  }

  if (!script || !existsSync(script)) {
    return Promise.resolve({ ok: false, exitCode: null, stdout: '', stderr: '', message: `找不到本机数据库引导脚本：${script || '(未提供仓库路径)'}` })
  }

  const pathModule = pathModuleForPlatform(platform)
  const args = ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, '-Action', 'setup', '-Quiet']

  if (hermesHome) {
    args.push('-DataRoot', pathModule.join(String(hermesHome), 'pgsql'), '-DataDir', pathModule.join(String(hermesHome), 'pgsql-data'))
  }

  if (installDir) {
    args.push('-EnvFile', pathModule.join(String(installDir), '.env.db'))
  }

  return new Promise(resolve => {
    let stdout = ''
    let stderr = ''
    let settled = false
    const child = spawnImpl('pwsh', args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })

    const timer = setTimeout(() => {
      if (!settled) {
        settled = true
        child.kill?.()
        resolve({ ok: false, exitCode: null, stdout, stderr, message: '本机数据库初始化超时（超过 20 分钟），请检查网络后重试。' })
      }
    }, timeoutMs)

    child.stdout?.on('data', (chunk: any) => {
      stdout += String(chunk)
    })
    child.stderr?.on('data', (chunk: any) => {
      stderr += String(chunk)
    })
    child.on('error', (error: any) => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolve({ ok: false, exitCode: null, stdout, stderr, message: `无法启动本机数据库脚本：${error.message}` })
      }
    })
    child.on('close', (code: any) => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolve({ ok: code === 0, exitCode: code, stdout, stderr, message: describeSetupExitCode(code) })
      }
    })
  })
}

export {
  describeSetupExitCode,
  hermesManagedPostgresPathEntries,
  isLocalPostgresSupported,
  isLoopbackPostgresUrl,
  parseEnvText,
  portablePostgresRoot,
  portablePostgresScriptPath,
  readDatabaseUrlFromEnvFile,
  runLocalPostgresSetup,
  SETUP_EXIT_MESSAGES
}
