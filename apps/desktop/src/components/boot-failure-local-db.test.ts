/**
 * 「本机数据库准备失败」文案解析的测试。
 *
 * 断言的是契约：哪个退出码对应哪句话、非本机数据库的失败绝不能套这套文案
 * （否则远程登录过期之类的错误会被说成「数据库下载失败」），以及日志路径要带出去。
 */
import assert from 'node:assert/strict'

import { test } from 'vitest'

import { localDbFailureCopy, localDbExitCode, localDbLogPath } from './boot-failure-local-db'

// 用桩对象而不是真的 zh/en：这里测的是映射规则；文案是否齐全由 Translations 类型保证。
const t = {
  boot: {
    failure: {
      localDb: {
        title: '本机数据库没能启动',
        downloadFailed: '下载失败',
        binMissing: '组件不完整',
        startFailed: '启动不了',
        credentialsLost: '凭据丢了',
        selfTestFailed: '自检没过',
        configInvalid: '配置被改过',
        unexpected: '未预期的错误',
        hint: (logPath: string) => `日志：${logPath}`
      }
    }
  }
} as any

test('localDbExitCode only reports a code for local database failures', () => {
  assert.equal(localDbExitCode({ localDbExitCode: 6 }), 6)
  assert.equal(localDbExitCode({ localDbExitCode: 0 }), null)
  assert.equal(localDbExitCode({ localDbExitCode: '6' }), null)
  assert.equal(localDbExitCode(new Error('backend exited')), null)
  assert.equal(localDbExitCode(null), null)
  assert.equal(localDbExitCode(undefined), null)
})

test('each bootstrap exit code maps to its own recovery copy', () => {
  const cases: [number, string][] = [
    [2, '下载失败'],
    [3, '组件不完整'],
    [4, '启动不了'],
    [5, '启动不了'],
    [6, '凭据丢了'],
    [7, '自检没过'],
    [8, '配置被改过'],
    [9, '未预期的错误'],
    [42, '未预期的错误']
  ]

  for (const [code, expected] of cases) {
    const copy = localDbFailureCopy({ localDbExitCode: code }, t)
    assert.ok(copy, `exit ${code} should yield copy`)
    assert.equal(copy!.title, '本机数据库没能启动')
    assert.equal(copy!.description, expected, `exit ${code}`)
  }
})

test('a non-local-database failure never gets this copy', () => {
  assert.equal(localDbFailureCopy(new Error('Remote gateway sign-in required'), t), null)
  assert.equal(localDbFailureCopy({ isBootstrapFailure: true }, t), null)
})

test('the hint carries the database log path when we know it', () => {
  const withPath = localDbFailureCopy({ localDbExitCode: 5, localDbLogPath: 'C:\\hermes\\pgsql-data\\coco-postgres.log' }, t)
  assert.equal(withPath!.hint, '日志：C:\\hermes\\pgsql-data\\coco-postgres.log')

  const withoutPath = localDbFailureCopy({ localDbExitCode: 5 }, t)
  assert.equal(withoutPath!.hint, '日志：')

  assert.equal(localDbLogPath({ localDbLogPath: 42 }), '')
  assert.equal(localDbLogPath({ localDbLogPath: '/tmp/x.log' }), '/tmp/x.log')
})
