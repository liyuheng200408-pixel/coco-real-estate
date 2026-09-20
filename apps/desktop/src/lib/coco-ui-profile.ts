/**
 * Coco 界面档位 —— 「收起技术向入口」的唯一开关。
 *
 * 这是 hide-versus-show 的唯一事实来源。界面上每个技术向入口（BOTS 页签、项目分组、
 * 技能与工具、消息平台、产物、账单/提供方、定时任务高级项…）都只在
 * `COCO_BROKER_HIDDEN_ENTRIES` 里登记一次；调用方一律问下面这几个 `coco*Visible()`
 * 函数，不自己判断档位、也不各自写「是不是中介版」的条件。
 *
 * 恢复工程师界面：把下面的 `COCO_UI_PROFILE` 改成 `'engineer'`。隐藏行为全部从这个
 * 常量派生，没有第二处开关，改回一行即全量恢复。
 *
 * 「收起」的边界 = 不展示 / 不进导航 / 不注册内建插件；底层路由、工具、数据一律不动。
 * 因此深链接（如 /skills、/messaging）与已在用的快捷键仍然可用、不会报错，只是界面上
 * 不再有入口 —— 见 apps/desktop/AGENTS.md「不破坏功能」的约定。
 */

export type CocoUiProfile = 'broker' | 'engineer'

/** 当前档位。发给房产中介的安装包用 `'broker'`；工程师自用/排障改 `'engineer'`。 */
export const COCO_UI_PROFILE: CocoUiProfile = 'broker'

/**
 * 入口 id 词表。id 就是各注册表里已经在用的那个 id（侧栏导航行用 keybind 动作 id，
 * 设置项用 `SettingsViewId`），这样调用方不必再维护一套平行命名。
 */
export const COCO_ENTRY = {
  /** 内建插件 Bot Mode（BOTS 页签 + 名册/例程面板 + @机器人提及）。 */
  bots: 'plugin.hermes-bots',
  /** 定时任务编辑器里的「自定义排程」（裸 cron 表达式）。 */
  cronCustomSchedule: 'cron.customSchedule',
  /** 定时任务编辑器里的按任务模型覆盖。 */
  cronModel: 'cron.model',
  /** 侧栏 / 命令面板的「产物」页。 */
  navArtifacts: 'nav.artifacts',
  /** 侧栏 / 命令面板的「消息平台」页。 */
  navMessaging: 'nav.messaging',
  /** 侧栏 / 命令面板的「技能与工具」页（能力：技能/工具集/MCP/插件）。 */
  navSkills: 'nav.skills',
  /** 设置里的「账单」。 */
  settingsBilling: 'settings.billing',
  /** 设置里的「工具与密钥」（工具用 API 密钥/环境变量）。 */
  settingsKeys: 'settings.keys',
  /** 设置里的「提供方」（账号 / API 密钥 / 自定义端点 / 本地模型）。 */
  settingsProviders: 'settings.providers',
  /** 侧栏里的消息平台会话分组（Telegram/Discord/Slack…）。 */
  sidebarMessagingGroups: 'sidebar.messagingGroups',
  /** 侧栏视图筛选里的「项目」筛选（按项目/工作树过滤会话）。 */
  sidebarProjectFilter: 'sidebar.projectFilter',
  /** 侧栏视图筛选里的「项目」分组（按项目分组会话）。 */
  sidebarProjectGrouping: 'sidebar.projectGrouping'
} as const

export type CocoEntryId = (typeof COCO_ENTRY)[keyof typeof COCO_ENTRY]

/**
 * 中介版里收起的入口。分三组记，方便以后逐条增删：
 *
 * - 技术向页面：BOTS（Bot Mode 插件）、技能与工具、消息平台、产物。
 * - 技术向设置：账单、提供方、工具与密钥。
 * - 技术向细节：侧栏的项目分组/项目筛选、消息平台会话分组、定时任务的裸 cron 与模型覆盖。
 *
 * 明确**不**在这里的（保留给中介用）：会话侧栏与新建会话、定时任务页与侧栏任务分组、
 * 设置里的模型/聊天/外观/工作区/安全/浏览器/记忆/语音/高级、网关（连服务器要用）、
 * 键盘快捷键、归档会话、通知、密码与登录、关于。
 */
export const COCO_BROKER_HIDDEN_ENTRIES: readonly CocoEntryId[] = [
  COCO_ENTRY.bots,
  COCO_ENTRY.navSkills,
  COCO_ENTRY.navMessaging,
  COCO_ENTRY.navArtifacts,
  COCO_ENTRY.settingsBilling,
  COCO_ENTRY.settingsProviders,
  COCO_ENTRY.settingsKeys,
  COCO_ENTRY.sidebarProjectGrouping,
  COCO_ENTRY.sidebarProjectFilter,
  COCO_ENTRY.sidebarMessagingGroups,
  COCO_ENTRY.cronCustomSchedule,
  COCO_ENTRY.cronModel
]

/** 命令面板「跳转」行的 id（带连字符）对应哪个入口 id。只列需要收起的那些。 */
const PALETTE_ROW_ENTRIES: Readonly<Record<string, CocoEntryId>> = {
  'nav-artifacts': COCO_ENTRY.navArtifacts,
  'nav-messaging': COCO_ENTRY.navMessaging,
  'nav-skills': COCO_ENTRY.navSkills
}

const HIDDEN_ENTRIES: ReadonlySet<string> = new Set<string>(COCO_BROKER_HIDDEN_ENTRIES)

/** 纯函数：给定档位下某个入口是否可见 —— `cocoEntryVisible` 就是它对当前档位的调用，
 *  单独暴露是为了让两种档位都能被测试钉住（见 coco-ui-profile.test.ts）。 */
export function isCocoEntryVisibleForProfile(profile: CocoUiProfile, id: string): boolean {
  return profile === 'engineer' || !HIDDEN_ENTRIES.has(id)
}

/** 工程师档位下一切照旧；中介档位下只有登记过的 id 不可见。 */
export function cocoEntryVisible(id: string): boolean {
  return isCocoEntryVisibleForProfile(COCO_UI_PROFILE, id)
}

/** 内建插件（`src/plugins/<id>`）是否注册。id 按 `plugin.<插件 id>` 登记。 */
export function cocoPluginVisible(pluginId: string): boolean {
  return cocoEntryVisible(`plugin.${pluginId}`)
}

/** 设置视图（`SettingsViewId`，如 `billing`）是否进设置导航。 */
export function cocoSettingsViewVisible(view: string): boolean {
  return cocoEntryVisible(`settings.${view}`)
}

/** 设置视图带子页参数的形式（命令面板里的 `providers&pview=accounts`）。 */
export function cocoSettingsTabVisible(tab: string): boolean {
  return cocoSettingsViewVisible(tab.split('&')[0])
}

/** 命令面板「跳转」行（如 `nav-skills`）是否展示。 */
export function cocoPaletteRowVisible(rowId: string): boolean {
  const entryId = PALETTE_ROW_ENTRIES[rowId]

  return entryId === undefined || cocoEntryVisible(entryId)
}
