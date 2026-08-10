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
    
    # 获取本周新增房源（模拟）
    new_listings = 5  # 实际应从数据库统计
    
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
