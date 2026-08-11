"""
Coco 房产工具 - 成交/交易管理
"""
import json
from datetime import datetime
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


STAGES = ['deposit', 'signing', 'loan', 'transfer', 'finalized']
STAGE_LABELS = {
    'deposit': '意向金/定金', 'signing': '签约', 'loan': '贷款审批',
    'transfer': '过户', 'finalized': '交房完成',
}


def _parse_date(value: str, field_name: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"{field_name} 格式错误: {value}，请用 YYYY-MM-DD")


def start_deal(customer_id: int, property_id: int, price: int = None, deposit_amount: int = None,
               deposit_date: str = None, notes: str = None, task_id: str = None) -> str:
    """创建成交单：录入成交客户、房源、价格、定金，进入交易流程"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    kwargs = {'price': price, 'deposit_amount': deposit_amount, 'notes': notes}
    try:
        kwargs['deposit_date'] = _parse_date(deposit_date, '定金日期')
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    result = db.add_deal(customer_id=customer_id, property_id=property_id, **kwargs)
    return json.dumps({
        "success": True, "deal": result,
        "message": f"已创建成交单：{customer.get('name')} 成交 {result.get('property_title')}，当前阶段：定金；该房源已标记售出/出租，不再对外推荐"
    }, ensure_ascii=False)


def advance_deal(deal_id: int, stage: str, date: str = None, notes: str = None, task_id: str = None) -> str:
    """推进交易阶段：deposit(定金)→signing(签约)→loan(贷款)→transfer(过户)→finalized(交房)"""
    if stage not in STAGES:
        return json.dumps({"success": False, "error": f"阶段必须是 {'/'.join(STAGES)}"}, ensure_ascii=False)
    db = _get_db()
    deal = db.get_deal(deal_id)
    if not deal:
        return json.dumps({"success": False, "error": "成交单不存在"}, ensure_ascii=False)
    kwargs = {'stage': stage}
    if date:
        try:
            kwargs[f'{stage}_date'] = _parse_date(date, f'{STAGE_LABELS[stage]}日期')
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    if notes is not None:
        kwargs['notes'] = notes
    updated = db.update_deal(deal_id, **kwargs)
    return json.dumps({
        "success": True, "deal": updated,
        "message": f"交易已推进至：{STAGE_LABELS[stage]}"
    }, ensure_ascii=False)


def get_deal(deal_id: int, task_id: str = None) -> str:
    """查看成交详情"""
    db = _get_db()
    result = db.get_deal(deal_id)
    if result:
        return json.dumps({"success": True, "deal": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "成交单不存在"}, ensure_ascii=False)


def list_deals(stage: str = None, limit: int = 20, task_id: str = None) -> str:
    """列出成交单，可按阶段筛选"""
    db = _get_db()
    result = db.list_deals(stage=stage, limit=limit)
    for d in result:
        d['stage_label'] = STAGE_LABELS.get(d.get('stage'), d.get('stage'))
    return json.dumps({"success": True, "deals": result, "count": len(result)}, ensure_ascii=False)


def deal_stats(task_id: str = None) -> str:
    """成交统计：各阶段数量、总成交数"""
    db = _get_db()
    stats = db.deal_stats()
    stats['stage_labels'] = STAGE_LABELS
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


# 注册工具
registry.register(
    name="start_deal",
    toolset="real_estate",
    schema={"name": "start_deal", "description": "创建成交单：录入成交客户、房源、价格、定金，进入交易流程", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "property_id": {"type": "integer", "description": "房源ID"},
            "price": {"type": "integer", "description": "成交价（元，如 400万=4000000）"},
            "deposit_amount": {"type": "integer", "description": "定金（元）"},
            "deposit_date": {"type": "string", "description": "定金日期 YYYY-MM-DD"},
            "notes": {"type": "string", "description": "备注"},
        },
        "required": ["customer_id", "property_id"],
    }},
    handler=lambda args, **kw: start_deal(**args),
)

registry.register(
    name="advance_deal",
    toolset="real_estate",
    schema={"name": "advance_deal", "description": "推进交易阶段：deposit(定金)→signing(签约)→loan(贷款)→transfer(过户)→finalized(交房)", "parameters": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "integer", "description": "成交单ID"},
            "stage": {"type": "string", "enum": STAGES, "description": "目标阶段"},
            "date": {"type": "string", "description": "该阶段日期 YYYY-MM-DD"},
            "notes": {"type": "string", "description": "备注"},
        },
        "required": ["deal_id", "stage"],
    }},
    handler=lambda args, **kw: advance_deal(**args),
)

registry.register(
    name="get_deal",
    toolset="real_estate",
    schema={"name": "get_deal", "description": "查看成交详情", "parameters": {
        "type": "object",
        "properties": {"deal_id": {"type": "integer"}},
        "required": ["deal_id"],
    }},
    handler=lambda args, **kw: get_deal(**args),
)

registry.register(
    name="list_deals",
    toolset="real_estate",
    schema={"name": "list_deals", "description": "列出成交单，可按阶段筛选", "parameters": {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": STAGES, "description": "阶段筛选"},
            "limit": {"type": "integer"},
        },
    }},
    handler=lambda args, **kw: list_deals(**args),
)

registry.register(
    name="deal_stats",
    toolset="real_estate",
    schema={"name": "deal_stats", "description": "成交统计：各阶段数量、总成交数", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: deal_stats(),
)
