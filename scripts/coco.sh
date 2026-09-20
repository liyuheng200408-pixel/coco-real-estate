#!/usr/bin/env bash
# =============================================================================
# Coco 命令入口
#   用法: coco [命令]        （不给参数 = version）
#     version  查看当前版本（默认）
#     check    部署体检
#     backup   手动备份数据库
#     help     帮助
#
# 为什么需要它：官方 `hermes --version` 显示的是底座（官方 Hermes）版本，
# Coco 自己的版本号存在仓库根目录的 VERSION 文件里。本命令负责把它读出来。
# =============================================================================
set -euo pipefail

# 本脚本会被软链到 /usr/local/bin/coco（或 ~/.local/bin/coco）调用，
# 那时 BASH_SOURCE 是软链路径而不是真实脚本路径 —— 必须先解析软链，否则读不到 VERSION。
SELF="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1 && readlink -f "$SELF" >/dev/null 2>&1; then
  SELF="$(readlink -f "$SELF")"
fi
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
COCO_VER="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION" 2>/dev/null || echo "未知")"
COCO_BASE="${COCO_VER%%-*}"
COCO_COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "未知")"
COCO_BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "")"
COCO_CHANNEL_LABEL="$(bash "$REPO_ROOT/scripts/coco_channel.sh" label "$COCO_BRANCH" 2>/dev/null || echo "")"

case "${1:-version}" in
  version|--version|-v|"")
    echo "Coco v${COCO_VER}（官方 Hermes ${COCO_BASE} 定制版）· 提交 ${COCO_COMMIT}${COCO_CHANNEL_LABEL:+ · ${COCO_CHANNEL_LABEL}}"
    ;;
  check)
    exec "$REPO_ROOT/venv/bin/python" "$REPO_ROOT/scripts/healthcheck.py"
    ;;
  backup)
    exec "$REPO_ROOT/venv/bin/python" "$REPO_ROOT/scripts/backup_db.py" backup
    ;;
  help|--help|-h)
    cat <<EOF
Coco v${COCO_VER}（官方 Hermes ${COCO_BASE} 定制版）

用法: coco <命令>
  version  查看版本号（默认）
  check    部署体检（服务/依赖/数据库/密钥/备份/日志等）
  backup   手动备份数据库
  help     显示本帮助

更新到最新版:
  git -C ~/hermes-agent pull && bash ~/hermes-agent/scripts/update.sh
  （更新只跑这条。不要用 install.sh 更新：它会重建安装目录、清掉数据库密钥与图片缓存；
    也不要直接跑 hermes update：官方更新会重置你手改过的代码。你的本地代码改动会被自动备份。）

说明: Coco 版本号存在 $REPO_ROOT/VERSION；官方 \`hermes --version\` 显示的是底座版本。
EOF
    ;;
  *)
    echo "未知命令: $1" >&2
    echo "用法: coco [version|check|backup|help]" >&2
    exit 1
    ;;
esac
