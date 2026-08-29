#!/usr/bin/env bash
# =============================================================================
# Coco（可可）房产机器人 · 一键无损更新脚本
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

info "[1/7] 前置检查：git 工作区"
if [[ -n "$(git status --porcelain)" ]]; then
  # 允许"未跟踪"运行时文件（.env.db / 缓存等）；但"已跟踪文件被改动"则拒绝，避免覆盖
  if [[ -n "$(git status --porcelain | grep -vE '^\?\?')" ]]; then
    err "检测到已跟踪文件的本地改动。为避免覆盖/丢失，请先提交或 stash 后再更新。"
    git status --short
    exit 1
  fi
fi
ok "工作区干净；本脚本绝不运行 git clean（不删 .env.db / 加密密钥等未跟踪文件）"

info "[2/7] 备份数据库（安全网，可回滚到更新前）"
if [[ "$SKIP_BACKUP" == "1" ]]; then
  echo "  已跳过备份（--skip-backup）"
else
  "$VENV_PY" scripts/backup_db.py backup
  ok "已生成恢复点（~/backups/real_estate/）"
fi

info "[3/7] 拉取最新代码（git pull --ff-only）"
git pull --ff-only
ok "代码已更新"

info "[4/7] 安装 / 更新 Python 依赖（pip install -e .）"
"$VENV_PY" -m pip install -e . -q
ok "依赖已就绪"

info "[5/7] 应用数据库迁移（只增不删、事务、失败回滚）"
"$VENV_PY" scripts/migrate.py
ok "数据库迁移检查完成（若提示'数据库已是最新'即无表结构变更）"

info "[6/7] 部署健康自检"
"$VENV_PY" scripts/healthcheck.py || echo "  警告：健康自检存在 FAIL 项，请查看上方提示"

info "[7/7] 重启服务（以 hermes-gateway 用户服务为准，兼容 hermes-agent）"
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
      ok "已重启 hermes-agent.service（系统服务）"
      RESTARTED=1
    fi
  fi
  if [[ "$RESTARTED" == "0" ]]; then
    err "未检测到在运行的 hermes-gateway / hermes-agent 服务，请手动重启以加载新代码。"
  fi
fi

echo ""
ok "无损更新完成。若本次更新涉及表结构，数据库已通过迁移升级，旧数据全部保留。"
