#!/usr/bin/env bash
# =============================================================================
# Coco 版本晋升脚本（2026-09-21 加）：把老板实测通过的测试版(next)晋升为稳定版(master)
#
# 背景：老板要求"我测的版本跟别人装的不一样；我测通过了再正式发布"。
# 通道模型见 scripts/coco_channel.sh：master=稳定版（别人装这个）、next=测试版（老板测这个）。
# 本脚本负责最后一步：老板说"可以"之后，把 next 的内容快进到 master。
#
# 只做**快进**（要求 master 是 next 的祖先），不做自动合并 —— 合并会造出历史分叉，
# 已装实例的 `git pull --ff-only` 更新会失败，违反更新铁律。
#
# 用法:
#   bash scripts/promote_release.sh --dry-run          # 只看会晋升什么，不动仓库
#   bash scripts/promote_release.sh                    # 把 next 快进到 master 并双推
#   bash scripts/promote_release.sh --tag v0.21.3-65   # 顺手打标签并推送标签
#
# 晋升后仍需人工做两件事（脚本只保证代码到位，避免误发对外内容）：
#   ① 在 Gitee/GitHub 建对应 Release（对外的"正式发布"动作）；
#   ② 更新博客的版本行（post 70）。
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[1;34m'; NC='\033[0m'
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

FROM_BRANCH="next"      # 测试通道
TO_BRANCH="master"      # 稳定通道
TAG=""
DRY_RUN=0
REMOTES=("origin" "github")
LABELS=("Gitee" "GitHub")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --tag) TAG="${2:-}"; shift 2 ;;
        --from) FROM_BRANCH="${2:-}"; shift 2 ;;
        --to) TO_BRANCH="${2:-}"; shift 2 ;;
        *) fail "未知参数: $1" ;;
    esac
done

if [[ -n "$(git status --porcelain)" ]]; then
    fail "工作区有未提交改动，先 commit（晋升必须是"仓库里的东西"）"
fi

info "取两个远程的最新状态..."
for r in "${REMOTES[@]}"; do
    git fetch -q "$r" || fail "拉取 $r 失败（网络问题？）"
done

FROM_SHA="$(git rev-parse "origin/$FROM_BRANCH" 2>/dev/null || git rev-parse "$FROM_BRANCH")"
TO_SHA="$(git rev-parse "origin/$TO_BRANCH")"

if [[ "$FROM_SHA" == "$TO_SHA" ]]; then
    ok "$TO_BRANCH 与 $FROM_BRANCH 已经是同一个提交（${TO_SHA:0:7}），无需晋升"
    exit 0
fi

# 关键校验：必须能快进（master 是 next 的祖先），否则拒绝
if ! git merge-base --is-ancestor "$TO_SHA" "$FROM_SHA"; then
    fail "$TO_BRANCH 不是 $FROM_BRANCH 的祖先，无法快进 —— 说明稳定线有测试线没有的提交，需要人工处理后再晋升"
fi

AHEAD="$(git rev-list --count "$TO_SHA..$FROM_SHA")"
VER="$(git show "$FROM_SHA:VERSION" 2>/dev/null | tr -d '[:space:]' || echo '未知')"
echo "----------------------------------------"
info "晋升 ${BLUE}$FROM_BRANCH${NC} → ${BLUE}$TO_BRANCH${NC}"
echo "  晋升内容: ${AHEAD} 个提交"
echo "  晋升到:   ${FROM_SHA:0:7}（版本 v${VER}）"
echo "  原本:     ${TO_SHA:0:7}"
echo "----------------------------------------"

if [[ "$DRY_RUN" == "1" ]]; then
    warn "dry-run：以上是将会发生的事，未做任何改动"
    exit 0
fi

# 用 refspec 推（next:master）：不依赖本地当前在哪个分支，也不动工作区
for idx in "${!REMOTES[@]}"; do
    r="${REMOTES[$idx]}"; label="${LABELS[$idx]}"
    info "推送 $label：$FROM_BRANCH → $TO_BRANCH"
    git push "$r" "$FROM_BRANCH:$TO_BRANCH" || fail "$label 推送失败（重跑本脚本即可，快进是幂等的）"
done

# 本地 master 引用同步跟上（若当前就停在 master，用快进合并；否则直接更新引用）
if [[ "$(git branch --show-current)" == "$TO_BRANCH" ]]; then
    git merge --ff-only "$FROM_SHA" >/dev/null || warn "本地 $TO_BRANCH 快进失败（不影响远程，远程已更新）"
else
    git update-ref "refs/heads/$TO_BRANCH" "$FROM_SHA" || warn "本地 $TO_BRANCH 引用更新失败（不影响远程）"
fi

if [[ -n "$TAG" ]]; then
    info "打标签 $TAG 并推送"
    git tag -a "$TAG" -m "Coco $TAG（官方 Hermes ${VER%%-*} 定制版）" "$FROM_SHA" 2>/dev/null \
        || warn "标签 $TAG 已存在，沿用现有标签"
    for r in "${REMOTES[@]}"; do
        git push "$r" "$TAG" || fail "标签推送到 $r 失败"
    done
fi

# 复核：两个远程的 master 都必须等于 next 的提交
mismatch=0
for idx in "${!REMOTES[@]}"; do
    r="${REMOTES[$idx]}"; label="${LABELS[$idx]}"
    got="$(git ls-remote "$r" "refs/heads/$TO_BRANCH" | cut -f1)"
    if [[ "$got" != "$FROM_SHA" ]]; then
        warn "$label 的 $TO_BRANCH 停在 ${got:0:7}，期望 ${FROM_SHA:0:7}"
        mismatch=1
    fi
done
[[ "$mismatch" == "1" ]] && fail "有远程未同步成功 —— 重跑本脚本（快进幂等）"

ok "晋升完成：$TO_BRANCH = ${FROM_SHA:0:7}（版本 v${VER}）"
echo "  还需人工完成：① 建 Release（Gitee/GitHub）② 更新博客版本行"
