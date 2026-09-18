#!/usr/bin/env bash
# Coco 海报字体 + 渲染器安装（幂等、可重复执行、失败不阻塞）
#
# 装什么：
#   1) librsvg2-bin —— 海报 SVG 渲染器（约 7MB，apt）
#   2) 中文商用字体 —— 海报标题/数字/正文用（约 140MB，多源自动回退）
#
# 为什么：海报要"专业感"，靠的是字体字重层级；服务器默认只有文泉驿一种细笔画字体。
# 所有字体均为免费可商用（思源/得意黑/霞鹜文楷为 SIL OFL 开源；普惠体/MiSans/鸿蒙/站酷/庞门正道/优设
# 为各自官方声明的免费商用）。许可与来源见 docs/FONTS.md。
#
# 用法：
#   bash scripts/install_fonts.sh            # 默认装核心字体
#   bash scripts/install_fonts.sh --quiet    # 只在缺失时输出（update.sh 用）
#   COCO_FONTS_EXTRA=1 bash scripts/install_fonts.sh   # 额外装 MiSans / 鸿蒙黑体（下载量大）
#   COCO_SKIP_FONTS=1 ...                    # 明确跳过（海报自动回落系统字体，仍可出图）
set -uo pipefail

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1
FONT_DIR="/usr/local/share/fonts/coco"
MARKER="$FONT_DIR/.coco_fonts_ok"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log()  { [[ $QUIET -eq 1 ]] || echo "$@"; }
ok()   { echo "  [OK] $*"; }
warn() { echo "  [提示] $*"; }

[[ "${COCO_SKIP_FONTS:-0}" == "1" ]] && { log "已跳过字体安装（COCO_SKIP_FONTS=1）"; exit 0; }

# ---- 渲染器 ----
if ! command -v rsvg-convert >/dev/null 2>&1; then
  log "安装海报渲染器（librsvg2-bin）..."
  if sudo apt-get install -y -q librsvg2-bin >/dev/null 2>&1; then
    ok "渲染器已安装：$(rsvg-convert --version)"
  else
    warn "渲染器安装失败（可能需要 sudo 或网络）——海报会回落旧版排版引擎"
  fi
fi

sudo mkdir -p "$FONT_DIR" 2>/dev/null || mkdir -p "$FONT_DIR"
mkdir -p "$TMP"

# 字体清单：相对文件名|来源URL（多个 URL 用空格分隔，依次尝试）
CORE_FONTS=(
  "NotoSansCJKsc-Regular.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
  "NotoSansCJKsc-Bold.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf"
  "NotoSansCJKsc-Black.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Black.otf"
  "NotoSerifCJKsc-Black.otf|https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Black.otf"
  "Alibaba-PuHuiTi-Heavy.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4%E6%99%AE%E6%83%A0%E4%BD%93/Alibaba-PuHuiTi-Heavy.ttf https://gitee.com/mirrors_free-font/raw/master/assets/font/%E4%B8%AD%E6%96%87/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4%E6%99%AE%E6%83%A0%E4%BD%93/Alibaba-PuHuiTi-Heavy.ttf"
  "Alibaba-PuHuiTi-Bold.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4%E6%99%AE%E6%83%A0%E4%BD%93/Alibaba-PuHuiTi-Bold.ttf"
  "PangMenZhengDao.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E5%BA%9E%E9%97%A8%E6%AD%A3%E9%81%93%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%E5%BA%9E%E9%97%A8%E6%AD%A3%E9%81%93%E6%A0%87%E9%A2%98%E4%BD%93.ttf"
  "站酷高端黑.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E7%AB%99%E9%85%B7%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%20%E7%AB%99%E9%85%B7%E9%AB%98%E7%AB%AF%E9%BB%91.ttf"
  "站酷庆科黄油体.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E7%AB%99%E9%85%B7%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%E7%AB%99%E9%85%B7%E5%BA%86%E7%A7%91%E9%BB%84%E6%B2%B9%E4%BD%93.ttf"
  "YouSheBiaoTiHei.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E5%85%B6%E4%BB%96%E5%AD%97%E4%BD%93/%E4%BC%98%E8%AE%BE%E6%A0%87%E9%A2%98%E9%BB%91.ttf"
  "LXGWWenKaiScreen.ttf|https://github.com/lxgw/LxgwWenKai-Screen/releases/download/v1.522/LXGWWenKaiScreen.ttf"
  "SmileySans-Oblique.ttf|zip:https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip"
)

# 可选字体（下载量大，默认跳过）
EXTRA_FONTS=(
  "HarmonyOS_Sans_SC.ttf|zip:https://alliance-communityfile-drcn.dbankcdn.com/FileServer/getFile/cmtyManage/011/111/111/0000000000011111111.20260611171743.77886644144213121813005934094365:50001231000000:2800:0CCF575ADA0FCAD85EE25909C15C402A40FA94ABCCFEFC5BD37061A6B94239FF.zip"
)

fetch_one() {
  local name="$1" urls="$2" tmpfile
  [[ -s "$FONT_DIR/$name" ]] && return 0
  tmpfile="$TMP/$name"
  for url in $urls; do
    if [[ "$url" == zip:* ]]; then
      local zurl="${url#zip:}" zf="$TMP/$(basename "${url##*/}")"
      curl -fsSL --max-time 300 -o "$zf" "$zurl" >/dev/null 2>&1 || continue
      (cd "$TMP" && unzip -o -q "$zf") >/dev/null 2>&1 || continue
      local found
      found="$(find "$TMP" -type f -iname '*.ttf' -o -type f -iname '*.otf' 2>/dev/null | grep -iv '__MACOSX' | head -1)"
      [[ -n "$found" ]] && { cp -f "$found" "$tmpfile"; }
      [[ -s "$tmpfile" ]] && break || continue
    else
      curl -fsSL --max-time 300 -o "$tmpfile" "$url" >/dev/null 2>&1 && [[ -s "$tmpfile" ]] && break
    fi
  done
  # 简单校验：字体文件必须有 sfnt 头（\x00\x01\x00\x00 或 OTTO）
  if [[ -s "$tmpfile" ]]; then
    local magic
    magic=$(head -c 4 "$tmpfile" | od -An -tx1 | tr -d ' \n')
    if [[ "$magic" == "00010000" || "$magic" == "4f54544f" || "$magic" == "74727565" ]]; then
      sudo cp -f "$tmpfile" "$FONT_DIR/$name" 2>/dev/null || cp -f "$tmpfile" "$FONT_DIR/$name"
      return 0
    fi
  fi
  return 1
}

log "安装海报字体到 $FONT_DIR ..."
missed=()
for entry in "${CORE_FONTS[@]}"; do
  name="${entry%%|*}"; urls="${entry#*|}"
  fetch_one "$name" "$urls" || missed+=("$name")
done
if [[ "${COCO_FONTS_EXTRA:-0}" == "1" ]]; then
  for entry in "${EXTRA_FONTS[@]}"; do
    name="${entry%%|*}"; urls="${entry#*|}"
    fetch_one "$name" "$urls" || missed+=("$name")
  done
else
  log "（MiSans / 鸿蒙黑体等可选字体未安装：需要时用 COCO_FONTS_EXTRA=1 重跑）"
fi

fc-cache -f >/dev/null 2>&1 || true
count=$(find "$FONT_DIR" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) 2>/dev/null | wc -l | tr -d ' ')
size=$(du -sh "$FONT_DIR" 2>/dev/null | cut -f1)

if [[ ${#missed[@]} -gt 0 ]]; then
  warn "以下字体未下载成功：${missed[*]}（海报会回落系统字体，不影响出图）"
  warn "网络恢复后可重跑：bash scripts/install_fonts.sh"
else
  ok "海报字体已就绪（${count} 个文件，${size}）"
fi
touch "$MARKER" 2>/dev/null || true
exit 0
