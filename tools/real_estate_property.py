"""
Coco 房产工具 - 房源管理
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def add_property(
    title: str, price: int, area: float,
    community: str = None, district: str = None, address: str = None,
    rooms: int = None, halls: int = None, bathrooms: int = None,
    floor: str = None, orientation: str = None,
    renovation: str = None, year_built: int = None,
    has_elevator: int = 1, parking: int = 0,
    property_type: str = "second_hand",
    tags: str = None, images: str = None,
    agent_id: str = None, task_id: str = None,
) -> str:
    """添加新房源
    
    property_type: new(新房) / second_hand(二手房) / rental(租房)
    """
    db = _get_db()
    unit_price = int(price * 10000 / area) if area > 0 else None
    result = db.add_property(
        title=title, price=price, area=area, community=community,
        district=district, address=address, unit_price=unit_price,
        rooms=rooms, halls=halls, bathrooms=bathrooms, floor=floor,
        orientation=orientation, renovation=renovation, year_built=year_built,
        has_elevator=has_elevator, parking=parking, property_type=property_type,
        tags=tags, images=images, agent_id=agent_id,
    )
    # 房源反匹配：自动扫描 S/A 级客户
    try:
        matched = db.match_customers_for_property(result['id'])
    except Exception:
        matched = []
    response = {"success": True, "property": result}
    if matched:
        response["matched_customers"] = matched
        response["message"] = f"房源已添加，有 {len(matched)} 位 S/A 级客户可能感兴趣"
    return json.dumps(response, ensure_ascii=False)


def update_property(
    property_id: int, title: str = None, price: int = None,
    area: float = None, status: str = None,
    community: str = None, district: str = None, renovation: str = None,
    task_id: str = None,
) -> str:
    """更新房源信息"""
    db = _get_db()
    kwargs = {k: v for k, v in {
        'title': title, 'price': price, 'area': area, 'status': status,
        'community': community, 'district': district, 'renovation': renovation,
    }.items() if v is not None}
    result = db.update_property(property_id, **kwargs)
    if result:
        return json.dumps({"success": True, "property": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "房源不存在"}, ensure_ascii=False)


def search_property(
    min_price: int = None, max_price: int = None,
    min_area: float = None, max_area: float = None,
    rooms: int = None, district: str = None,
    renovation: str = None, property_type: str = None,
    limit: int = 20, task_id: str = None,
) -> str:
    """搜索房源（支持按价格、面积、户型、区域、类型筛选）
    
    property_type: new(新房) / second_hand(二手房) / rental(租房)
    """
    db = _get_db()
    filters = {}
    if min_price: filters['min_price'] = min_price
    if max_price: filters['max_price'] = max_price
    if min_area: filters['min_area'] = min_area
    if max_area: filters['max_area'] = max_area
    if rooms: filters['rooms'] = rooms
    if district: filters['district'] = district
    if renovation: filters['renovation'] = renovation
    if property_type: filters['property_type'] = property_type
    result = db.search_properties(**filters)
    return json.dumps({"success": True, "properties": result, "count": len(result)}, ensure_ascii=False)


def match_property(customer_id: int, top_n: int = 5, task_id: str = None) -> str:
    """根据客户需求智能匹配最合适的房源"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    matches = db.match_property(customer_id, top_n)
    return json.dumps({
        "success": True, "customer": customer.get('name'),
        "customer_tier": customer.get('tier'),
        "total_properties": len(db.search_properties()),
        "matches": [{k: v for k, v in m.items() if k in ('id','title','community','price','area','rooms','halls','district','score','match_reasons')} for m in matches],
    }, ensure_ascii=False)


def property_stats(task_id: str = None) -> str:
    """获取房源统计数据"""
    db = _get_db()
    stats = db.get_stats()
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


TOOLS = [
    {"name": "add_property", "description": "添加新房源", "parameters": {
        "type": "object", "properties": {
            "title": {"type": "string", "description": "房源标题"},
            "price": {"type": "integer", "description": "总价（万元）"},
            "area": {"type": "number", "description": "面积（㎡）"},
            "community": {"type": "string", "description": "小区名"},
            "district": {"type": "string", "description": "区域"},
            "rooms": {"type": "integer", "description": "室数"},
            "halls": {"type": "integer", "description": "厅数"},
            "renovation": {"type": "string", "enum": ["毛坯", "简装", "精装"], "description": "装修状态"},
            "property_type": {"type": "string", "enum": ["new", "second_hand", "rental"], "description": "房源类型：new(新房)/second_hand(二手房)/rental(租房)"},
            "images": {"type": "string", "description": "房源图片，多个用逗号分隔（URL或本地路径）"},
        }, "required": ["title", "price", "area"],
    }, "handler": lambda args, **kw: add_property(**args)},
    {"name": "update_property", "description": "更新房源信息", "parameters": {
        "type": "object", "properties": {
            "property_id": {"type": "integer"}, "title": {"type": "string"},
            "price": {"type": "integer"}, "area": {"type": "number"},
            "status": {"type": "string", "enum": ["available", "sold", "rented"]},
        }, "required": ["property_id"],
    }, "handler": lambda args, **kw: update_property(**args)},
    {"name": "search_property", "description": "搜索房源", "parameters": {
        "type": "object", "properties": {
            "min_price": {"type": "integer"}, "max_price": {"type": "integer"},
            "min_area": {"type": "number"}, "max_area": {"type": "number"},
            "rooms": {"type": "integer"}, "district": {"type": "string"},
            "renovation": {"type": "string"},
        },
    }, "handler": lambda args, **kw: search_property(**args)},
    {"name": "match_property", "description": "根据客户需求智能匹配房源", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer"}, "top_n": {"type": "integer"},
        }, "required": ["customer_id"],
    }, "handler": lambda args, **kw: match_property(**args)},
    {"name": "property_stats", "description": "获取房源统计数据", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: property_stats()},
]

registry.register(
    name="add_property",
    toolset="real_estate",
    schema={"name": "add_property", "description": "添加新房源", "parameters": TOOLS[0]["parameters"]},
    handler=TOOLS[0]["handler"],
)
registry.register(
    name="update_property",
    toolset="real_estate",
    schema={"name": "update_property", "description": "更新房源信息", "parameters": TOOLS[1]["parameters"]},
    handler=TOOLS[1]["handler"],
)
registry.register(
    name="search_property",
    toolset="real_estate",
    schema={"name": "search_property", "description": "搜索房源", "parameters": TOOLS[2]["parameters"]},
    handler=TOOLS[2]["handler"],
)
registry.register(
    name="match_property",
    toolset="real_estate",
    schema={"name": "match_property", "description": "智能匹配房源", "parameters": TOOLS[3]["parameters"]},
    handler=TOOLS[3]["handler"],
)
registry.register(
    name="property_stats",
    toolset="real_estate",
    schema={"name": "property_stats", "description": "获取房源统计数据", "parameters": TOOLS[4]["parameters"]},
    handler=TOOLS[4]["handler"],
)
