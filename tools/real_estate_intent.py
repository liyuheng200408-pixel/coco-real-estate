"""
Coco 房产工具 - 竞品对比与客户意向度
"""
import json
from tools.registry import registry
from agent.real_estate_input import clamp_limit, norm_id
from agent.real_estate_money import fmt_budget


# 条数口径：对比默认 5/上限 20（一次列太多没意义）；列表默认 20/上限 200（与其它列表同一套）
_COMPARE_LIMIT_DEFAULT = 5
_COMPARE_LIMIT_MAX = 20
_LIST_LIMIT_DEFAULT = 20
_LIST_LIMIT_MAX = 200

# 意向度权重（**唯一实现**：两处计分都调 `_score_intent`，别在别处再写一份）
_TIER_BASE = {'S': 40, 'A': 25, 'B': 15, 'C': 5}
_TIER_BASE_FALLBACK = 5          # 等级没填/认不出：按最低档给基础分，不猜
_VIEWING_EACH = 15
_VIEWING_CAP = 30
_RECENT_FOLLOWUP_BONUS = 15
_BUDGET_BONUS = 10
_DEAL_SCORE = 100


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def _budget_label(budget_min, budget_max):
    """预算展示（走共用 `fmt_budget`：≥1 万按万、低于 1 万按元）；一头都没填给 None。"""
    if budget_min and budget_max:
        return f"{fmt_budget(budget_min)}-{fmt_budget(budget_max)}"
    if budget_min or budget_max:
        return fmt_budget(budget_min or budget_max)
    return None


def _score_intent(comp):
    """把分项算成 0–100 分（**唯一实现**：`intent_score` 与 `list_intent_scores` 都调它）。

    权重：等级基础分 S/A/B/C = 40/25/15/5（等级没填按最低档 5）+ 已完成带看每次 15
    （最多 30）+ 近 7 天有跟进 15 + 预算上下限都填 10；已成交直接 100（不再累加）。

    两个必须守住的口径：
    - **分项要能加回总分**（每项都写清加了几分，经纪人能自己核账）；
    - **缺数据不等于低意向**：没有任何带看/跟进/成交时给 `data_sufficient=False` 与
      `score_note`，说明"这个分数只反映登记等级" —— 新客户不能因为没记录就被当成冷客户。
    """
    tier = (comp.get('tier') or '').upper() or None
    base = _TIER_BASE.get(tier, _TIER_BASE_FALLBACK)
    score = base
    breakdown = [f"等级{tier}基础分 +{base}" if tier in _TIER_BASE
                 else f"等级没填（按最低档） +{base}"]

    viewing_count = comp.get('viewing_count') or 0
    viewing_score = min(viewing_count * _VIEWING_EACH, _VIEWING_CAP)
    if viewing_score:
        score += viewing_score
        breakdown.append(f"带看{viewing_count}次 +{viewing_score}")

    recent_fu = comp.get('recent_followups') or 0
    if recent_fu:
        score += _RECENT_FOLLOWUP_BONUS
        breakdown.append(f"近7天跟进{recent_fu}次 +{_RECENT_FOLLOWUP_BONUS}")

    budget_min, budget_max = comp.get('budget_min'), comp.get('budget_max')
    if budget_min and budget_max:
        score += _BUDGET_BONUS
        breakdown.append(f"预算明确 +{_BUDGET_BONUS}")

    deal_count = comp.get('deal_count') or 0
    if deal_count:
        score = _DEAL_SCORE
        breakdown = ["已成交直接 100 分（不再累加）"]

    score = min(score, _DEAL_SCORE)
    data_sufficient = bool(viewing_count or recent_fu or deal_count)
    note = None
    if not data_sufficient:
        note = (f"这位客户还没有带看或跟进记录，数据不足、分数仅供参考：{score} 分只反映登记等级"
                f"（{tier or '未填'}），不能当成「不感兴趣」")
    last_fu = comp.get('last_followup_at')
    return {
        'customer_id': comp.get('customer_id'), 'customer_name': comp.get('customer_name'),
        'tier': comp.get('tier'), 'status': comp.get('status'),
        'score': score, 'breakdown': breakdown,
        'viewing_count': viewing_count, 'recent_followups': recent_fu,
        'deal_count': deal_count, 'budget': [budget_min, budget_max],
        'budget_label': _budget_label(budget_min, budget_max),
        'data_sufficient': data_sufficient, 'score_note': note,
        'last_followup_at': last_fu.isoformat() if last_fu else None,
    }


def _intent_message(intent):
    """给经纪人看的那句话：总分 + 每一分的来历（数据不足时如实说明）。"""
    message = f"意向度 {intent.get('score')} 分：" + "、".join(intent.get('breakdown') or [])
    if intent.get('score_note'):
        message += f"｜{intent['score_note']}"
    return message


def compare_property(property_id: int, limit: int = 5, task_id: str = None) -> str:
    """同小区/同区域竞品对比：显示指定房源与周边在售房源的价格、面积、单价对比"""
    property_id, problem = norm_id(property_id, '房源编号')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    limit = clamp_limit(limit, _COMPARE_LIMIT_DEFAULT, _COMPARE_LIMIT_MAX)
    db = _get_db()
    result = db.compare_properties(property_id, limit)
    if result is None:
        return json.dumps({"success": False, "error": "房源不存在"}, ensure_ascii=False)
    return json.dumps({"success": True, "comparison": result}, ensure_ascii=False)


def intent_score(customer_id: int, task_id: str = None) -> str:
    """客户意向度评分（0-100，含每一分的来历）"""
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    comps = db.intent_components(customer_id=customer_id)
    if not comps:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    intent = _score_intent(comps[0])
    return json.dumps({"success": True, "intent": intent, "message": _intent_message(intent)},
                      ensure_ascii=False)


def list_intent_scores(tier: str = None, limit: int = _LIST_LIMIT_DEFAULT, task_id: str = None) -> str:
    """列出客户意向度评分排名"""
    limit = clamp_limit(limit, _LIST_LIMIT_DEFAULT, _LIST_LIMIT_MAX)
    db = _get_db()
    customers = db.list_customers(tier=tier, status='active', limit=limit)
    scored = []
    failed = []
    for c in customers:
        try:
            comps = db.intent_components(customer_id=c['id'])
            if comps:
                scored.append(_score_intent(comps[0]))
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
            "limit": {"type": "integer", "description": "对比条数（默认 5，最多 20；传 0/负数/非数字按默认 5）"},
        },
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: compare_property(**args),
)

registry.register(
    name="intent_score",
    toolset="real_estate",
    schema={"name": "intent_score", "description":
            "客户意向度评分（0-100）：按登记等级、已完成带看次数、近 7 天跟进、预算是否明确逐项加分"
            "（等级 S/A/B/C = 40/25/15/5 分，带看每次 +15 最多 +30，近 7 天有跟进 +15，"
            "预算上下限都填 +10，已成交直接 100）。返回总分和每一分的来历；客户还没有跟进或带看"
            "记录时会标注「数据不足、分数仅供参考」，别当成客户不感兴趣。要看多位客户的排序用"
            " list_intent_scores。", "parameters": {
        "type": "object",
        "properties": {"customer_id": {"type": "integer",
                                       "description": "客户编号（数字，如 12；可在客户列表里查）"}},
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
            "limit": {"type": "integer", "description": "返回条数（默认 20，最多 200；传 0/负数/非数字按默认 20）"},
        },
    }},
    handler=lambda args, **kw: list_intent_scores(**args),
)
