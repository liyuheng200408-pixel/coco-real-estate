"""
Coco 房产工具 - 数据分析
业绩看板、转化漏斗、市场周报
"""
import json
from datetime import datetime, timedelta
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def performance_dashboard(
    period: str = "month",
    task_id: str = None,
) -> str:
    """
    业绩看板
    
    参数:
        period: 统计周期 (week/month/quarter/year)
    """
    db = _get_db()
    stats = db.get_stats()
    
    # 获取各等级客户数
    tier_counts = stats.get('tier_counts', {})
    
    # 获取逾期跟进
    overdue = db.get_overdue()
    
    result = {
        "统计周期": period,
        "客户总数": stats.get('total_customers', 0),
        "各等级客户": {
            "S级（高意向）": tier_counts.get('S', 0),
            "A级（有需求）": tier_counts.get('A', 0),
            "B级（培养中）": tier_counts.get('B', 0),
            "C级（初步接触）": tier_counts.get('C', 0),
        },
        "在售房源": stats.get('available_properties', 0),
        "逾期跟进": len(overdue),
        "逾期客户": [f"客户ID:{f['customer_id']}" for f in overdue[:5]],
    }
    
    return json.dumps({"success": True, "dashboard": result}, ensure_ascii=False)


def conversion_funnel(
    period: str = "month",
    task_id: str = None,
) -> str:
    """
    转化漏斗分析
    """
    db = _get_db()
    stats = db.get_stats()
    tier_counts = stats.get('tier_counts', {})
    
    # 模拟转化漏斗数据（实际应从数据库统计）
    total_leads = stats.get('total_customers', 0)
    viewings = int(total_leads * 0.3)  # 假设30%带看
    intentions = int(total_leads * 0.1)  # 假设10%有意向
    deals = int(total_leads * 0.03)  # 假设3%成交
    
    result = {
        "统计周期": period,
        "转化漏斗": {
            "总线索": total_leads,
            "带看数": viewings,
            "带看率": f"{viewings/total_leads*100:.1f}%" if total_leads > 0 else "0%",
            "意向数": intentions,
            "意向率": f"{intentions/total_leads*100:.1f}%" if total_leads > 0 else "0%",
            "成交数": deals,
            "成交率": f"{deals/total_leads*100:.1f}%" if total_leads > 0 else "0%",
        },
        "客户分布": {
            "S级": tier_counts.get('S', 0),
            "A级": tier_counts.get('A', 0),
            "B级": tier_counts.get('B', 0),
            "C级": tier_counts.get('C', 0),
        },
    }
    
    return json.dumps({"success": True, "funnel": result}, ensure_ascii=False)


def weekly_market_report(
    district: str = None,
    task_id: str = None,
) -> str:
    """
    市场周报
    """
    db = _get_db()
    stats = db.get_stats()

    # 本周新增房源真实统计（2026-08-28 修硬编码）
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)
    try:
        with db.get_session() as s:
            from agent.real_estate_db import Property
            new_listings = s.query(Property).filter(
                Property.created_at >= week_ago).count()
    except Exception:
        new_listings = 0

    result = {
        "报告周期": "本周",
        "区域": district or "全部",
        "新增房源": f"{new_listings}套",
        "在售房源": stats.get('available_properties', 0),
        "客户总数": stats.get('total_customers', 0),
        "逾期跟进": stats.get('overdue_followups', 0),
        "本周重点": [
            "关注S级客户跟进情况",
            "新房源及时录入系统",
            "逾期客户优先处理",
        ],
    }
    
    return json.dumps({"success": True, "report": result}, ensure_ascii=False)


# 注册工具
registry.register(
    name="performance_dashboard",
    toolset="real_estate",
    schema={"name": "performance_dashboard", "description": "业绩看板（客户统计、房源统计）", "parameters": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["week", "month", "quarter", "year"], "description": "统计周期"},
        },
    }},
    handler=lambda args, **kw: performance_dashboard(**args),
)

registry.register(
    name="conversion_funnel",
    toolset="real_estate",
    schema={"name": "conversion_funnel", "description": "转化漏斗分析", "parameters": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["week", "month", "quarter", "year"], "description": "统计周期"},
        },
    }},
    handler=lambda args, **kw: conversion_funnel(**args),
)

registry.register(
    name="weekly_market_report",
    toolset="real_estate",
    schema={"name": "weekly_market_report", "description": "市场周报", "parameters": {
        "type": "object",
        "properties": {
            "district": {"type": "string", "description": "区域"},
        },
    }},
    handler=lambda args, **kw: weekly_market_report(**args),
)


def channel_stats(task_id: str = None) -> str:
    """渠道线索统计：按客户来源分组统计客户数、S/A/B/C分级、成交数、成交率

    来源为固定选项：安居客/贝壳/抖音/转介绍/门店/58/其他（未填写归入"未填写"）。
    """
    db = _get_db()
    channels = db.get_channel_stats()
    return json.dumps({
        "success": True,
        "channels": channels,
        "total_channels": len(channels),
        "message": "各渠道线索量与成交率一览，可据此判断广告投放性价比",
    }, ensure_ascii=False)


registry.register(
    name="channel_stats",
    toolset="real_estate",
    schema={"name": "channel_stats", "description": "渠道线索统计：按客户来源分组统计客户数、分级、成交数、成交率，判断哪个渠道来客多、成交率高", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: channel_stats(**args),
)


def market_brief(city: str = None, district: str = None, task_id: str = None) -> str:
    """市场行情简报：自家真实盘况 + 联网行情（标注来源）+ 行动建议"""
    db = _get_db()
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)

    # ① 自家盘况（真实统计）
    try:
        with db.get_session() as s:
            from agent.real_estate_db import Property, Viewing, Deal
            new_props = s.query(Property).filter(Property.created_at >= week_ago).count()
            avail = s.query(Property).filter(Property.status == 'available').count()
            viewings_week = s.query(Viewing).filter(Viewing.viewing_time >= week_ago).count()
            deals_week = s.query(Deal).filter(Deal.created_at >= week_ago).count()
    except Exception:
        new_props = avail = viewings_week = deals_week = 0

    conversion = f"{deals_week / viewings_week * 100:.0f}%" if viewings_week else "暂无数据"

    own_section = [
        "一、自家盘况（系统数据）",
        f"· 本周新增房源: {new_props} 套",
        f"· 当前在售: {avail} 套",
        f"· 本周带看: {viewings_week} 次",
        f"· 本周成交: {deals_week} 单（带看转化率 {conversion}）",
    ]

    # ② 联网行情（标注来源；失败不阻塞）
    news_section = ["\n二、市场动态（来源: 网络检索，仅供参考）"]
    news_items = []
    if city:
        try:
            from hermes_tools import web_search
            query = f"{city} 楼市 最新政策 房价" + (f" {district}" if district else "")
            res = web_search(query, limit=5)
            items = (res.get("data") or {}).get("web") or []
            for it in items[:3]:
                title = (it.get("title") or "").strip()
                if title:
                    news_items.append(f"· {title}")
                    news_items.append(f"  {it.get('url', '')}")
        except Exception as e:
            news_items.append(f"· 联网检索暂不可用（{str(e)[:50]}），建议稍后重试")
    else:
        news_items.append("· 未指定城市，跳过联网检索（传 city 参数可启用）")
    news_section.extend(news_items or ["· 无结果"])

    # ③ 行动建议（基于自家数据生成）
    advice = ["\n三、本周行动建议"]
    if deals_week == 0 and viewings_week > 0:
        advice.append("· 有带看无成交：回访本周带看客户，用 intent_score 找接近成交的推进")
    if avail < 10:
        advice.append("· 在售房源偏少：联系房东补盘，可用 exclusive_expiring 找委托到期房源谈续期")
    high = db.churn_risk_customers(min_risk=60)
    if high:
        advice.append(f"· {len(high)} 位客户流失风险高危，优先用 churn_warning 名单挽回")
    if len(advice) == 1:
        advice.append("· 节奏健康，按日常跟进计划执行即可")

    report = "\n".join(own_section + news_section + advice)
    return json.dumps({
        "success": True,
        "city": city, "district": district,
        "stats": {"new_listings": new_props, "available": avail,
                  "viewings": viewings_week, "deals": deals_week},
        "message": report,
    }, ensure_ascii=False)


registry.register(
    name="market_brief",
    toolset="real_estate",
    schema={"name": "market_brief", "description": "市场行情简报：自家盘况+联网行情（标注来源）+本周行动建议，可直接转发朋友圈/客户群", "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市（启用联网行情检索）"},
            "district": {"type": "string", "description": "区域（可选）"},
        },
    }},
    handler=lambda args, **kw: market_brief(**args),
)
