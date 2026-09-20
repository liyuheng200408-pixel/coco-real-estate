#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coco 挂钩点自检 —— 同步官方 Hermes 上游代码后运行

用途
    每次把 Coco 的底座同步到官方新版本后，跑这个脚本确认两件事：
      ① Coco 对官方文件的 7 处改动都还在
      ② Coco 自建的文件（房产模块 / 部署体系 / 文档 / CI）都还在

为什么需要它
    Coco 是「官方代码 + 我们的改动」的形态。同步上游时官方文件会被整批
    替换，我们的改动必须重新应用。漏掉任何一处，症状都很隐蔽：
      · 工具集没注册   → 模型看不到房产工具，Coco 会说"我没有这个能力"
      · 身份文案丢了   → Coco 自我介绍变回官方默认（"我是 Hermes…"）
      · 提示词没注入   → 房产规则失效，模型行为退化成通用助手
      · 启动不建库     → 新装的库没有表（幽灵库事故的同类问题）
      · 配置阈值回退   → 上下文压缩行为回到官方默认（爆上下文风险）
      · 飞书欢迎语丢了 → 经纪人首次对话没有引导，以为机器人是哑的
      · 网关开场白丢了 → 首次对话自我介绍错误
    这个脚本把 7 处改动 + 文件完整性一次扫完，30 秒内给出结论。

用法
    python3 scripts/check_coco_hooks.py                 # 自动定位仓库根
    python3 scripts/check_coco_hooks.py /path/to/repo   # 指定仓库路径

退出码
    0 = 全部通过    1 = 有失败项（列表见输出）
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 检查项定义
# 每项：编号 / 名称 / 目标文件 / 必需正则(全部命中才算过) / 失败后果与处理提示
CONTENT_CHECKS = [
    (
        "01",
        "工具集注册",
        "toolsets.py",
        [r'"real_estate"\s*:'],
        "模型看不到房产工具（会自称没有登记房源/客户的能力）。"
        "处理：在 TOOLSETS 里补 real_estate 定义，并把 real_estate 加进 hermes-feishu 的 includes。",
    ),
    (
        "02",
        "Coco 身份文案",
        "agent/prompt_builder.py",
        [r"DEFAULT_AGENT_IDENTITY[\s\S]{0,800}?Coco", r"Coco（可可）"],
        "Coco 自我介绍会变回官方默认（自称 Hermes）。"
        "处理：按 patches/02-prompt-builder-identity.patch 的语义重写身份常量。",
    ),
    (
        "03",
        "房产提示词注入",
        "agent/system_prompt.py",
        [r"real_estate_prompt"],
        "房产业务规则不再注入系统提示词，模型行为退化成通用助手。"
        "处理：恢复对 agent.real_estate_prompt 的导入与拼接。",
    ),
    (
        "04",
        "启动初始化房产库",
        "agent/agent_init.py",
        [r"init_real_estate_db"],
        "CLI 启动路径不建表（agent_init 属 CLI 专用；gateway 有惰性兜底，但别依赖兜底）。"
        "处理：恢复 init_real_estate_db 调用。",
    ),
    (
        "05",
        "上下文压缩阈值",
        "hermes_cli/config_defaults.py",
        [r'"threshold"\s*:\s*0\.8', r'"destructive_slash_confirm"\s*:\s*False'],
        "压缩阈值回到官方默认 0.50（会提前压缩、丢失更多上下文）；"
        "或清空对话类命令又弹回确认框（经纪人不会输入 /always，会卡住开新会话）。"
        "处理：改回 0.8（含 protect_last_n=40）与 destructive_slash_confirm=False。",
    ),
    (
        "06",
        "飞书首次对话功能",
        "plugins/platforms/feishu/adapter.py",
        [r"_maybe_send_coco_welcome|Coco: 首次对话"],
        "经纪人首次对话收不到欢迎语/密钥提醒/定时任务自动注册。"
        "处理：按 patches/06-feishu-adapter-welcome.patch 恢复三处（欢迎语、密钥备份提醒、注册定时任务）。",
    ),
    (
        "07",
        "网关首次对话开场白",
        # 注意：官方 v0.21 把这段逻辑从 gateway/run.py 拆到了 gateway/run_turn.py
        # 的 _hmwa_first_contact_notes()。官方将来再拆分时，按同样方式更新这里的路径
        # （找不到文件即 FAIL，会提醒我们重新定位）。
        "gateway/run_turn.py",
        [r"我是 Coco|你是 Coco|Coco（可可）"],
        "首次对话开场白变回官方文案（并可能带回官方 profile-build 引导）。"
        "处理：按 patches/07-gateway-run-greeting.patch 恢复。",
    ),
    (
        "08",
        "CI 挑标签正则",
        "scripts/sandbox/pick-release-tags.sh",
        # 只在「放宽后」才存在的特征串；被官方版覆盖后会立刻 FAIL
        [r"\(-\[0-9\]\+\)\?"],
        "Coco 用语义化标签（v0.21.3-1），正则应同时认日期式与语义化。\n"
        "处理：放宽 grep 正则为 '^v[0-9]{4}...|^v[0-9]+\\.[0-9]+\\.[0-9]+(-[0-9]+)?$'，\n"
        "      否则继承自官方的 install-e2e 会报 no release tags found。",
    ),
    (
        "09",
        "核心依赖 ddgs",
        "pyproject.toml",
        [r'"ddgs'],
        "ddgs 被官方快照覆盖后，pip install -e . 不会装它 → web_search 注册时的\n"
        "check_fn 检测不到后端、工具被隐藏，Coco 联网查政策会退化成「建议咨询当地」。\n"
        "处理：在 dependencies 里补回 \"ddgs==<版本>\"，并确认 install.sh 里也有它。",
    ),
    (
        "10",
        "E2E 定时触发已移除",
        ".github/workflows/install-e2e.yml",
        # 反向匹配（! 开头）：文件里**不能**出现这个模式
        [r"!^  schedule:"],
        "官方 install-e2e 带每 12 小时 schedule 定时触发，但它测的是 Hermes 本体\n"
        "（uv/Node、上游分发方式）的安装升级，与 Coco 的 install.sh 分发方式不符 →\n"
        "定时跑必失败、每 12 小时制造一次 CI 红灯，并持续消耗 Actions 配额。\n"
        "处理：删掉 on: 下的 schedule 段，保留 workflow_dispatch 与 push tags（参考提交 e1a42a84）。",
    ),
    (
        "11",
        "文档站部署触发已移除",
        ".github/workflows/deploy-site.yml",
        # 反向匹配（! 开头）：这两个触发不能出现
        [r"!^  release:", r"!^  push:"],
        "官方 deploy-site 在 release published / push 上触发，靠 VERCEL_DEPLOY_HOOK 部署文档站；\n"
        "本仓库没有该钩子 → curl -X POST \"\" 报 URL rejected，每次发版必红（与代码无关）。\n"
        "处理：删掉 on: 下的 release / push 段，只留 workflow_dispatch（参考本次提交）。",
    ),
    (
        "13",
        "Coco 运行时配置标准值",
        "scripts/coco_config_align.py",
        [
            r'"agent\.max_turns":\s*500',
            r'"compression\.threshold":\s*0\.8',
            r'"compression\.protect_last_n":\s*40',
            r'"compression\.hygiene_hard_message_limit":\s*5000',
        ],
        "对齐脚本缺失或标准值被改，安装/更新就不会再校正运行时配置，\n"
        "表现为「代码默认值对了但服务器上不生效」或「重装后又回到 150 轮」。\n"
        "处理：恢复 scripts/coco_config_align.py 的 STANDARD 与安装/更新脚本里的调用。",
    ),
    (
        "14",
        "设置向导的轮次上限",
        "hermes_cli/setup.py",
        [r'max_turns"\]\s*=\s*500'],
        "官方向导写 max_turns=150，重跑向导会把 Coco 的 500 冲掉。\n"
        "处理：恢复 COCO-PATCH（向导写 500 + 压缩阈值 0.8 / 保留 40 条）。",
    ),
    (
        "15",
        "海报不写平台名",
        "tools/real_estate_poster_svg.py",
        # 结构检查：品牌栏必须来自经纪人名片，页脚免责句必须在位
        [r"def _brand\(", r"房源信息以实际看房为准"],
        "海报品牌栏/免责句被改动：品牌应只来自经纪人名片（缺失时不画），页脚固定「房源信息以实际看房为准」。\n"
        "处理：恢复 _brand() 与 _footer() 的默认文案；渲染结果里不得出现平台名。",
    ),
    (
        "16",
        "更新类命令拦截",
        "tools/terminal_tool.py",
        [r"coco_update_block"],
        "Coco 会话里的终端更新命令拦截被移除：经纪人一句“帮我更新”，她就可能自己跑官方 "
        "hermes update（不跑我们的数据库迁移、可能覆盖手改代码）或 update.sh（重启网关连自己一起杀掉）。\n"
        "处理：恢复 COCO-PATCH 调用点（tools/real_estate_update_guard.coco_update_block）。",
    ),
    (
        "12",
        "README 命令不污染终端",
        "README.md",
        [r"!cd ~/hermes-agent"],
        "对外命令里写 `cd ~/hermes-agent && ...` 会把用户终端切到仓库目录，跑完提示符变成\n"
        "`user@host:~/hermes-agent$`（用户会以为出问题了）。\n"
        "处理：改成自定位写法 —— `git -C ~/hermes-agent ...`、`~/hermes-agent/venv/bin/python ~/hermes-agent/scripts/x.py`、\n"
        "必须切目录时用括号子 shell `( cd ... && ... )`。",
    ),
    (
        "13",
        "README(中文) 命令不污染终端",
        "README.zh-CN.md",
        [r"!cd ~/hermes-agent"],
        "同第 12 项：中英两份 README 的命令写法要保持一致，都用自定位写法。",
    ),
    (
        "14",
        "备份迁移手册命令不污染终端",
        "docs/BACKUP_MIGRATION.md",
        [r"!cd ~/hermes-agent"],
        "同第 12 项：备份/恢复/迁移步骤里的命令都用 venv 绝对路径，不要 cd 到仓库目录。",
    ),
    (
        "16",
        "工具必填参数校验",
        "tools/registry.py",
        [r"COCO-PATCH", r"_missing_required_params"],
        "官方 registry 被上游快照覆盖后，模型漏传必填参数会重新变成 TypeError（模型看到\n"
        "\"Tool execution failed\" 就会自己编答案）。\n"
        "处理：在 dispatch 里补回必填参数校验（标记 COCO-PATCH 2026-09-18）。",
    ),
    (
        "15",
        "飞书实测清单命令不污染终端",
        "docs/TESTING_FEISHU_FULL.md",
        [r"!cd ~/hermes-agent"],
        "同第 12 项：前置检查与查库模板都用自定位写法（查库用 `export $(grep DATABASE_URL ~/hermes-agent/.env.db)` 或一次性取值）。",
    ),
]

# 文件/目录存在性检查：编号 / 名称 / 相对路径 / 类型(file|dir|glob) / 最少数量 / 失败提示
PATH_CHECKS = [
    ("A1", "版本标识", "VERSION", "file", 1, "Coco 版本号丢失（安装/更新终端不再显示版本）"),
    ("A2", "房产数据层", "agent/real_estate_db.py", "file", 1, "房产数据库层丢失"),
    ("A3", "房产提示词", "agent/real_estate_prompt.py", "file", 1, "房产提示词模块丢失"),
    ("A4", "定时任务模块", "agent/coco_cron.py", "file", 1, "定时任务模块丢失（enable_cron 会失效）"),
    ("A5", "房产工具集", "tools/real_estate_*.py", "glob", 20, "房产工具文件缺失（工具数会减少）"),
    ("A6", "房产技能", "skills/real_estate/SKILL.md", "file", 1, "Coco 操作手册（技能）丢失"),
    ("A7", "数据库迁移", "migrations/*.sql", "glob", 1, "迁移目录丢失（表结构升级会失败）"),
    ("A8", "一键安装脚本", "install.sh", "file", 1, "安装脚本丢失（新用户无法安装）"),
    ("A9", "一键更新脚本", "scripts/update.sh", "file", 1, "更新脚本丢失（更新铁律被破坏）"),
    ("A10", "部署体检脚本", "scripts/healthcheck.py", "file", 1, "体检脚本丢失"),
    ("A11", "迁移执行器", "scripts/migrate.py", "file", 1, "迁移执行器丢失"),
    ("A12", "数据库备份脚本", "scripts/backup_db.py", "file", 1, "备份脚本丢失（数据安全网缺失）"),
    ("A13", "工具冒烟脚本", "scripts/smoke_test_real_estate.py", "file", 1, "冒烟脚本丢失（无法做工具层验收）"),
    ("A14", "房产单测", "tests/real_estate/*.py", "glob", 5, "房产单测丢失（回归无保障）"),
    ("A15", "房产 CI 工作流", ".github/workflows/real-estate-tests.yml", "file", 1, "房产测试 CI 丢失"),
    ("A16", "迁移/备份文档", "docs/BACKUP_MIGRATION.md", "file", 1, "备份迁移文档丢失"),
    ("A17", "飞书实测清单", "docs/TESTING_FEISHU_FULL.md", "file", 1, "飞书全量实测清单丢失"),
    ("A18", "官方残留清理脚本", "scripts/prune_official_deleted.sh", "file", 1, "官方已删残留的清理脚本丢失（同步时无法顺带清理）"),
                    ]


def check_content(repo: Path):
    results = []
    for cid, name, rel, patterns, tip in CONTENT_CHECKS:
        target = repo / rel
        if not target.exists():
            results.append((cid, name, False, f"文件不存在：{rel}"))
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover
            results.append((cid, name, False, f"读取失败：{exc}"))
            continue
        # 模式以 ! 开头 = 反向匹配（不应出现）：用于守「官方版带回来、Coco 必须去掉」的东西
        missing = []
        for _p in patterns:
            if _p.startswith("!"):
                if re.search(_p[1:], text, re.M):
                    missing.append(_p)
            elif not re.search(_p, text, re.M):
                missing.append(_p)
        if missing:
            results.append((cid, name, False, f"未匹配到模式：{missing} —— {tip}"))
        else:
            results.append((cid, name, True, rel))
    return results


def check_paths(repo: Path):
    results = []
    for cid, name, pattern, kind, min_count, tip in PATH_CHECKS:
        if kind == "file":
            ok = (repo / pattern).is_file()
            found = 1 if ok else 0
        elif kind == "dir":
            ok = (repo / pattern).is_dir()
            found = 1 if ok else 0
        else:  # glob
            found = len(list(repo.glob(pattern)))
            ok = found >= min_count
        detail = f"{pattern}" + (f"（找到 {found}，需 ≥{min_count}）" if kind == "glob" else "")
        results.append((cid, name, ok, detail if ok else f"{detail} —— {tip}"))
    return results


def main() -> int:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    print("=" * 74)
    print(" Coco 挂钩点自检")
    print(f" 仓库：{repo}")
    print("=" * 74)

    all_results = check_content(repo) + check_paths(repo)

    width = 34
    print(f"\n{'编号':<5}{'检查项':<{width}}{'结果':<6}说明")
    print("-" * 74)
    failures = []
    for cid, name, ok, detail in all_results:
        pad = width - sum(2 if ord(ch) > 127 else 1 for ch in name)
        status = "PASS" if ok else "FAIL"
        print(f"{cid:<5}{name}{' ' * max(pad, 1)}{status:<6}{detail}")
        if not ok:
            failures.append((cid, name, detail))

    print("-" * 74)
    total = len(all_results)
    print(f"合计 {total} 项：通过 {total - len(failures)}，失败 {len(failures)}")

    if failures:
        print("\n【需要处理】")
        for cid, name, detail in failures:
            print(f"  [{cid}] {name}\n       {detail}")
        print("\n提示：Coco 的改动语义说明见 patches/README.md；")
        print("      同步上游的操作流程见 docs/UPSTREAM_SYNC.md。")
        return 1

    print("\n全部通过 —— 挂钩点与自建文件都在位。")
    print("下一步：跑 scripts/smoke_test_real_estate.py（工具层冒烟）与单测。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
