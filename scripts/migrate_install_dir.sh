#!/usr/bin/env bash
# =============================================================================
# Coco 安装目录迁移（2026-09-21 起新装目录是 ~/coco，老实例用本脚本搬迁）
#
# 为什么需要它：安装目录改名后，下面这些地方还记着旧路径，必须一起处理——
#   ① venv 的可编辑安装记录（pip install -e . 写的是绝对路径）与 venv/bin/* 的 shebang
#   ② systemd 服务单元（ExecStart 里是 <安装目录>/venv/bin/python 绝对路径）
#   ③ 夜间备份 crontab 行（含旧安装目录）
#   ④ coco 命令软链指向
# 任一步失败会**回滚**（把目录移回原位），不会留下半迁移状态。
#
# 用法（必须在服务器终端执行，不要在飞书里让 Coco 代跑）:
#   bash scripts/migrate_install_dir.sh --dry-run        # 先看会做什么
#   bash scripts/migrate_install_dir.sh --yes            # 真正迁移到 ~/coco
#   bash scripts/migrate_install_dir.sh --to /opt/coco --yes   # 迁到自定义目录
# =============================================================================
set -uo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[1;34m'; NC='\033[0m'
info() { echo -e "${YELLOW}==>${NC} $*"; }
ok()   { echo -e "${GREEN}  OK${NC} $*"; }
warn() { echo -e "${YELLOW}  WARN${NC} $*"; }
fail() { echo -e "${RED}  FAIL${NC} $*" >&2; }

SELF="${BASH_SOURCE[0]}"
command -v readlink >/dev/null 2>&1 && SELF="$(readlink -f "$SELF" 2>/dev/null || echo "$SELF")"
OLD_DIR="$(cd "$(dirname "$SELF")/.." && pwd)"
NEW_DIR="$HOME/coco"
DRY_RUN=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --to) NEW_DIR="${2:-}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        -h|--help) sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "未知参数: $1"; exit 1 ;;
    esac
done

echo "========================================"
echo " Coco 安装目录迁移"
echo " 从: $OLD_DIR"
echo " 到: $NEW_DIR"
[[ "$DRY_RUN" == "1" ]] && echo " 模式: 干跑（不做任何改动）"
echo "========================================"

command -v git >/dev/null 2>&1 || { fail "缺少 git"; exit 1; }
git -C "$OLD_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { fail "$OLD_DIR 不是 git 仓库，无法迁移"; exit 1; }
if [[ -n "$(git -C "$OLD_DIR" status --porcelain | grep -vE '^\?\?' || true)" ]]; then
    fail "工作区有未提交的代码改动，先处理再迁移（避免搬动中丢改动）"; exit 1
fi
if [[ "$NEW_DIR" == "$OLD_DIR" ]]; then
    ok "安装目录已经是 $NEW_DIR，无需迁移"; exit 0
fi
if [[ -e "$NEW_DIR" ]]; then
    fail "$NEW_DIR 已存在，请先处理（本脚本不会覆盖已有目录）"; exit 1
fi
if [[ "$DRY_RUN" != "1" && "$ASSUME_YES" != "1" ]]; then
    echo ""
    echo "迁移会：停服务 → 移动目录 → 重装依赖 → 重装服务 → 修夜间备份定时任务 → 体检。"
    echo "期间飞书对话会中断（服务重启）。失败会自动回滚。"
    printf "确认继续请输入 yes: "
    read -r answer || answer=""
    [[ "$(echo "${answer:-}" | tr -d '[:space:]' | tr 'A-Z' 'a-z')" == "yes" ]] || { echo "已取消。"; exit 0; }
fi

if [[ "$DRY_RUN" == "1" ]]; then
    echo ""
    info "干跑：将会执行的动作"
    echo "   1) 停止服务（systemctl --user stop hermes-gateway）"
    echo "   2) 移动目录：$OLD_DIR → $NEW_DIR"
    echo "   3) 修正 venv：重写 venv/bin/* 里的旧路径 + 重装可编辑包（pip install -e .）"
    echo "   4) 重装服务：$NEW_DIR/venv/bin/hermes gateway install --start-now --start-on-login"
    echo "   5) 修夜间备份定时任务里的旧路径"
    echo "   6) 重指 coco 命令软链，移除 hermes 软链"
    echo "   7) 体检（coco check）核对"
    exit 0
fi

# ---------- 1) 停服务 ----------
info "[1/7] 停止服务"
systemctl --user stop hermes-gateway 2>/dev/null || true
sleep 2
ok "已停止（若本来没在跑则忽略）"

# ---------- 2) 移动目录 ----------
info "[2/7] 移动目录"
cd / || true                      # 必须在仓库外，否则 mv 会失败
if ! mv "$OLD_DIR" "$NEW_DIR"; then
    fail "移动目录失败（目标目录可能被占用或权限不足）"; exit 1
fi
ok "已移动：$OLD_DIR → $NEW_DIR"

ROLLBACK_NEEDED=1
rollback() {
    warn "开始回滚：把目录移回 $OLD_DIR"
    systemctl --user stop hermes-gateway 2>/dev/null || true
    mv "$NEW_DIR" "$OLD_DIR" 2>/dev/null || warn "回滚失败，请手动把 $NEW_DIR 移回 $OLD_DIR"
    "$OLD_DIR"/venv/bin/python -m pip install -e "$OLD_DIR" -q >/dev/null 2>&1 || true
    "$OLD_DIR"/venv/bin/hermes gateway install --start-now --start-on-login >/dev/null 2>&1 || true
    rm -rf "$NEW_DIR" 2>/dev/null || true
    fail "迁移失败，已尝试回滚到 $OLD_DIR（请检查上面的错误）"
    exit 1
}

# ---------- 3) 修正 venv ----------
info "[3/7] 修正 venv（shebang 与可编辑安装记录）"
for f in "$NEW_DIR"/venv/bin/*; do
    [[ -f "$f" && ! -L "$f" ]] || continue
    if head -c 2 "$f" 2>/dev/null | grep -q '#!'; then
        sed -i "1s|$OLD_DIR|$NEW_DIR|g" "$f" 2>/dev/null || true
    fi
    sed -i "s|$OLD_DIR|$NEW_DIR|g" "$f" 2>/dev/null || true
done
ok "venv 内可执行文件的路径已更新"
if ! "$NEW_DIR"/venv/bin/python -m pip install -e "$NEW_DIR" -q >/dev/null 2>&1; then
    warn "重装可编辑包失败，改用重建 venv"
    rm -rf "$NEW_DIR/venv"
    if ! python3 -m venv "$NEW_DIR/venv" >/dev/null 2>&1 \
       || ! "$NEW_DIR"/venv/bin/python -m pip install -e "$NEW_DIR" -q >/dev/null 2>&1; then
        rollback
    fi
fi
if "$NEW_DIR"/venv/bin/python -c "import hermes_cli" >/dev/null 2>&1; then
    ok "依赖与导入自检通过"
else
    warn "导入自检未通过，尝试重建 venv"
    rm -rf "$NEW_DIR/venv"
    if python3 -m venv "$NEW_DIR/venv" >/dev/null 2>&1 \
       && "$NEW_DIR"/venv/bin/python -m pip install -e "$NEW_DIR" -q >/dev/null 2>&1 \
       && "$NEW_DIR"/venv/bin/python -c "import hermes_cli" >/dev/null 2>&1; then
        ok "重建 venv 后导入自检通过"
    else
        rollback
    fi
fi

# ---------- 4) 重装服务 ----------
info "[4/7] 重装服务（服务单元里是绝对路径，必须重装）"
if "$NEW_DIR"/venv/bin/hermes gateway install --start-now --start-on-login 2>&1 | tail -4; then
    ok "服务已安装并启动"
else
    warn "服务安装异常 —— 回滚"
    rollback
fi

# ---------- 5) 修夜间备份定时任务 ----------
info "[5/7] 修正夜间备份定时任务"
if command -v crontab >/dev/null 2>&1; then
    CRON_NOW="$(crontab -l 2>/dev/null || true)"
    if printf '%s' "$CRON_NOW" | grep -q "$OLD_DIR"; then
        printf '%s\n' "$CRON_NOW" | sed "s|$OLD_DIR|$NEW_DIR|g" | crontab - \
            && ok "定时任务里的旧路径已更新" || warn "更新 crontab 失败，请手动检查"
    else
        ok "定时任务里没有旧路径"
    fi
fi

# ---------- 6) 软链 ----------
info "[6/7] 修正命令软链"
COCO_BIN="$NEW_DIR/scripts/coco.sh"
if [[ -w /usr/local/bin ]]; then
    ln -sf "$COCO_BIN" /usr/local/bin/coco 2>/dev/null && ok "coco → /usr/local/bin/coco"
else
    mkdir -p "$HOME/.local/bin" && ln -sf "$COCO_BIN" "$HOME/.local/bin/coco" 2>/dev/null && ok "coco → ~/.local/bin/coco"
fi
for _l in /usr/local/bin/hermes "$HOME/.local/bin/hermes"; do
    [[ -L "$_l" ]] || continue
    rm -f "$_l" 2>/dev/null || sudo rm -f "$_l" 2>/dev/null || true
    ok "已移除 hermes 命令入口（统一用 coco）"
done

# ---------- 7) 体检 ----------
info "[7/7] 体检"
sleep 3
if "$NEW_DIR"/venv/bin/python "$NEW_DIR/scripts/healthcheck.py" | tail -6; then
    ok "体检完成（上方结论为准）"
else
    warn "体检有异常，请按提示处理（迁移本身已完成）"
fi

ROLLBACK_NEEDED=0
echo ""
ok "迁移完成：安装目录现在是 $NEW_DIR"
echo "  日常命令：coco version / coco check / coco update"
echo "  更新命令（等价写法）：git -C $NEW_DIR pull && bash $NEW_DIR/scripts/update.sh"
