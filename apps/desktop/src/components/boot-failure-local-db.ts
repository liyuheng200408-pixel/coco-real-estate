/**
 * 本机模式「数据库准备失败」的用户可见文案。
 *
 * COCO-PATCH：官方的启动失败界面只区分「远程登录过期 / 云端宕机 / 本地起不来」，
 * 本地这一档是一句笼统的「后台网关没有启动」。Coco 本机模式多了一层「便携数据库
 * 准备失败」，而且原因差别很大（网络下载不到、密码文件丢了、自检不过……），
 * 笼统文案会让经纪人只能来问我们。这里按引导脚本的退出码映射成具体说法与下一步。
 *
 * 与 boot-failure-reauth.ts 同一套路：纯函数，便于单测，不依赖 React。
 */
import type { Translations } from '@/i18n/types'

export interface LocalDbFailureCopy {
  title: string
  description: string
  hint: string
}

/** 引导脚本/主进程挂在本机数据库错误对象上的字段。 */
interface LocalDbFailureFields {
  localDbExitCode?: unknown
  localDbLogPath?: unknown
  localDbMessage?: unknown
}

function fields(error: unknown): LocalDbFailureFields {
  return (error || {}) as LocalDbFailureFields
}

/** 退出码存在才说明这是「本机数据库」失败，其它失败不能套这套文案。 */
export function localDbExitCode(error: unknown): number | null {
  const code = fields(error).localDbExitCode

  return typeof code === 'number' && Number.isFinite(code) && code > 0 ? code : null
}

export function localDbLogPath(error: unknown): string {
  const p = fields(error).localDbLogPath

  return typeof p === 'string' ? p : ''
}

export function localDbFailureCopy(error: unknown, t: Translations): LocalDbFailureCopy | null {
  const code = localDbExitCode(error)

  if (code === null) {
    return null
  }

  const copy = t.boot.failure.localDb
  // 退出码 → 具体说法（与 docs/DESKTOP_LOCAL_PG.md 的分流表一一对应）。
  // 4/5 都是「进程起不来」，对用户是同一件事：看日志。
  const byCode: Record<number, string> = {
    1: copy.unexpected,
    2: copy.downloadFailed,
    3: copy.binMissing,
    4: copy.startFailed,
    5: copy.startFailed,
    6: copy.credentialsLost,
    7: copy.selfTestFailed,
    8: copy.configInvalid,
    9: copy.unexpected
  }

  return {
    title: copy.title,
    description: byCode[code] || copy.unexpected,
    hint: copy.hint(localDbLogPath(error))
  }
}
