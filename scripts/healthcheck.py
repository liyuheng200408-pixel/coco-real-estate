#!/usr/bin/env python3
"""Coco 部署健康自检脚本

用法（在服务器上）:
    cd ~/hermes-agent && source venv/bin/activate && python3 scripts/healthcheck.py

覆盖检查项:
    1. 安装目录与代码版本（是否落后远程）
    2. hermes-agent 服务状态
    3. Python 依赖（ddgs 缺失 = web_search 对模型不可见）
    4. web_search 后端可用性（Coco 能否联网查政策）
    5. 数据库连接与数据量
    6. COCO_ENC_KEY 与密钥备份
    7. cron 注册（4 个定时任务）
    8. 技能同步
    9. 磁盘空间
    10. 网关近期日志错误

退出码: 0 = 全部通过/仅警告; 1 = 存在 FAIL 项
"""
import importlib.util
import os
import subprocess
import sys

INSTALL_DIR = os.environ.get("HERMES_AGENT_DIR", os.path.expanduser("~/hermes-agent"))
SERVICE = "hermes-agent"
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
        return r.returncode == 0, r.stdout.strip()
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
             "cd ~/hermes-agent && source venv/bin/activate && git pull && pip install -e . -q && sudo systemctl restart hermes-agent")
    elif rc:
        ok("代码已是最新")
else:
    warn("非 git 目录，跳过版本检查")

# ---- 2. 服务状态 ----
print("\n[2] 服务状态")
rc, _ = sh(f"systemctl is-active --quiet {SERVICE}")
if rc:
    rc2, since = sh(f"systemctl show -p ActiveEnterTimestamp --value {SERVICE}")
    ok(f"服务 {SERVICE} 运行中" + (f"（自 {since}）" if rc2 and since else ""))
else:
    bad(f"服务 {SERVICE} 未运行", f"sudo systemctl start {SERVICE} 或 sudo systemctl restart {SERVICE}")

# ---- 3. Python 依赖 ----
print("\n[3] Python 依赖")
PY = os.path.join(INSTALL_DIR, "venv", "bin", "python")
missing = []
for pkg in ("ddgs", "PIL", "qrcode", "lark_oapi", "sqlalchemy", "psycopg2", "cryptography", "apscheduler"):
    if importlib.util.find_spec(pkg) is None:
        missing.append(pkg)
if not missing:
    ok("依赖齐全（ddgs/Pillow/qrcode/lark-oapi/sqlalchemy/psycopg2 等）")
else:
    bad(f"缺少依赖: {', '.join(missing)}",
        "cd ~/hermes-agent && source venv/bin/activate && git pull && pip install -e . -q && sudo systemctl restart hermes-agent")

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
        "确认 ddgs 已装: pip show ddgs; 再重启: sudo systemctl restart hermes-agent")
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
    e = sqlalchemy.create_engine({db_url!r}, connect_args={{'connect_timeout': 5}})
    with e.connect() as c:
        props = c.execute('select count(*) from re_properties').scalar()
        custs = c.execute('select count(*) from re_customers').scalar()
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

# ---- 6. 加密密钥 ----
print("\n[6] 加密密钥")
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

# ---- 7. cron 注册 ----
print("\n[7] 定时任务（cron）")
marker = os.path.join(HERMES_HOME, ".coco_cron_registered")
if os.path.isfile(marker):
    ok("cron 已注册（标记文件存在），含早报/午间/逾期/生日 4 个任务")
else:
    warn("cron 未注册（无标记文件）",
         "重启服务后 gateway 会自动注册: sudo systemctl restart hermes-agent")

# ---- 8. 技能同步 ----
print("\n[8] 技能同步")
skill = os.path.join(HERMES_HOME, "skills", "real_estate", "SKILL.md")
if os.path.isfile(skill):
    ok("Coco 操作手册技能已同步")
else:
    warn("技能未同步", "重启服务后 gateway 自动同步: sudo systemctl restart hermes-agent")

# ---- 9. 磁盘空间 ----
print("\n[9] 磁盘空间")
rc, out = sh("df -P / | awk 'NR==2{print $4}'")
if rc and out.isdigit():
    free_mb = int(out) // 1024
    if free_mb > 2048:
        ok(f"磁盘可用 {free_mb} MB")
    else:
        warn(f"磁盘可用仅 {free_mb} MB", "清理空间，避免备份/日志写满")
else:
    warn("无法读取磁盘空间")

# ---- 10. 网关日志 ----
print("\n[10] 网关近期日志（最近 200 行）")
rc, out = sh(f"journalctl -u {SERVICE} -n 200 --no-pager 2>/dev/null")
if rc and out:
    errs = [l for l in out.splitlines() if "ERROR" in l or "Traceback" in l]
    if errs:
        warn(f"近期日志有 {len(errs)} 处错误/异常", "sudo journalctl -u hermes-agent -n 100 --no-pager 查看详情并发给技术顾问")
    else:
        ok("近期日志无错误")
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
