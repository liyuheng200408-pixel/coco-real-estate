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
    image_paths: str = None, agent_id: str = None,
    force: bool = False, task_id: str = None,
) -> str:
    """添加新房源
    
    property_type: new(新房) / second_hand(二手房) / rental(租房)
    images: 图片链接或标识（逗号分隔）
    image_paths: 本地图片文件路径（逗号分隔），优先于 images 合并存储
    force=True 跳过房源查重强制新增（仅当老板确认是不同期数/楼栋而要保留同名时用，默认 False）。
    """
    db = _get_db()
    # 录入前查重（2026-08-29 老板要求：跟客户一致，重复就不录入）：按 小区名称(标题)+房号 与 面积 完全一致判定
    if not force:
        dup = db.find_duplicate_property(title=title, area=area)
        if dup:
            return json.dumps({
                "success": False, "duplicate": True, "existing_property": dup,
                "error": (f"该房源已存在（id={dup['id']} {dup['title']}，{dup.get('price')}元 {dup.get('area')}平）。"
                          f"请先向老板确认：合并/更新请用 update_property(property_id={dup['id']}, ...)；"
                          f"确实要新增请用 add_property(..., force=true)。"),
            }, ensure_ascii=False)
    unit_price = int(price / area) if area > 0 else None  # 元/㎡
    # 合并 images 和 image_paths
    img_list = []
    for src in (images, image_paths):
        if src:
            img_list.extend([x.strip() for x in src.split(',') if x.strip()])
    merged_images = ','.join(img_list) if img_list else None
    result = db.add_property(
        title=title, price=price, area=area, community=community,
        district=district, address=address, unit_price=unit_price,
        rooms=rooms, halls=halls, bathrooms=bathrooms, floor=floor,
        orientation=orientation, renovation=renovation, year_built=year_built,
        has_elevator=has_elevator, parking=parking, property_type=property_type,
        tags=tags, images=merged_images, agent_id=agent_id,
    )
    # 房源反匹配：自动扫描 S/A 级客户
    try:
        matched = db.match_customers_for_property(result['id'])
    except Exception:
        matched = []
    # 同名提示（2026-08-13 加）：防重复录入——同标题在售房源已存在时提醒经纪人确认
    #（真实案例：雅居乐金沙湾/保利中央海岸/恒大美丽沙均录入两条价格、区域冲突的记录）
    duplicate_warning = None
    try:
        # 排除刚插入的这套房源自身 id（避免"每套房都提示同名1条"的误报——2026-08-29 修复）
        same_title = [d for d in db.search_properties(title=title, limit=10)
                      if d.get('title') == title and d.get('id') != result.get('id')]
        if same_title:
            d0 = same_title[0]
            duplicate_warning = (
                f"库内已有同名在售房源 {len(same_title)} 条（如 id={d0['id']} {d0['title']} "
                f"{d0['price']}元 {d0.get('district') or '区域未填'}），"
                f"请确认是否为不同期数/楼栋，避免重复录入"
            )
    except Exception:
        duplicate_warning = None
    response = {"success": True, "property": result}
    if duplicate_warning:
        response["duplicate_warning"] = duplicate_warning
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
    title: str = None, limit: int = 20, task_id: str = None,
) -> str:
    """搜索房源（支持按标题关键词、价格、面积、户型、区域、类型筛选）
    
    title: 标题关键词（模糊匹配，如"华庭"可匹配滨海华庭）
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
    if title: filters['title'] = title
    if limit: filters['limit'] = limit
    result = db.search_properties(**filters)
    return json.dumps({"success": True, "properties": result, "count": len(result)}, ensure_ascii=False)


def match_property(customer_id: int, top_n: int = 5, task_id: str = None) -> str:
    """根据客户需求智能匹配最合适的房源"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    # 已有交易记录的客户不再推送房源（真实案例 2026-08-11：过户完成仍被推荐）
    if db.customer_has_deal(customer_id):
        return json.dumps({
            "success": True, "customer": customer.get('name'),
            "customer_tier": customer.get('tier'),
            "matched": False,
            "reason": "客户已有交易记录（进行中或已完成），不再推送房源；除非经纪人明确说明客户还需购房",
            "matches": [],
        }, ensure_ascii=False)
    matches = db.match_property(customer_id, top_n)
    return json.dumps({
        "success": True, "customer": customer.get('name'),
        "customer_tier": customer.get('tier'),
        "matched": True,
        "total_properties": len(db.search_properties()),
        "matches": [{k: v for k, v in m.items() if k in ('id','title','community','price','area','rooms','halls','district','score','match_reasons')} for m in matches],
    }, ensure_ascii=False)


def batch_match_report(
    customer_type: str = None, tier: str = None, district: str = None,
    top_n: int = 1, task_id: str = None,
) -> str:
    """批量匹配汇报：为全部客户（或按类型/等级/区域筛选）生成逐客户匹配明细与汇总

    每个客户必有一行（无匹配显式标注"无匹配"），汇总统计由代码生成，禁止自行口算。
    customer_type: buy_new(买新房) / buy_second_hand(买二手房) / rent(租房)
    tier: S/A/B/C
    district: 区域筛选（如"美兰区"或"美兰"）
    top_n: 每个客户展示的最佳房源数（默认 1）
    """
    db = _get_db()
    result = db.match_all_customers(top_n=top_n, customer_type=customer_type,
                                    tier=tier, district=district)
    return json.dumps({
        "success": True,
        "total_properties": len(db.search_properties(limit=10000)),
        "summary": result['summary'],
        "customers": result['customers'],
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
            "price": {"type": "integer", "description": "价格（元）：二手房/新房总价如 4000000=400万；出租月租如 1000=1000元/月"},
            "area": {"type": "number", "description": "面积（㎡）"},
            "community": {"type": "string", "description": "小区名"},
            "district": {"type": "string", "description": "区域"},
            "rooms": {"type": "integer", "description": "室数"},
            "halls": {"type": "integer", "description": "厅数"},
            "renovation": {"type": "string", "enum": ["毛坯", "简装", "精装"], "description": "装修状态"},
            "property_type": {"type": "string", "enum": ["new", "second_hand", "rental"], "description": "房源类型：new(新房)/second_hand(二手房)/rental(租房)"},
            "images": {"type": "string", "description": "房源图片，多个用逗号分隔（URL或本地路径）"},
            "image_paths": {"type": "string", "description": "经纪人消息中附带的图片本地路径，多个用逗号分隔，与 images 合并存入房源"},
            "force": {"type": "boolean", "description": "默认 false。true=跳过房源查重强制新增（仅当老板确认是不同期数/楼栋而要保留同名时用）"},
        }, "required": ["title", "price", "area"],
    }, "handler": lambda args, **kw: add_property(**args)},
    {"name": "update_property", "description": "更新房源信息", "parameters": {
        "type": "object", "properties": {
            "property_id": {"type": "integer"}, "title": {"type": "string"},
            "price": {"type": "integer"}, "area": {"type": "number"},
            "status": {"type": "string", "enum": ["available", "sold", "rented"]},
        }, "required": ["property_id"],
    }, "handler": lambda args, **kw: update_property(**args)},
    {"name": "search_property", "description": "搜索房源（支持按标题关键词/价格/面积/户型/区域/类型筛选）", "parameters": {
        "type": "object", "properties": {
            "title": {"type": "string", "description": "标题关键词（模糊匹配，如华庭可匹配滨海华庭）"},
            "min_price": {"type": "integer", "description": "最低价（元）"}, "max_price": {"type": "integer", "description": "最高价（元）"},
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
    {"name": "batch_match_report", "description": "批量匹配汇报：为全部客户（或按类型/等级/区域筛选）生成逐客户匹配明细与汇总，每个客户一行（无匹配显式标注），完全匹配/接近匹配/无匹配由代码判定，汇总数字由代码统计，禁止自行口算", "parameters": {
        "type": "object", "properties": {
            "customer_type": {"type": "string", "enum": ["buy_new", "buy_second_hand", "rent"], "description": "客户类型筛选：buy_new买新房/buy_second_hand买二手房/rent租房"},
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"], "description": "客户等级筛选"},
            "district": {"type": "string", "description": "区域筛选，如 美兰区 或 美兰"},
            "top_n": {"type": "integer", "description": "每个客户展示的最佳房源数，默认1"},
        },
    }, "handler": lambda args, **kw: batch_match_report(**args)},
]

def get_property_form(task_id: str = None) -> str:
    """获取房源录入模板"""
    form = """【房源录入表】

- 房源标题：（必填，如"望京新城精装三居"）
- 售价：（元，必填，如 4000000=400万；出租房填月租，如 1000=1000元/月）
- 面积：（㎡，必填）
- 小区名称：
- 所在区域：
- 详细地址：
- 户型：室 / 厅 / 卫
- 楼层：
- 朝向：（南/北/东南/南北通透等）
- 装修：（毛坯/简装/精装/豪装）
- 建造年份：
- 有无电梯：（有/无）
- 车位：（有/无）
- 房源类型：（新房/二手房/租房）
- 特色标签：（如"学区房""地铁房"，多个用逗号分隔）
- 房源图片：（可直接在消息中发送图片，会自动关联）"""
    return json.dumps({"success": True, "form": form}, ensure_ascii=False)


registry.register(
    name="get_property_form",
    toolset="real_estate",
    schema={"name": "get_property_form", "description": "房源登记/录入时获取标准表单模板，按模板逐项收集房源信息。当经纪人要求登记房源、录入房源、添加房源、新建房源时，必须调用此工具，禁止自行编造录入格式。", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: get_property_form(**kw),
)

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
registry.register(
    name="batch_match_report",
    toolset="real_estate",
    schema={"name": "batch_match_report", "description": "批量匹配汇报：为全部客户（或按类型/等级/区域筛选）生成逐客户匹配明细与汇总，每个客户一行（无匹配显式标注），完全匹配/接近匹配/无匹配由代码判定，汇总数字由代码统计，禁止自行口算", "parameters": TOOLS[5]["parameters"]},
    handler=TOOLS[5]["handler"],
)


def deduplicate_properties(dry_run: bool = True, task_id: str = None) -> str:
    """房源去重：按 标题+面积+价格 找出重复房源，保留最早录入的一条

    dry_run=True（默认）只统计不删除；dry_run=False 执行删除。
    有关联带看/成交/跟进记录的重复房源自动跳过（保守处理）。
    """
    db = _get_db()
    result = db.remove_duplicate_properties(dry_run=dry_run)
    if result.get('dry_run'):
        message = (
            f"发现 {result['duplicate_groups']} 组重复房源，共 {result['duplicate_total']} 条可清理。"
            f"确认清理请调用 deduplicate_properties(dry_run=False)。"
        )
    else:
        message = f"已清理 {len(result['removable'])} 条重复房源（{result['duplicate_groups']} 组）。"
        if result.get('skipped'):
            message += f" 跳过 {len(result['skipped'])} 条有关联记录的房源。"
    return json.dumps({"success": True, "result": result, "message": message}, ensure_ascii=False)


registry.register(
    name="deduplicate_properties",
    toolset="real_estate",
    schema={"name": "deduplicate_properties", "description": "房源去重：按标题+面积+价格找出重复房源，保留最早录入的一条。dry_run=True只统计，dry_run=False执行删除。", "parameters": {
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "True只统计不删除（默认），False执行删除"},
        },
    }},
    handler=lambda args, **kw: deduplicate_properties(**args),
)


def price_history(property_id: int, limit: int = 20, task_id: str = None) -> str:
    """查询房源调价历史"""
    db = _get_db()
    history = db.get_price_history(property_id, limit)
    if not history:
        return json.dumps({"success": True, "message": "该房源暂无调价记录", "history": []}, ensure_ascii=False)
    total_change = 0
    has_old = False
    first_old = None
    for h in history:
        if h["old_price"] is not None:
            if not has_old:
                first_old = h["old_price"]
                has_old = True
            total_change += h["change"]
    message = f"共 {len(history)} 次调价，累计变动 {total_change/10000:+.1f}万"
    return json.dumps({"success": True, "message": message, "history": history}, ensure_ascii=False)


def price_drop_alerts(days: int = 7, task_id: str = None) -> str:
    """降价提醒：扫描近期降价房源，反匹配"预算差一点够得着"的客户，输出联系建议"""
    db = _get_db()
    props = db.search_properties(limit=10000)
    alerts = []
    for p in props:
        customers = db.find_customers_for_price_drop(p["id"], days=days)
        if customers:
            history = db.get_price_history(p["id"], limit=1)
            if not history:
                continue
            drop = history[0]
            alerts.append({
                "property_id": p["id"],
                "title": p["title"],
                "old_price": drop["old_price"],
                "new_price": drop["new_price"],
                "drop_amount": (drop["old_price"] - drop["new_price"]) if drop["old_price"] else None,
                "matched_customers": customers,
            })
    if not alerts:
        return json.dumps({"success": True, "message": f"近{days}天无降价房源或降价后无可捞回客户", "alerts": []}, ensure_ascii=False)
    total_hits = sum(len(a["matched_customers"]) for a in alerts)
    lines = [f"📢 近{days}天降价提醒：{len(alerts)} 套房降价，可捞回 {total_hits} 位客户"]
    for a in alerts:
        drop_w = (a["drop_amount"] or 0) / 10000
        lines.append(f"\n· {a['title']}（ID:{a['property_id']}）降价 {drop_w:.0f}万 → 现价 {a['new_price']/10000:.0f}万")
        for c in a["matched_customers"][:5]:
            afford = "现在够得着" if c["now_affordable"] else "还差一点"
            lines.append(f"   → {c['name']}（{c['tier']}级，预算上限{c['budget_max']/10000:.0f}万，上次差{c['gap']/10000:.0f}万，{afford}）建议联系")
    return json.dumps({
        "success": True,
        "summary": f"{len(alerts)}套降价、{total_hits}位可捞回客户",
        "alerts": alerts,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


registry.register(
    name="price_history",
    toolset="real_estate",
    schema={"name": "price_history", "description": "查询房源调价历史（每次价格变动的记录）", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "limit": {"type": "integer", "description": "返回条数（默认20）"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: price_history(**args),
)

registry.register(
    name="price_drop_alerts",
    toolset="real_estate",
    schema={"name": "price_drop_alerts", "description": "降价提醒：扫描近期降价房源，找出预算刚够得着的客户并生成联系建议", "parameters": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "扫描近几天的调价（默认7天）"},
        },
    }},
    handler=lambda args, **kw: price_drop_alerts(**args),
)


def find_alternatives(property_id: int, limit: int = 5, task_id: str = None) -> str:
    """一键平替：客户看中的房被抢/下架时，按贴近度找替代房源"""
    db = _get_db()
    alts = db.find_alternatives(property_id, limit)
    if not alts:
        return json.dumps({"success": True, "message": "暂无贴近度足够的替代房源，建议扩大区域或预算范围", "alternatives": []}, ensure_ascii=False)
    lines = [f"🔁 找到 {len(alts)} 套平替方案（按贴近度排序）"]
    for a in alts:
        diff = a.get("diff_price") or 0
        diff_str = f"{'贵' if diff > 0 else '便宜'}{abs(diff)/10000:.0f}万" if diff else "同价"
        lines.append(f"\n· {a['title']}（ID:{a['id']}）{a['price']/10000:.0f}万（{diff_str}）{a['area']}㎡ {a['rooms'] or '?'}室")
        lines.append(f"  贴近度: {a['match_level']}分")
    return json.dumps({
        "success": True,
        "alternatives": alts,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


registry.register(
    name="find_alternatives",
    toolset="real_estate",
    schema={"name": "find_alternatives", "description": "一键平替：客户看中的房源被抢/下架时，按同小区/同户型/同价位找替代清单", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "原房源ID"},
            "limit": {"type": "integer", "description": "最多返回几套（默认5）"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: find_alternatives(**args),
)
