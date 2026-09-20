"""部署体检用的纯函数库（无副作用，可单测）。

为什么单独成文件：`scripts/healthcheck.py` 是扁平脚本（没有 main 守卫），import 它
会真的跑一遍体检并可能 sys.exit —— 单测没法用。这里放「与宿主无关」的决策函数：
平台默认路径、服务探针选择、时区名归一化、日志噪音过滤等，脚本 import 它们，
测试也能直接断言（不依赖宿主环境）。

约定：凡涉及平台的函数都把 platform 当参数传进来（不读全局），这样在 Linux CI 上
也能守住 Windows 分支的行为。
"""
import os
import sys

# ---- 路径 ----

def platform_defaults(platform: str, env: dict):
    """安装目录与 HERMES_HOME 的平台默认值。

    Linux/macOS 走 ~/hermes-agent 与 ~/.hermes；Windows 桌面版（本机模式）跟着官方
    安装器走 %LOCALAPPDATA%\\hermes 下的同名子目录，与
    hermes_constants._get_platform_default_hermes_home 和 scripts/install.ps1 一致。
    """
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or os.path.join(env.get("USERPROFILE", ""), "AppData", "Local")
        hermes_home = os.path.join(base, "hermes")
        return os.path.join(hermes_home, "hermes-agent"), hermes_home
    return os.path.expanduser("~/hermes-agent"), os.path.expanduser("~/.hermes")


def python_in_venv(install_dir: str, platform: str = sys.platform) -> str:
    """venv 里的解释器：Windows 是 Scripts\\python.exe，其它平台是 bin/python。"""
    if platform.startswith("win"):
        return os.path.join(install_dir, "venv", "Scripts", "python.exe")
    return os.path.join(install_dir, "venv", "bin", "python")


def windows_log_paths(hermes_home: str):
    """Windows 没有 journalctl：按「离运行期多近」列出日志文件候选。"""
    logs = os.path.join(hermes_home, "logs")
    return [
        os.path.join(logs, "desktop.log"),
        os.path.join(logs, "gateway.log"),
        os.path.join(logs, "errors.log"),
    ]


# ---- 服务探针 ----

def service_probe_plan(platform: str) -> str:
    """第 2 项怎么查「服务」：Linux 用 systemd，Windows 本机模式看便携数据库 + 进程。

    为什么必须分：Windows 上没有 systemd，照 Linux 口径查必然 FAIL —— 会把一个
    正常工作着的本机部署判成故障，用户一旦见到误报就不再信体检结果了。
    """
    return "windows-local" if platform.startswith("win") else "systemd"


def windows_process_command() -> str:
    """Windows 没有 pgrep：用 CIM 列出与本机 Hermes / 数据库相关的进程命令行。"""
    return (
        'powershell -NoProfile -Command "Get-CimInstance Win32_Process | '
        "Where-Object { $_.CommandLine -match 'hermes' -or $_.CommandLine -match 'pgsql' } | "
        'Select-Object -ExpandProperty CommandLine"'
    )


def windows_database_status_command(hermes_home: str):
    """返回 (pg_ctl 路径, 数据目录)，供 -D ... status 使用。"""
    return os.path.join(hermes_home, "pgsql", "bin", "pg_ctl.exe"), os.path.join(hermes_home, "pgsql-data")


# ---- 时区 ----

TARGET_TZ = "Asia/Shanghai"

# tzutil 给的是 Windows 时区名，体检口径统一用 IANA 名
_WINDOWS_TZ_ALIASES = {"China Standard Time": "Asia/Shanghai", "Taipei Standard Time": "Asia/Taipei"}


def parse_tzutil(text) -> str:
    """把 `tzutil /g` 的输出归一化成体检口径的时区名；不认识的照原样返回。"""
    lines = (text or "").strip().splitlines()
    name = lines[0].strip() if lines else ""
    return _WINDOWS_TZ_ALIASES.get(name, name)


def timezone_fix_command(platform: str) -> str:
    """时区不对时的修复命令（Windows 用 tzutil，Linux 用 timedatectl）。"""
    if platform.startswith("win"):
        return 'tzutil /s "China Standard Time"'
    return f"sudo timedatectl set-timezone {TARGET_TZ}"


# ---- 日志噪音过滤（2026-09-18 定的口径，别动）----
# 重启会让飞书长连接正常断开（websocket code 1000），lark 库把"正常断开"也记成 ERROR
# 并附一条 traceback —— 每次重启固定产生 4 行噪音。不排除，日志项每次更新后必然 WARN，
# 反而盖住真正的运行期错误。
LOG_NOISE = (
    "receive message loop exit",
    "ConnectionClosed",
    "Task exception was never retrieved",
    "Shutdown context: signal=",
    "1000 (OK)",
    "Main process exited",
    "Stopping hermes-gateway",
)


def log_noise(line: str) -> bool:
    return any(pattern in line for pattern in LOG_NOISE)


def scan_gateway_log(text: str):
    """挑出真正的运行期错误行；紧跟噪音的 Traceback 块整块跳过。"""
    lines = (text or "").splitlines()
    hits = []
    for i, line in enumerate(lines):
        if log_noise(line):
            continue
        if "Traceback" in line:
            if log_noise("\n".join(lines[i:i + 12])):
                continue
            hits.append(line)
        elif "ERROR" in line:
            hits.append(line)
    return hits
