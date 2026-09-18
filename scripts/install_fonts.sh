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
#   bash scripts/install_fonts.sh            # 安装/补齐（逐条显示进度）
#   bash scripts/install_fonts.sh --quiet    # 已就绪时少说话（update.sh 用；下载时仍显示进度）
#   COCO_FONTS_EXTRA=1 bash scripts/install_fonts.sh   # 额外装鸿蒙黑体等（下载量大）
#   COCO_SKIP_FONTS=1 ...                    # 明确跳过（海报自动回落系统字体，仍可出图）
#
# 注意：共约 140MB，视网速需 2~10 分钟。下载期间会逐条打印进度，别以为卡住了；
#      中途 Ctrl+C 也安全（已下好的会保留，重跑会跳过），不影响 COCO 使用。
set -uo pipefail

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1
FONT_DIR="/usr/local/share/fonts/coco"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say()  { echo "$@"; }                                   # 进度：任何模式都显示
info() { [[ $QUIET -eq 1 ]] || echo "$@"; }             # 闲聊：quiet 模式不显示
ok()   { echo "  [OK] $*"; }
warn() { echo "  [提示] $*"; }

[[ "${COCO_SKIP_FONTS:-0}" == "1" ]] && { say "已跳过海报字体安装（COCO_SKIP_FONTS=1），海报将使用系统字体"; exit 0; }

# ---- 先一次性拿到 sudo 授权：避免下载/安装途中再弹密码，看着像卡住 ----
if [[ "$(id -u)" != "0" ]] && ! sudo -n true 2>/dev/null; then
  say "海报组件需要系统权限：接下来要输入服务器密码（输入时屏幕不显示字符，属正常）"
  sudo -v || warn "未获得 sudo 授权，将尽力继续（渲染器/字体可能装不上）"
fi

# ---- 渲染器 ----
if ! command -v rsvg-convert >/dev/null 2>&1; then
  say "安装海报渲染器（librsvg2-bin，约 7MB）..."
  if sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q librsvg2-bin 2>&1 | tail -2; then
    if command -v rsvg-convert >/dev/null 2>&1; then
      ok "渲染器就绪：$(rsvg-convert --version 2>/dev/null | head -1)"
    else
      warn "渲染器未生效（海报会回落旧版排版引擎）"
    fi
  else
    warn "渲染器安装失败（网络或软件源不可用）——海报会回落旧版排版引擎"
  fi
else
  info "渲染器已就绪：$(rsvg-convert --version 2>/dev/null | head -1)"
fi

sudo mkdir -p "$FONT_DIR" 2>/dev/null || mkdir -p "$FONT_DIR" 2>/dev/null || true
mkdir -p "$TMP"

# 字体清单：相对文件名|来源URL（多个 URL 用空格分隔，依次尝试）
CORE_FONTS=(
  "NotoSansCJKsc-Regular.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
  "NotoSansCJKsc-Bold.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf"
  "NotoSansCJKsc-Black.otf|https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Black.otf"
  "NotoSerifCJKsc-Black.otf|https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Black.otf"
  "Alibaba-PuHuiTi-Heavy.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4%E6%99%AE%E6%83%A0%E4%BD%93/Alibaba-PuHuiTi-Heavy.ttf"
  "Alibaba-PuHuiTi-Bold.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E9%98%BF%E9%87%8C%E5%B7%B4%E5%B7%B4%E6%99%AE%E6%83%A0%E4%BD%93/Alibaba-PuHuiTi-Bold.ttf"
  "PangMenZhengDao.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E5%BA%9E%E9%97%A8%E6%AD%A3%E9%81%93%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%E5%BA%9E%E9%97%A8%E6%AD%A3%E9%81%93%E6%A0%87%E9%A2%98%E4%BD%93.ttf"
  "站酷高端黑.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E7%AB%99%E9%85%B7%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%20%E7%AB%99%E9%85%B7%E9%AB%98%E7%AB%AF%E9%BB%91.ttf"
  "站酷庆科黄油体.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E7%AB%99%E9%85%B7%E5%AD%97%E4%BD%93%E7%B3%BB%E5%88%97/%E7%AB%99%E9%85%B7%E5%BA%86%E7%A7%91%E9%BB%84%E6%B2%B9%E4%BD%93.ttf"
  "YouSheBiaoTiHei.ttf|https://raw.githubusercontent.com/wordshub/free-font/master/assets/font/%E4%B8%AD%E6%96%87/%E5%85%B6%E4%BB%96%E5%AD%97%E4%BD%93/%E4%BC%98%E8%AE%BE%E6%A0%87%E9%A2%98%E9%BB%91.ttf"
  "LXGWWenKaiScreen.ttf|https://github.com/lxgw/LxgwWenKai-Screen/releases/download/v1.522/LXGWWenKaiScreen.ttf"
  "SmileySans-Oblique.ttf|zip:https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip"
)

EXTRA_FONTS=(
  "HarmonyOS_Sans_SC.ttf|zip:https://alliance-communityfile-drcn.dbankcdn.com/FileServer/getFile/cmtyManage/011/111/111/0000000000011111111.20260611171743.77886644144213121813005934094365:50001231000000:2800:0CCF575ADA0FCAD85EE25909C15C402A40FA94ABCCFEFC5BD37061A6B94239FF.zip"
)

# 返回 0=本次装上；1=失败；2=已存在
fetch_one() {
  local name="$1" urls="$2" tmpfile
  [[ -s "$FONT_DIR/$name" ]] && return 2
  tmpfile="$TMP/$name"
  for url in $urls; do
    if [[ "$url" == zip:* ]]; then
      local zurl="${url#zip:}" zf="$TMP/pkg.zip"
      curl -fsSL --retry 2 --retry-delay 3 --max-time 600 -o "$zf" "$zurl" >/dev/null 2>&1 || continue
      (cd "$TMP" && unzip -o -q "$zf") >/dev/null 2>&1 || continue
      local found
      found="$(find "$TMP" -type f \( -iname '*.ttf' -o -iname '*.otf' \) 2>/dev/null | grep -iv '__MACOSX' | head -1)"
      [[ -n "$found" ]] && cp -f "$found" "$tmpfile"
      [[ -s "$tmpfile" ]] && break || continue
    else
      curl -fsSL --retry 2 --retry-delay 3 --max-time 600 -o "$tmpfile" "$url" >/dev/null 2>&1 \
        && [[ -s "$tmpfile" ]] && break
    fi
  done
  # 校验字体文件头（sfnt: 00010000 / OTTO / true），防止把错误页当字体装进去
  if [[ -s "$tmpfile" ]]; then
    local magic
    magic=$(head -c 4 "$tmpfile" | od -An -tx1 | tr -d ' \n')
    if [[ "$magic" == "00010000" || "$magic" == "4f54544f" || "$magic" == "74727565" ]]; then
      sudo cp -f "$tmpfile" "$FONT_DIR/$name" 2>/dev/null || cp -f "$tmpfile" "$FONT_DIR/$name" 2>/dev/null
      [[ -s "$FONT_DIR/$name" ]] && return 0
    fi
  fi
  return 1
}

ALL=("${CORE_FONTS[@]}")
[[ "${COCO_FONTS_EXTRA:-0}" == "1" ]] && ALL+=("${EXTRA_FONTS[@]}")

todo=0
for entry in "${ALL[@]}"; do
  [[ -s "$FONT_DIR/${entry%%|*}" ]] || todo=$((todo + 1))
done

missed=()
if [[ $todo -eq 0 ]]; then
  info "海报字体已就绪（$(find "$FONT_DIR" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) | wc -l | tr -d ' ') 个文件，$(du -sh "$FONT_DIR" 2>/dev/null | cut -f1)）"
else
  say "下载海报字体：缺 $todo 个（合计约 $((todo * 12))MB，视网速 2~10 分钟；可 Ctrl+C 中断，下次重跑会跳过已装部分）"
  i=0
  for entry in "${ALL[@]}"; do
    name="${entry%%|*}"; urls="${entry#*|}"
    [[ -s "$FONT_DIR/$name" ]] && continue      # 已装好：安静跳过，不刷屏
    i=$((i + 1))
    if fetch_one "$name" "$urls"; then
      say "  [$i/$todo] $name ... 已安装（$(du -h "$FONT_DIR/$name" 2>/dev/null | cut -f1)）"
    else
      say "  [$i/$todo] $name ... 未装成功（继续下一个）"
      missed+=("$name")
    fi
  done
fi

fc-cache -f >/dev/null 2>&1 || true
count=$(find "$FONT_DIR" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' \) 2>/dev/null | wc -l | tr -d ' ')
size=$(du -sh "$FONT_DIR" 2>/dev/null | cut -f1)

if [[ ${#missed[@]} -gt 0 ]]; then
  warn "未装成功：${missed[*]}（海报会回落系统字体，不影响出图；网络好了重跑本脚本即可）"
else
  ok "海报字体已就绪（${count} 个文件，${size}）"
fi
exit 0
