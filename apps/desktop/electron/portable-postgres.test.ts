/**
 * 本机模式便携 PostgreSQL 接线的测试。
 *
 * 这些断言是「契约」而不是快照：路径拼接规则、.env.db 解析规则、退出码到用户提示
 * 的映射、以及后端 PATH/环境里必须出现什么 —— 换实现也不该变。
 */
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import path from 'node:path'

import { test } from 'vitest'

import { buildDesktopBackendEnv, buildDesktopBackendPath } from './backend-env'
import {
  describeSetupExitCode,
  desktopScriptPath,
  hermesManagedPostgresPathEntries,
  isLocalPostgresSupported,
  isLoopbackPostgresUrl,
  parseEnvText,
  portablePostgresRoot,
  portablePostgresScriptPath,
  readDatabaseUrlFromEnvFile,
  runLocalBackupRegister,
  runLocalPostgresSetup
} from './portable-postgres'

const ENV_SAMPLE = [
  '# 数据库配置（由 portable-postgres.ps1 生成/维护）',
  'DB_HOST=127.0.0.1',
  'DB_PORT=45678',
  'COCO_ENABLE_CRON=1',
  'DATABASE_URL=postgresql://hermes:pw123@127.0.0.1:45678/hermes_agent',
  'QUOTED="has spaces"',
  "export EXPORTED=value",
  '',
  'NOTE=a=b=c'
].join('\n')

test('parseEnvText reads dotenv lines, skips comments, strips quotes and a leading export', () => {
  const parsed = parseEnvText(ENV_SAMPLE)

  assert.equal(parsed.DB_PORT, '45678')
  assert.equal(parsed.COCO_ENABLE_CRON, '1')
  assert.equal(parsed.QUOTED, 'has spaces')
  assert.equal(parsed.EXPORTED, 'value')
  assert.equal(parsed.NOTE, 'a=b=c')
  assert.equal('# 数据库配置' in parsed, false)
})

test('parseEnvText tolerates CRLF and an empty body', () => {
  assert.equal(parseEnvText('A=1\r\nB=2\r\n').B, '2')
  assert.deepEqual(parseEnvText(''), {})
  assert.deepEqual(parseEnvText(null), {})
})

test('isLoopbackPostgresUrl accepts only loopback postgres URLs', () => {
  assert.equal(isLoopbackPostgresUrl('postgresql://hermes:pw@127.0.0.1:5432/hermes_agent'), true)
  assert.equal(isLoopbackPostgresUrl('postgres://hermes:pw@localhost:5432/hermes_agent'), true)
  assert.equal(isLoopbackPostgresUrl('postgresql://hermes:pw@[::1]:5432/hermes_agent'), true)

  // 远程地址 / 别的协议 / 空值一律不注入 —— 注错了比不注入更难排查
  assert.equal(isLoopbackPostgresUrl('postgresql://hermes:pw@db.example.com:5432/hermes_agent'), false)
  assert.equal(isLoopbackPostgresUrl('sqlite:///real_estate.db'), false)
  assert.equal(isLoopbackPostgresUrl(''), false)
  assert.equal(isLoopbackPostgresUrl(null), false)
})

test('readDatabaseUrlFromEnvFile returns the URL only when the file parses and stays on loopback', () => {
  const good = readDatabaseUrlFromEnvFile('/tmp/.env.db', { readFileSync: () => ENV_SAMPLE })

  assert.equal(good, 'postgresql://hermes:pw123@127.0.0.1:45678/hermes_agent')

  const remote = readDatabaseUrlFromEnvFile('/tmp/.env.db', {
    readFileSync: () => 'DATABASE_URL=postgresql://hermes:pw@10.0.0.9:5432/hermes_agent\n'
  })

  assert.equal(remote, null)

  const missing = readDatabaseUrlFromEnvFile('/tmp/.env.db', {
    readFileSync: () => {
      throw new Error('ENOENT')
    }
  })

  assert.equal(missing, null)
  assert.equal(readDatabaseUrlFromEnvFile(null, { readFileSync: () => ENV_SAMPLE }), null)
})

test('describeSetupExitCode maps every documented exit code to actionable Chinese text', () => {
  assert.match(describeSetupExitCode(0), /就绪/)
  assert.match(describeSetupExitCode(2), /下载失败/)
  assert.match(describeSetupExitCode(3), /修复安装/)
  assert.match(describeSetupExitCode(6), /凭据文件缺失/)
  assert.match(describeSetupExitCode(7), /自检未通过/)
  assert.match(describeSetupExitCode(42), /退出码 42/)
})

test('portable postgres paths mirror the script defaults', () => {
  assert.equal(portablePostgresRoot('C:\\Users\\me\\AppData\\Local\\hermes', { pathModule: path.win32 }), 'C:\\Users\\me\\AppData\\Local\\hermes\\pgsql')
  assert.deepEqual(hermesManagedPostgresPathEntries('/home/me/.hermes', { pathModule: path.posix }), ['/home/me/.hermes/pgsql/bin'])
  assert.deepEqual(hermesManagedPostgresPathEntries(null), [])
  assert.equal(portablePostgresScriptPath('/repo'), path.join('/repo', 'apps', 'desktop', 'scripts', 'portable-postgres.ps1'))
  assert.equal(portablePostgresScriptPath(null), null)
})

test('local postgres is Windows-only for now', () => {
  assert.equal(isLocalPostgresSupported({ platform: 'win32' }), true)
  assert.equal(isLocalPostgresSupported({ platform: 'darwin' }), false)
  assert.equal(isLocalPostgresSupported({ platform: 'linux' }), false)
})

test('backend PATH carries the portable postgres bin ahead of the rest', () => {
  const winPath = buildDesktopBackendPath({
    hermesHome: 'C:\\Users\\me\\AppData\\Local\\hermes',
    venvRoot: 'C:\\Users\\me\\AppData\\Local\\hermes\\hermes-agent\\venv',
    currentPath: 'C:\\Windows\\system32',
    platform: 'win32',
    pathModule: path.win32
  })

  const winEntries = winPath.split(';')
  const pgBin = path.win32.join('C:\\Users\\me\\AppData\\Local\\hermes', 'pgsql', 'bin')

  assert.ok(winEntries.includes(pgBin), 'the portable postgres bin must be on PATH')
  assert.ok(
    winEntries.indexOf(pgBin) < winEntries.indexOf('C:\\Windows\\system32'),
    'our pg_dump/pg_restore/psql must win over an inherited system PostgreSQL'
  )
  // 官方既有顺序（node → venv）保持不变，上游的 backend-env.test.ts 盯着这一点
  assert.ok(winEntries.indexOf(path.win32.join('hermes', 'node')) < winEntries.indexOf(pgBin))
  assert.ok(winPath.includes(path.win32.join('hermes', 'node')))

  const posixPath = buildDesktopBackendPath({
    hermesHome: '/home/me/.hermes',
    venvRoot: '/home/me/.hermes/hermes-agent/venv',
    currentPath: '/usr/bin',
    platform: 'linux',
    pathModule: path.posix
  })

  assert.ok(posixPath.split(':').includes('/home/me/.hermes/pgsql/bin'))
})

test('backend env gets DATABASE_URL only when the caller supplies a loopback URL', () => {
  const withDb = buildDesktopBackendEnv({
    hermesHome: 'C:\\Users\\me\\AppData\\Local\\hermes',
    venvRoot: 'C:\\Users\\me\\AppData\\Local\\hermes\\hermes-agent\\venv',
    databaseUrl: 'postgresql://hermes:pw@127.0.0.1:45678/hermes_agent',
    currentEnv: { PATH: 'C:\\Windows\\system32' },
    platform: 'win32',
    pathModule: path.win32
  })

  assert.equal(withDb.DATABASE_URL, 'postgresql://hermes:pw@127.0.0.1:45678/hermes_agent')

  const withoutDb = buildDesktopBackendEnv({
    hermesHome: 'C:\\Users\\me\\AppData\\Local\\hermes',
    currentEnv: { PATH: 'C:\\Windows\\system32' },
    platform: 'win32',
    pathModule: path.win32
  })

  assert.equal('DATABASE_URL' in withoutDb, false, 'no local DB means the official behaviour must be untouched')
  assert.equal(withoutDb.PYTHONUTF8, '1')
})

test('desktopScriptPath points at the shipped scripts folder', () => {
  assert.equal(
    desktopScriptPath('C:\\repo', 'local-backup.ps1', { pathModule: path.win32 }),
    path.win32.join('C:\\repo', 'apps', 'desktop', 'scripts', 'local-backup.ps1')
  )
  assert.equal(desktopScriptPath(null, 'local-backup.ps1'), null)
})

test('runLocalBackupRegister calls the backup script with -Action register on Windows', async () => {
  const calls: any[] = []
  const spawnImpl = (command: string, args: string[]) => {
    calls.push({ command, args })
    const child = new EventEmitter() as any
    child.stdout = new EventEmitter()
    child.stderr = new EventEmitter()
    child.kill = () => undefined
    setImmediate(() => child.emit('close', 0))

    return child
  }

  const result = await runLocalBackupRegister({
    hermesHome: 'C:\\Users\\me\\AppData\\Local\\hermes',
    installDir: 'C:\\Users\\me\\AppData\\Local\\hermes\\hermes-agent',
    repoRoot: 'C:\\repo',
    platform: 'win32',
    existsSync: () => true,
    spawnImpl
  })

  assert.equal(calls.length, 1)
  assert.ok(calls[0].args.includes(path.win32.join('C:\\repo', 'apps', 'desktop', 'scripts', 'local-backup.ps1')))
  assert.ok(calls[0].args.includes('-Action') && calls[0].args.includes('register'))
  assert.ok(calls[0].args.includes('-InstallDir'))
  assert.equal(result.ok, true)
  assert.match(result.message, /备份任务已就绪/)
})

test('runLocalBackupRegister reports a readable message when it fails', async () => {
  const spawnImpl = () => {
    const child = new EventEmitter() as any
    child.stdout = new EventEmitter()
    child.stderr = new EventEmitter()
    child.kill = () => undefined
    setImmediate(() => child.emit('close', 8))

    return child
  }

  const result = await runLocalBackupRegister({
    installDir: 'C:\\hermes-agent',
    repoRoot: 'C:\\repo',
    platform: 'win32',
    existsSync: () => true,
    spawnImpl
  })

  assert.equal(result.ok, false)
  assert.match(result.message, /没有自动备份/)
})

test('runLocalPostgresSetup refuses to run off Windows without spawning anything', async () => {
  let spawned = false
  const result = await runLocalPostgresSetup({
    installDir: '/tmp/install',
    repoRoot: '/repo',
    platform: 'linux',
    spawnImpl: () => {
      spawned = true
      throw new Error('must not spawn')
    }
  })

  assert.equal(result.ok, false)
  assert.equal(spawned, false)
  assert.match(result.message, /暂不支持/)
})

test('runLocalPostgresSetup reports a missing bootstrap script instead of spawning', async () => {
  const result = await runLocalPostgresSetup({
    installDir: 'C:\\hermes-agent',
    repoRoot: 'C:\\repo',
    platform: 'win32',
    existsSync: () => false,
    spawnImpl: () => {
      throw new Error('must not spawn')
    }
  })

  assert.equal(result.ok, false)
  assert.match(result.message, /找不到脚本/)
  // 路径要按目标平台拼（Windows 上不能出现 C:\repo/apps/... 这种混搭）
  assert.ok(result.message.includes('apps\\desktop\\scripts\\portable-postgres.ps1'))
})

test('runLocalPostgresSetup passes explicit paths to the script and maps the exit code', async () => {
  const calls = []

  const spawnImpl = (command, args) => {
    calls.push({ command, args })
    const child = new EventEmitter()
    child.stdout = new EventEmitter()
    child.stderr = new EventEmitter()
    child.kill = () => undefined
    setImmediate(() => {
      child.stdout.emit('data', '  [OK]   PostgreSQL 已启动\n')
      child.emit('close', 6)
    })

    return child
  }

  const result = await runLocalPostgresSetup({
    hermesHome: 'C:\\Users\\me\\AppData\\Local\\hermes',
    installDir: 'C:\\Users\\me\\AppData\\Local\\hermes\\hermes-agent',
    repoRoot: 'C:\\repo',
    platform: 'win32',
    existsSync: () => true,
    spawnImpl
  })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].command, 'pwsh')
  assert.ok(calls[0].args.includes('-Action') && calls[0].args.includes('setup'))
  assert.ok(calls[0].args.includes('-EnvFile'))
  assert.ok(calls[0].args.includes(path.win32.join('C:\\Users\\me\\AppData\\Local\\hermes\\hermes-agent', '.env.db')))
  assert.equal(result.ok, false)
  assert.equal(result.exitCode, 6)
  assert.match(result.message, /凭据文件缺失/)
  assert.match(result.stdout, /PostgreSQL 已启动/)
})

test('runLocalPostgresSetup surfaces spawn errors as a readable message', async () => {
  const result = await runLocalPostgresSetup({
    installDir: 'C:\\hermes-agent',
    repoRoot: 'C:\\repo',
    platform: 'win32',
    existsSync: () => true,
    spawnImpl: () => {
      const child = new EventEmitter()
      child.kill = () => undefined
      setImmediate(() => child.emit('error', new Error('spawn pwsh ENOENT')))

      return child
    }
  })

  assert.equal(result.ok, false)
  assert.match(result.message, /spawn pwsh ENOENT/)
})
