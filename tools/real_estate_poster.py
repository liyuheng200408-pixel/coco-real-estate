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
    """价格展示（系统存元）：二手/一手房 → '400万'，出租 → '1000元/月'"""
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
    """模板1 高端黑金：深黑蓝渐变 + 金色价格 + 细线装饰（一手房）"""
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
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '一手房'}.get(p.get('property_type'), '房源')
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
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '一手房'}.get(p.get('property_type'), '房源')
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
    type_label = {'second_hand': '二手房', 'rental': '租房', 'new': '一手房'}.get(p.get('property_type'), '房源')
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


# ---------------- 经纪人名片与信息齐全校验（2026-09-19 加） ----------------
_FOOTER_TEXT = "房源信息以实际看房为准"


def _agent_card() -> dict:
    """读取经纪人名片（姓名/电话/微信/公司名）；未配置的字段为空串"""
    try:
        from tools.real_estate_settings import get_agent_card_or_empty

        return get_agent_card_or_empty()
    except Exception:
        return {}


def _property_photo(p) -> str:
    """房源第一张可用照片路径；没有则空串"""
    images = [x.strip() for x in str(p.get('images') or '').split(',') if x.strip()]
    for path in images:
        if os.path.exists(path):
            return path
    return ''


def _missing_poster_info(p, card, need_photo: bool, need_floor: bool = False,
                         need_orientation: bool = False) -> list:
    """出图前的信息齐全校验：返回缺失项清单（空列表 = 信息齐全，可以出图）

    need_floor / need_orientation：所选模板会显示这两栏（目前是 B 极简高级款）。
    **先问清再出图**，别等图做完了才发现两栏是「—」（2026-09-21 老板要求）。
    """
    miss = []
    if not (p.get('title') or p.get('community')):
        miss.append("房源名称/房号（如 262栋1009）")
    if not p.get('area'):
        miss.append("建筑面积（㎡）")
    if not p.get('price'):
        miss.append("价格（总价或月租）")
    if not card.get('company'):
        miss.append("您的公司/门店名称（海报品牌栏显示，不会写任何平台或虚构名称）")
    if not (card.get('name') or card.get('phone') or card.get('wechat')):
        miss.append("您的联系方式（姓名 / 电话 / 微信 至少一项，海报名片区使用）")
    if need_photo:
        miss.append("房源照片（所选模板需要照片；也可以改用不需要照片的模板）")
    if need_floor and not p.get('floor'):
        miss.append("楼层（如 11层；标题或地址里带房号如 301/1602 时系统会自动按房号推断，不必您提供）")
    if need_orientation and not p.get('orientation'):
        miss.append("朝向（如 朝南 / 南北通透；房号推不出朝向，需要您告知）")
    return miss


def _title_candidates(p) -> list:
    """主标题候选（2~3 个）：Coco 拿给经纪人挑，不擅自定稿"""
    tags = [x.strip() for x in str(p.get('tags') or '').replace('，', ',').replace('、', ',').split(',') if x.strip()]
    t = p.get('property_type')
    if t == 'rental':
        cands = ["拎包入住", "今日可看", "月租好房"]
    elif t == 'new':
        cands = ["新盘在售", "开发商直售", "今日主推"]
    else:
        cands = ["今日主推", "业主诚售", "仅此一套"]
    for tag in tags[:2]:
        cands.append(f"{tag}好房")
    renovation = str(p.get('renovation') or '')
    if renovation in ('精装', '豪装'):
        cands.append(f"{renovation}好房")
    out = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out[:3]


def _pick_template(p, template: str, photo: str) -> tuple:
    """返回 (模板代号, 选择理由)。template 为空时按房源特征自动挑。"""
    alias = {"premium": "A", "modern": "B", "vibrant": "A", "promo": "A", "classic": "B"}
    if template:
        code = alias.get(str(template).lower(), str(template).upper())
        if code in ("A", "B"):
            return code, "按指定模板"
    try:
        area = float(p.get('area') or 0)
    except (TypeError, ValueError):
        area = 0
    ren = str(p.get('renovation') or '')
    if photo and (area >= 110 or ren in ('豪装', '精装')):
        return "B", "房源照片齐全且面积/装修偏高端 → 极简高级款"
    return "A", "促销风主力款（无需照片也能出图）"


def generate_property_poster(property_id: int = None, title: str = None, qr_content: str = None,
                            template: str = None, poster_title: str = None,
                            allow_missing: bool = False, task_id: str = None) -> str:
    """生成房源海报（1080x1920）

    property_id 或 title 二选一：传 id 精确匹配；传标题模糊匹配。
    template 可选 A（红金促销）/B（极简高级，需照片）；不传按房源特征自动选。
    poster_title：海报主标题文案（先调 suggest_poster_titles 拿候选给经纪人挑）。
    allow_missing=True：经纪人明确说"先出图/信息就这些"时使用，缺的字段留空不编造。
    信息不齐时**不出图**，返回 missing 清单让 Coco 一次问清。
    """
    db = _get_db()
    p = db.get_available_property(property_id) if property_id is not None else None
    if p is None and title:
        hits = db.find_available_property_by_title(title)
        p = hits[0] if hits else None
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)

    card = _agent_card()
    photo = _property_photo(p)
    tpl, reason = _pick_template(p, template, photo)
    if tpl == "B" and not photo:
        if allow_missing:
            tpl, reason = "A", "无照片（经纪人同意先出图）→ 改为不需要照片的促销款"
        else:
            _need = ["房源照片"] + _missing_poster_info(p, card, need_photo=False,
                                                       need_floor=True, need_orientation=True)
            return json.dumps({
                "success": False,
                "need_photo": True,
                "missing": _need,
                "ask": ("所选模板（B 极简高级款）需要这些信息，请**一次问清后再出图**："
                        + "；".join(_need) + "。若经纪人不想发照片，可改用 A 红金促销款，或说「先出图」我再生成。"),
                "templates_without_photo": ["A"],
            }, ensure_ascii=False)

    # B 款会显示「楼层 / 朝向」两栏 —— 缺了就先问清，不要等出图后再补问
    _need_extras = tpl == "B"
    missing = (_missing_poster_info(p, card, need_photo=False,
                                    need_floor=_need_extras, need_orientation=_need_extras)
               if not allow_missing else [])
    cands = _title_candidates(p) if not poster_title else []
    if missing or cands:
        payload = {
            "success": False,
            "ask": ("海报还差这些，请一次问清后再出图（不要臆造、不要用占位符）："
                    + ("①缺信息：" + "、".join(missing) + "；" if missing else "")
                    + ("②主标题候选（发给经纪人挑，或他自己给文案）：" + " / ".join(cands) + "；" if cands else "")
                    + "拿齐后用 poster_title 传标题、必要时先 save_agent_card 存名片，再调用本工具。"
                      "经纪人若明确说「就这些，先出图」，带 allow_missing=true 再调一次。"),
        }
        if missing:
            payload["need_info"] = True
            payload["missing"] = missing
        if cands:
            payload["need_title"] = True
            payload["candidates"] = cands
        return json.dumps(payload, ensure_ascii=False)

    qr_path = None
    qr_value = qr_content or card.get('wechat') or ''
    if qr_value:
        qr_path = _make_qr_png(qr_value)

    data = {
        "template": tpl,
        "title": poster_title,
        "subtitle": " · ".join(str(x) for x in [p.get('community'), p.get('district'),
                                               p.get('renovation')] if x),
        "properties": [p],
        "agent": card,
        "qr_path": qr_path,
        "photo_path": photo or None,
        "footer": _FOOTER_TEXT,
    }

    pid = p.get('id') if isinstance(p, dict) else property_id
    out_path = os.path.join(_poster_dir(), f'poster_{pid}_{tpl}.png')
    result = None
    try:
        from tools import real_estate_poster_svg

        result = real_estate_poster_svg.render(data, out_path)
    except Exception as exc:  # noqa: BLE001
        result = {"success": False, "error": f"SVG 引擎不可用：{exc}"}

    notes = []
    if not result.get("success"):
        # 回落旧 Pillow 引擎（保证任何服务器都能出图）
        notes.append(f"已回落到旧引擎（原因：{result.get('error')}）")
        path = _render_legacy(p, qr_content, tpl)
    else:
        path = result["png_path"]

    if not card.get('company'):
        notes.append("未提供公司名称，海报未显示品牌（不臆造）")
    return json.dumps({
        "success": True,
        "property_id": property_id,
        "template": tpl,
        "why": reason,
        "poster_path": path,
        "notes": notes,
        "message": f"海报已生成（模板 {tpl}）：{path}（发送时用 MEDIA:{path} 直接发图）",
    }, ensure_ascii=False)


def _make_qr_png(content: str):
    """生成二维码 PNG（内容 = 经纪人微信名片）"""
    try:
        from tools import real_estate_poster_svg

        return real_estate_poster_svg.make_qr_png(
            content, os.path.join(_poster_dir(), 'poster_qr.png'))
    except Exception:
        return None


def _render_legacy(p, qr_content, tpl: str) -> str:
    """旧 Pillow 引擎兜底（rsvg 缺失/渲染失败时使用）"""
    from PIL import Image, ImageDraw

    template = {"A": "vibrant", "B": "modern"}.get(tpl, "modern")
    W, H = 1080, 1440
    img = Image.new('RGB', (W, H), (240, 244, 250))
    draw = ImageDraw.Draw(img)
    if template == 'vibrant':
        _draw_vibrant(img, draw, p, qr_content)
    else:
        _draw_modern(img, draw, p, qr_content)
    pid = p.get('id') if isinstance(p, dict) else None
    path = os.path.join(_poster_dir(), f'poster_{pid}_{template}.png')
    img.save(path)
    return path


def suggest_poster_titles(property_id: int = None, title: str = None, task_id: str = None) -> str:
    """给经纪人挑的海报主标题候选（2~3 个）"""
    db = _get_db()
    p = db.get_available_property(property_id) if property_id is not None else None
    if p is None and title:
        hits = db.find_available_property_by_title(title)
        p = hits[0] if hits else None
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)
    cands = _title_candidates(p)
    return json.dumps({
        "success": True,
        "candidates": cands,
        "ask": "把候选标题发给经纪人挑一个（他也可以自己给文案），选定后用 poster_title 传给 generate_property_poster。",
    }, ensure_ascii=False)


# 九宫格（旧版 3x3 拼图，保留兼容）
def generate_poster_grid(property_ids: str, qr_content: str = None, task_id: str = None) -> str:
    """生成朋友圈九宫格大图（3x3 拼图，最多9套房源）

    property_ids: 房源ID列表，逗号分隔（如 "1,2,3,4,5,6,7,8,9"），最多9个。
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return json.dumps({"success": False, "error": "缺少 Pillow 依赖，请执行 pip install Pillow"}, ensure_ascii=False)

    db = _get_db()
    # 2026-09-18 修：九宫格原先只在前 50 条里找编号，房源一多就报"房源不存在"
    ids = [int(x.strip()) for x in property_ids.split(',') if x.strip()][:9]
    by_id = {i: q for i in ids if (q := db.get_available_property(i)) is not None}
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
    schema={"name": "generate_property_poster", "description": "生成房源海报图（1080x1920）。**出图前必须先把信息问齐**：B 极简高级款需要 照片+楼层+朝向，缺任一项都会拒绝出图并返回 missing 清单（一次问清，不要先出图再补问）；楼层若标题/地址带房号会自动推断。未提供主标题会返回 2~3 个候选让经纪人挑。模板 A 红金促销/B 极简高级(需照片)，不传自动选。返回图片路径，用 MEDIA:路径 发送", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID（与 title 二选一，优先用 ID）"},
            "title": {"type": "string", "description": "房源标题关键词（与 property_id 二选一，模糊匹配）"},
            "poster_title": {"type": "string", "description": "海报主标题文案（先用 suggest_poster_titles 拿候选给经纪人挑）"},
            "template": {"type": "string", "enum": ["A", "B"], "description": "可选：A 红金促销（默认，无需照片）/B 极简高级（需照片）"},
            "qr_content": {"type": "string", "description": "可选：二维码内容；不传则用经纪人名片里的微信号（微信名片）"},
            "allow_missing": {"type": "boolean", "description": "仅当经纪人明确说「就这些，先出图」时传 true；缺的字段留空，不编造"},
        },
    }},
    handler=lambda args, **kw: generate_property_poster(**args),
)

registry.register(
    name="suggest_poster_titles",
    toolset="real_estate",
    schema={"name": "suggest_poster_titles", "description": "给房产海报出 2~3 个主标题候选（按房源类型/标签生成），把候选发给经纪人挑，选定后用 poster_title 传给 generate_property_poster", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID（与 title 二选一）"},
            "title": {"type": "string", "description": "房源标题关键词（与 property_id 二选一）"},
        },
    }},
    handler=lambda args, **kw: suggest_poster_titles(**args),
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
