"""
Coco 房产海报 - SVG 渲染引擎（2026-09-19 新增，v2 版式）

为什么：Pillow 画不出渐变字、描边、投影这类"海报感"元素；改用 SVG 描述版式 +
rsvg-convert 渲染，设计自由度接近网页，依赖却很轻（librsvg 约 7MB）。

设计约束：
- 画幅 1080x1920
- 海报上**只显示经纪人自己的公司/门店名**，绝不出现"Coco"字样；公司名没拿到就不显示品牌
- 页脚固定一句「房源信息以实际看房为准」
- 二维码内容 = 经纪人微信名片
- 两款模板：A 红金促销（有照片/无照片两版）、B 极简高级（需照片）
  （2026-09-19 老板评审：B 款效果好；C 清单款做的差，已删除，待以后重新设计）

版式原则（v2 修版）：竖直方向按"块"排布 —— 先算每块高度，再把剩余空间**均分到块间间距**，
保证既不重叠也不出现大空洞；所有文本按列宽量宽后自适应字号/截断。
"""
from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import tempfile

W, H = 1080, 1920
MARGIN = 70                      # 左右安全边
CONTENT_W = W - MARGIN * 2       # 940

FONTS = {
    "title_heavy": ["Alibaba PuHuiTi Heavy", "Noto Sans CJK SC"],      # 大标题/数字
    "title_promo": ["Alibaba PuHuiTi Heavy", "YouSheBiaoTiHei", "Noto Sans CJK SC"],
    "title_serif": ["Noto Serif CJK SC", "zcool-gdh", "Noto Sans CJK SC"],  # 中式庄重
    "title_list": ["Smiley Sans", "PangMenZhengDao", "Noto Sans CJK SC"],    # 动感
    "number": ["Alibaba PuHuiTi Heavy", "Noto Sans CJK SC"],
    "body": ["Noto Sans CJK SC", "MiSans"],
}
_MEASURE_FILES = {
    "title_heavy": ["/usr/local/share/fonts/coco/Alibaba-PuHuiTi-Heavy.ttf",
                    "/usr/local/share/fonts/coco/NotoSansCJKsc-Black.otf"],
    "body": ["/usr/local/share/fonts/coco/NotoSansCJKsc-Regular.otf",
             "/usr/local/share/fonts/coco/Alibaba-PuHuiTi-Bold.ttf"],
}


def _esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _measure(text: str, size: int, role: str = "body") -> float:
    try:
        from PIL import ImageFont

        for path in _MEASURE_FILES.get(role, []) + _MEASURE_FILES["body"]:
            if os.path.exists(path):
                return float(ImageFont.truetype(path, size).getlength(text))
    except Exception:
        pass
    return sum(size if ord(ch) > 0x2E80 else size * 0.55 for ch in text)


def _fit(text: str, max_width: float, size: int, role: str = "body", tail: str = "…") -> str:
    text = str(text if text is not None else "")
    if _measure(text, size, role) <= max_width:
        return text
    out = ""
    for ch in text:
        if _measure(out + ch + tail, size, role) > max_width:
            break
        out += ch
    return out + tail


def _auto_size(text: str, max_width: float, base: int, role: str = "body", floor: int = 28) -> int:
    """自适应字号：尽量用 base，放不下就逐级缩小到 floor"""
    size = base
    while size > floor and _measure(str(text), size, role) > max_width:
        size -= 2
    return size


def _stack(blocks: list, top: float, bottom: float, weights: list | None = None) -> list:
    """竖直排布：blocks=[(height, render_fn(y)) ...]；剩余空间按权重均分到块间间距。
    返回 [render_fn(y), ...] 的新 y 列表（调用方负责把渲染结果拼起来）。"""
    heights = [b[0] for b in blocks]
    n_gaps = max(len(blocks) - 1, 1)
    slack = (bottom - top) - sum(heights)
    weights = weights or [1.0] * n_gaps
    unit = max(slack, 0) / sum(weights) if slack > 0 else 0
    ys, y = [], top
    for i, h in enumerate(heights):
        ys.append(y)
        y += h
        if i < len(heights) - 1:
            y += unit * (weights[i] if i < len(weights) else weights[-1])
    return ys


def _fit_mode(d: dict, has_image: bool) -> str:
    """图片适配：照片默认裁切铺满（slice）；显式指定或户型图用完整显示（meet）"""
    mode = str(d.get("image_fit") or "").lower()
    if mode in ("meet", "slice"):
        return mode
    return "slice" if has_image else "meet"


def _image_size(path: str | None):
    """读取图片宽高（失败返回 (0, 0)）"""
    if not path or not os.path.exists(path):
        return (0, 0)
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def _panel_size(box_w: float, box_h: float, path: str | None, fit: str):
    """meet 模式：按图片宽高比收缩面板，避免大块白边（户型图多为竖图）"""
    if fit != "meet":
        return box_w, box_h
    iw, ih = _image_size(path)
    if not iw or not ih:
        return box_w, box_h
    aspect = iw / ih
    if aspect < box_w / box_h:
        h = box_h
        w = max(h * aspect, 360.0)
    else:
        w = box_w
        h = max(w / aspect, 360.0)
    return min(w, box_w), min(h, box_h)


def _img_href(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "png")
        with open(path, "rb") as fh:
            return "data:image/%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode())
    except Exception:
        return "file://" + os.path.abspath(path)


def make_qr_png(content: str, out_path: str) -> str | None:
    """生成二维码 PNG（内容 = 经纪人微信名片）"""
    try:
        import qrcode

        qrcode.make(content).convert("RGB").resize((420, 420)).save(out_path)
        return out_path
    except Exception:
        return None


def _defs(gold=("#F7E3A1", "#D9A93C"), red=("#E03A3A", "#A81018")) -> str:
    return (
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="%s"/><stop offset="100%%" stop-color="%s"/></linearGradient>'
        '<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="%s"/><stop offset="52%%" stop-color="%s"/>'
        '<stop offset="100%%" stop-color="#B8862B"/></linearGradient>'
        '<linearGradient id="photoFade" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="45%%" stop-color="#000000" stop-opacity="0"/>'
        '<stop offset="100%%" stop-color="#000000" stop-opacity="0.82"/></linearGradient>'
        '<linearGradient id="topScrim" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%%" stop-color="#000000" stop-opacity="0.55"/>'
        '<stop offset="100%%" stop-color="#000000" stop-opacity="0"/></linearGradient>'
        '<filter id="soft" x="-25%%" y="-25%%" width="150%%" height="150%%">'
        '<feGaussianBlur in="SourceAlpha" stdDeviation="9" result="b"/>'
        '<feOffset in="b" dx="0" dy="7" result="o"/>'
        '<feComponentTransfer in="o" result="s"><feFuncA type="linear" slope="0.3"/></feComponentTransfer>'
        '<feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '</defs>'
    ) % (red[0], red[1], gold[0], gold[1])


def _brand(company: str, slogan: str = "", color: str = "#FFE9AE", rule: str = "#FFD98A") -> str:
    """顶部品牌栏：只写经纪人公司名；没有公司名就整条不画（绝不写 Coco）"""
    if not company:
        return ""
    out = ('<text x="%d" y="96" font-family="%s" font-weight="700" font-size="42" fill="%s" '
           'letter-spacing="3">%s</text>'
           % (MARGIN, _esc(FONTS["title_heavy"][0]), color, _esc(company)))
    if slogan:
        out += ('<text x="%d" y="94" text-anchor="end" font-family="%s" font-size="30" fill="%s" '
                'opacity="0.9">%s</text>'
                % (W - MARGIN, _esc(FONTS["body"][0]), color, _esc(slogan)))
    out += ('<line x1="%d" y1="124" x2="%d" y2="124" stroke="%s" stroke-width="2" opacity="0.5"/>'
            % (MARGIN, W - MARGIN, rule))
    return out


def _capsules(items: list, y: float, gold: str = "#FFE9AE", fg: str = "#8E1B20", size: int = 34,
              max_width: float = CONTENT_W) -> str:
    items = [str(i) for i in (items or []) if str(i).strip()][:4]
    if not items:
        return ""
    gap = 20
    widths, used = [], 0.0
    for t in items:
        w = min(max(_measure(t, size, "body") + 60, 190), 420)
        if used + w + gap > max_width:
            break
        widths.append(w)
        used += w + gap
    if not widths:
        return ""
    total = sum(widths) + gap * (len(widths) - 1)
    x = (W - total) / 2
    out = []
    for text, w in zip(items, widths):
        out.append('<rect x="%.0f" y="%.0f" width="%.0f" height="74" rx="37" fill="%s" filter="url(#soft)"/>'
                   '<text x="%.0f" y="%.0f" text-anchor="middle" font-family="%s" font-size="%d" fill="%s">%s</text>'
                   % (x, y, w, gold, x + w / 2, y + 50, _esc(FONTS["body"][0]), size, fg,
                      _esc(_fit(text, w - 40, size))))
        x += w + gap
    return "".join(out)


def _agent_dark(agent: dict, qr_path: str | None, y: float, height: float = 252) -> str:
    """深色底上的名片区：左二维码 + 右姓名/电话/微信/公司"""
    agent = agent or {}
    parts = []
    has_qr = bool(qr_path and os.path.exists(qr_path))
    qsize = 210
    if has_qr:
        parts.append('<rect x="%d" y="%.0f" width="246" height="246" rx="18" fill="#FFFFFF" '
                     'filter="url(#soft)"/>' % (MARGIN, y))
        parts.append('<image href="%s" x="%d" y="%.0f" width="%d" height="%d"/>'
                     % (_img_href(qr_path), MARGIN + 18, y + 18, qsize, qsize))
    tx = MARGIN + 292 if has_qr else MARGIN
    out = ["<g>"] + parts
    if has_qr:
        out.append('<text x="%d" y="%.0f" font-family="%s" font-weight="700" font-size="42" '
                   'fill="#FFE9AE">扫码加我微信</text>' % (tx, y + 52, _esc(FONTS["body"][0])))
    name_line = " · ".join(str(x) for x in [agent.get("name"), agent.get("phone")] if x)
    if name_line:
        out.append('<text x="%d" y="%.0f" font-family="%s" font-weight="700" font-size="44" '
                   'fill="#FFFFFF">%s</text>'
                   % (tx, y + (128 if has_qr else 56), _esc(FONTS["body"][0]),
                      _esc(_fit(name_line, W - MARGIN - tx, 44))))
    row_y = y + (196 if has_qr else 124)
    if agent.get("wechat"):
        out.append('<text x="%d" y="%.0f" font-family="%s" font-size="34" fill="#FFFFFF" opacity="0.92">微信 %s</text>'
                   % (tx, row_y, _esc(FONTS["body"][0]), _esc(agent["wechat"])))
        row_y += 44
    if agent.get("company") and len(str(agent["company"])) > 0:
        # 公司名单独一行，允许更长（最多两行）
        avail = W - MARGIN - tx
        text = str(agent["company"])
        first = _fit(text, avail, 32)
        out.append('<text x="%d" y="%.0f" font-family="%s" font-size="32" fill="#FFE9AE" opacity="0.95">%s</text>'
                   % (tx, row_y, _esc(FONTS["body"][0]), _esc(first)))
        if first.endswith("…"):
            rest = text[len(first) - 1:]
            out.append('<text x="%d" y="%.0f" font-family="%s" font-size="32" fill="#FFE9AE" opacity="0.95">%s</text>'
                       % (tx, row_y + 42, _esc(FONTS["body"][0]), _esc(_fit(rest, avail, 32))))
    out.append("</g>")
    return "".join(out)


def _footer(text: str = "房源信息以实际看房为准", color: str = "#FFFFFF", opacity: float = 0.72,
            y: float = 1878) -> str:
    return ('<text x="%d" y="%.0f" text-anchor="middle" font-family="%s" font-size="28" fill="%s" '
            'opacity="%s">%s</text>'
            % (W // 2, y, _esc(FONTS["body"][0]), color, opacity, _esc(text)))


def _price_text(p: dict) -> str:
    price = p.get("price")
    if price in (None, ""):
        return "价格待定"
    try:
        price = float(price)
    except (TypeError, ValueError):
        return "价格待定"
    if p.get("property_type") == "rental":
        return "%d元/月" % round(price)
    wan = price / 10000
    return ("%d万" % round(wan)) if abs(wan - round(wan)) < 0.05 else ("%.1f万" % wan)


def _unit_price_text(p: dict, prefix: str = "单价 ") -> str:
    up = p.get("unit_price")
    if not up:
        return ""
    try:
        up = float(up)
    except (TypeError, ValueError):
        return ""
    return (prefix + "%.2f万/㎡" % (up / 10000)) if up >= 10000 else (prefix + "%.0f元/㎡" % up)


def _layout_text(p: dict) -> str:
    return "".join(x for x in [
        ("%s室" % p.get("rooms")) if p.get("rooms") else "",
        ("%s厅" % p.get("halls")) if p.get("halls") else "",
        ("%s卫" % p.get("bathrooms")) if p.get("bathrooms") else "",
    ] if x)


def _tags_of(d: dict, p: dict | None = None) -> list:
    tags = (p or {}).get("tags") or d.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.replace("，", ",").replace("、", ",").split(",")]
    return [str(t).strip() for t in tags if str(t).strip()]


# ---------------- 模板 A：红金促销（单套，有照片/无照片） ----------------
def template_a(d: dict) -> str:
    p = d["properties"][0]
    agent = d.get("agent") or {}
    title = d.get("title") or "今日主推"
    photo = d.get("photo_path")
    has_photo = bool(photo and os.path.exists(photo))
    sub = d.get("subtitle") or " · ".join(
        str(x) for x in [p.get("community"), p.get("district"), p.get("renovation")] if x)
    code_line = d.get("code_line") or p.get("title") or p.get("community") or "房源"
    tags = _tags_of(d, p)
    cards = [("建面", ("%s㎡" % p.get("area")) if p.get("area") else ""),
             ("户型", _layout_text(p)),
             ("装修", p.get("renovation") or "")]
    cards = [c for c in cards if c[1]]

    top = 168
    title_h, sub_h = 196, 84
    card_h = 94 + 60 + max(len(cards), 1) * 122
    caps_h = 74 if tags else 0
    agent_h = 252
    foot_h = 40
    gaps = [1.15, 1.0, 0.55, 0.35, 0.3]
    if not tags:
        gaps = [1.15, 1.0, 0.9, 0.35]
    ys = _stack([(title_h, 0), (sub_h, 1), (card_h, 2), (caps_h, 3), (agent_h, 4), (foot_h, 5)],
                top, 1820, gaps)

    tsize = _auto_size(title, CONTENT_W, 138, "title_heavy", 72)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
           % (W, H, W, H), _defs()]
    out.append('<rect width="%d" height="%d" fill="url(#bg)"/>' % (W, H))
    out.append('<circle cx="950" cy="180" r="280" fill="#FFFFFF" opacity="0.05"/>'
               '<circle cx="110" cy="1500" r="300" fill="#000000" opacity="0.07"/>')
    if has_photo:
        fit = _fit_mode(d, True)
        if fit == "meet":
            pw, ph = _panel_size(W, 900, photo, fit)
            out.append('<rect x="0" y="0" width="%d" height="900" fill="#F3EFE7"/>' % W)
            out.append('<image href="%s" x="%.0f" y="%.0f" width="%.0f" height="%.0f"/>'
                       % (_img_href(photo), (W - pw) / 2, (900 - ph) / 2, pw, ph))
        else:
            out.append('<image href="%s" x="0" y="0" width="%d" height="900" '
                       'preserveAspectRatio="xMidYMid slice"/>' % (_img_href(photo), W))
        out.append('<rect x="0" y="400" width="%d" height="500" fill="url(#photoFade)"/>' % W)
    else:
        out.append('<g opacity="0.16">'
                   '<circle cx="880" cy="352" r="206" fill="none" stroke="#FFE9AE" stroke-width="3"/>'
                   '<circle cx="880" cy="352" r="146" fill="none" stroke="#FFE9AE" stroke-width="2"/>'
                   '<circle cx="204" cy="318" r="112" fill="none" stroke="#FFE9AE" stroke-width="2"/></g>')
        out.append('<path d="M0 470 L%d 330 L%d 424 L0 564 Z" fill="#FFFFFF" opacity="0.06"/>' % (W, W))
        out.append('<rect x="%d" y="206" width="180" height="9" fill="url(#gold)"/>'
                   '<rect x="%d" y="206" width="9" height="180" fill="url(#gold)"/>' % (MARGIN, MARGIN))
    if has_photo:
        out.append('<rect x="0" y="0" width="%d" height="176" fill="url(#topScrim)"/>' % W)
    light_bg = bool(has_photo and _fit_mode(d, True) == "meet")   # 浅底图（户型图等）→ 文字要用深色
    out.append(_brand(agent.get("company", ""), d.get("slogan", ""),
                      color=("#8E1B20" if light_bg else "#FFE9AE"),
                      rule=("#C79A4A" if light_bg else "#FFD98A")))

    # 主标题
    out.append('<text x="%d" y="%.0f" text-anchor="middle" font-family="%s" font-size="%d" fill="url(#gold)" '
               'stroke="#7A0C10" stroke-width="6" filter="url(#soft)" letter-spacing="4">%s</text>'
               % (W // 2, ys[0] + title_h - 44, _esc(FONTS["title_promo"][0]), tsize, _esc(title)))
    out.append('<text x="%d" y="%.0f" text-anchor="middle" font-family="%s" font-size="%d" fill="%s" '
               'letter-spacing="6">%s</text>'
               % (W // 2, ys[1] + 52, _esc(FONTS["body"][0]),
                  _auto_size(sub, CONTENT_W - 40, 44, "body", 32),
                  ("#8E1B20" if light_bg else "#FFE9AE"), _esc(sub)))

    # 房源卡
    cy0 = ys[2]
    out.append('<g filter="url(#soft)"><rect x="%d" y="%.0f" width="%d" height="%.0f" rx="28" '
               'fill="#FFF7EC"/></g>' % (MARGIN, cy0, CONTENT_W, card_h))
    out.append('<rect x="%d" y="%.0f" width="%d" height="94" rx="28" fill="#F2E4CB"/>'
               '<rect x="%d" y="%.0f" width="%d" height="30" fill="#F2E4CB"/>'
               % (MARGIN, cy0, CONTENT_W, MARGIN, cy0 + 64, CONTENT_W))
    out.append('<text x="%d" y="%.0f" text-anchor="middle" font-family="%s" font-weight="700" font-size="%d" '
               'fill="#8E1B20">%s</text>'
               % (W // 2, cy0 + 64, _esc(FONTS["body"][0]),
                  _auto_size(code_line, CONTENT_W - 80, 40, "body", 30),
                  _esc(_fit(code_line, CONTENT_W - 80, 40))))

    # 左：总价（大字自适应右列宽度）
    divider_x = 660
    left_w = divider_x - MARGIN - 60
    out.append('<text x="%d" y="%.0f" font-family="%s" font-size="40" fill="#8A7A6A">总价</text>'
               % (MARGIN + 50, cy0 + 214, _esc(FONTS["body"][0])))
    ptext = _price_text(p)
    psize = _auto_size(ptext, left_w, 150, "title_heavy", 76)
    out.append('<text x="%d" y="%.0f" font-family="%s" font-weight="900" font-size="%d" fill="#C81E2B" '
               'letter-spacing="-3">%s</text>'
               % (MARGIN + 50, cy0 + 214 + psize * 0.86, _esc(FONTS["number"][0]), psize, _esc(ptext)))
    up_text = _unit_price_text(p)
    if up_text:
        out.append('<text x="%d" y="%.0f" font-family="%s" font-size="34" fill="#8A7A6A">%s</text>'
                   % (MARGIN + 50, cy0 + 214 + psize * 0.86 + 62, _esc(FONTS["body"][0]),
                      _esc(_fit(up_text, left_w, 34))))

    # 右：建面/户型/装修（列宽固定，字号自适应）
    right_x = divider_x + 42
    right_w = W - MARGIN - right_x
    out.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="#E3D3B8" stroke-width="3"/>'
               % (divider_x, cy0 + 130, divider_x, cy0 + card_h - 60))
    ry = cy0 + 200
    for label, val in cards:
        out.append('<text x="%d" y="%.0f" font-family="%s" font-size="32" fill="#8A7A6A">%s</text>'
                   % (right_x, ry, _esc(FONTS["body"][0]), _esc(label)))
        out.append('<text x="%d" y="%.0f" font-family="%s" font-weight="700" font-size="%d" fill="#3C2E26">%s</text>'
                   % (right_x, ry + 62, _esc(FONTS["title_heavy"][0]),
                      _auto_size(val, right_w, 58, "title_heavy", 34), _esc(_fit(val, right_w, 58, "title_heavy"))))
        ry += 122

    if tags:
        out.append(_capsules(tags, ys[3]))
    out.append(_agent_dark(agent, d.get("qr_path"), ys[4]))
    out.append(_footer(d.get("footer", "房源信息以实际看房为准")))
    out.append("</svg>")
    return "\n".join(out)


# ---------------- 模板 B：极简高级（需照片） ----------------
def template_b(d: dict) -> str:
    p = d["properties"][0]
    agent = d.get("agent") or {}
    title = d.get("title") or "今日主推"
    photo = d.get("photo_path")
    cream, ink, gold, mute = "#F5F1EA", "#3C2E26", "#C9A227", "#8C8072"
    sub = d.get("subtitle") or " · ".join(str(x) for x in [p.get("community"), p.get("district")] if x)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
           % (W, H, W, H), _defs()]
    out.append('<rect width="%d" height="%d" fill="%s"/>' % (W, H, cream))
    if agent.get("company"):
        out.append('<text x="%d" y="112" font-family="%s" font-size="36" fill="%s" letter-spacing="6">%s</text>'
                   % (80, _esc(FONTS["body"][0]), ink, _esc(_fit(agent["company"], 700, 36))))
    out.append('<line x1="80" y1="148" x2="%d" y2="148" stroke="%s" stroke-width="1.5" opacity="0.32"/>'
               % (W - 80, ink))

    photo_y, box_w, box_h = 196, W - 160, 720
    fit = _fit_mode(d, bool(photo))
    panel_w, photo_h = _panel_size(box_w, box_h, photo, fit) if photo else (box_w, box_h)
    panel_x = (W - panel_w) / 2
    if photo and os.path.exists(photo):
        out.append('<clipPath id="photoClip"><rect x="%.0f" y="%d" width="%.0f" height="%.0f" rx="18"/>'
                   '</clipPath>' % (panel_x, photo_y, panel_w, photo_h))
        if fit == "meet":
            # 户型图/横幅图：白底完整显示，绝不裁切
            out.append('<rect x="%.0f" y="%d" width="%.0f" height="%.0f" rx="18" fill="#FFFFFF"/>'
                       % (panel_x, photo_y, panel_w, photo_h))
        out.append('<image href="%s" x="%.0f" y="%d" width="%.0f" height="%.0f" clip-path="url(#photoClip)" '
                   'preserveAspectRatio="xMidYMid %s"/>'
                   % (_img_href(photo), panel_x, photo_y, panel_w, photo_h, fit))
    else:
        out.append('<rect x="80" y="%d" width="%d" height="%d" rx="18" fill="#E7E0D4"/>'
                   '<text x="%d" y="%d" text-anchor="middle" font-family="%s" font-size="38" fill="%s">'
                   '本模板需要房源照片</text>'
                   % (photo_y, box_w, box_h, W // 2, photo_y + box_h // 2, _esc(FONTS["body"][0]), mute))

    ty = photo_y + photo_h + 132
    tsize = _auto_size(title, W - 160, 104, "body", 64)
    out.append('<text x="80" y="%d" font-family="%s" font-weight="900" font-size="%d" fill="%s" '
               'letter-spacing="4">%s</text>' % (ty, _esc(FONTS["title_serif"][0]), tsize, ink, _esc(title)))
    out.append('<text x="80" y="%d" font-family="%s" font-size="38" fill="%s" letter-spacing="3">%s</text>'
               % (ty + 84, _esc(FONTS["body"][0]), mute, _esc(_fit(sub, W - 160, 38))))
    out.append('<line x1="80" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="3"/>' % (ty + 128, W - 80, ty + 128, gold))

    info = [("建筑面积", ("%s㎡" % p.get("area")) if p.get("area") else "—"),
            ("户型", _layout_text(p) or "—"),
            ("楼层", p.get("floor") or "—"),
            ("朝向", p.get("orientation") or "—")]
    for i, (label, val) in enumerate(info):
        cx = 80 + (i % 2) * 470
        cy = ty + 208 + (i // 2) * 116
        out.append('<text x="%d" y="%d" font-family="%s" font-size="30" fill="%s" letter-spacing="2">%s</text>'
                   % (cx, cy, _esc(FONTS["body"][0]), mute, _esc(label)))
        out.append('<text x="%d" y="%d" font-family="%s" font-weight="700" font-size="%d" fill="%s">%s</text>'
                   % (cx, cy + 56, _esc(FONTS["title_heavy"][0]),
                      _auto_size(val, 400, 52, "title_heavy", 32), ink,
                      _esc(_fit(val, 400, 52, "title_heavy"))))

    py = ty + 440
    out.append('<line x1="80" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2" opacity="0.7"/>'
               % (py, W - 80, py, gold))
    ptext = _price_text(p)
    out.append('<text x="80" y="%d" font-family="%s" font-size="34" fill="%s">总价</text>'
               % (py + 66, _esc(FONTS["body"][0]), mute))
    psize = _auto_size(ptext, 520, 132, "title_heavy", 76)
    out.append('<text x="80" y="%d" font-family="%s" font-weight="900" font-size="%d" fill="%s" '
               'letter-spacing="-2">%s</text>'
               % (py + 66 + psize * 0.84, _esc(FONTS["title_serif"][0]), psize, ink, _esc(ptext)))
    up_text = _unit_price_text(p)
    if up_text:
        out.append('<text x="640" y="%d" font-family="%s" font-size="34" fill="%s">%s</text>'
                   % (py + 176, _esc(FONTS["body"][0]), mute, _esc(_fit(up_text, 340, 34))))

    foot_y = 1770
    out.append('<line x1="80" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.2" opacity="0.28"/>'
               % (foot_y - 60, W - 80, foot_y - 60, ink))
    name_line = " · ".join(str(x) for x in [agent.get("name"), agent.get("phone")] if x)
    out.append('<text x="80" y="%d" font-family="%s" font-size="38" fill="%s">%s</text>'
               % (foot_y, _esc(FONTS["body"][0]), ink, _esc(_fit(name_line, 700, 38))))
    if agent.get("wechat"):
        out.append('<text x="80" y="%d" font-family="%s" font-size="32" fill="%s">微信 %s</text>'
                   % (foot_y + 48, _esc(FONTS["body"][0]), mute, _esc(agent["wechat"])))
    if agent.get("company"):
        out.append('<text x="80" y="%d" font-family="%s" font-size="32" fill="%s">%s</text>'
                   % (foot_y + 92, _esc(FONTS["body"][0]), mute,
                      _esc(_fit(str(agent["company"]), 700, 32))))
    if d.get("qr_path"):
        out.append('<rect x="892" y="%d" width="124" height="124" rx="12" fill="#FFFFFF"/>' % (foot_y - 84))
        out.append('<image href="%s" x="900" y="%d" width="108" height="108"/>'
                   % (_img_href(d["qr_path"]), foot_y - 76))
    out.append(_footer(d.get("footer", "房源信息以实际看房为准"), color=mute, opacity=0.95, y=1904))
    out.append("</svg>")
    return "\n".join(out)


TEMPLATES = {"A": template_a, "B": template_b}


def render(d: dict, out_path: str | None = None) -> dict:
    """渲染海报：SVG → rsvg-convert → PNG。失败时返回 success=False（调用方回退 Pillow 引擎）。"""
    template = str(d.get("template") or "A").upper()
    if template not in TEMPLATES:
        return {"success": False, "error": "未知模板 %s（可选 A/B）" % template}
    svg = TEMPLATES[template](d)
    if not out_path:
        out_path = os.path.join(tempfile.mkdtemp(prefix="coco_poster_"), "poster_%s.png" % template)
    svg_path = out_path + ".svg"
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    conv = shutil.which("rsvg-convert")
    if not conv:
        return {"success": False, "error": "未安装 rsvg-convert（librsvg2-bin）", "svg_path": svg_path}
    proc = subprocess.run([conv, "-w", str(W), "-h", str(H), "-o", out_path, svg_path],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        return {"success": False, "error": "渲染失败：%s" % proc.stderr.strip()[:200], "svg_path": svg_path}
    return {"success": True, "png_path": out_path, "svg_path": svg_path, "template": template}
