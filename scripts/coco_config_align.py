#!/usr/bin/env python3
"""Coco 运行时配置对齐（幂等）。

为什么需要这个脚本
------------------
Hermes 读配置时，**config.yaml 里显式写过的值优先于代码里的默认值**，而且"新版默认值不会
自动补写进配置文件"。所以：

* 只改代码默认值（config_defaults.py）→ 对**已安装实例无效**（它的 config.yaml 里早就存着旧值）；
* 只写在 config.yaml 里 → 会被重跑向导（官方向导写 `agent.max_turns = 150`）、重装、
  恢复配置冲掉。

两头都靠不住，所以把 Coco 的标准值**显式写进 config.yaml**，安装与更新各跑一次：
新装即正确，老实例更新即对齐，重装后也丢不了。

用法：
    python scripts/coco_config_align.py            # 写入/对齐（幂等，已一致则不动）
    python scripts/coco_config_align.py --check    # 只核对运行时生效值；不一致退出码 1
    python scripts/coco_config_align.py --verbose  # 打印写入过程
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
from pathlib import Path

# Coco 标准运行时配置（2026-09-19 老板拍板：轮次 500、压缩阈值 0.8、保留最近 40 条、
# 网关卫生 5000（官方默认）、时区北京时间）
STANDARD: "dict[str, object]" = {
    "agent.max_turns": 500,
    "compression.threshold": 0.8,
    "compression.protect_last_n": 40,
    "compression.hygiene_hard_message_limit": 5000,
    "timezone": "Asia/Shanghai",
}

# 人话说明（终端与体检输出用）
LABELS: "dict[str, str]" = {
    "agent.max_turns": "单次任务最大轮次",
    "compression.threshold": "上下文压缩阈值",
    "compression.protect_last_n": "保留最近消息条数",
    "compression.hygiene_hard_message_limit": "网关强制压缩消息上限",
    "timezone": "时区",
}


def _backup_config() -> None:
    """改配置前留一份备份（config.yaml.coco-bak），出问题可对比/回滚。"""
    from hermes_cli.config import get_config_path

    try:
        cfg = Path(get_config_path())
        if cfg.is_file():
            shutil.copy2(cfg, cfg.with_suffix(cfg.suffix + ".coco-bak"))
    except Exception:
        pass


def dig(cfg, key: str, default=None):
    """按点号路径取值（纯函数，便于单测）。"""
    cur = cfg
    for part in key.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


def effective_values() -> "dict[str, object]":
    """运行时**实际生效**的值（Hermes load_config：默认值深合并 + 用户配置覆盖）。"""
    from hermes_cli.config import load_config

    cfg = load_config()
    return {key: dig(cfg, key) for key in STANDARD}


def _state_path():
    """对齐状态文件（记录"我们上次写进去的值"），放在用户配置旁边 —— 未跟踪，更新不碰。"""
    from pathlib import Path

    from hermes_cli.config import get_config_path

    return Path(get_config_path()).parent / ".coco_config_aligned.json"


def _read_state() -> dict:
    import json

    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(written: dict) -> None:
    import json
    from datetime import datetime

    try:
        with open(_state_path(), "w", encoding="utf-8") as fh:
            json.dump({"written": written, "updated_at": datetime.now().isoformat(timespec="seconds")},
                      fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _same(a, b) -> bool:
    """数值容忍比较（0.8 与 0.8000000000000001 视为相同）"""
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return False


def plan(effective: "dict[str, object] | None" = None, state: "dict | None" = None):
    """决定每个键怎么处理。返回 (to_align, preserved)：

    - to_align: [(key, 当前值, 标准值), ...] —— 需要写入标准值
    - preserved: [(key, 当前值), ...] —— **经纪人自己改过，保留不动**

    判定规则（2026-09-19 老板拍板："经纪人改过就不动"）：
    1. 没有状态文件（首次对齐，含存量实例） → 一律对齐（这是修复"设定失效"的初衷）
    2. 有状态文件：
       - 当前值 == 标准值            → 不动（顺带刷新状态）
       - 当前值 == 我们上次写的值     → 我们在升级标准值 → 对齐
       - 当前值 ∉ {标准值, 上次写的}  → **经纪人改的 → 保留**
       - 当前值缺失/为空             → 对齐（补上）
    """
    effective = effective_values() if effective is None else effective
    state = _read_state() if state is None else state
    last_written = dict(state.get("written") or {})
    first_run = not last_written

    to_align, preserved = [], []
    for key, want in STANDARD.items():
        got = effective.get(key)
        if _same(got, want):
            continue
        if got in (None, "") or first_run:
            to_align.append((key, got, want))
            continue
        if _same(got, last_written.get(key)):
            to_align.append((key, got, want))     # 我们的标准升级了
            continue
        preserved.append((key, got))              # 经纪人自己改的 → 保留
    return to_align, preserved


def diffs(effective: "dict[str, object] | None" = None):
    """返回 [(key, 生效值, 标准值), ...]；已一致则空列表。"""
    effective = effective_values() if effective is None else effective
    out = []
    for key, want in STANDARD.items():
        got = effective.get(key)
        if not _same(got, want):
            out.append((key, got, want))
    return out


def apply(verbose: bool = False, force: bool = False) -> "list[tuple[str, object, object]]":
    """把标准值写入 config.yaml；返回被修正的 [(key, 旧值, 新值), ...]。

    force=True（或 COCO_FORCE_CONFIG=1）：无视"经纪人改过"的保护，一律拉回标准值。
    """
    from hermes_cli.config import set_config_value

    force = force or os.environ.get("COCO_FORCE_CONFIG") == "1"
    state = _read_state()
    written = dict(state.get("written") or {})
    effective = effective_values()

    if force:
        items = diffs(effective)
        preserved = []
    else:
        items, preserved = plan(effective, state)

    changed = []
    if items:
        _backup_config()
    for key, got, want in items:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            set_config_value(key, str(want))
        changed.append((key, got, want))
        if verbose:
            print(buf.getvalue(), end="")
    # 状态文件记录"我们写了什么"，下次才能区分"我们写的"与"经纪人改的"
    for key, _got, want in changed:
        written[key] = want
    for key, want in STANDARD.items():
        if key not in written and _same(effective.get(key), want):
            written[key] = want
    if changed or preserved:
        _write_state(written)
    if preserved:
        names = "；".join(f"{LABELS.get(k, k)}={v}" for k, v in preserved)
        print(f"  已保留你自行调整的设置（未拉回标准值）：{names}")
    return changed


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv
    verbose = "--verbose" in argv
    force = "--force" in argv or os.environ.get("COCO_FORCE_CONFIG") == "1"

    try:
        if check_only:
            to_align, preserved = plan()
            for key, got, want in to_align:
                print(f"  {key}: 生效 {got!r} ≠ 标准 {want!r}（{LABELS.get(key, '')}）")
            for key, got in preserved:
                print(f"  {LABELS.get(key, key)}: {got!r}（经纪人自行调整，已保留）")
            return 1 if to_align else 0
        changed = apply(verbose=verbose, force=force)
    except Exception as exc:  # 配置读不到/写不进时不能拖垮安装与更新
        print(f"  提示: 配置对齐未完成（{exc}）")
        return 2

    if changed:
        for key, got, want in changed:
            print(f"  已对齐 {LABELS.get(key, key)}: {got} → {want}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
