#!/usr/bin/env bash
# =============================================================================
# Coco（可可）房产智能体 · 一键无损更新脚本
#
# 用法（在任何目录都能跑，脚本自己定位仓库根目录）：
#   bash /home/ubuntu/hermes-agent/scripts/update.sh
#   bash scripts/update.sh --skip-backup      # 跳过备份（仅纯代码零风险场景）
#   bash scripts/update.sh --no-restart       # 更新后不自动重启（手动重启）
#
# 设计目标：后续"新增功能"无论纯代码还是动表结构，都用这一条命令无损更新。
# 数据库是用户重要数据，三重硬防护：
#   ① 更新前强制备份（可回滚）
#   ② git 只 pull，绝不跑 git clean（会删 .env.db / 加密密钥）
#   ③ 迁移只增不删、事务内执行失败回滚（由 scripts/migrate.py 校验器硬约束）
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/venv/bin/python"

SKIP_BACKUP=0
NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --skip-backup) SKIP_BACKUP=1 ;;
    --no-restart)  NO_RESTART=1 ;;
    *) echo "未知参数: $arg（支持 --skip-backup / --no-restart）" >&2; exit 1 ;;
  esac
done

info(){ echo -e "\033[1;34m==>\033[0m $*"; }
ok(){   echo -e "\033[1;32m   OK\033[0m $*"; }
err(){  echo -e "\033[1;31m   FAIL\033[0m $*" >&2; }

# ---- 前提检查：venv python 必须存在（说明已跑过 install.sh）----
if [[ ! -x "$VENV_PY" ]]; then
  err "未找到虚拟环境 Python: $VENV_PY"
  echo "  请确认已在仓库目录运行过 install.sh（会创建 venv/）。"
  exit 1
fi

info "[1/8] 前置检查：git 工作区"
if [[ -n "$(git status --porcelain)" ]]; then
  # 允许"未跟踪"运行时文件（.env.db / 缓存等）；但"已跟踪文件被改动"则拒绝，避免覆盖
  if [[ -n "$(git status --porcelain | grep -vE '^\?\?')" ]]; then
    err "检测到已跟踪文件的本地改动。为避免覆盖/丢失，请先提交或 stash 后再更新。"
    git status --short
    exit 1
  fi
fi
ok "工作区干净；本脚本绝不运行 git clean（不删 .env.db / 加密密钥等未跟踪文件）"

info "[2/8] 备份数据库（安全网，可回滚到更新前）"
if [[ "$SKIP_BACKUP" == "1" ]]; then
  echo "  已跳过备份（--skip-backup）"
else
  "$VENV_PY" scripts/backup_db.py backup
  ok "已生成恢复点（~/backups/real_estate/）"
fi

info "[3/8] 拉取最新代码（git pull --ff-only）"
git pull --ff-only
ok "代码已更新"

info "[4/8] 安装 / 更新 Python 依赖（pip install -e .）"
"$VENV_PY" -m pip install -e . -q
ok "依赖已就绪"

info "[5/8] 应用数据库迁移（只增不删、事务、失败回滚）"
"$VENV_PY" scripts/migrate.py
ok "数据库迁移检查完成（若提示'数据库已是最新'即无表结构变更）"

info "[6/8] 迁移配置文件（跟随官方版本升级时需要，非交互式）"
# 官方配置带版本号（_config_version）；底座升级后旧配置会落后（实测 33 → 44）。
# 官方命令 hermes config migrate 是交互式的，在无人值守更新里会卡住，故走本脚本。
"$VENV_PY" scripts/migrate_config.py || echo "  警告：配置迁移步骤异常，不阻断更新"
ok "配置迁移步骤完成"

info "补齐海报字体与渲染器（幂等，已装则跳过）"
bash "$REPO_ROOT/scripts/install_fonts.sh" --quiet || echo "  提示: 字体安装未完成，可重跑 scripts/install_fonts.sh（海报会回落系统字体，不阻塞）"

info "统一时区（北京时间；如需保留原时区可设 COCO_SKIP_TZ=1）"
TARGET_TZ="Asia/Shanghai"
CUR_TZ=""
if command -v timedatectl >/dev/null 2>&1; then
  CUR_TZ="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
fi
if [[ -z "$CUR_TZ" && -f /etc/timezone ]]; then
  CUR_TZ="$(tr -d '[:space:]' < /etc/timezone 2>/dev/null || true)"
fi
if [[ "${COCO_SKIP_TZ:-0}" == "1" ]]; then
  echo "  已跳过（COCO_SKIP_TZ=1）"
elif [[ "$CUR_TZ" == "$TARGET_TZ" ]]; then
  ok "服务器时区已是 $TARGET_TZ"
elif command -v timedatectl >/dev/null 2>&1 && sudo timedatectl set-timezone "$TARGET_TZ" 2>/dev/null; then
  ok "服务器时区已统一为 $TARGET_TZ（当前 $(date '+%Y-%m-%d %H:%M %Z')）"
elif sudo ln -sf "/usr/share/zoneinfo/$TARGET_TZ" /etc/localtime 2>/dev/null; then
  echo "$TARGET_TZ" | sudo tee /etc/timezone >/dev/null 2>&1 || true
  ok "服务器时区已统一为 $TARGET_TZ"
else
  echo "  提示: 未能自动设置时区（可能需要 sudo）。手动: sudo timedatectl set-timezone $TARGET_TZ"
fi
# Coco 标准运行时配置（幂等）：时区 + 轮次上限 + 压缩阈值等，避免被向导/重装冲掉
if "$REPO_ROOT/venv/bin/python" "$REPO_ROOT/scripts/coco_config_align.py"; then
  ok "Coco 标准运行时配置已对齐（时区 / 轮次 500 / 压缩阈值 0.8 / 保留最近 40 条）"
else
  echo "  提示: 运行时配置对齐未完成，可执行 hermes config set 手动设置，或用 hermes config 查看当前值"
fi

info "[7/8] 重启服务（以 hermes-gateway 用户服务为准，兼容 hermes-agent）"
if [[ "$NO_RESTART" == "1" ]]; then
  echo "  已跳过重启（--no-restart），请稍后手动重启。"
else
  RESTARTED=0
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active --quiet hermes-gateway.service 2>/dev/null; then
      systemctl --user restart hermes-gateway.service
      ok "已重启 hermes-gateway.service（用户服务）"
      RESTARTED=1
    elif systemctl is-active --quiet hermes-agent.service 2>/dev/null; then
      sudo systemctl restart hermes-agent.service
      ok "已重启 hermes-agent.service（旧版系统服务）"
      RESTARTED=1
    fi
  fi
  if [[ "$RESTARTED" == "0" ]]; then
    err "未检测到在运行的 hermes-gateway / hermes-agent 服务，请手动重启以加载新代码。"
  fi
  # 体检放在重启之后，读到的才是新进程的状态与日志；服务是 Type=simple，
  # restart 会在进程刚起来时就返回，所以等它真正 active 再体检。
  if [[ "$RESTARTED" == "1" ]]; then
    for _ in $(seq 1 30); do
      systemctl --user is-active --quiet hermes-gateway.service 2>/dev/null && break
      sleep 2
    done
    sleep 5
  fi
fi

info "[8/8] 部署健康自检"
"$VENV_PY" scripts/healthcheck.py || echo "  警告：健康自检存在 FAIL 项，请查看上方提示"

echo ""
# 确保 coco 命令入口存在（新命令靠这条通道分发给已安装实例；幂等，失败不阻断）
COCO_BIN="$REPO_ROOT/scripts/coco.sh"
if [[ -x "$COCO_BIN" ]] && ! command -v coco >/dev/null 2>&1; then
  COCO_LINKED=0
  if [[ -w /usr/local/bin ]] && ln -sf "$COCO_BIN" /usr/local/bin/coco 2>/dev/null; then
    COCO_LINKED=1
  elif command -v sudo >/dev/null 2>&1 && sudo ln -sf "$COCO_BIN" /usr/local/bin/coco 2>/dev/null; then
    COCO_LINKED=1
  else
    mkdir -p "$HOME/.local/bin"
    ln -sf "$COCO_BIN" "$HOME/.local/bin/coco" 2>/dev/null && COCO_LINKED=1
  fi
  if [[ "$COCO_LINKED" == "1" ]]; then
    ok "coco 命令已就绪（coco version 查版本号 / coco check 体检）"
  else
    echo "  提示: coco 命令未创建，可手动执行 sudo ln -sf $COCO_BIN /usr/local/bin/coco"
  fi
fi

# 版本号直接读仓库根 VERSION 文件（2026-08-29 加，与 install.sh 保持一致）：以后只改 VERSION，更新终端自动同步
COCO_VER=$(cat "$REPO_ROOT/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "未知")
# 版本号形如 0.21.3-1：前半段是官方底座，后半段是 Coco 自己的第 N 次发行
COCO_BASE="${COCO_VER%%-*}"
echo -e "版本: \033[1;34mv${COCO_VER}\033[0m  （官方 Hermes ${COCO_BASE} 定制版）"
ok "无损更新完成。若本次更新涉及表结构，数据库已通过迁移升级，旧数据全部保留。"
