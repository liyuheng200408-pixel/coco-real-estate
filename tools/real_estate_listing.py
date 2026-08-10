"""
Coco 房产工具 - 房源发布文案生成
为不同平台生成标准化的房源发布文案
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def _fmt_title(p):
    return p.get('title') or f"{p.get('community') or ''} {p.get('rooms') or '?'}室{p.get('halls') or '?'}厅"


def _fmt_basic(p):
    parts = []
    parts.append(f"面积：{p.get('area')}㎡")
    if p.get('rooms'):
        parts.append(f"户型：{p.get('rooms')}室{p.get('halls') or 0}厅{p.get('bathrooms') or 1}卫")
    if p.get('orientation'):
        parts.append(f"朝向：{p.get('orientation')}")
    if p.get('floor'):
        parts.append(f"楼层：{p.get('floor')}")
    if p.get('renovation'):
        parts.append(f"装修：{p.get('renovation')}")
    if p.get('year_built'):
        parts.append(f"建成年份：{p.get('year_built')}")
    if p.get('has_elevator') == 1:
        parts.append("有电梯")
    if p.get('parking') == 1:
        parts.append("有车位")
    return "，".join(parts)


def generate_listing_copy(property_id: int, platform: str = "friends", task_id: str = None) -> str:
    """生成房源发布文案

    platform: friends(朋友圈) / beike(贝壳) / anjuke(安居客) / 58
    """
    db = _get_db()
    properties = db.search_properties()
    p = None
    for item in properties:
        if item.get('id') == property_id:
            p = item
            break
    if p is None:
        # 尝试直接查（可能非在售）
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)

    title = _fmt_title(p)
    basic = _fmt_basic(p)
    price = p.get('price')
    unit_price = p.get('unit_price')
    community = p.get('community') or ''
    district = p.get('district') or ''
    address = p.get('address') or ''

    if platform == "friends":
        copy = (
            f"🏠 优质房源推荐\n\n"
            f"{title}\n"
            f"📍 {district} {community}\n"
            f"{basic}\n"
            f"💰 总价 {price}万"
            + (f"（单价 {unit_price}元/㎡）" if unit_price else "")
            + "\n\n"
            f"感兴趣的私信我，随时约看房！"
        )
    elif platform == "beike":
        copy = (
            f"{title}，{district} {community}\n"
            f"{basic}\n"
            f"总价：{price}万元"
            + (f"，单价：{unit_price}元/㎡" if unit_price else "")
            + "\n"
            f"地址：{address or community}\n"
            f"真实房源，看房方便，欢迎咨询。"
        )
    elif platform == "anjuke":
        copy = (
            f"【{title}】\n"
            f"{district}·{community}\n"
            f"{basic}\n"
            f"售价：{price}万元"
            + (f"（{unit_price}元/㎡）" if unit_price else "")
            + "\n"
            f"地址：{address or community}\n"
            f"房源真实有效，随时可看，中介费优惠，欢迎来电咨询。"
        )
    elif platform == "58":
        copy = (
            f"{title}（{community or district}）\n"
            f"【房屋信息】{basic}\n"
            f"【售价】{price}万元"
            + (f"（单价{unit_price}元/㎡）" if unit_price else "")
            + "\n"
            f"【位置】{address or community or district}\n"
            f"【亮点】真实房源，产权清晰，看房方便，价格可谈。"
        )
    else:
        return json.dumps({"success": False, "error": "platform 必须是 friends/beike/anjuke/58"}, ensure_ascii=False)

    return json.dumps({"success": True, "platform": platform, "copy": copy}, ensure_ascii=False)


registry.register(
    name="generate_listing_copy",
    toolset="real_estate",
    schema={"name": "generate_listing_copy", "description": "生成房源发布文案（朋友圈/贝壳/安居客/58）", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "platform": {"type": "string", "enum": ["friends", "beike", "anjuke", "58"], "description": "发布平台"},
        },
        "required": ["property_id", "platform"],
    }},
    handler=lambda args, **kw: generate_listing_copy(**args),
)
