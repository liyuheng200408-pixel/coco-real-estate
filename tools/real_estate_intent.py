"""
Coco 房产工具 - 竞品对比与客户意向度
"""
import json
from tools.registry import registry
from agent.real_estate_input import norm_id


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def compare_property(property_id: int, limit: int = 5, task_id: str = None) -> str:
    """同小区/同区域竞品对比：显示指定房源与周边在售房源的价格、面积、单价对比"""
    property_id, problem = norm_id(property_id, '房源编号')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    result = db.compare_properties(property_id, limit)
    if result is None:
        return json.dumps({"success": False, "error": "房源不存在"}, ensure_ascii=False)
    return json.dumps({"success": True, "comparison": result}, ensure_ascii=False)


def intent_score(customer_id: int, task_id: str = None) -> str:
    """客户意向度评分（0-100）：基于等级、带看次数、跟进活跃度、预算明确度"""
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    result = db.customer_intent_score(customer_id)
    if result is None:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    return json.dumps({"success": True, "intent": result}, ensure_ascii=False)


def list_intent_scores(tier: str = None, limit: int = 20, task_id: str = None) -> str:
    """列出客户意向度评分排名"""
    db = _get_db()
    customers = db.list_customers(tier=tier, status='active', limit=limit)
    scored = []
    failed = []
    for c in customers:
        try:
            s = db.customer_intent_score(c['id'])
            if s:
                scored.append(s)
        except Exception as exc:
            # 单个客户算分失败不能悄悄跳过：否则排名少人，经纪人以为这些客户不在库里
            failed.append(f"{c.get('name') or c['id']}（{type(exc).__name__}）")
    # 安全排序：个别客户的 score 可能为空（数据不足），不能让整个排名崩掉
    scored.sort(key=lambda x: (x.get('score') if x.get('score') is not None else 0), reverse=True)
    out = {"success": True, "rankings": scored, "count": len(scored)}
    if failed:
        out["warning_scores"] = f"{len(failed)} 位客户意向评分计算失败，未计入排名：" + "、".join(failed[:5])
    return json.dumps(out, ensure_ascii=False)


registry.register(
    name="compare_property",
    toolset="real_estate",
    schema={"name": "compare_property", "description": "同小区/同区域竞品对比", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "limit": {"type": "integer", "description": "对比房源数量"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: compare_property(**args),
)

registry.register(
    name="intent_score",
    toolset="real_estate",
    schema={"name": "intent_score", "description": "客户意向度评分（0-100）", "parameters": {
        "type": "object",
        "properties": {"customer_id": {"type": "integer", "description": "客户ID"}},
        "required": ["customer_id"],
    }},
    handler=lambda args, **kw: intent_score(**args),
)

registry.register(
    name="list_intent_scores",
    toolset="real_estate",
    schema={"name": "list_intent_scores", "description": "客户意向度评分排名", "parameters": {
        "type": "object",
        "properties": {
            "tier": {"type": "string", "enum": ["S", "A", "B", "C"]},
            "limit": {"type": "integer"},
        },
    }},
    handler=lambda args, **kw: list_intent_scores(**args),
)
