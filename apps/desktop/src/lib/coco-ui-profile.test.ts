import { describe, expect, it } from 'vitest'

import {
  COCO_BROKER_HIDDEN_ENTRIES,
  COCO_ENTRY,
  COCO_UI_PROFILE,
  cocoEntryVisible,
  cocoPaletteRowVisible,
  cocoPluginVisible,
  cocoSettingsTabVisible,
  cocoSettingsViewVisible,
  isCocoEntryVisibleForProfile
} from './coco-ui-profile'

// 收起技术向入口（中介版）的三条契约：登记过的看不见、没登记的照旧、改成 engineer 全部回来。
// 谁把某个入口从清单里删掉、或让判定绕开 COCO_UI_PROFILE，这里就红。
describe('coco ui profile — 收起技术向入口', () => {
  it('中介档位：登记的入口不可见', () => {
    for (const id of COCO_BROKER_HIDDEN_ENTRIES) {
      expect(isCocoEntryVisibleForProfile('broker', id)).toBe(false)
    }

    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.navSkills)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.navMessaging)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.navArtifacts)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.settingsBilling)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.settingsProviders)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.sidebarProjectGrouping)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.sidebarMessagingGroups)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.cronCustomSchedule)).toBe(false)
    expect(isCocoEntryVisibleForProfile('broker', COCO_ENTRY.cronModel)).toBe(false)
  })

  it('中介档位：没登记的入口照旧可见（会话、定时任务、模型设置、网关…）', () => {
    for (const id of [
      'nav.settings',
      'nav.cron',
      'settings.model',
      'settings.chat',
      'settings.appearance',
      'settings.workspace',
      'settings.gateway',
      'settings.keybinds',
      'settings.vault',
      'settings.sessions',
      'settings.notifications',
      'settings.about',
      'sidebar.grouping.date',
      'sidebar.grouping.status',
      'plugin.radio'
    ]) {
      expect(isCocoEntryVisibleForProfile('broker', id)).toBe(true)
    }
  })

  it('engineer 档位：全部恢复（改回全显示只有这一个开关）', () => {
    for (const id of COCO_BROKER_HIDDEN_ENTRIES) {
      expect(isCocoEntryVisibleForProfile('engineer', id)).toBe(true)
    }

    expect(isCocoEntryVisibleForProfile('engineer', 'nav.settings')).toBe(true)
  })

  it('派生判定与清单一致：插件 / 设置视图 / 设置子页 / 命令面板行', () => {
    expect(cocoPluginVisible('hermes-bots')).toBe(false)
    expect(cocoPluginVisible('radio')).toBe(true)
    expect(cocoSettingsViewVisible('billing')).toBe(false)
    expect(cocoSettingsViewVisible('providers')).toBe(false)
    expect(cocoSettingsViewVisible('model')).toBe(true)
    expect(cocoSettingsTabVisible('providers&pview=accounts')).toBe(false)
    expect(cocoSettingsTabVisible('keys&kview=tools')).toBe(false)
    expect(cocoSettingsTabVisible('about')).toBe(true)
    expect(cocoPaletteRowVisible('nav-skills')).toBe(false)
    expect(cocoPaletteRowVisible('nav-messaging')).toBe(false)
    expect(cocoPaletteRowVisible('nav-artifacts')).toBe(false)
    expect(cocoPaletteRowVisible('nav-cron')).toBe(true)
    expect(cocoPaletteRowVisible('nav-settings')).toBe(true)
  })

  it('加载期档位就是中介版（安装包默认发出去的就是收起后的界面）', () => {
    expect(COCO_UI_PROFILE).toBe('broker')
    expect(cocoEntryVisible(COCO_ENTRY.navSkills)).toBe(false)
    expect(cocoEntryVisible('nav.cron')).toBe(true)
  })
})
