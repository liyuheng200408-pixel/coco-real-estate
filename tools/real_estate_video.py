"""
Coco 房产工具 - 短视频口播脚本生成
抖音/视频号 30 秒卖房口播脚本：开头钩子 + 房源亮点 + 价格钩子 + 行动号召
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


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


def _layout_text(p):
    rooms, halls = p.get('rooms'), p.get('halls')
    if rooms and halls:
        return f"{rooms}室{halls}厅"
    if rooms == 1:
        return '开间'
    return ''


def _highlights(p):
    """从房源数据提取 3 个可口播的亮点"""
    items = []
    area = p.get('area')
    layout = _layout_text(p)
    if area:
        items.append(f"{area}㎡{' ' + layout if layout else ''}空间")
    if p.get('orientation'):
        items.append(f"{p['orientation']}朝向")
    if p.get('renovation'):
        items.append(f"{p['renovation']}装修")
    if p.get('floor'):
        items.append(f"{p['floor']}楼层")
    if p.get('has_elevator'):
        items.append('带电梯')
    if p.get('year_built'):
        items.append(f"{p['year_built']}年建成")
    tags = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]
    for tag in tags:
        if '景观' in tag:
            items.append(tag.split(':', 1)[-1] + '景观')
        else:
            items.append(tag)
    # 去重并补足/截断到 3 个
    seen, uniq = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            uniq.append(it)
    return uniq[:3]


def generate_short_video_script(property_id: int, platform: str = "douyin", task_id: str = None) -> str:
    """生成 30 秒短视频口播脚本

    platform: douyin(抖音，快节奏强悬念) / shipinhao(视频号，接地气重信任)
    结构：0-3s 钩子 → 3-20s 亮点 → 20-25s 价格 → 25-30s 行动号召
    """
    db = _get_db()
    properties = db.search_properties()
    p = None
    for item in properties:
        if item.get('id') == property_id:
            p = item
            break
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)

    if platform not in ('douyin', 'shipinhao'):
        return json.dumps({"success": False, "error": "platform 必须是 douyin 或 shipinhao"}, ensure_ascii=False)

    title = p.get('title') or '这套房子'
    price = _fmt_price(p)
    district = p.get('district') or p.get('community') or '这个位置'
    layout = _layout_text(p)
    highlights = _highlights(p)
    h1 = highlights[0] if len(highlights) > 0 else '格局方正'
    h2 = highlights[1] if len(highlights) > 1 else '采光通透'
    h3 = highlights[2] if len(highlights) > 2 else '产权清晰随时看房'

    if platform == 'douyin':
        hook = f"在{district}，{price}就能拿下这套{layout or '房子'}，你敢信？"
        price_hook = f"重点来了，总价只要{price}，这个价格在{district}基本找不到第二套"
        cta = "想看房源的评论区扣1，我挨个发资料，手慢无！"
        closing = f"关注我，{district}好房每天更新"
    else:
        hook = f"今天带大家看一套{district}的房子，{layout or '面积适中'}，性价比很高"
        if p.get('property_type') == 'rental':
            price_hook = f"这套房{price}，业主诚心出租，租金还能谈"
        else:
            price_hook = f"这套房总价{price}，业主诚心卖，价格还能谈"
        cta = "想实地看看的朋友，点个关注私信我，随时带你看房"
        closing = "我是本地中介，房源真实，看房不收费"

    script = (
        f"【0-3秒 钩子】{hook}\n"
        f"【3-20秒 亮点】这套房子的亮点有三个：第一，{h1}；第二，{h2}；第三，{h3}。\n"
        f"【20-25秒 价格】{price_hook}。\n"
        f"【25-30秒 行动号召】{cta}\n"
        f"【结尾】{closing}"
    )

    return json.dumps({
        "success": True,
        "platform": platform,
        "property_id": property_id,
        "title": title,
        "duration": "30秒",
        "highlights": highlights,
        "script": script,
        "tip": "录制时语速保持每分钟240-260字，价格和地点放慢强调；可让Coco按此框架润色成更口语化的版本",
    }, ensure_ascii=False)


registry.register(
    name="generate_short_video_script",
    toolset="real_estate",
    schema={"name": "generate_short_video_script", "description": "生成30秒短视频口播脚本（抖音/视频号），包含开头钩子、房源亮点、价格钩子、行动号召", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "platform": {"type": "string", "enum": ["douyin", "shipinhao"], "description": "douyin=抖音（快节奏强悬念），shipinhao=视频号（接地气重信任）"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: generate_short_video_script(**args),
)
