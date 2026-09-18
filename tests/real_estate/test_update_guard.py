"""更新类命令拦截（tools/real_estate_update_guard.py）测试

背景：Coco 在飞书会话里有 terminal 工具；如果她自己去执行更新命令，要么跑官方更新
（跳过我们的数据库迁移、可能覆盖手改代码），要么重启网关把自己也杀掉（更新半截 + 打断对话）。
所以终端层硬拦截，并把正确做法（让经纪人在服务器执行）回给她。
"""
from __future__ import annotations

import json

import pytest

from tools.real_estate_update_guard import coco_update_block, is_update_command

try:  # 终端工具依赖较多（含 requests）；开发环境缺依赖时跳过"接线"用例，不误报
    import tools.terminal_tool as terminal_tool
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    terminal_tool = None
    _IMPORT_ERROR = exc

BLOCKED_CASES = [
    "hermes update",
    "hermes update --yes",
    "sudo hermes update",
    "bash /home/ubuntu/hermes-agent/scripts/update.sh",
    "bash ~/hermes-agent/scripts/update.sh",
    "cd ~/hermes-agent && bash scripts/update.sh",
    "/home/ubuntu/hermes-agent/scripts/update.sh",
    "sh scripts/update.sh",
    "curl -fsSL https://gitee.com/x/y/raw/master/install.sh -o install.sh && bash install.sh",
    "bash install.sh",
    "hermes gateway restart",
    "hermes gateway stop",
    "systemctl --user restart hermes-gateway",
    "systemctl --user restart hermes-gateway.service",
    "sudo systemctl stop hermes-gateway",
    "git -C ~/hermes-agent pull",
    "git -C /home/ubuntu/hermes-agent reset --hard",
    "cd /home/ubuntu/hermes-agent && git pull",
]

ALLOWED_CASES = [
    "ls -la ~/hermes-agent",
    "cat ~/hermes-agent/VERSION",
    "bash ~/hermes-agent/scripts/healthcheck.py",
    "~/hermes-agent/venv/bin/python ~/hermes-agent/scripts/healthcheck.py",
    "psql \"$(sed -n 's/^DATABASE_URL=//p' ~/hermes-agent/.env.db)\" -c 'SELECT 1'",
    "systemctl --user status hermes-gateway",
    "journalctl --user -u hermes-gateway -n 50 --no-pager",
    "git -C ~/blog status",
    "git -C ~/my-other-project pull",
    "python3 -c 'print(1)'",
]


def test_update_commands_are_blocked():
    for command in BLOCKED_CASES:
        assert is_update_command(command), f"应拦截：{command}"
        result = coco_update_block(command=command)
        assert result, f"应返回拦截信息：{command}"
        payload = json.loads(result)
        assert payload["status"] == "blocked"
        assert "update.sh" in payload["error"]
        assert "服务器" in payload["error"]


def test_normal_commands_pass_through():
    for command in ALLOWED_CASES:
        assert not is_update_command(command), f"不应拦截：{command}"
        assert coco_update_block(command=command) is None


def test_coco_block_ignores_unknown_kwargs():
    """与上游守卫同签名用法：多传无关关键字参数也不能炸"""
    assert coco_update_block(command="ls", env=None, env_type="local", whatever=1) is None
    assert coco_update_block(command="hermes update", env=None, env_type="local") is not None


def test_empty_command_is_safe():
    assert not is_update_command("")
    assert coco_update_block(command="") is None


@pytest.mark.skipif(terminal_tool is None, reason=f"终端工具依赖不可用：{_IMPORT_ERROR}")


def test_wired_into_terminal_tool_pre_exec_block():
    """守卫必须真的接在终端工具的前置拦截里（上游同步冲掉时这条会失败）"""
    assert hasattr(terminal_tool, "coco_update_block"), "terminal_tool 未导入更新拦截守卫"
    assert terminal_tool.coco_update_block is coco_update_block
    assert terminal_tool.coco_update_block(command="hermes update") is not None
