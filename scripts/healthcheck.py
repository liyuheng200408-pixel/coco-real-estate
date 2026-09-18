#!/usr/bin/env python3
"""Coco 部署健康自检脚本

用法（在服务器上）:
    ~/hermes-agent/venv/bin/python ~/hermes-agent/scripts/healthcheck.py

覆盖检查项:
    1. 安装目录与代码版本（是否落后远程）
    2. hermes-gateway 服务状态（用户服务，备选 hermes-agent 系统服务）
    3. Python 依赖（ddgs 缺失 = web_search 对模型不可见）
    4. web_search 后端可用性（Coco 能否联网查政策）
    5. 数据库连接与数据量
    6. 数据库结构是否已是最新（有无待执行迁移）
    7. COCO_ENC_KEY 与密钥备份
    8. 备份新鲜度（最新 dump 是否 <48h，2026-08-12 加）
    9. 定时任务注册（早报/午间/逾期 3 个，默认关闭属预期）
    10. 技能同步
    11. 磁盘空间
    12. 网关运行期日志错误（已排除"重启导致飞书长连接正常断开"的噪音）

退出码: 0 = 全部通过/仅警告; 1 = 存在 FAIL 项
"""
import importlib.util
import os
import subprocess
import sys
import time

INSTALL_DIR = os.environ.get("HERMES_AGENT_DIR", os.path.expanduser("~/hermes-agent"))
# 主服务是官方 hermes gateway install 生成的用户服务 hermes-gateway —— 真正连飞书的就是它
# （2026-09-16 老板重装实测：重启系统服务 hermes-agent 机器人无响应，重启这个才响应）。
# 备选是旧版 install.sh 自建的系统服务 hermes-agent，兼容尚未收口的老部署。
# 顺序：先查用户服务 hermes-gateway，再查系统服务 hermes-agent。
SERVICE = "hermes-gateway"
SERVICE_USER = True  # 用户服务需 systemctl --user
SERVICE_FALLBACK = "hermes-agent"  # 旧版自建系统服务
SERVICE_FALLBACK_USER = False
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))

PASS = FAIL = WARN = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg, hint=""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")
    if hint:
        print(f"         修复: {hint}")


def warn(msg, hint=""):
    global WARN
    WARN += 1
    print(f"  [WARN] {msg}")
    if hint:
        print(f"         建议: {hint}")


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        if r.stderr.strip():
            out = out + "\n" + r.stderr.strip()
        return r.returncode == 0, out
    except Exception as e:
        return False, str(e)


def env_file_get(path, key):
    """读取 EnvironmentFile(.env.db) 里的 KEY=VALUE"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


print("=" * 56)
print(f" Coco 部署健康自检  {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S}")
print(f" 安装目录: {INSTALL_DIR}")
print("=" * 56)

# ---- 1. 安装目录与代码版本 ----
print("\n[1] 安装目录与代码版本")
if not os.path.isdir(INSTALL_DIR):
    bad(f"安装目录不存在: {INSTALL_DIR}", "先执行一键安装 install.sh")
    print("\n汇总: PASS=%d FAIL=%d WARN=%d" % (PASS, FAIL, WARN))
    sys.exit(1)
ok(f"安装目录存在 {INSTALL_DIR}")

if os.path.isdir(os.path.join(INSTALL_DIR, ".git")):
    rc, cur = sh(f"git -C {INSTALL_DIR} rev-parse --short HEAD")
    if rc:
        print(f"        当前提交: {cur}")
    sh(f"git -C {INSTALL_DIR} fetch -q origin 2>/dev/null", timeout=30)
    rc, behind = sh(f"git -C {INSTALL_DIR} rev-list --count HEAD..origin/master 2>/dev/null")
    if rc and behind.isdigit() and int(behind) > 0:
        warn(f"代码落后远程 {behind} 个提交",
             "git -C ~/hermes-agent pull && bash ~/hermes-agent/scripts/update.sh")
    elif rc:
        ok("代码已是最新")
else:
    warn("非 git 目录，跳过版本检查")

# ---- 2. 服务状态 ----
print("\n[2] 服务状态")
_user = "--user " if SERVICE_USER else ""
rc, _ = sh(f"systemctl {_user}is-active --quiet {SERVICE}")
if rc:
    rc2, since = sh(f"systemctl {_user}show -p ActiveEnterTimestamp --value {SERVICE}")
    ok(f"服务 {SERVICE} 运行中" + (f"（自 {since}）" if rc2 and since else ""))
else:
    # 主服务未运行，查备选系统服务（旧版 install.sh 自建的那个）
    _fb_user = "--user " if SERVICE_FALLBACK_USER else ""
    rc3, _ = sh(f"systemctl {_fb_user}is-active --quiet {SERVICE_FALLBACK}")
    if rc3:
        rc4, since2 = sh(f"systemctl {_fb_user}show -p ActiveEnterTimestamp --value {SERVICE_FALLBACK}")
        warn(
            f"主服务 {SERVICE}（用户服务）未运行，但备选 {SERVICE_FALLBACK}（旧版系统服务）运行中",
            f"推荐统一用 {SERVICE}：systemctl --user restart {SERVICE}；"
            f"若两者并存会互相抢 bot token（2026-08-12 事故），停掉一个",
        )
        if rc4 and since2:
            print(f"        {SERVICE_FALLBACK} 自 {since2} 运行")
    else:
        bad(
            f"服务 {SERVICE}（用户服务）与 {SERVICE_FALLBACK}（旧版系统服务）均未运行",
            f"先 hermes gateway install 再 systemctl --user start {SERVICE}；"
            f"查看状态: systemctl --user status {SERVICE}",
        )

# ---- 3. Python 依赖 ----
print("\n[3] Python 依赖")
PY = os.environ.get("COCO_PYTHON", os.path.join(INSTALL_DIR, "venv", "bin", "python"))
missing = []
for pkg in ("ddgs", "PIL", "qrcode", "lark_oapi", "sqlalchemy", "psycopg2", "cryptography", "apscheduler"):
    if importlib.util.find_spec(pkg) is None:
        missing.append(pkg)
if not missing:
    ok("依赖齐全（ddgs/Pillow/qrcode/lark-oapi/sqlalchemy/psycopg2 等）")
else:
    bad(f"缺少依赖: {', '.join(missing)}",
        "git -C ~/hermes-agent pull && bash ~/hermes-agent/scripts/update.sh")

# ---- 4. web_search 可用性 ----
print("\n[4] web_search 联网搜索后端")
ws_state = "ERR"
try:
    sys.path.insert(0, INSTALL_DIR)
    from tools.web_tools import check_web_api_key

    ws_state = "OK" if check_web_api_key() else "NO"
except Exception as e:
    ws_state = "ERR:" + str(e)[:120]
if ws_state == "OK":
    ok("web_search 后端可用，Coco 可联网查最新政策")
elif ws_state == "NO":
    bad("web_search 不可用（未检测到搜索后端），Coco 只能回复'未收录'",
        "确认 ddgs 已装: pip show ddgs; 再重启: systemctl --user restart hermes-gateway.service")
else:
    warn(f"web_search 检查异常: {ws_state}", "把以下日志发技术顾问")

# ---- 5. 数据库 ----
print("\n[5] 数据库连接")
env_path = os.path.join(INSTALL_DIR, ".env.db")
db_url = env_file_get(env_path, "DATABASE_URL") if os.path.isfile(env_path) else None
if db_url:
    db_code = f"""
import sqlalchemy
try:
    kw = {{'connect_args': {{'connect_timeout': 5}}}} if {db_url.startswith('postgresql')!r} else {{}}
    e = sqlalchemy.create_engine({db_url!r}, **kw)
    with e.connect() as c:
        props = c.execute(sqlalchemy.text('select count(*) from re_properties')).scalar()
        custs = c.execute(sqlalchemy.text('select count(*) from re_customers')).scalar()
    print(f'OK props={{props}} custs={{custs}}')
except Exception as ex:
    print('ERR:' + str(ex)[:120])
"""
    rc, out = sh(f"{PY} -c {__import__('shlex').quote(db_code)}", timeout=20)
    if rc and out.startswith("OK"):
        ok(f"数据库连接正常（房源 {out.split('props=')[1].split()[0]} 条，客户 {out.split('custs=')[1]} 条）")
    else:
        bad(f"数据库连接失败: {out[:120]}", "检查 PostgreSQL 是否运行: sudo systemctl status postgresql")
else:
    warn("未读取到 DATABASE_URL（.env.db 缺失或未配置）",
         "重跑 install.sh 或检查 $INSTALL_DIR/.env.db")

# ---- 6. 数据库迁移状态 ----
print("\n[6] 数据库迁移")
if db_url:
    mig_rc, mig_out = sh(f"{PY} {INSTALL_DIR}/scripts/migrate.py --database-url {__import__('shlex').quote(db_url)} --status", timeout=20)
    if mig_rc and "待执行: 0" in mig_out:
        ok("数据库结构已是最新（无待执行迁移）")
    elif mig_rc:
        pending_count = [l for l in mig_out.splitlines() if "待执行" in l]
        bad(f"有未执行的迁移", f"执行 python3 scripts/migrate.py 应用: {pending_count}")
    else:
        warn(f"迁移状态查询失败: {mig_out[:100]}", "手动执行 python3 scripts/migrate.py --status 查看")
else:
    warn("跳过迁移检查（无 DATABASE_URL）")

# ---- 7. 加密密钥 ----
print("\n[7] 加密密钥")
enc_key = env_file_get(env_path, "COCO_ENC_KEY") if os.path.isfile(env_path) else None
if enc_key:
    ok("COCO_ENC_KEY 已配置（客户手机号/微信加密正常）")
else:
    bad("COCO_ENC_KEY 未配置", "install.sh 会自动生成；确认 .env.db 存在且含 COCO_ENC_KEY")
key_backup = os.path.expanduser("~/backups/real_estate/enc_key.txt")
if os.path.isfile(key_backup):
    ok("密钥备份存在 ~/backups/real_estate/enc_key.txt")
else:
    warn("密钥备份不存在", "密钥丢失将无法解密客户手机号，尽快备份到安全位置")

# ---- 8. 备份新鲜度 ----（2026-08-12 加）
print("\n[8] 备份新鲜度")
backup_dir = os.path.expanduser("~/backups/real_estate")
dumps = []
if os.path.isdir(backup_dir):
    dumps = [f for f in os.listdir(backup_dir) if f.endswith(".dump")]
if not dumps:
    warn("无任何数据库备份", "立即执行: python3 scripts/backup_db.py backup --force；建议配置每日自动备份")
else:
    newest = max(dumps, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
    age_h = (time.time() - os.path.getmtime(os.path.join(backup_dir, newest))) / 3600
    if age_h <= 48:
        ok(f"最新备份 {newest}（{age_h:.0f} 小时前），备份新鲜")
    else:
        warn(f"备份已过期（最新 {newest}，{age_h:.0f} 小时前 > 48h）",
             "立即执行: python3 scripts/backup_db.py backup --force；检查每日自动备份任务是否失效")

# ---- 9. cron 注册 ----
print("\n[9] 定时任务（cron）")
marker = os.path.join(HERMES_HOME, ".coco_cron_registered")
if os.path.isfile(marker):
    ok("定时任务已注册（早报 09:00 / 午间 13:00 / 逾期每 30 分钟）")
else:
    ok("定时任务默认关闭（省 token，属预期；需要时对 Coco 说一句「开启定时任务」即可）")

# ---- 10. 技能同步 ----
print("\n[10] 技能同步")
skill = os.path.join(HERMES_HOME, "skills", "real_estate", "SKILL.md")
if os.path.isfile(skill):
    ok("Coco 操作手册技能已同步")
else:
    warn("技能未同步", "重启 gateway 服务后会自动同步（hermes gateway restart）")

# ---- 11. 磁盘空间 ----
print("\n[11] 磁盘空间")
rc, out = sh("df -P / | awk 'NR==2{print $4}'")
if rc and out.isdigit():
    free_mb = int(out) // 1024
    if free_mb > 2048:
        ok(f"磁盘可用 {free_mb / 1024:.1f} GB")
    else:
        warn(f"磁盘可用仅 {free_mb / 1024:.1f} GB", "清理空间，避免备份/日志写满")
else:
    warn("无法读取磁盘空间")

# ---- 12. 网关日志 ----
print("\n[12] 网关运行期错误（已排除重启噪音）")
_user = "--user " if SERVICE_USER else ""
rc, out = sh(f"journalctl {_user}-u {SERVICE} -n 200 --no-pager 2>/dev/null")

# 重启会让飞书长连接正常断开（websocket code 1000），lark 库把"正常断开"也记成 ERROR 并附一条
# traceback —— 每次重启固定产生 4 行这类噪音。不排除掉，这一项每次更新后必然 WARN，反而盖住
# 真正的运行期错误（2026-09-18 老板追问"为什么老有这条"后改的口径）。
_LOG_NOISE = (
    "receive message loop exit",
    "ConnectionClosed",
    "Task exception was never retrieved",
    "Shutdown context: signal=",
    "1000 (OK)",
    "Main process exited",
    "Stopping hermes-gateway",
)


def _log_noise(line: str) -> bool:
    return any(p in line for p in _LOG_NOISE)


def _scan_gateway_log(text: str):
    """挑出真正的运行期错误行；紧跟噪音的 Traceback 块整块跳过"""
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines):
        if _log_noise(line):
            continue
        if "Traceback" in line:
            if _log_noise("\n".join(lines[i:i + 12])):
                continue
            hits.append(line)
        elif "ERROR" in line:
            hits.append(line)
    return hits


if rc and out:
    errs = _scan_gateway_log(out)
    if errs:
        warn(f"近期日志有 {len(errs)} 处运行期错误",
             f"完整日志: journalctl {_user}-u {SERVICE} -n 200 --no-pager")
        for line in errs[-3:]:
            print(f"         {line.strip()[:150]}")
    else:
        ok("近期日志无运行期错误（重启时的飞书断开噪音已排除）")
else:
    warn("无法读取服务日志")

# ---- 汇总 ----
print("\n" + "=" * 56)
print(f" 汇总: PASS {PASS}  /  FAIL {FAIL}  /  WARN {WARN}")
if FAIL == 0:
    print(" 结论: 部署健康" + ("（有几项建议关注）" if WARN else "，一切正常"))
else:
    print(f" 结论: 存在 {FAIL} 个问题，按上方修复提示处理后再测")
print("=" * 56)
sys.exit(1 if FAIL else 0)
