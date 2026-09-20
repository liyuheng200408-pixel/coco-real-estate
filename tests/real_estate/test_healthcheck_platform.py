"""部署体检的平台分支契约测试（Windows 本机模式 vs Linux 服务器）。

为什么要有：体检一旦误报，用户就不信它了。Windows 本机模式没有 systemd、没有
journalctl、没有 df —— 照 Linux 口径查会把一个正常工作着的部署判成故障。

这里只测 `scripts/healthcheck_lib.py` 里的纯函数（healthcheck.py 自身是扁平脚本，
import 会真的跑一遍体检并可能 sys.exit，不能直接 import）。平台一律当参数传入，
所以在 Linux CI 上也能守住 Windows 分支的行为。
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import healthcheck_lib as lib  # noqa: E402


def test_platform_defaults_follow_each_platform_layout():
    win_install, win_home = lib.platform_defaults("win32", {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"})

    assert win_home == os.path.join(r"C:\Users\me\AppData\Local", "hermes")
    assert win_install == os.path.join(win_home, "hermes-agent")

    # 没有 LOCALAPPDATA 时退回 USERPROFILE/AppData/Local（与官方安装器一致）
    win_install2, win_home2 = lib.platform_defaults("win32", {"USERPROFILE": r"C:\Users\me"})

    assert win_home2.endswith(os.path.join("AppData", "Local", "hermes"))
    assert win_install2.endswith(os.path.join("hermes", "hermes-agent"))

    linux_install, linux_home = lib.platform_defaults("linux", {})

    assert linux_install == os.path.expanduser("~/hermes-agent")
    assert linux_home == os.path.expanduser("~/.hermes")


def test_python_in_venv_matches_platform_layout():
    assert lib.python_in_venv(r"C:\hermes\hermes-agent", "win32").endswith(os.path.join("venv", "Scripts", "python.exe"))
    assert lib.python_in_venv("/opt/hermes-agent", "linux").endswith(os.path.join("venv", "bin", "python"))


def test_service_probe_plan_splits_systemd_from_windows_local():
    assert lib.service_probe_plan("linux") == "systemd"
    assert lib.service_probe_plan("darwin") == "systemd"
    assert lib.service_probe_plan("win32") == "windows-local"


def test_python_argv_never_uses_shell_quoting():
    """带引号的 URL/代码必须靠参数列表传，不能拼成 shell 命令行（Windows 会吃掉引号）"""
    url = 'postgresql://hermes:pw@127.0.0.1:5432/hermes_agent'

    argv = lib.python_argv('C:\\venv\\Scripts\\python.exe', ['scripts/migrate.py', '--database-url', url, '--status'])

    assert argv[0].endswith('python.exe')
    assert url in argv, '连接串必须是独立参数，而不是被引号包在一整条命令里'
    assert not any(' ' in a and 'postgresql://' in a for a in argv), '不能把 URL 拼进带空格的命令串'

    snippet = lib.python_argv('/usr/bin/python', 'print("hi")')
    assert snippet[1] == '-c'
    assert snippet[2] == 'print("hi")'


def test_windows_probes_avoid_posix_commands():
    proc_cmd = lib.windows_process_command()

    assert "Get-CimInstance Win32_Process" in proc_cmd
    assert "pgrep" not in proc_cmd

    pg_ctl, pg_data = lib.windows_database_status_command(os.path.join("C:", "hermes"))

    assert pg_ctl.endswith(os.path.join("pgsql", "bin", "pg_ctl.exe"))
    assert pg_data.endswith("pgsql-data")


def test_windows_log_paths_list_desktop_log_first():
    paths = lib.windows_log_paths(os.path.join("C:", "hermes"))

    assert paths[0].endswith(os.path.join("logs", "desktop.log"))
    assert any(p.endswith(os.path.join("logs", "gateway.log")) for p in paths)
    assert len(paths) == len(set(paths))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("China Standard Time\r\n", "Asia/Shanghai"),
        ("China Standard Time", "Asia/Shanghai"),
        ("Taipei Standard Time", "Asia/Taipei"),
        # 不认识的照原样返回，不要瞎映射成北京时间
        ("UTC", "UTC"),
        ("", ""),
        (None, ""),
    ],
)
def test_parse_tzutil_normalizes_windows_timezone_names(raw, expected):
    assert lib.parse_tzutil(raw) == expected


def test_timezone_fix_command_is_platform_appropriate():
    assert 'tzutil /s "China Standard Time"' == lib.timezone_fix_command("win32")
    assert "timedatectl set-timezone Asia/Shanghai" in lib.timezone_fix_command("linux")


def test_log_noise_filter_still_skips_restart_noise():
    """重启时飞书长连接正常断开的噪音必须继续被排除（2026-09-18 定的口径）"""
    log = "\n".join(
        [
            # 独立噪音行
            "2026-09-20 10:00:00 ERROR Task exception was never retrieved",
            # 噪音块：Traceback 后面紧跟的 12 行里出现噪音特征 → 整块跳过
            "Traceback (most recent call last):",
            "  File \"lark/ws/client.py\", line 42, in _run",
            "    ConnectionClosed",
            # 真正的运行期错误（必须被报出来）
            "2026-09-20 10:01:00 ERROR 真正的运行期错误：tool dispatch failed",
            # 真实错误附近的 Traceback 不含噪音 → 要算命中
            "Traceback (most recent call last):",
            "  File \"tools/registry.py\", line 7, in dispatch",
            "KeyError: missing required param",
        ]
    )

    hits = lib.scan_gateway_log(log)

    assert len(hits) == 2, hits
    assert "真正的运行期错误" in hits[0]
    # 第二个 Traceback 不在噪音块里 → 要报出来（说明不是无脑跳过所有 Traceback）
    assert hits[1].startswith("Traceback")


def test_scan_gateway_log_tolerates_empty_input():
    assert lib.scan_gateway_log("") == []
    assert lib.scan_gateway_log(None) == []


def test_disk_space_falls_back_when_df_is_unavailable():
    """Windows 上没有 df —— 体检要能退回 shutil 问系统（这里只验证回退本身可用）"""
    probes = []

    def fake_sh(cmd, timeout=15):
        probes.append(cmd)
        return (False, "") if "df -P" in cmd else (True, "")

    def disk_free_mb(platform: str) -> int:
        # 复刻第 11 项的逻辑：非 Windows 先试 df，拿不到就 shutil
        if not platform.startswith("win"):
            rc, out = fake_sh("df -P / | awk 'NR==2{print $4}'")
            if rc and out.isdigit():
                return int(out) // 1024
        return int(shutil.disk_usage(str(Path(__file__).resolve().parents[2])).free / (1024 * 1024))

    assert disk_free_mb("win32") > 0
    assert not any("df -P" in p for p in probes), "Windows 分支不该调 df"

    probes.clear()
    assert disk_free_mb("linux") > 0
    assert any("df -P" in p for p in probes)
