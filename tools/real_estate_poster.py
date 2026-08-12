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
    """价格展示（系统存元）：二手/新房 → '400万'，出租 → '1000元/月'"""
    price = p.get('price')
    if price is None:
        return '价格待定'
    price = float(price)
    if p.get('property_type') == 'rental':
        return f"{price:.0f}元/月"
    wan = price / 10000
    return f"{wan:.0f}万" if wan == int(wan) else f"{wan:.1f}万"


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


# ==================== B 档专业模板（2026-08-12 加） ====================

def _get_brand():
    """品牌名：数据库 re_settings.brand_name 优先，环境变量 COCO_BRAND 兜底；都无返回空"""
    try:
        from tools.real_estate_settings import get_brand_or_none
        db_brand = get_brand_or_none()
        if db_brand:
            return db_brand
    except Exception:
        pass
    return os.getenv('COCO_BRAND', '')


def _load_property_image(p, target_w, target_h):
    """加载房源第一张图片并 cover 裁剪到目标尺寸；无图返回 None"""
    from PIL import Image
    images = [x.strip() for x in (p.get('images') or '').split(',') if x.strip()]
    if not images:
        return None
    try:
        img = Image.open(images[0]).convert('RGB')
    except Exception:
        return None
    # cover 裁剪
    iw, ih = img.size
    scale = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _overlay_gradient_mask(img, bottom_dark=True, alpha=150):
    """在图片上叠加竖向渐变蒙版（底部压暗，让文字可读）"""
    from PIL import Image, ImageDraw
    w, h = img.size
    mask = Image.new('L', (1, h), 0)
    md = ImageDraw.Draw(mask)
    if bottom_dark:
        for y in range(h):
            ratio = y / max(h - 1, 1)
            md.point((0, y), fill=int(alpha * ratio))
    else:
        for y in range(h):
            ratio = 1 - y / max(h - 1, 1)
            md.point((0, y), fill=int(alpha * ratio))
    mask = mask.resize((w, h))
    black = Image.new('RGB', (w, h), (0, 0, 0))
    img.paste(black, (0, 0), mask)
    return img


def _rounded_card(size, radius, fill, outline=None, width=0):
    """圆角卡片（带可选描边）"""
    from PIL import Image, ImageDraw
    w, h = size
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=fill,
                        outline=outline, width=width)
    return card


def _draw_qr(img, qr_content, center_x, center_y, size=260, bg_light=True):
    """在 img 上画二维码（居中定位）"""
    if not qr_content:
        return
    try:
        import qrcode
        from PIL import Image
        qr = qrcode.make(qr_content)
        qr = qr.convert('RGB')
        # 白底
        pad = 18
        panel = Image.new('RGB', (size + pad * 2, size + pad * 2), (255, 255, 255))
        panel.paste(qr.resize((size, size)), (pad, pad))
        img.paste(panel, (int(center_x - panel.width / 2), int(center_y - panel.height / 2)))
    except ImportError:
        pass


def _draw_premium(img, draw, p, qr_content):
    """模板1 高端黑金：深黑蓝渐变 + 金色价格 + 细线装饰（新房）"""
    from PIL import ImageDraw
    W, H = img.size
    gold = (212, 175, 55)
    white = (255, 255, 255)
    soft = (200, 210, 230)

    # 顶部房源大图（0-640）压暗
    photo = _load_property_image(p, W, 640)
    if photo:
        photo = _overlay_gradient_mask(photo, bottom_dark=True, alpha=190)
        img.paste(photo, (0, 0))
    else:
        c1, c2 = _type_colors(p.get('property_type'))
        img.paste(_gradient((W, 640), c1, c2), (0, 0))

    # 类型角标（左上）
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '新房'}.get(p.get('property_type'), '房源')
    f_type = _load_font(30)
    tw = draw.textlength(type_label, font=f_type) + 36
    draw.rounded_rectangle([(40, 40), (40 + tw, 92)], radius=26,
                           fill=(212, 175, 55, 220))
    draw.text((40 + 18, 48), type_label, font=f_type, fill=(20, 20, 25))

    # 品牌（右上）
    f_brand = _load_font(34)
    brand = _get_brand()
    bw = draw.textlength(brand, font=f_brand)
    draw.text((W - 40 - bw, 48), brand, font=f_brand, fill=white)

    # 标题（图片下方）
    f_title = _load_font(56)
    title = _ellipsis(draw, p.get('title') or '优质房源', f_title, W - 100)
    draw.text((50, 700), title, font=f_title, fill=(30, 30, 40))

    # 金色装饰线
    draw.rectangle([(50, 800), (160, 806)], fill=gold)

    # 价格
    price_text = _fmt_price(p)
    f_price = _load_font(120)
    draw.text((50, 830), price_text, font=f_price, fill=gold)
    f_unit = _load_font(34)
    if p.get('unit_price'):
        draw.text((50, 990), f"单价 {p['unit_price']} 元/㎡", font=f_unit, fill=(120, 125, 140))

    # 信息卡（白色圆角卡片）
    area = p.get('area')
    rooms, halls = p.get('rooms'), p.get('halls')
    layout = f"{rooms}室{halls}厅" if (rooms and halls) else ('开间' if rooms == 1 else '')
    district = p.get('district') or p.get('community') or '位置详情'
    items = [
        ('面积', f"{area}㎡" if area else '-'),
        ('户型', layout or '-'),
        ('区域', district),
    ]
    card = _rounded_card((W - 100, 180), 24, (255, 255, 255))
    img.paste(card, (50, 1050), card)
    f_k = _load_font(30)
    f_v = _load_font(36)
    x = 80
    for k, v in items:
        draw.text((x, 1085), k, font=f_k, fill=(130, 135, 150))
        draw.text((x, 1125), _ellipsis(draw, v, f_v, 260), font=f_v, fill=(40, 40, 50))
        x += 310

    # 标签（金色描边）
    tags = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]
    y = 1270
    if tags:
        f_tag = _load_font(30)
        x = 50
        for tag in tags[:4]:
            tw = draw.textlength(tag, font=f_tag) + 36
            draw.rounded_rectangle([(x, y), (x + tw, y + 58)], radius=29,
                                   outline=gold, width=2)
            draw.text((x + 18, y + 12), tag, font=f_tag, fill=(60, 55, 40))
            x += tw + 20

    # 底部：二维码 + 引导语
    if qr_content:
        _draw_qr(img, qr_content, W - 170, H - 150, size=200)
    f_foot = _load_font(34)
    draw.text((50, H - 220), "真实房源 · 随时约看", font=f_foot, fill=(110, 115, 130))


def _draw_modern(img, draw, p, qr_content):
    """模板2 现代白卡：白/浅灰背景 + 圆角卡片 + 清爽灰调（二手房）"""
    from PIL import Image, ImageDraw
    W, H = img.size
    dark = (40, 45, 55)
    gray = (130, 135, 145)
    accent = (52, 120, 246)
    white = (255, 255, 255)
    bg = (245, 247, 250)

    # 背景浅灰
    img.paste(Image.new('RGB', (W, H), bg), (0, 0))

    # 顶部大图（0-560）白色圆角卡片包裹
    photo = _load_property_image(p, W - 60, 500)
    if photo:
        photo = _overlay_gradient_mask(photo, bottom_dark=True, alpha=140)
        card = _rounded_card((W - 60, 500), 28, (255, 255, 255))
        img.paste(card, (30, 30), card)
        img.paste(photo, (30, 30), card)
    else:
        c1, c2 = _type_colors(p.get('property_type'))
        photo2 = _gradient((W - 60, 500), c1, c2)
        card = _rounded_card((W - 60, 500), 28, (255, 255, 255))
        img.paste(card, (30, 30), card)
        img.paste(photo2, (30, 30), card)

    # 类型角标
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '新房'}.get(p.get('property_type'), '房源')
    f_type = _load_font(28)
    tw = draw.textlength(type_label, font=f_type) + 30
    draw.rounded_rectangle([(52, 52), (52 + tw, 96)], radius=22, fill=accent)
    draw.text((52 + 15, 60), type_label, font=f_type, fill=white)

    # 标题
    f_title = _load_font(52)
    title = _ellipsis(draw, p.get('title') or '优质房源', f_title, W - 100)
    draw.text((50, 590), title, font=f_title, fill=dark)

    # 价格（accent 蓝）
    price_text = _fmt_price(p)
    f_price = _load_font(110)
    draw.text((50, 660), price_text, font=f_price, fill=accent)
    f_unit = _load_font(32)
    if p.get('unit_price'):
        draw.text((50, 800), f"单价 {p['unit_price']} 元/㎡", font=f_unit, fill=gray)

    # 信息卡（三列白卡）
    area = p.get('area')
    rooms, halls = p.get('rooms'), p.get('halls')
    layout = f"{rooms}室{halls}厅" if (rooms and halls) else ('开间' if rooms == 1 else '')
    district = p.get('district') or p.get('community') or '位置详情'
    items = [
        ('面积', f"{area}㎡" if area else '-'),
        ('户型', layout or '-'),
        ('区域', district),
    ]
    f_k = _load_font(28)
    f_v = _load_font(32)
    x = 50
    for k, v in items:
        card = _rounded_card((300, 130), 20, white)
        img.paste(card, (x, 850), card)
        draw.text((x + 22, 880), k, font=f_k, fill=gray)
        draw.text((x + 22, 915), _ellipsis(draw, v, f_v, 250), font=f_v, fill=dark)
        x += 320

    # 标签（浅蓝底圆角）
    tags = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]
    y = 1020
    if tags:
        f_tag = _load_font(28)
        x = 50
        for tag in tags[:4]:
            tw = draw.textlength(tag, font=f_tag) + 32
            draw.rounded_rectangle([(x, y), (x + tw, y + 54)], radius=27,
                                   fill=(232, 240, 255))
            draw.text((x + 16, y + 11), tag, font=f_tag, fill=accent)
            x += tw + 18

    # 底部品牌 + 二维码
    f_brand = _load_font(30)
    brand = _get_brand()
    draw.text((50, H - 130), brand, font=f_brand, fill=gray)
    f_foot = _load_font(30)
    draw.text((50, H - 80), "真实房源 · 随时约看", font=f_foot, fill=gray)
    if qr_content:
        _draw_qr(img, qr_content, W - 140, H - 120, size=170)


def _draw_vibrant(img, draw, p, qr_content):
    """模板3 活力橙红：橙红渐变 + 大号促销价签 + 行动号召（出租/快节奏）"""
    from PIL import ImageDraw
    W, H = img.size
    white = (255, 255, 255)
    soft = (255, 225, 215)
    red = (232, 65, 24)

    # 顶部大图 + 渐变
    photo = _load_property_image(p, W, 620)
    if photo:
        photo = _overlay_gradient_mask(photo, bottom_dark=True, alpha=170)
        img.paste(photo, (0, 0))
    else:
        c1, c2 = ((214, 69, 28), (255, 140, 60))
        img.paste(_gradient((W, 620), c1, c2), (0, 0))

    # 类型角标
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '新房'}.get(p.get('property_type'), '房源')
    f_type = _load_font(30)
    tw = draw.textlength(type_label, font=f_type) + 36
    draw.rounded_rectangle([(40, 40), (40 + tw, 92)], radius=26, fill=red)
    draw.text((40 + 18, 48), type_label, font=f_type, fill=white)

    # 品牌
    f_brand = _load_font(34)
    brand = _get_brand()
    bw = draw.textlength(brand, font=f_brand)
    draw.text((W - 40 - bw, 48), brand, font=f_brand, fill=white)

    # 标题
    f_title = _load_font(56)
    title = _ellipsis(draw, p.get('title') or '优质房源', f_title, W - 100)
    draw.text((50, 680), title, font=f_title, fill=(40, 30, 25))

    # 价格（橙红大价签）
    price_text = _fmt_price(p)
    f_price = _load_font(130)
    draw.text((50, 760), price_text, font=f_price, fill=red)
    f_unit = _load_font(34)
    if p.get('unit_price'):
        draw.text((50, 930), f"单价 {p['unit_price']} 元/㎡", font=f_unit, fill=(140, 90, 70))

    # 信息卡（半透明白卡片）
    area = p.get('area')
    rooms, halls = p.get('rooms'), p.get('halls')
    layout = f"{rooms}室{halls}厅" if (rooms and halls) else ('开间' if rooms == 1 else '')
    district = p.get('district') or p.get('community') or '位置详情'
    items = [
        ('面积', f"{area}㎡" if area else '-'),
        ('户型', layout or '-'),
        ('区域', district),
    ]
    f_k = _load_font(30)
    f_v = _load_font(34)
    x = 50
    for k, v in items:
        card = _rounded_card((300, 120), 20, (255, 255, 255, 230))
        img.paste(card, (x, 1000), card)
        draw.text((x + 22, 1025), k, font=f_k, fill=(150, 100, 80))
        draw.text((x + 22, 1060), _ellipsis(draw, v, f_v, 250), font=f_v, fill=(60, 40, 30))
        x += 320

    # 标签（橙红描边）
    tags = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]
    y = 1160
    if tags:
        f_tag = _load_font(28)
        x = 50
        for tag in tags[:4]:
            tw = draw.textlength(tag, font=f_tag) + 32
            draw.rounded_rectangle([(x, y), (x + tw, y + 54)], radius=27,
                                   outline=red, width=2)
            draw.text((x + 16, y + 11), tag, font=f_tag, fill=red)
            x += tw + 18

    # 底部行动号召 + 二维码
    f_cta = _load_font(44)
    draw.text((50, H - 260), "🏠 好房不等人 速约看房", font=f_cta, fill=red)
    if qr_content:
        _draw_qr(img, qr_content, W - 150, H - 130, size=190)
    f_foot = _load_font(30)
    draw.text((50, H - 80), _get_brand() + " · 真实房源", font=f_foot, fill=(140, 90, 70))


def generate_property_poster(property_id: int = None, title: str = None, qr_content: str = None, template: str = None, task_id: str = None) -> str:
    """生成房源朋友圈海报图（1080x1440）

    property_id 或 title 二选一：传 id 精确匹配；传标题模糊匹配（包含关系，多个匹配取第一个）。
    template 可选：premium（高端黑金）/ modern（现代白卡）/ vibrant（活力橙红）
    不传时按房源类型自动选：new→premium、second_hand→modern、rental→vibrant。
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
    if property_id is not None:
        for item in properties:
            if item.get('id') == property_id:
                p = item
                break
    elif title:
        # 标题模糊匹配：包含关系，返回第一个命中（2026-08-12 加：Coco 曾用标题搜索失败）
        tl = str(title).strip()
        for item in properties:
            if tl and tl in (item.get('title') or ''):
                p = item
                break
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)

    # 品牌必须真实：数据库/环境变量都无品牌时，不生成，让模型先询问经纪人（2026-08-12 加）
    brand = _get_brand()
    if not brand:
        return json.dumps({
            "success": False,
            "need_brand": True,
            "error": "经纪人品牌名称未配置。请先询问经纪人公司/门店名称（说明：海报上需要展示您的品牌，避免用错误信息生成），获取准确名称后调用 save_agent_brand 保存，再生成海报。",
        }, ensure_ascii=False)

    # 模板选择：显式指定 > 按类型自动
    if not template:
        template = {'new': 'premium', 'second_hand': 'modern', 'rental': 'vibrant'}.get(
            p.get('property_type'), 'modern')
    if template not in ('premium', 'modern', 'vibrant'):
        template = 'modern'

    W, H = 1080, 1440
    img = Image.new('RGB', (W, H), (240, 244, 250))
    draw = ImageDraw.Draw(img)

    if template == 'premium':
        _draw_premium(img, draw, p, qr_content)
    elif template == 'vibrant':
        _draw_vibrant(img, draw, p, qr_content)
    else:
        _draw_modern(img, draw, p, qr_content)

    path = os.path.join(_poster_dir(), f'poster_{property_id}_{template}.png')
    img.save(path)
    return json.dumps({
        "success": True,
        "property_id": property_id,
        "template": template,
        "poster_path": path,
        "message": f"海报已生成（模板 {template}）：{path}（发送时用 MEDIA:{path} 直接发图）",
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
    schema={"name": "generate_property_poster", "description": "生成房源朋友圈海报图（标题+价格+面积+可选二维码），支持三套模板（premium 高端黑金/modern 现代白卡/vibrant 活力橙红）。传 property_id 或 title（标题模糊匹配）定位房源，返回图片路径，发消息时用 MEDIA:路径 发送图片", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID（与 title 二选一，优先用 ID）"},
            "title": {"type": "string", "description": "房源标题关键词（与 property_id 二选一，模糊匹配）"},
            "qr_content": {"type": "string", "description": "可选：二维码内容（微信号/房源链接），不传不画二维码"},
            "template": {"type": "string", "enum": ["premium", "modern", "vibrant"], "description": "可选：海报模板 premium(高端黑金)/modern(现代白卡)/vibrant(活力橙红)，不传按房源类型自动选"},
        },
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
