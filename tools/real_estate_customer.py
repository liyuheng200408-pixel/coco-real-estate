"""
Coco 房产工具 - 客户管理
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def add_customer(
    name: str,
    phone: str = None,
    wechat: str = None,
    tier: str = 'C',
    budget_min: int = None,
    budget_max: int = None,
    area_pref: str = None,
    layout_pref: str = None,
    location: str = None,
    renovation: str = None,
    notes: str = None,
    source: str = None,
    customer_type: str = "buy",
    birthday: str = None,
    force: bool = False,
    task_id: str = None,
) -> str:
    """添加新客户到系统
    
    customer_type: buy_new(买新房) / buy_second_hand(买二手房) / rent(租房)
    force=True 跳过客户查重强制新增（仅当老板确认要新增重复客户时才用，默认 False）。
    """
    db = _get_db()
    if not force:
        dup, warn = db.find_duplicate_customer(
            phone=phone, wechat=wechat, name=name, customer_type=customer_type)
        if warn:
            # 密钥不一致防御：不强行判重，提示先检查 COCO_ENC_KEY
            return json.dumps({
                "success": False, "duplicate": False, "warning": warn,
                "error": "检测到客户字段可能因密钥不一致无法安全判重，请先检查 COCO_ENC_KEY 再操作。",
            }, ensure_ascii=False)
        if dup:
            # 判断本次录入与已存在客户的关键字段是否完全一致（2026-08-30 加）
            identical = True
            for k, new_v in [('name', name), ('phone', phone), ('budget_min', budget_min),
                             ('budget_max', budget_max), ('area_pref', area_pref),
                             ('layout_pref', layout_pref), ('location', location),
                             ('customer_type', customer_type), ('source', source)]:
                if new_v is None:
                    continue  # 本次未提供的字段不参与一致判断
                if str(dup.get(k)) != str(new_v):
                    identical = False
                    break
            msg = ("信息完全一致，无需重复登记。" if identical else
                   f"信息有差异，请先向老板确认：合并更新请用 update_customer(customer_id={dup['id']}, ...)；"
                   f"确实要新增请用 add_customer(..., force=True)。")
            return json.dumps({
                "success": False, "duplicate": True, "identical": identical, "existing_customer": dup,
                "error": (f"该客户已存在（id={dup['id']} {dup['name']}，手机 {dup.get('phone') or '未填'}）。" + msg),
            }, ensure_ascii=False)
    result = db.add_customer(
        name=name, phone=phone, wechat=wechat, tier=tier,
        budget_min=budget_min, budget_max=budget_max,
        area_pref=area_pref, layout_pref=layout_pref,
        location=location, renovation=renovation,
        notes=notes, source=source, customer_type=customer_type,
        birthday=birthday,
    )
    # 录入后自动匹配（2026-08-29 加）：新客户 → 自动找匹配房源，随返回主动报告
    matched_properties = []
    try:
        matched_properties = db.match_property(result['id'], top_n=5)
    except Exception:
        matched_properties = []
    response = {"success": True, "customer": result}
    if matched_properties:
        response["matched_properties"] = matched_properties
        response["message"] = f"客户已添加，有 {len(matched_properties)} 套房源可能符合需求"
    return json.dumps(response, ensure_ascii=False)


def update_customer(
    customer_id: int,
    name: str = None,
    phone: str = None,
    wechat: str = None,
    tier: str = None,
    budget_min: int = None,
    budget_max: int = None,
    area_pref: str = None,
    layout_pref: str = None,
    location: str = None,
    renovation: str = None,
    notes: str = None,
    status: str = None,
    source: str = None,
    birthday: str = None,
    task_id: str = None,
) -> str:
    """更新客户信息（自动记录变更历史；预算大幅下调时给出需求漂移预警）"""
    db = _get_db()
    old = db.get_customer(customer_id)
    if old is None:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    kwargs = {k: v for k, v in {
        'name': name, 'phone': phone, 'wechat': wechat, 'tier': tier,
        'budget_min': budget_min, 'budget_max': budget_max,
        'area_pref': area_pref, 'layout_pref': layout_pref,
        'location': location, 'renovation': renovation,
        'notes': notes, 'status': status, 'source': source, 'birthday': birthday,
    }.items() if v is not None}
    result = db.update_customer(customer_id, **kwargs)

    # 需求漂移预警：预算上限下调 >=30% → 客户可能转向更便宜的房子
    alerts = []
    if 'budget_max' in kwargs and old.get('budget_max'):
        old_max = float(old['budget_max'])
        new_max = float(kwargs['budget_max'])
        if old_max > 0 and new_max < old_max * 0.7:
            drop_pct = round((old_max - new_max) / old_max * 100)
            alerts.append({
                'type': 'budget_drift',
                'level': 'warning',
                'message': f"预算上限从 {old_max:.0f}万 下调到 {new_max:.0f}万（降 {drop_pct}%），"
                           f"客户很可能在别处看到了更便宜的房子，建议主动联系确认需求变化。",
            })
    if 'location' in kwargs and old.get('location') and kwargs['location'] != old.get('location'):
        alerts.append({
            'type': 'location_change',
            'level': 'info',
            'message': f"意向区域从「{old['location']}」变更为「{kwargs['location']}」，留意需求方向变化。",
        })

    response = {"success": True, "customer": result}
    if alerts:
        response['alerts'] = alerts
    return json.dumps(response, ensure_ascii=False)


def customer_change_history(customer_id: int, limit: int = 20, task_id: str = None) -> str:
    """查询客户需求变更历史（预算/区域/户型/等级等字段的变更记录）"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    changes = db.get_customer_changes(customer_id, limit=limit)
    return json.dumps({
        "success": True, "customer_id": customer_id,
        "customer_name": customer.get('name'),
        "changes": changes, "count": len(changes),
    }, ensure_ascii=False)


def get_customer(customer_id: int, task_id: str = None) -> str:
    """获取客户详情"""
    db = _get_db()
    result = db.get_customer(customer_id)
    if result:
        return json.dumps({"success": True, "customer": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)


def list_customers(tier: str = None, status: str = None, customer_type: str = None, limit: int = 20, task_id: str = None) -> str:
    """列出客户列表
    
    customer_type: buy_new(买新房) / buy_second_hand(买二手房) / rent(租房)
    """
    db = _get_db()
    result = db.list_customers(tier=tier, status=status, customer_type=customer_type, limit=limit)
    return json.dumps({"success": True, "customers": result, "count": len(result)}, ensure_ascii=False)


def update_tier(customer_id: int, tier: str, task_id: str = None) -> str:
    """调整客户等级（S高意向/A有需求/B培养/C初步接触）"""
    if tier not in ['S', 'A', 'B', 'C']:
        return json.dumps({"success": False, "error": "等级必须是 S/A/B/C"}, ensure_ascii=False)
    db = _get_db()
    result = db.update_customer(customer_id, tier=tier)
    if result:
        return json.dumps({"success": True, "customer": result, "message": f"已将客户等级调整为 {tier}"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)


def customer_stats(task_id: str = None) -> str:
    """获取客户统计数据"""
    db = _get_db()
    stats = db.get_stats()
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


# 注册工具
TOOLS = [
    {"name": "add_customer", "description": "添加新客户到系统", "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "客户姓名"},
            "phone": {"type": "string", "description": "手机号"},
            "wechat": {"type": "string", "description": "微信号"},
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"], "description": "客户等级（仅经纪人明确告知等级时才传；未告知则不传，默认 C 级）"},
            "budget_min": {"type": "integer", "description": "预算下限（元，如 300万=3000000）"},
            "budget_max": {"type": "integer", "description": "预算上限（元）"},
            "area_pref": {"type": "string", "description": "面积偏好，如 80-120"},
            "layout_pref": {"type": "string", "description": "户型偏好，如 3室2厅"},
            "location": {"type": "string", "description": "意向区域"},
            "renovation": {"type": "string", "description": "装修偏好"},
            "notes": {"type": "string", "description": "备注"},
            "source": {"type": "string", "description": "客户来源"},
            "customer_type": {"type": "string", "enum": ["buy_new", "buy_second_hand", "rent"], "description": "客户类型：buy_new(买新房)/buy_second_hand(买二手房)/rent(租房)"},
            "birthday": {"type": "string", "description": "客户生日 YYYY-MM-DD"},
            "force": {"type": "boolean", "description": "默认 false。true=跳过客户查重强制新增（仅当老板确认要新增重复客户时才用）"},
        },
        "required": ["name"],
    }, "handler": lambda args, **kw: add_customer(**args)},
    {"name": "update_customer", "description": "更新客户信息。注意：仅当经纪人明确要求调整客户等级时才传 tier 参数，否则不要传、不要自行修改客户等级", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "name": {"type": "string"}, "phone": {"type": "string"},
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"], "description": "客户等级（仅经纪人明确要求调整等级时传，禁止自行修改）"},
            "budget_min": {"type": "integer"}, "budget_max": {"type": "integer"},
            "area_pref": {"type": "string"}, "layout_pref": {"type": "string"},
            "location": {"type": "string"}, "renovation": {"type": "string"},
            "notes": {"type": "string"}, "status": {"type": "string", "enum": ["active", "paused", "closed"]},
            "source": {"type": "string", "description": "客户来源（如 抖音/贝壳/安居客/转介绍/门店/58/其他）"},
        },
        "required": ["customer_id"],
    }, "handler": lambda args, **kw: update_customer(**args)},
    {"name": "get_customer", "description": "获取客户详情", "parameters": {
        "type": "object", "properties": {"customer_id": {"type": "integer"}}, "required": ["customer_id"],
    }, "handler": lambda args, **kw: get_customer(**args)},
    {"name": "list_customers", "description": "列出客户列表", "parameters": {
        "type": "object", "properties": {
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"]},
            "status": {"type": "string", "enum": ["active", "paused", "closed"]},
            "limit": {"type": "integer"},
        },
    }, "handler": lambda args, **kw: list_customers(**args)},
    {"name": "update_tier", "description": "调整客户等级", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer"},
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"]},
        },
        "required": ["customer_id", "tier"],
    }, "handler": lambda args, **kw: update_tier(**args)},
    {"name": "customer_stats", "description": "获取客户统计数据", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: customer_stats()},
]

registry.register(
    name="add_customer",
    toolset="real_estate",
    schema={"name": "add_customer", "description": "添加新客户到系统", "parameters": TOOLS[0]["parameters"]},
    handler=TOOLS[0]["handler"],
)
registry.register(
    name="update_customer",
    toolset="real_estate",
    schema={"name": "update_customer", "description": "更新客户信息（自动记录变更历史；预算大幅下调≥30%时返回需求漂移预警）", "parameters": TOOLS[1]["parameters"]},
    handler=TOOLS[1]["handler"],
)
registry.register(
    name="customer_change_history",
    toolset="real_estate",
    schema={"name": "customer_change_history", "description": "查询客户需求变更历史（预算/区域/户型/等级等字段的变更记录）", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "limit": {"type": "integer", "description": "返回条数，默认20"},
        },
        "required": ["customer_id"],
    }},
    handler=lambda args, **kw: customer_change_history(**args),
)
registry.register(
    name="get_customer",
    toolset="real_estate",
    schema={"name": "get_customer", "description": "获取客户详情", "parameters": TOOLS[2]["parameters"]},
    handler=TOOLS[2]["handler"],
)
registry.register(
    name="list_customers",
    toolset="real_estate",
    schema={"name": "list_customers", "description": "列出客户列表", "parameters": TOOLS[3]["parameters"]},
    handler=TOOLS[3]["handler"],
)
registry.register(
    name="update_tier",
    toolset="real_estate",
    schema={"name": "update_tier", "description": "调整客户等级", "parameters": TOOLS[4]["parameters"]},
    handler=TOOLS[4]["handler"],
)
registry.register(
    name="customer_stats",
    toolset="real_estate",
    schema={"name": "customer_stats", "description": "获取客户统计数据", "parameters": TOOLS[5]["parameters"]},
    handler=TOOLS[5]["handler"],
)


def add_customer_tag(
    customer_id: int,
    tag: str,
    task_id: str = None,
) -> str:
    """添加客户标签"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    
    tags = customer.get('tags', '')
    if tags:
        tag_list = tags.split(',') if tags else []
    else:
        tag_list = []
    
    if tag not in tag_list:
        tag_list.append(tag)
    
    db.update_customer(customer_id, tags=','.join(tag_list))
    return json.dumps({"success": True, "message": f"已添加标签: {tag}", "tags": tag_list}, ensure_ascii=False)


def remove_customer_tag(
    customer_id: int,
    tag: str,
    task_id: str = None,
) -> str:
    """移除客户标签"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    
    tags = customer.get('tags', '')
    tag_list = tags.split(',') if tags else []
    
    if tag in tag_list:
        tag_list.remove(tag)
        db.update_customer(customer_id, tags=','.join(tag_list))
        return json.dumps({"success": True, "message": f"已移除标签: {tag}", "tags": tag_list}, ensure_ascii=False)
    else:
        return json.dumps({"success": False, "error": f"标签不存在: {tag}"}, ensure_ascii=False)


def list_customer_tags(
    customer_id: int,
    task_id: str = None,
) -> str:
    """查看客户标签"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    
    tags = customer.get('tags', '')
    tag_list = tags.split(',') if tags else []
    return json.dumps({"success": True, "customer_id": customer_id, "tags": tag_list}, ensure_ascii=False)


# 注册新工具
registry.register(
    name="add_customer_tag",
    toolset="real_estate",
    schema={"name": "add_customer_tag", "description": "添加客户标签", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "tag": {"type": "string", "description": "标签名称"},
        },
        "required": ["customer_id", "tag"],
    }},
    handler=lambda args, **kw: add_customer_tag(**args),
)

registry.register(
    name="remove_customer_tag",
    toolset="real_estate",
    schema={"name": "remove_customer_tag", "description": "移除客户标签", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "tag": {"type": "string", "description": "标签名称"},
        },
        "required": ["customer_id", "tag"],
    }},
    handler=lambda args, **kw: remove_customer_tag(**args),
)

registry.register(
    name="list_customer_tags",
    toolset="real_estate",
    schema={"name": "list_customer_tags", "description": "查看客户标签", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
        },
        "required": ["customer_id"],
    }},
    handler=lambda args, **kw: list_customer_tags(**args),
)


def get_customer_form(task_id: str = None) -> str:
    """获取客户录入模板"""
    form = """【客户录入表】

- 客户姓名：（必填）
- 客户电话：
- 客户微信：
- 客户类型：(买新房) / (买二手房) / (租房)
- 预算范围：（元，如 3000000-5000000；经纪人若说"300-500万"，换算成元后填写）
- 面积偏好：（如 80-120㎡）
- 户型需求：（如 3室2厅）
- 意向区域：
- 装修偏好：（毛坯/简装/精装）
- 客户来源：（安居客/贝壳/抖音/转介绍/门店/58/其他）
- 客户等级（S/A/B）：
- 下次回访日期（YYYY-MM-DD）：
- 客户情况描述：
- 备注："""
    return json.dumps({"success": True, "form": form}, ensure_ascii=False)


registry.register(
    name="get_customer_form",
    toolset="real_estate",
    schema={"name": "get_customer_form", "description": "客户登记/录入时获取标准表单模板，按模板逐项收集客户信息。当经纪人要求登记客户、录入客户、新建客户资料时，必须调用此工具，禁止自行编造录入格式。", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: get_customer_form(**args),
)


def update_customer_stage(customer_id: int, stage: str, task_id: str = None) -> str:
    """更新客户生命周期阶段，自动写变更历史"""
    db = _get_db()
    STAGE_NAMES = {
        'lead': '潜在', 'interested': '意向', 'strong': '强意向',
        'viewed': '已看房', 'negotiating': '谈判', 'dealing': '成交中',
        'maintain': '售后维护', 'lost': '流失',
    }
    if stage not in STAGE_NAMES:
        return json.dumps({"success": False,
                           "error": f"非法阶段: {stage}，可选: {list(STAGE_NAMES.keys())}"},
                          ensure_ascii=False)
    try:
        updated = db.update_stage(customer_id, stage)
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    if not updated:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "message": f"{updated['name']} 生命周期阶段已更新为: {STAGE_NAMES[stage]}",
        "customer": updated,
    }, ensure_ascii=False)


registry.register(
    name="update_customer_stage",
    toolset="real_estate",
    schema={"name": "update_customer_stage", "description": "更新客户生命周期阶段（潜在/意向/强意向/已看房/谈判/成交中/售后维护/流失），自动记录变更历史", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "stage": {"type": "string", "enum": ["lead", "interested", "strong", "viewed", "negotiating", "dealing", "maintain", "lost"], "description": "目标阶段"},
        },
        "required": ["customer_id", "stage"],
    }},
    handler=lambda args, **kw: update_customer_stage(**args),
)


def add_referral(referrer_customer_id: int, referred_name: str,
                 referred_phone: str = None, reward_note: str = None,
                 task_id: str = None) -> str:
    """登记转介绍：老客户介绍新客，自动建新客户档案并标记来源为转介绍"""
    db = _get_db()
    referred_name = (referred_name or '').strip()
    if not referred_name:
        return json.dumps({"success": False, "error": "被介绍人姓名不能为空"}, ensure_ascii=False)
    referrer = db.get_customer(referrer_customer_id)
    if not referrer:
        return json.dumps({"success": False, "error": "介绍人客户不存在"}, ensure_ascii=False)
    r = db.add_referral(referrer_customer_id=referrer_customer_id,
                        referred_name=referred_name, referred_phone=referred_phone,
                        reward_note=reward_note)
    return json.dumps({
        "success": True,
        "message": (f"转介绍已登记：{referrer['name']} 介绍了 {referred_name}，"
                    f"新客户档案已建（来源: 转介绍）。成交后别忘了答谢 {referrer['name']}"),
        "referral": r,
    }, ensure_ascii=False)


def referral_stats(task_id: str = None) -> str:
    """转介绍贡献榜：谁介绍了几个客户、几个已成交"""
    db = _get_db()
    board = db.referral_stats()
    if not board:
        return json.dumps({"success": True, "message": "暂无转介绍记录", "leaderboard": []}, ensure_ascii=False)
    lines = ["🏆 转介绍贡献榜"]
    for i, row in enumerate(board, 1):
        lines.append(f"{i}. {row['referrer_name']}（{row['tier']}级）: "
                     f"介绍 {row['referrals']} 人，其中 {row['deals_from_referrals']} 人成交")
    return json.dumps({"success": True, "leaderboard": board, "message": "\n".join(lines)}, ensure_ascii=False)


registry.register(
    name="add_referral",
    toolset="real_estate",
    schema={"name": "add_referral", "description": "登记转介绍：老客户介绍新客，自动建新客户档案（来源:转介绍），成交后可答谢介绍人", "parameters": {
        "type": "object",
        "properties": {
            "referrer_customer_id": {"type": "integer", "description": "介绍人（老客户）ID"},
            "referred_name": {"type": "string", "description": "被介绍人姓名"},
            "referred_phone": {"type": "string", "description": "被介绍人手机号（加密存储）"},
            "reward_note": {"type": "string", "description": "酬谢备注"},
        },
        "required": ["referrer_customer_id", "referred_name"],
    }},
    handler=lambda args, **kw: add_referral(**args),
)

registry.register(
    name="referral_stats",
    toolset="real_estate",
    schema={"name": "referral_stats", "description": "转介绍贡献榜：按介绍人数排序，含成交数", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: referral_stats(**args),
)
