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


def diffs(effective: "dict[str, object] | None" = None):
    """返回 [(key, 生效值, 标准值), ...]；已一致则空列表。"""
    effective = effective_values() if effective is None else effective
    out = []
    for key, want in STANDARD.items():
        got = effective.get(key)
        # 数值容忍：YAML 里 0.8 可能是 0.8000000000000001 之类的浮点误差
        same = got == want
        if not same and isinstance(got, (int, float)) and isinstance(want, (int, float)):
            same = abs(float(got) - float(want)) < 1e-9
        if not same:
            out.append((key, got, want))
    return out


def apply(verbose: bool = False) -> "list[tuple[str, object, object]]":
    """把标准值写入 config.yaml；返回被修正的 [(key, 旧值, 新值), ...]。"""
    from hermes_cli.config import set_config_value

    changed = []
    effective = effective_values()
    items = diffs(effective)
    if items:
        _backup_config()
    for key, got, want in items:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            set_config_value(key, str(want))
        changed.append((key, got, want))
        if verbose:
            print(buf.getvalue(), end="")
    return changed


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv
    verbose = "--verbose" in argv

    try:
        if check_only:
            bad = diffs()
            if not bad:
                return 0
            for key, got, want in bad:
                print(f"  {key}: 生效 {got!r} ≠ 标准 {want!r}（{LABELS.get(key, '')}）")
            return 1
        changed = apply(verbose=verbose)
    except Exception as exc:  # 配置读不到/写不进时不能拖垮安装与更新
        print(f"  提示: 配置对齐未完成（{exc}）")
        return 2

    if changed:
        for key, got, want in changed:
            print(f"  已对齐 {LABELS.get(key, key)}: {got} → {want}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
