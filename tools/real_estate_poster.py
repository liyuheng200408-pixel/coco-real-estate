"""
Coco 房产工具 - 房源海报/九宫格生成
一键生成朋友圈海报图（标题+价格+面积+二维码），返回图片路径供飞书直接发送
"""
import json
import os
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


_FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    '/System/Library/Fonts/PingFang.ttc',
    'C:/Windows/Fonts/msyh.ttc',
]


def _load_font(size):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _poster_dir():
    cache_dir = os.path.expanduser('~/.hermes/image_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _fmt_price(p):
    """价格展示：二手/新房 → '40万'，出租 → '0.13万/月'"""
    price = p.get('price')
    if price is None:
        return '价格待定'
    price = float(price)
    if p.get('property_type') == 'rental':
        return f"{price:.2f}万/月" if price < 1 else f"{price:.0f}万/月"
    return f"{price:.0f}万" if price == int(price) else f"{price:.1f}万"


def _gradient(size, c1, c2):
    """竖版线性渐变背景"""
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new('RGB', (w, h), c1)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _type_colors(property_type):
    return {
        'second_hand': ((30, 58, 95), (46, 94, 158)),    # 深蓝 → 蓝
        'new': ((124, 45, 18), (194, 65, 12)),           # 深橙 → 橙
        'rental': ((20, 83, 45), (34, 139, 85)),         # 深绿 → 绿
    }.get(property_type, ((30, 58, 95), (46, 94, 158)))


def _ellipsis(draw, text, font, max_width):
    """按像素宽度截断文本"""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + '…', font=font) > max_width:
        text = text[:-1]
    return text + '…'


def generate_property_poster(property_id: int, qr_content: str = None, task_id: str = None) -> str:
    """生成房源朋友圈海报图（1080x1440）

    qr_content 可选：二维码内容（如微信号/房源链接），不传则不画二维码。
    返回图片绝对路径，可直接在飞书发送。
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return json.dumps({"success": False, "error": "缺少 Pillow 依赖，请执行 pip install Pillow"}, ensure_ascii=False)

    db = _get_db()
    properties = db.search_properties()
    p = None
    for item in properties:
        if item.get('id') == property_id:
            p = item
            break
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)

    W, H = 1080, 1440
    c1, c2 = _type_colors(p.get('property_type'))
    img = _gradient((W, H), c1, c2)
    draw = ImageDraw.Draw(img)
    white = (255, 255, 255)
    soft = (220, 230, 245)

    # 品牌条
    draw.rectangle([(0, 0), (W, 150)], fill=(0, 0, 0, 90))
    f_brand = _load_font(52)
    draw.text((60, 45), "COCO 房产", font=f_brand, fill=white)
    f_type = _load_font(36)
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '新房'}.get(p.get('property_type'), '房源')
    draw.text((W - 200, 52), type_label, font=f_type, fill=soft)

    # 标题（最多两行）
    f_title = _load_font(64)
    title = p.get('title') or '优质房源'
    line1 = _ellipsis(draw, title, f_title, W - 120)
    draw.text((60, 210), line1, font=f_title, fill=white)

    # 价格
    price_text = _fmt_price(p)
    f_price = _load_font(150)
    draw.text((60, 380), price_text, font=f_price, fill=white)
    f_unit = _load_font(40)
    if p.get('unit_price'):
        draw.text((60, 570), f"单价 {p['unit_price']} 元/㎡", font=f_unit, fill=soft)

    # 信息卡
    f_info = _load_font(46)
    area = p.get('area')
    rooms = p.get('rooms')
    halls = p.get('halls')
    layout = f"{rooms}室{halls}厅" if (rooms and halls) else ('开间' if rooms == 1 else '')
    district = p.get('district') or p.get('community') or '位置详情'
    info_lines = [
        f"面积：{area}㎡" if area else None,
        f"户型：{layout}" if layout else None,
        f"区域：{district}",
    ]
    info_lines = [x for x in info_lines if x]
    y = 700
    for line in info_lines:
        draw.text((60, y), line, font=f_info, fill=white)
        y += 76

    # 特色标签
    tags = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]
    if tags:
        f_tag = _load_font(36)
        x = 60
        for tag in tags[:4]:
            tw = draw.textlength(tag, font=f_tag) + 40
            draw.rounded_rectangle([(x, y + 10), (x + tw, y + 74)], radius=32, fill=(255, 255, 255, 40), outline=soft)
            draw.text((x + 20, y + 18), tag, font=f_tag, fill=white)
            x += tw + 24

    # 底部文案 + 二维码
    f_foot = _load_font(40)
    draw.text((60, H - 320), "真实房源 · 随时约看", font=f_foot, fill=soft)
    if qr_content:
        try:
            import qrcode
            qr = qrcode.make(qr_content)
            qr = qr.convert('RGB').resize((280, 280))
            img.paste(qr, (W - 340, H - 360))
        except ImportError:
            pass  # 无 qrcode 库则只出文案版

    path = os.path.join(_poster_dir(), f'poster_{property_id}.png')
    img.save(path)
    return json.dumps({
        "success": True,
        "property_id": property_id,
        "poster_path": path,
        "message": f"海报已生成：{path}（发送时用 MEDIA:{path} 直接发图）",
    }, ensure_ascii=False)


def generate_poster_grid(property_ids: str, qr_content: str = None, task_id: str = None) -> str:
    """生成朋友圈九宫格大图（3x3 拼图，最多9套房源）

    property_ids: 房源ID列表，逗号分隔（如 "1,2,3,4,5,6,7,8,9"），最多9个。
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return json.dumps({"success": False, "error": "缺少 Pillow 依赖，请执行 pip install Pillow"}, ensure_ascii=False)

    db = _get_db()
    properties = db.search_properties()
    by_id = {p['id']: p for p in properties}
    ids = [int(x.strip()) for x in property_ids.split(',') if x.strip()][:9]
    if not ids:
        return json.dumps({"success": False, "error": "请提供房源ID列表（逗号分隔，最多9个）"}, ensure_ascii=False)

    missing = [i for i in ids if i not in by_id]
    if missing:
        return json.dumps({"success": False, "error": f"房源不存在或不在售：{missing}"}, ensure_ascii=False)

    cell, gap = 360, 0
    grid = Image.new('RGB', (cell * 3, cell * 3), (240, 244, 250))
    draw = ImageDraw.Draw(grid)
    f_title = _load_font(38)
    f_price = _load_font(44)
    f_area = _load_font(30)

    for idx, pid in enumerate(ids):
        p = by_id[pid]
        cx, cy = (idx % 3) * cell, (idx // 3) * cell
        c1, c2 = _type_colors(p.get('property_type'))
        card = _gradient((cell, cell), c1, c2)
        d = ImageDraw.Draw(card)
        title = _ellipsis(d, p.get('title') or '房源', f_title, cell - 40)
        d.text((20, 20), title, font=f_title, fill=(255, 255, 255))
        d.text((20, 130), _fmt_price(p), font=f_price, fill=(255, 255, 255))
        area = f"{p.get('area')}㎡" if p.get('area') else ''
        d.text((20, 240), area, font=f_area, fill=(220, 230, 245))
        grid.paste(card, (cx, cy))

    path = os.path.join(_poster_dir(), 'poster_grid.png')
    grid.save(path)
    return json.dumps({
        "success": True,
        "property_ids": ids,
        "grid_path": path,
        "message": f"九宫格已生成：{path}（发送时用 MEDIA:{path} 直接发图）",
    }, ensure_ascii=False)


registry.register(
    name="generate_property_poster",
    toolset="real_estate",
    schema={"name": "generate_property_poster", "description": "生成房源朋友圈海报图（标题+价格+面积+可选二维码），返回图片路径，发消息时用 MEDIA:路径 发送图片", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "qr_content": {"type": "string", "description": "可选：二维码内容（微信号/房源链接），不传不画二维码"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: generate_property_poster(**args),
)

registry.register(
    name="generate_poster_grid",
    toolset="real_estate",
    schema={"name": "generate_poster_grid", "description": "生成朋友圈九宫格大图（3x3拼图，最多9套房源），返回图片路径，发消息时用 MEDIA:路径 发送图片", "parameters": {
        "type": "object",
        "properties": {
            "property_ids": {"type": "string", "description": "房源ID列表，逗号分隔，最多9个，如 1,2,3,4,5,6,7,8,9"},
            "qr_content": {"type": "string", "description": "可选：二维码内容"},
        },
        "required": ["property_ids"],
    }},
    handler=lambda args, **kw: generate_poster_grid(**args),
)
