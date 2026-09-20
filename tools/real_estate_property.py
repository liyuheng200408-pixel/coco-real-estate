"""
Coco 房产工具 - 房源管理
"""
import json
import re

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
    tenant_requirements: str = None,
    owner_name: str = None, owner_phone: str = None, owner_wechat: str = None,
    force: bool = False, task_id: str = None,
) -> str:
    """添加新房源
    
    property_type: new(一手房) / second_hand(二手房) / rental(租房)
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
    # 合并 images 和 image_paths
    img_list = []
    for src in (images, image_paths):
        if src:
            img_list.extend([x.strip() for x in src.split(',') if x.strip()])
    merged_images = ','.join(img_list) if img_list else None
    result = db.add_property(
        title=title, price=price, area=area, community=community,
        district=district, address=address,
        rooms=rooms, halls=halls, bathrooms=bathrooms,
        floor=_norm_floor(floor), orientation=_norm_orientation(orientation),
        renovation=renovation, year_built=year_built,
        has_elevator=has_elevator, parking=parking, property_type=property_type,
        tags=tags, images=merged_images, agent_id=agent_id,
        tenant_requirements=tenant_requirements,
    )
    # 租客要求入库后同步到返回结果
    if tenant_requirements:
        result['tenant_requirements'] = tenant_requirements
    # 业主信息一步关联：找到/新建房东(电话加密)并挂到房源 owner_id
    # 业主信息一步关联：失败要如实告知经纪人（原先静默吞掉，经纪人以为登记好了）
    owner = None
    owner_warning = None
    if owner_name or owner_phone:
        try:
            owner = db.link_owner_to_property(result['id'], name=owner_name, phone=owner_phone, wechat=owner_wechat)
        except Exception as exc:
            owner = None
            owner_warning = f"业主信息登记失败：{type(exc).__name__}: {exc}（房源已录入，可用 update_property 补录业主）"
    # 房源反匹配：自动扫描匹配到的客户（失败同样要如实说，不能悄悄跳过）
    match_warning = None
    try:
        matched = db.match_customers_for_property(result['id'])
    except Exception as exc:
        matched = []
        match_warning = f"自动匹配客户失败：{type(exc).__name__}: {exc}（可稍后重跑匹配）"
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
    if owner:
        response["owner"] = owner
    if owner_warning:
        response["warning_owner"] = owner_warning
    if match_warning:
        response["warning_match"] = match_warning
    if duplicate_warning:
        response["duplicate_warning"] = duplicate_warning
    if matched:
        response["matched_customers"] = matched
        response["message"] = f"房源已添加，有 {len(matched)} 位客户可能感兴趣"
    return json.dumps(response, ensure_ascii=False)


def update_property(
    property_id: int, title: str = None, price: int = None,
    area: float = None, status: str = None,
    community: str = None, district: str = None, renovation: str = None,
    rooms: int = None, halls: int = None, bathrooms: int = None,
    floor: str = None, orientation: str = None, address: str = None,
    year_built: int = None, has_elevator: int = None, parking: int = None,
    tags: str = None,
    owner_name: str = None, owner_phone: str = None, owner_wechat: str = None,
    task_id: str = None,
) -> str:
    """更新房源信息（可同时补充业主联系方式：owner_name/owner_phone/owner_wechat，自动登记房东并关联）

    也支持补录/修改：户型(rooms/halls/bathrooms)、楼层(floor)、朝向(orientation)、
    详细地址(address)、建造年份(year_built)、电梯(has_elevator)、车位(parking)、标签(tags)。
    """
    db = _get_db()
    kwargs = {k: v for k, v in {
        'title': title, 'price': price, 'area': area, 'status': status,
        'community': community, 'district': district, 'renovation': renovation,
        'rooms': rooms, 'halls': halls, 'bathrooms': bathrooms,
        'floor': _norm_floor(floor), 'orientation': _norm_orientation(orientation),
        'address': address, 'year_built': year_built,
        'has_elevator': has_elevator, 'parking': parking, 'tags': tags,
    }.items() if v is not None}
    result = db.update_property(property_id, **kwargs)
    if not result:
        return json.dumps({"success": False, "error": "房源不存在"}, ensure_ascii=False)
    owner = None
    owner_warning = None
    if owner_name or owner_phone:
        try:
            owner = db.link_owner_to_property(property_id, name=owner_name, phone=owner_phone, wechat=owner_wechat)
        except Exception as exc:
            owner = None
            owner_warning = f"业主信息登记失败：{type(exc).__name__}: {exc}（房源已更新，可重试补录业主）"
    response = {"success": True, "property": result}
    if owner:
        response["owner"] = owner
    if owner_warning:
        response["warning_owner"] = owner_warning
    return json.dumps(response, ensure_ascii=False)


def search_property(
    min_price: int = None, max_price: int = None,
    min_area: float = None, max_area: float = None,
    rooms: int = None, district: str = None,
    renovation: str = None, property_type: str = None,
    title: str = None, limit: int = 20, task_id: str = None,
) -> str:
    """搜索房源（支持按标题关键词、价格、面积、户型、区域、类型筛选）
    
    title: 标题关键词（模糊匹配，如"华庭"可匹配滨海华庭）
    property_type: new(一手房) / second_hand(二手房) / rental(租房)
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


_TYPE_LABELS = {"new": "一手房", "second_hand": "二手房", "rental": "租房"}

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_FLOOR_PRESETS = ("负一层", "负二层", "底层", "顶层", "低楼层", "中楼层", "高楼层")


def _cn_to_int(text: str):
    """把「十六」「二十」「三」这类中文数字转成整数（支持 1~99，认不出返回 None）"""
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + ones if (head or tail) else None
    return _CN_DIGITS.get(text)


def _norm_floor(value):
    """楼层归一：16楼/十六楼/16F → 16层；5/18层 → 5层（共18层）；低/中/高楼层、顶层、底层原样保留。

    为什么要归一：经纪人写法五花八门，不统一的话海报上会出现「3楼/三楼/03F」，
    筛选「中高楼层」也会漏。认不出的写法**原样保留**，绝不臆造。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Ｆ", "F").replace("f", "F").replace("樓", "楼")
    if s in _FLOOR_PRESETS:
        return s
    m = re.match(r"^(\d{1,3})\s*[/／]\s*(\d{1,3})\s*(?:楼|层|F)?$", s)       # 5/18层
    if m:
        return f"{int(m.group(1))}层（共{int(m.group(2))}层）"
    m = re.match(r"^(?:共)?(\d{1,3})\s*(?:楼|层|F)$", s)                       # 16楼 / 16层 / 16F
    if m:
        return f"{int(m.group(1))}层"
    m = re.match(r"^(?:共)?(\d{1,3})\s*层?\s*[/／]\s*共?\s*(\d{1,3})\s*层?$", s)  # 16层/共18层
    if m:
        return f"{int(m.group(1))}层（共{int(m.group(2))}层）"
    m = re.match(r"^([一二三四五六七八九十两]{1,3})楼$", s)                        # 十六楼
    if m:
        n = _cn_to_int(m.group(1))
        return f"{n}层" if n else s
    return s


def _norm_orientation(value):
    """朝向归一：朝北/北向/北面/北向一线 → 北；南北通 → 南北通透；认不出的原样保留。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "").replace("　", "")
    s = re.sub(r"^(朝|面向|正向|向|正)", "", s)
    stripped = re.sub(r"(向|面|方向)$", "", s)
    if stripped:          # 剥完不能是空串（"一线看海"这类描述不该被剥没）
        s = stripped
    if s in ("南北通", "南北"):
        return "南北通透"
    if s in ("东西通", "东西"):
        return "东西通透"
    dirs = ("东南北", "西南北", "东南", "西南", "东北", "西北", "南", "北", "东", "西")
    for d in dirs:
        if s == d:
            return d
    return s
_STATUS_LABELS = {"available": "在售", "sold": "已售", "rented": "已租"}


def _fmt_price(prop: dict) -> str:
    """价格展示（系统存元）：二手/一手房 → '28.37万'，出租 → '1000元/月'"""
    price = prop.get("price")
    if price is None:
        return "未录入"
    price = float(price)
    if prop.get("property_type") == "rental":
        return f"{price:.0f}元/月"
    wan = price / 10000
    return f"{wan:.0f}万" if wan == int(wan) else f"{wan:.2f}万"


def _fmt_field(value) -> str:
    return str(value) if value not in (None, "") else "未录入"


def _prop_brief(prop: dict) -> dict:
    """候选列表用的房源简短信息（编号/标题/价格/面积/单价/类型/状态）"""
    return {
        "id": prop.get("id"), "title": prop.get("title"),
        "price": prop.get("price"), "area": prop.get("area"),
        "district": prop.get("district"), "property_type": prop.get("property_type"),
        "status": prop.get("status"), "unit_price": prop.get("unit_price"),
    }


def _detail_message(prop: dict, owner, image_count: int, history: list) -> str:
    """房源详情的人类可读摘要（模型照抄即可，避免它自己拼表时漏字段）"""
    lines = [f"【房源】{prop.get('title')}（编号 {prop.get('id')}）"]
    unit_price = prop.get("unit_price")
    unit_part = f"单价 {unit_price}元/㎡" if unit_price else "单价 面积缺失，无法计算"
    lines.append(f"总价 {_fmt_price(prop)} | 面积 {_fmt_field(prop.get('area'))}㎡ | {unit_part}")
    lines.append(
        f"类型 {_TYPE_LABELS.get(prop.get('property_type'), prop.get('property_type') or '未录入')}"
        f" | 状态 {_STATUS_LABELS.get(prop.get('status'), prop.get('status') or '未录入')}"
    )
    lines.append(
        "户型 " + (f"{prop['rooms']}室{prop.get('halls') or 0}厅{prop.get('bathrooms') or 0}卫"
                   if prop.get("rooms") else "未录入")
        + f" | 楼层 {_fmt_field(prop.get('floor'))} | 朝向 {_fmt_field(prop.get('orientation'))}"
        + f" | 装修 {_fmt_field(prop.get('renovation'))} | 年份 {_fmt_field(prop.get('year_built'))}"
        + f" | 电梯 {'有' if prop.get('has_elevator') else '无'}"
        + f" | 车位 {'有' if prop.get('parking') else '无'}"
    )
    region = " ".join(x for x in [prop.get("district"), prop.get("community"), prop.get("address")] if x)
    if region:
        lines.append(f"区域 {region}")
    if prop.get("tenant_requirements"):
        lines.append(f"租客要求 {prop['tenant_requirements']}")
    if owner:
        line = (f"【业主】{owner.get('name') or '未填姓名'}，电话 {owner.get('phone') or '未录入'}")
        if owner.get("wechat"):
            line += f"，微信 {owner['wechat']}"
        if prop.get("viewing_note"):
            line += f"，看房方式 {prop['viewing_note']}"
        lines.append(line)
    else:
        lines.append("【业主】该房源未录入业主信息（可用 update_property 传 owner_name/owner_phone/owner_wechat 补录）")
    lines.append(f"【图片】{image_count} 张" if image_count else "【图片】未关联图片")
    if history:
        h = history[0]
        lines.append(f"【调价】最近一次 调至 {_fmt_price({'price': h.get('new_price'), 'property_type': prop.get('property_type')})}"
                     f"（原 {_fmt_price({'price': h.get('old_price'), 'property_type': prop.get('property_type')})}）")
    return "\n".join(lines)


def get_property_detail(property_id: int = None, title: str = None, task_id: str = None) -> str:
    """房源详情（一次给全）：房源全部字段 + 单价 + 业主 + 图片 + 调价记录。

    按编号或标题定位**唯一一套**房源；标题查不到 → not_found + 最接近的候选（不返回单套数据）；
    标题命中多套 → ambiguous + 候选列表。目的是让"问某套房详情"有确定答案，既不漏业主段，
    也不会拿别的房源顶替。
    """
    db = _get_db()
    if property_id:
        prop = db.get_property(int(property_id))
        if not prop:
            return json.dumps({"success": False, "not_found": True,
                               "error": f"没有编号为 {property_id} 的房源"}, ensure_ascii=False)
    else:
        title = (title or "").strip()
        if not title:
            return json.dumps({"success": False, "error": "请提供 property_id（房源编号）或 title（房源标题）"},
                              ensure_ascii=False)
        found = db.find_property_by_title(title)
        hits = found["exact"] or found["contains"]
        if not hits:
            candidates = db.similar_properties_by_title(title)
            error = f"库里没有找到标题为「{title}」的房源。"
            if candidates:
                error += "最接近的是下面这几套，请确认是哪一套（把编号告诉我）："
            return json.dumps({
                "success": False, "not_found": True,
                "candidates": [_prop_brief(c) for c in candidates],
                "error": error,
            }, ensure_ascii=False)
        if len(hits) > 1:
            return json.dumps({
                "success": False, "ambiguous": True,
                "candidates": [_prop_brief(h) for h in hits[:5]],
                "error": f"标题「{title}」命中 {len(hits)} 套房源，请告诉我要看哪一套（把编号告诉我）",
            }, ensure_ascii=False)
        prop = hits[0]

    pid = prop["id"]
    rows = db.get_property_owners([pid])
    owner = rows[0].get("owner") if rows else None
    image_count = len([x for x in (prop.get("images") or "").split(",") if x.strip()])
    history = db.get_price_history(pid, limit=3)
    return json.dumps({
        "success": True,
        "property": prop,
        "owner": owner,
        "images": {"count": image_count},
        "price_history": history,
        "message": _detail_message(prop, owner, image_count, history),
    }, ensure_ascii=False)


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
        "total_properties": db.count_available_properties(),
        "matches": [{k: v for k, v in m.items() if k in ('id','title','community','price','area','rooms','halls','district','score','match_reasons')} for m in matches],
    }, ensure_ascii=False)


def batch_match_report(
    customer_type: str = None, tier: str = None, district: str = None,
    top_n: int = 1, task_id: str = None,
) -> str:
    """批量匹配汇报：为全部客户（或按类型/等级/区域筛选）生成逐客户匹配明细与汇总

    每个客户必有一行（无匹配显式标注"无匹配"），汇总统计由代码生成，禁止自行口算。
    customer_type: buy_new(买一手房) / buy_second_hand(买二手房) / rent(租房)
    tier: S/A/B/C
    district: 区域筛选（如"美兰区"或"美兰"）
    top_n: 每个客户展示的最佳房源数（默认 1）
    """
    db = _get_db()
    result = db.match_all_customers(top_n=top_n, customer_type=customer_type,
                                    tier=tier, district=district)
    return json.dumps({
        "success": True,
        "total_properties": db.count_available_properties(),
        "summary": result['summary'],
        "customers": result['customers'],
    }, ensure_ascii=False)


def property_stats(task_id: str = None) -> str:
    """获取房源统计数据"""
    db = _get_db()
    stats = db.get_stats()
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


TOOLS = [
    {"name": "add_property", "description": "添加新房源（支持业主信息：owner_name/owner_phone/owner_wechat 会自动登记房东并关联此房源、电话加密；出租房源可传 tenant_requirements 租客要求，匹配租客时用于筛选）", "parameters": {
        "type": "object", "properties": {
            "title": {"type": "string", "description": "房源标题"},
            "price": {"type": "integer", "description": "价格（元）：二手房/一手房总价如 4000000=400万；出租月租如 1000=1000元/月"},
            "area": {"type": "number", "description": "面积（㎡）"},
            "community": {"type": "string", "description": "小区名"},
            "district": {"type": "string", "description": "区域"},
            "rooms": {"type": "integer", "description": "室数"},
            "halls": {"type": "integer", "description": "厅数"},
            "renovation": {"type": "string", "enum": ["毛坯", "简装", "精装"], "description": "装修状态"},
            "property_type": {"type": "string", "enum": ["new", "second_hand", "rental"], "description": "房源类型：new(一手房)/second_hand(二手房)/rental(租房)"},
            "images": {"type": "string", "description": "房源图片，多个用逗号分隔（URL或本地路径）"},
            "image_paths": {"type": "string", "description": "经纪人消息中附带的图片本地路径，多个用逗号分隔，与 images 合并存入房源"},
            "tenant_requirements": {"type": "string", "description": "出租房源的租客要求（如不吸烟/办居住证/学生优先），多个用逗号或顿号分隔，匹配租客时会用于过滤"},
            "owner_name": {"type": "string", "description": "业主（房东）姓名。填了即自动登记房东并关联此房源"},
            "owner_phone": {"type": "string", "description": "业主（房东）手机号，加密存储"},
            "owner_wechat": {"type": "string", "description": "业主（房东）微信号，加密存储"},
            "address": {"type": "string", "description": "详细地址（楼栋门牌等，如 7号楼2单元301）"},
            "bathrooms": {"type": "integer", "description": "卫数"},
            "floor": {"type": "string", "description": "楼层。经纪人怎么说都行（3楼/十六楼/16F/5/18层/低楼层/中楼层/高楼层/顶层），系统会归一成「16层」「5层（共18层）」这类写法"},
            "orientation": {"type": "string", "description": "朝向。如 南/北/东/西/东南/西南/东北/西北/南北通透（朝南、南向、南北通都会归一）"},
            "year_built": {"type": "integer", "description": "建造年份，如 2015"},
            "has_elevator": {"type": "integer", "description": "有无电梯：1=有，0=无（默认 1）"},
            "parking": {"type": "integer", "description": "有无车位：1=有，0=无（默认 0）"},
            "tags": {"type": "string", "description": "特色标签，多个用逗号分隔，如 学区房,地铁房,精装修"},
            "force": {"type": "boolean", "description": "默认 false。true=跳过房源查重强制新增（仅当老板确认是不同期数/楼栋而要保留同名时用）"},
        }, "required": ["title", "price", "area"],
    }, "handler": lambda args, **kw: add_property(**args)},
    {"name": "update_property", "description": "更新房源信息（可补充业主联系方式：owner_name/owner_phone/owner_wechat，自动登记房东并关联）", "parameters": {
        "type": "object", "properties": {
            "property_id": {"type": "integer"}, "title": {"type": "string"},
            "price": {"type": "integer"}, "area": {"type": "number"},
            "status": {"type": "string", "enum": ["available", "sold", "rented"]},
            "community": {"type": "string", "description": "小区名（录错时可改）"},
            "district": {"type": "string", "description": "区域（录错时可改）"},
            "renovation": {"type": "string", "enum": ["毛坯", "简装", "精装", "豪装"], "description": "装修状态（可改）"},
            "rooms": {"type": "integer", "description": "室数"}, "halls": {"type": "integer", "description": "厅数"},
            "bathrooms": {"type": "integer", "description": "卫数"},
            "floor": {"type": "string", "description": "楼层（补录或修改；3楼/十六楼/16F/中楼层 都会归一成「16层」这类写法）"},
            "orientation": {"type": "string", "description": "朝向（补录或修改；朝北/北向 → 北；南北通 → 南北通透）"},
            "address": {"type": "string", "description": "详细地址"},
            "year_built": {"type": "integer", "description": "建造年份"},
            "has_elevator": {"type": "integer", "description": "有无电梯：1=有/0=无"},
            "parking": {"type": "integer", "description": "有无车位：1=有/0=无"},
            "tags": {"type": "string", "description": "特色标签，多个用逗号分隔"},
            "owner_name": {"type": "string", "description": "业主姓名。填了即自动登记房东并关联此房源"},
            "owner_phone": {"type": "string", "description": "业主手机号，加密存储"},
            "owner_wechat": {"type": "string", "description": "业主微信号，加密存储"},
        }, "required": ["property_id"],
    }, "handler": lambda args, **kw: update_property(**args)},
    {"name": "search_property", "description": "搜索房源（支持按标题关键词/价格/面积/户型/区域/类型筛选）", "parameters": {
        "type": "object", "properties": {
            "title": {"type": "string", "description": "标题关键词（模糊匹配，如华庭可匹配滨海华庭）"},
            "min_price": {"type": "integer", "description": "最低价（元）"}, "max_price": {"type": "integer", "description": "最高价（元）"},
            "min_area": {"type": "number"}, "max_area": {"type": "number"},
            "rooms": {"type": "integer"}, "district": {"type": "string"},
            "renovation": {"type": "string"},
            "property_type": {"type": "string", "enum": ["new", "second_hand", "rental"], "description": "房源类型筛选：new(一手房)/second_hand(二手房)/rental(租房)"},
            "limit": {"type": "integer", "description": "最多返回多少条（默认 20；要全量统计时显式给大值）"},
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
            "customer_type": {"type": "string", "enum": ["buy_new", "buy_second_hand", "rent"], "description": "客户类型筛选：buy_new买一手房/buy_second_hand买二手房/rent租房"},
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
- 房源类型：（一手房/二手房/租房）
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
    handler=lambda args, **kw: get_property_form(**args),
)

registry.register(
    name="add_property",
    toolset="real_estate",
    schema={"name": "add_property", "description": "添加新房源（支持业主信息：owner_name/owner_phone/owner_wechat 会自动登记房东并关联此房源、电话加密；出租房源可传 tenant_requirements 租客要求，匹配租客时用于筛选）", "parameters": TOOLS[0]["parameters"]},
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
registry.register(
    name="get_property_detail",
    toolset="real_estate",
    schema={"name": "get_property_detail", "description": "房源详情（一次给全）：按 房源编号(property_id) 或 标题(title) 查**单套**房源的完整资料——全部字段 + 单价(元/㎡，系统按总价÷面积自动计算) + 业主（姓名/电话/微信/看房方式）+ 图片数量 + 调价记录。经纪人问'某套房源的详细信息/详情/资料/这套房什么情况/XX栋XX房给我看看'时必须用本工具（不要用 search_property 自己拼表，否则容易漏业主段）。标题查不到会返回 not_found 与最接近的候选（绝不返回别的房源充当答案）；命中多套会返回候选列表，需先让经纪人确认编号。", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源编号（与标题二选一，优先）"},
            "title": {"type": "string", "description": "房源标题（如 262栋1009）；精确匹配优先，其次包含匹配"},
        },
    }},
    handler=lambda args, **kw: get_property_detail(**args),
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
    # 2026-09-18 修：原先遍历 1 万套房、对每套各查一次调价历史 + 一次客户反匹配（N+1 很慢且漏房源）。
    # 现在先用一次 SQL 取出"近期降过价的在售房源"，再只对这些房源做客户反匹配。
    alerts = []
    for drop in db.recent_price_drops(days=days):
        customers = db.find_customers_for_price_drop(drop["property_id"], days=days)
        if not customers:
            continue
        alerts.append({
            "property_id": drop["property_id"],
            "title": drop["title"],
            "old_price": drop["old_price"],
            "new_price": drop["new_price"],
            "drop_amount": drop["drop_amount"],
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
