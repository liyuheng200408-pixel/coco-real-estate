#!/usr/bin/env bash
# ============================================================================
# portable-postgres.ps1 的 Linux 等价验证（只能在 Linux 上跑，Windows 请用真机）
#
# 为什么需要它：便携包的下载/解压只发生在 Windows；但脚本里「幂等、随机端口、
# 随机口令、只监听回环、.env.db 连接串可被 psql 连上、凭据丢失可恢复」这些逻辑
# 与平台无关。本脚本用系统自带 PG 的 bin 目录（-PgBinDir）替代便携包，在真
# PostgreSQL 上把这部分逐条跑一遍。它验证的是同一个脚本文件，不是复制品。
#
# 用法（必须非 root：initdb 拒绝以 root 运行，与 Windows 的受限令牌同理）：
#   PG_BIN=/usr/lib/postgresql/16/bin PWSH=/opt/pwsh/pwsh \
#     bash apps/desktop/scripts/tests/portable-postgres-linux-e2e.sh
# ============================================================================
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="$REPO_ROOT/apps/desktop/scripts/portable-postgres.ps1"
PWSH="${PWSH:-$(command -v pwsh || true)}"
PG_BIN="${PG_BIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"
WORK="${WORK:-$(mktemp -d /tmp/coco-pg-e2e.XXXXXX)}"
ENVFILE="$WORK/hermes-agent/.env.db"
LOG="$WORK/run.log"
CANARY='e2e-canary'

FAILS=0
PASSES=0
ok() { printf '  [PASS] %s\n' "$1"; PASSES=$((PASSES + 1)); }
bad() { printf '  [FAIL] %s\n' "$1"; FAILS=$((FAILS + 1)); }
section() { printf '\n== %s ==\n' "$1"; }
assert_eq() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1（期望 $3，实际 $2）"; fi }
assert_ne() { if [ "$2" != "$3" ]; then ok "$1"; else bad "$1（两者相同：$2）"; fi }

[ "$(id -u)" -ne 0 ] || { echo '本测试必须用非 root 用户运行（initdb 拒绝 root）'; exit 1; }
[ -n "$PWSH" ] || { echo '找不到 pwsh（PowerShell 7）'; exit 1; }
[ -n "$PG_BIN" ] && [ -x "$PG_BIN/initdb" ] || { echo "找不到 PG bin 目录（PG_BIN=$PG_BIN）"; exit 1; }
[ -f "$SCRIPT" ] || { echo "找不到被测脚本：$SCRIPT"; exit 1; }

envval() { sed -n "s/^$1=//p" "$ENVFILE" 2>/dev/null | tail -1; }
confval() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$WORK/data/postgresql.conf" | tr -d "\"'" | tail -1; }
port_open() { python3 -c "import socket,sys;s=socket.socket();s.settimeout(1.5);sys.exit(0 if s.connect_ex(('$1',$2))==0 else 1)"; }

run_pg() {   # run_pg <期望退出码> <参数...>
    local expect="$1"; shift
    ( cd "$WORK/hermes-agent" && "$PWSH" -NoLogo -NoProfile -File "$SCRIPT" "$@" ) >"$LOG" 2>&1
    RC=$?
    if [ "$RC" != "$expect" ]; then
        bad "脚本退出码 $RC（期望 $expect）：$*"
        sed 's/^/      | /' "$LOG" | tail -30
    fi
    return 0
}

fresh_workspace() {
    rm -rf "$WORK/data" "$WORK/pgsql" "$ENVFILE" "$WORK/pgsql-data"
    mkdir -p "$WORK/hermes-agent/agent"
    # 用仓库里真实的 agent/real_estate_db.py（脚本第 6 步会真的建表）。
    # __init__.py 自建空文件：仓库那份会 import 整个 agent 包的子模块，
    # 单文件复制进来必然 ImportError —— 那是夹具的局限，不是被测逻辑的问题。
    cp "$REPO_ROOT/agent/real_estate_db.py" "$WORK/hermes-agent/agent/"
    : > "$WORK/hermes-agent/agent/__init__.py"
    echo "COCO_ENABLE_CRON=1" >"$ENVFILE"
    echo "MODEL_API_KEY=keep-me" >>"$ENVFILE"
}

base_args=( -PgBinDir "$PG_BIN" -DataRoot "$WORK/pgsql" -DataDir "$WORK/data" -EnvFile "$ENVFILE" -Quiet )

printf '被测脚本 : %s\n' "$SCRIPT"
printf 'PG bin   : %s\n' "$PG_BIN"
printf '工作目录 : %s\n' "$WORK"
printf '真实建表用文件 sha256: %s\n' "$(sha256sum "$REPO_ROOT/agent/real_estate_db.py" | cut -c1-16)"

# ---------------------------------------------------------------------------
section 'T1 首次安装（setup）'
# ---------------------------------------------------------------------------
if [ ! -x "$WORK/venv/bin/python" ]; then
    echo "缺少 $WORK/venv（需要 sqlalchemy + psycopg2-binary + cryptography）"; exit 1
fi
mkdir -p "$WORK/hermes-agent"
ln -sfn "$WORK/venv" "$WORK/hermes-agent/venv"
fresh_workspace
[ -x "$WORK/hermes-agent/venv/bin/python" ] && ok 'venv 就位（脚本第 6 步能建表）' || bad 'venv 软链没建好'
run_pg 0 "${base_args[@]}" -Action setup
[ -f "$ENVFILE" ] && ok '生成 .env.db' || bad '未生成 .env.db'

PORT="$(envval DB_PORT)"; PW="$(envval DB_PASSWORD)"; URL="$(envval DATABASE_URL)"; HOSTV="$(envval DB_HOST)"
assert_eq '.env.db DB_HOST=127.0.0.1' "$HOSTV" '127.0.0.1'
assert_eq '.env.db 库名' "$(envval DB_NAME)" 'hermes_agent'
assert_eq '.env.db 用户' "$(envval DB_USER)" 'hermes'
if [ "${PORT:-0}" -ge 1024 ] && [ "${PORT:-0}" -le 65535 ]; then ok "随机端口落在 1024-65535（$PORT）"; else bad "端口异常：$PORT"; fi
assert_eq '随机口令长度 32' "${#PW}" '32'
case "$PW" in *[!A-Za-z0-9]*) bad '口令含特殊字符（会有 URL 转义风险）' ;; *) ok '口令仅字母数字（URL 安全）' ;; esac
assert_eq 'DATABASE_URL 形状' "$URL" "postgresql://hermes:$PW@127.0.0.1:$PORT/hermes_agent"
assert_eq '既有条目 COCO_ENABLE_CRON 未被破坏' "$(envval COCO_ENABLE_CRON)" '1'
assert_eq '既有条目 MODEL_API_KEY 未被破坏' "$(envval MODEL_API_KEY)" 'keep-me'
assert_eq 'DB_PASSWORD 与 DATABASE_URL 中的口令一致' "$(printf '%s' "$URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')" "$PW"
assert_eq '.env.db 权限 600' "$(stat -c '%a' "$ENVFILE")" '600'
assert_eq 'COCO_ENC_KEY 已生成' "$([ -n "$(envval COCO_ENC_KEY)" ] && echo yes)" 'yes'
assert_eq 'postgresql.conf 监听地址' "$(confval listen_addresses)" '127.0.0.1'
assert_eq '127.0.0.1 可连' "$(port_open 127.0.0.1 "$PORT" && echo yes || echo no)" 'yes'
assert_eq 'pg_hba 只有回环规则' "$(grep -cE '^(host|local)' "$WORK/data/pg_hba.conf")" '2'
assert_eq 'pg_hba 无 0.0.0.0/0 或 trust（忽略注释）' "$(grep -vE '^[[:space:]]*#' "$WORK/data/pg_hba.conf" | grep -cE '0\.0\.0\.0/0|::/0|\btrust\b')" '0'
assert_eq '脚本第 6 步真的建表了' "$(grep -c '数据表已就绪' "$LOG")" '1'
RETABLES="$(PGPASSWORD="$PW" psql -h 127.0.0.1 -p "$PORT" -U hermes -d hermes_agent -tAc "select count(*) from information_schema.tables where table_name like 're\_%'" 2>/dev/null || echo 0)"
if [ "${RETABLES:-0}" -ge 9 ]; then ok "PG 里建成 re_ 业务表 $RETABLES 张（≥9）"; else bad "re_ 业务表只有 $RETABLES 张"; fi
assert_eq '用 .env.db 里的连接串能连上（psql 直连 URL）' "$(psql "$URL" -tAc 'select 1' 2>/dev/null || echo fail)" '1'
assert_eq '错误口令被拒' "$(PGPASSWORD=wrong-password psql -h 127.0.0.1 -p "$PORT" -U hermes -d postgres -tAc 'select 1' >/dev/null 2>&1 && echo accepted || echo rejected)" 'rejected'

LAN_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^127\.' | head -1)"
if [ -n "$LAN_IP" ]; then
    assert_eq "非回环地址 $LAN_IP 连不上" "$(port_open "$LAN_IP" "$PORT" && echo reachable || echo blocked)" 'blocked'
else
    echo '  [SKIP] 本机无非回环 IPv4，跳过外部不可达检查'
fi

# ---------------------------------------------------------------------------
section 'T2 幂等：重复 setup 不重建、不换口令、不动数据'
# ---------------------------------------------------------------------------
pgdata_mtime_before="$(stat -c '%Y' "$WORK/data/PG_VERSION")"
assert_eq 'canary 行已写入业务表' "$(PGPASSWORD="$PW" psql "$URL" -tAc "INSERT INTO re_settings(key, value) VALUES('$CANARY','1')" >/dev/null 2>&1 && echo inserted || echo insert-failed)" 'inserted'
assert_eq '数据表由真实 agent/real_estate_db.py 建出（脚本第 6 步）' "$(grep -c '数据表已就绪' "$LOG")" '1'
run_pg 0 "${base_args[@]}" -Action setup
assert_eq '端口未变' "$(envval DB_PORT)" "$PORT"
assert_eq '口令未变' "$(envval DB_PASSWORD)" "$PW"
assert_eq '连接串未变' "$(envval DATABASE_URL)" "$URL"
assert_eq '数据目录未被重新初始化（PG_VERSION 时间戳不变）' "$(stat -c '%Y' "$WORK/data/PG_VERSION")" "$pgdata_mtime_before"
assert_eq '数据仍在（canary 行）' "$(PGPASSWORD="$PW" psql "$URL" -tAc "select value from re_settings where key='$CANARY'")" '1'
assert_eq '托管块只出现一次' "$(grep -c 'coco-managed (portable-postgres.ps1) - do not edit by hand >>>' "$WORK/data/postgresql.conf")" '1'
assert_eq '生效的 listen_addresses 只有 1 处' "$(grep -cE '^[[:space:]]*listen_addresses' "$WORK/data/postgresql.conf")" '1'
assert_eq '二次运行未重新 initdb' "$(grep -c 'initdb →' "$LOG")" '0'
assert_eq '二次运行复用已有数据目录' "$(grep -c '复用已有数据目录与口令' "$LOG")" '1'

# ---------------------------------------------------------------------------
section 'T3 自检（selftest）'
# ---------------------------------------------------------------------------
run_pg 0 "${base_args[@]}" -Action selftest
assert_eq '自检全绿' "$(grep -c '全部通过' "$LOG")" '1'
assert_eq '自检无 FAIL' "$(grep -c '\[失败\]' "$LOG")" '0'

# ---------------------------------------------------------------------------
section 'T4 端口冲突：服务停掉后端口被别人占用 → 自动改选并同步 .env.db'
# ---------------------------------------------------------------------------
( cd "$WORK/hermes-agent" && "$PWSH" -NoLogo -NoProfile -File "$SCRIPT" "${base_args[@]}" -Action stop ) >/dev/null 2>&1
python3 - "$PORT" >"$WORK/squatter.log" 2>&1 <<'PY' &
import socket, sys, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen(1); time.sleep(180)
PY
SQUATTER=$!
sleep 1
assert_eq "占用者已抢到 $PORT" "$(port_open 127.0.0.1 "$PORT" && echo yes || echo no)" 'yes'
run_pg 0 "${base_args[@]}" -Action setup
NEWPORT="$(envval DB_PORT)"
assert_ne '端口已改选' "$NEWPORT" "$PORT"
assert_eq '新连接串指向新端口' "$(printf '%s' "$(envval DATABASE_URL)" | sed -E 's|.*:([0-9]+)/.*|\1|')" "$NEWPORT"
assert_eq '新端口可连' "$(port_open 127.0.0.1 "$NEWPORT" && echo yes || echo no)" 'yes'
assert_eq '新端口连接串可用（psql 直连）' "$(psql "$(envval DATABASE_URL)" -tAc 'select 1' 2>/dev/null || echo fail)" '1'
assert_eq '数据仍在（canary 行）' "$(PGPASSWORD="$(envval DB_PASSWORD)" psql "$(envval DATABASE_URL)" -tAc "select value from re_settings where key='$CANARY'")" '1'
run_pg 0 "${base_args[@]}" -Action setup
assert_eq '再次 setup 端口稳定（不会每次启动都换端口）' "$(envval DB_PORT)" "$NEWPORT"
kill "$SQUATTER" 2>/dev/null

# ---------------------------------------------------------------------------
section 'T5 凭据丢失 → 明确报错 + reset-password 可恢复（数据不丢）'
# ---------------------------------------------------------------------------
cp "$ENVFILE" "$WORK/env.db.bak"
grep -v -E '^(DB_PASSWORD|DATABASE_URL)=' "$WORK/env.db.bak" >"$ENVFILE"
run_pg 6 "${base_args[@]}" -Action setup
assert_eq '凭据丢失时给出恢复指引（含 reset-password）' "$(grep -c 'reset-password' "$LOG")" '1'
assert_eq '凭据丢失时不静默重建（未 initdb）' "$(grep -c 'initdb →' "$LOG")" '0'
run_pg 0 "${base_args[@]}" -Action reset-password
NEWPW="$(envval DB_PASSWORD)"
assert_ne '口令已更换' "$NEWPW" "$PW"
assert_eq '新口令可连' "$(psql "$(envval DATABASE_URL)" -tAc 'select 1' 2>/dev/null || echo fail)" '1'
assert_eq '恢复后数据仍在' "$(psql "$(envval DATABASE_URL)" -tAc "select value from re_settings where key='$CANARY'" 2>/dev/null)" '1'
assert_eq '恢复后 pg_hba 已复原（无 trust）' "$(grep -vE '^[[:space:]]*#' "$WORK/data/pg_hba.conf" | grep -cE '\btrust\b')" '0'
assert_eq '恢复后自有 hba 备份已清理' "$(ls "$WORK/data" | grep -c 'coco-bak')" '0'
run_pg 0 "${base_args[@]}" -Action selftest
assert_eq '恢复后自检全绿' "$(grep -c '全部通过' "$LOG")" '1'

# ---------------------------------------------------------------------------
section 'T6 status / print-env 机器可读输出'
# ---------------------------------------------------------------------------
run_pg 0 "${base_args[@]}" -Action status -Json
STATUS_JSON="$(tail -1 "$LOG")"
assert_eq 'status 报运行中' "$(printf '%s' "$STATUS_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')" 'running'
assert_eq 'status 端口与 .env.db 一致' "$(printf '%s' "$STATUS_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["port"])')" "$(envval DB_PORT)"
assert_eq 'status 不含口令' "$(printf '%s' "$STATUS_JSON" | grep -c "$(envval DB_PASSWORD)")" '0'
run_pg 0 "${base_args[@]}" -Action print-env
assert_eq 'print-env 输出 6 个键' "$(grep -cE '^(DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD|DATABASE_URL)=' "$LOG")" '6'
assert_eq 'print-env 提示 PATH 注入' "$(grep -c '^PATH_PREPEND=' "$LOG")" '1'
assert_eq 'print-env 的 DATABASE_URL 就是 .env.db 里的' "$(grep '^DATABASE_URL=' "$LOG")" "DATABASE_URL=$(envval DATABASE_URL)"

# ---------------------------------------------------------------------------
section 'T7 停止后重启（模拟机器重启后桌面版再次拉起）'
# ---------------------------------------------------------------------------
run_pg 0 "${base_args[@]}" -Action stop
assert_eq '已停止后端口不再监听' "$(port_open 127.0.0.1 "$(envval DB_PORT)" && echo yes || echo no)" 'no'
run_pg 0 "${base_args[@]}" -Action start
assert_eq '重启后端口不变' "$(envval DB_PORT)" "$NEWPORT"
assert_eq '重启后可用' "$(psql "$(envval DATABASE_URL)" -tAc 'select 1' 2>/dev/null || echo fail)" '1'

# ---------------------------------------------------------------------------
printf '\n================ 结果 ================\n'
printf 'PASS %d / FAIL %d（工作目录 %s）\n' "$PASSES" "$FAILS" "$WORK"
[ "$FAILS" -eq 0 ] || exit 1
