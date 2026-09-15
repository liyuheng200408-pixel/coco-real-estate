#!/usr/bin/env bash
# =============================================================================
# Coco 同步官方上游 —— 把 Coco 的底座抬到官方新版本
#
# 做什么：
#   1. 下载官方指定版本的完整快照
#   2. 用官方新文件替换本仓库的「官方层」文件
#   3. 【保留】Coco 自有文件（官方快照里没有的，一律不动）
#   4. 【备份】7 个挂钩点文件，并列出需要重新应用改动的位置
#
# 不做什么（安全边界）：
#   · 不动未跟踪的运行时文件（.env.db / 加密密钥 / 缓存）
#   · 不自动删除文件（官方删掉的文件只列出来，由人确认）
#   · 不自动 git commit / push（验收通过后由人/上级流程提交）
#
# 用法：
#   bash scripts/sync_upstream.sh v2026.9.14 --dry-run   # 只演练，不改任何文件
#   bash scripts/sync_upstream.sh v2026.9.14             # 真实执行
# =============================================================================
set -uo pipefail

TAG="${1:-}"
DRY_RUN=0
for arg in "${@:2}"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "未知参数: $arg（支持 --dry-run）" >&2; exit 1 ;;
  esac
done

if [[ -z "$TAG" ]]; then
  echo "用法: bash scripts/sync_upstream.sh <官方版本tag> [--dry-run]"
  echo "例:   bash scripts/sync_upstream.sh v2026.9.14 --dry-run"
  echo "官方版本列表: gh release list --repo NousResearch/hermes-agent --limit 10"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
UPSTREAM_URL="${COCO_UPSTREAM_URL:-https://github.com/NousResearch/hermes-agent.git}"

# 7 个挂钩点：同步后会变成官方版本，需要重新应用 Coco 的改动
HOOK_FILES=(
  "toolsets.py"
  "agent/prompt_builder.py"
  "agent/system_prompt.py"
  "agent/agent_init.py"
  "hermes_cli/config_defaults.py"
  "plugins/platforms/feishu/adapter.py"
  "gateway/run.py"
  # 第 8 处：CI 挑标签的正则（2026-09-15 同步时被官方版冲掉，实测教训）
  "scripts/sandbox/pick-release-tags.sh"
)

# Coco 重写过、但官方也有同名文件：**跳过替换**，保住我们自己的版本。
# （2026-09-15 实测教训：第一次同步时没排除，README 被官方版覆盖，Coco 中文介绍丢失，
#   只能用 pre-sync tag 找回。）
COCO_OWNED_KEEP=(
  "README.md"
  "README.zh-CN.md"
  "SOUL.md"
  "VERSION"
  "UPSTREAM_VERSION"
)

info(){ echo -e "\033[1;34m==>\033[0m $*"; }
ok(){   echo -e "\033[1;32m  OK\033[0m $*"; }
warn(){ echo -e "\033[1;33m  !!\033[0m $*"; }
err(){  echo -e "\033[1;31mFAIL\033[0m $*" >&2; }

echo "=========================================================="
echo " Coco 同步官方上游"
echo " 目标版本 : $TAG"
echo " 仓库     : $REPO_ROOT"
echo " 模式     : $([[ $DRY_RUN == 1 ]] && echo '演练（不改文件）' || echo '真实执行')"
echo "=========================================================="

# ---- 0. 前置检查 -----------------------------------------------------------
info "前置检查"
if [[ ! -d .git ]]; then err "当前目录不是 git 仓库"; exit 1; fi
if [[ -n "$(git status --porcelain | grep -vE '^\?\?' || true)" ]]; then
  err "检测到已跟踪文件的本地改动，请先提交或 stash 后再同步。"
  git status --short | head -20
  exit 1
fi
ok "工作区干净（未跟踪的运行时文件不受影响）"

CUR_VER=$(cat VERSION 2>/dev/null | tr -d '[:space:]' || echo "?")
CUR_SIZE=$(du -sm .git 2>/dev/null | cut -f1)
echo "  当前 Coco 版本: v${CUR_VER}  仓库体积: ${CUR_SIZE}MB"

# ---- 1. 下载官方快照 -------------------------------------------------------
SNAP=$(mktemp -d /tmp/coco-upstream-XXXXXX)
info "下载官方 $TAG 快照（浅克隆，只取该版本，不带历史）"
if ! git clone --quiet --depth=1 --branch "$TAG" --single-branch "$UPSTREAM_URL" "$SNAP/up" 2>/dev/null; then
  err "下载失败：检查版本 tag 是否存在、网络是否可达"
  echo "  可用版本: gh release list --repo NousResearch/hermes-agent --limit 10"
  rm -rf "$SNAP"; exit 1
fi
rm -rf "$SNAP/up/.git"
UP_FILES=$(find "$SNAP/up" -type f | wc -l)
ok "官方快照就绪：$UP_FILES 个文件"

# ---- 2. 计算差异 -----------------------------------------------------------
info "计算差异（官方快照 vs 本仓库）"
CHANGED=0; NEW=0; LOCAL_ONLY=0
: > "$SNAP/changed.txt"; : > "$SNAP/new.txt"
while IFS= read -r rel; do
  src="$SNAP/up/$rel"; dst="$REPO_ROOT/$rel"
  if [[ ! -e "$dst" ]]; then
    NEW=$((NEW+1)); echo "$rel" >> "$SNAP/new.txt"
  elif ! cmp -s "$src" "$dst"; then
    CHANGED=$((CHANGED+1)); echo "$rel" >> "$SNAP/changed.txt"
  fi
done < <(cd "$SNAP/up" && find . -type f | sed 's|^\./||')

# 本地独有（官方没有的）= Coco 自有文件 + 需人工确认的残留
(cd "$REPO_ROOT" && find . -type f \
   -not -path './.git/*' -not -path './venv/*' -not -path './node_modules/*' \
   -not -path './.venv*/*' -not -path '*/__pycache__/*' \
   | sed 's|^\./||' | sort) > "$SNAP/local_all.txt"
(cd "$SNAP/up" && find . -type f | sed 's|^\./||' | sort) > "$SNAP/up_all.txt"
comm -23 "$SNAP/local_all.txt" "$SNAP/up_all.txt" > "$SNAP/local_only.txt"
LOCAL_ONLY=$(wc -l < "$SNAP/local_only.txt")

echo "  内容有变化 : $CHANGED 个文件"
echo "  官方新增   : $NEW 个文件"
echo "  本地独有   : $LOCAL_ONLY 个（Coco 自有文件，将被完整保留）"

echo
echo "  --- 需要重新应用 Coco 改动的挂钩点（本次会被换成官方新版）---"
for f in "${HOOK_FILES[@]}"; do
  if [[ -e "$SNAP/up/$f" ]]; then
    printf "    · %-45s 官方新版 %s bytes\n" "$f" "$(stat -c%s "$SNAP/up/$f")"
  else
    warn "$f 在官方新版中不存在（可能被官方改路径或删除，需人工确认）"
  fi
done

if [[ $DRY_RUN == 1 ]]; then
  echo
  info "演练结束 —— 未改动任何文件"
  echo "  变化文件清单: $SNAP/changed.txt"
  echo "  新增文件清单: $SNAP/new.txt"
  echo "  自有文件清单: $SNAP/local_only.txt"
  echo
  echo "确认无误后去掉 --dry-run 执行真实同步。"
  exit 0
fi

# ---- 3. 备份挂钩点 + 打 tag -----------------------------------------------
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$REPO_ROOT/.sync-backup/$STAMP"
mkdir -p "$BACKUP"
for f in "${HOOK_FILES[@]}"; do
  [[ -f "$f" ]] && { mkdir -p "$BACKUP/$(dirname "$f")"; cp -a "$f" "$BACKUP/$f"; }
done
cp -a "$SNAP/local_only.txt" "$BACKUP/local_only_files.txt" 2>/dev/null || true
ok "挂钩点文件已备份到 .sync-backup/$STAMP/"

if git rev-parse -q --verify "refs/tags/pre-sync-$STAMP" >/dev/null 2>&1; then
  warn "备份 tag 已存在，跳过"
else
  git tag "pre-sync-$STAMP" 2>/dev/null && ok "已打备份 tag: pre-sync-$STAMP（回滚用 git reset --hard pre-sync-$STAMP）"
fi

# ---- 4. 替换官方层文件（不动本地独有文件、不删除）-------------------------
info "替换官方层文件"
# Coco 自己重写过的同名文件不替换（见上方 COCO_OWNED_KEEP 说明）
KEEP_ARGS=()
for keep in "${COCO_OWNED_KEEP[@]}"; do
  KEEP_ARGS+=("--exclude=/$keep")
  [[ "$keep" == */* ]] && KEEP_ARGS+=("--exclude=/$keep")
  echo "  跳过（保留 Coco 自有版本）: $keep"
done
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude='.git/' "${KEEP_ARGS[@]}" "$SNAP/up/" "$REPO_ROOT/"
else
  (cd "$SNAP/up" && find . -type f -exec sh -c '
      for src; do
        rel="${src#./}"
        case "$rel" in
          README.md|README.zh-CN.md|SOUL.md|VERSION|UPSTREAM_VERSION) continue ;;
        esac
        mkdir -p "'"$REPO_ROOT"'/$(dirname "$rel")"
        cp -a "$src" "'"$REPO_ROOT"'/$rel"
      done' _ {} +)
fi
ok "官方层已替换（Coco 自有文件与自有文档均未受影响）"

# ---- 5. 报告 ---------------------------------------------------------------
git add -A >/dev/null 2>&1 || true
ADDED=$(git diff --cached --numstat --diff-filter=A | wc -l)
MODIFIED=$(git diff --cached --numstat --diff-filter=M | wc -l)
DELETED=$(git diff --cached --numstat --diff-filter=D | wc -l)
NEW_SIZE=$(du -sm .git 2>/dev/null | cut -f1)

echo
echo "=========================================================="
echo " 同步完成 —— 但还没结束，按下面顺序继续"
echo "=========================================================="
echo "  变更统计: 新增 $ADDED / 修改 $MODIFIED / 删除 $DELETED"
echo "  仓库体积: ${CUR_SIZE}MB → ${NEW_SIZE}MB（增量 $((NEW_SIZE-CUR_SIZE))MB；Gitee 上限 500MB）"
echo
echo "  ① 重新应用 Coco 的 7 处改动（按语义，别机械 apply）："
echo "       cat patches/README.md"
echo "     挂钩点备份在 .sync-backup/$STAMP/"
echo
echo "  ② 自检（24 项应全 PASS）："
echo "       python3 scripts/check_coco_hooks.py"
echo
echo "  ③ 三层验收 + 灰度："
echo "       python3 scripts/healthcheck.py"
echo "       python3 scripts/smoke_test_real_estate.py"
echo "       （详见 docs/UPSTREAM_SYNC.md 第 5、6 步）"
echo
echo "  ④ 验收通过后再提交推送（脚本不替你决定）："
echo "       git commit -m 'chore: 同步官方 $TAG'"
echo
echo "  官方这次删掉的、但本地还在的文件（需人工确认是否保留）："
comm -13 "$SNAP/up_all.txt" <(cd "$REPO_ROOT" && git ls-files) 2>/dev/null | head -5
echo "      （完整清单：$SNAP/up_all.txt 与 git ls-files 的差集）"
echo
warn "回滚方式：git reset --hard pre-sync-$STAMP"
