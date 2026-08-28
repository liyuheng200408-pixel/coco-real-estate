#!/usr/bin/env bash
#
# Coco 仓库双远程推送脚本：Gitee + GitHub 同步推 + SHA 一致性验证
# 用法:
#   bash scripts/push_all.sh                # 推 master
#   bash scripts/push_all.sh --with-tags    # 推 master + 所有标签
#   bash scripts/push_all.sh <branch>       # 推指定分支
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${YELLOW}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="master"
WITH_TAGS=0

for arg in "$@"; do
    case "$arg" in
        --with-tags) WITH_TAGS=1 ;;
        *) BRANCH="$arg" ;;
    esac
done

cd "$REPO_DIR"

# 推送前确认工作区干净（未提交改动会导致两边推的内容不是最新）
if [[ -n "$(git status --porcelain)" ]]; then
    fail "工作区有未提交改动，先 commit 再推送"
fi

info "推送 master 分支: $BRANCH"
echo "----------------------------------------"

info "[1/2] 推送 Gitee (origin)..."
git push origin "$BRANCH" || fail "Gitee 推送失败"

info "[2/2] 推送 GitHub (github)..."
git push github "$BRANCH" || fail "GitHub 推送失败"

if [[ "$WITH_TAGS" == "1" ]]; then
    info "同步推送标签..."
    git push origin --tags || fail "Gitee 标签推送失败"
    git push github --tags || fail "GitHub 标签推送失败"
fi

# SHA 一致性验证
echo "----------------------------------------"
info "验证两仓库 HEAD SHA 一致性..."
GITEE_SHA=$(git ls-remote origin "refs/heads/$BRANCH" | cut -f1)
GITHUB_SHA=$(git ls-remote github "refs/heads/$BRANCH" | cut -f1)

if [[ -z "$GITEE_SHA" || -z "$GITHUB_SHA" ]]; then
    fail "SHA 查询失败 (Gitee: '$GITEE_SHA', GitHub: '$GITHUB_SHA')"
fi

if [[ "$GITEE_SHA" == "$GITHUB_SHA" ]]; then
    ok "两仓库同步完成 ${GITEE_SHA:0:7} ($BRANCH)"
else
    fail "SHA 不一致！Gitee: ${GITEE_SHA:0:7}  GitHub: ${GITHUB_SHA:0:7} —— 请检查网络后重推"
fi
