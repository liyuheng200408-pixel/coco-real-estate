"""
Coco 房产工具 - 跟进管理
"""
import json
from datetime import datetime
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def add_followup(
    customer_id: int, content: str, property_id: int = None,
    type: str = 'note', next_date: str = None, next_time: str = None,
    agent_id: str = None, task_id: str = None,
) -> str:
    """添加客户跟进记录"""
    db = _get_db()
    next_date_dt = None
    if next_date:
        try:
            next_date_dt = datetime.fromisoformat(next_date)
        except ValueError:
            return json.dumps({"success": False, "error": "日期格式错误，请使用 ISO 格式"}, ensure_ascii=False)
    result = db.add_followup(
        customer_id=customer_id, property_id=property_id, type=type,
        content=content, next_date=next_date_dt, next_time=next_time,
        agent_id=agent_id,
    )
    return json.dumps({"success": True, "followup": result}, ensure_ascii=False)


def get_followups(customer_id: int, limit: int = 20, task_id: str = None) -> str:
    """获取客户跟进历史"""
    db = _get_db()
    result = db.get_followups(customer_id, limit=limit)
    return json.dumps({"success": True, "followups": result, "count": len(result)}, ensure_ascii=False)


def get_overdue(task_id: str = None) -> str:
    """获取逾期跟进列表 + 流失预警（超期无互动客户自动降级）"""
    db = _get_db()
    result = db.get_overdue()
    # 流失预警：自动降级长期无互动客户（S>5天→A，A>10天→B，B>30天→C）
    downgrade = db.auto_downgrade_stale_customers()
    stale = db.get_stale_customers()
    message = f"有 {len(result)} 条跟进已逾期" if result else "暂无逾期跟进"
    response = {"success": True, "overdue": result, "count": len(result), "message": message}
    if downgrade.get('downgrades'):
        response['downgrades'] = downgrade['downgrades']
        response['message'] = message + f"；{len(downgrade['downgrades'])} 位客户长期无互动已自动降级"
    if stale:
        response['stale_customers'] = stale
    return json.dumps(response, ensure_ascii=False)


def stale_check(task_id: str = None) -> str:
    """流失预警检查：自动降级长期无互动客户并返回预警列表

    S级>5天无互动→降A，A级>10天→降B，B级>30天→降C；降级写入变更历史。
    """
    db = _get_db()
    downgrade = db.auto_downgrade_stale_customers()
    stale = db.get_stale_customers()
    return json.dumps({
        "success": True,
        "downgrades": downgrade['downgrades'],
        "still_stale": stale,
        "still_stale_count": len(stale),
        "message": f"本次自动降级 {len(downgrade['downgrades'])} 位客户" if downgrade['downgrades'] else "无客户需要降级",
    }, ensure_ascii=False)


def schedule_reminder(customer_id: int, date: str, time: str, content: str = None, task_id: str = None) -> str:
    """设置客户跟进提醒"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    next_date_dt = None
    if date:
        try:
            next_date_dt = datetime.fromisoformat(f"{date}T{time or '09:00'}")
        except ValueError:
            return json.dumps({"success": False, "error": "日期格式错误"}, ensure_ascii=False)
    reminder_content = content or f"跟进客户 {customer.get('name')}"
    db.add_followup(customer_id=customer_id, type='reminder', content=reminder_content, next_date=next_date_dt, next_time=time)
    return json.dumps({"success": True, "message": f"已设置 {date} {time} 提醒跟进 {customer.get('name')}"}, ensure_ascii=False)


def daily_report(task_id: str = None) -> str:
    """生成每日早报（附带流失预警与自动降级信息）"""
    db = _get_db()
    report = db.daily_report()
    downgrade = db.auto_downgrade_stale_customers()
    stale = db.get_stale_customers()
    if downgrade.get('downgrades'):
        report['downgrades'] = downgrade['downgrades']
    if stale:
        report['stale_customers'] = stale
    return json.dumps({"success": True, "report": report}, ensure_ascii=False)


def midday_check(task_id: str = None) -> str:
    """午间检查（附带流失预警）"""
    db = _get_db()
    check = db.midday_check()
    downgrade = db.auto_downgrade_stale_customers()
    stale = db.get_stale_customers()
    if downgrade.get('downgrades'):
        check['downgrades'] = downgrade['downgrades']
    if stale:
        check['stale_customers'] = stale
    return json.dumps({"success": True, "check": check}, ensure_ascii=False)


TOOLS = [
    {"name": "add_followup", "description": "添加客户跟进记录", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "content": {"type": "string", "description": "跟进内容"},
            "property_id": {"type": "integer", "description": "关联房源ID"},
            "type": {"type": "string", "enum": ["call", "visit", "deal", "note", "reminder"], "description": "跟进类型"},
            "next_date": {"type": "string", "description": "下次跟进日期（ISO格式）"},
            "next_time": {"type": "string", "description": "提醒时间，如 09:00"},
        }, "required": ["customer_id", "content"],
    }, "handler": lambda args, **kw: add_followup(**args)},
    {"name": "get_followups", "description": "获取客户跟进历史", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer"}, "limit": {"type": "integer"},
        }, "required": ["customer_id"],
    }, "handler": lambda args, **kw: get_followups(**args)},
    {"name": "get_overdue", "description": "获取逾期跟进列表", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: get_overdue()},
    {"name": "schedule_reminder", "description": "设置客户跟进提醒", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer"}, "date": {"type": "string"},
            "time": {"type": "string"}, "content": {"type": "string"},
        }, "required": ["customer_id", "date", "time"],
    }, "handler": lambda args, **kw: schedule_reminder(**args)},
    {"name": "daily_report", "description": "生成每日早报", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: daily_report()},
    {"name": "midday_check", "description": "午间检查", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: midday_check()},
    {"name": "stale_check", "description": "流失预警检查：自动降级长期无互动客户（S级>5天→A，A级>10天→B，B级>30天→C）并返回预警列表", "parameters": {
        "type": "object", "properties": {},
    }, "handler": lambda args, **kw: stale_check()},
]

registry.register(
    name="add_followup",
    toolset="real_estate",
    schema={"name": "add_followup", "description": "添加客户跟进记录", "parameters": TOOLS[0]["parameters"]},
    handler=TOOLS[0]["handler"],
)
registry.register(
    name="get_followups",
    toolset="real_estate",
    schema={"name": "get_followups", "description": "获取客户跟进历史", "parameters": TOOLS[1]["parameters"]},
    handler=TOOLS[1]["handler"],
)
registry.register(
    name="get_overdue",
    toolset="real_estate",
    schema={"name": "get_overdue", "description": "获取逾期跟进列表", "parameters": TOOLS[2]["parameters"]},
    handler=TOOLS[2]["handler"],
)
registry.register(
    name="schedule_reminder",
    toolset="real_estate",
    schema={"name": "schedule_reminder", "description": "设置客户跟进提醒", "parameters": TOOLS[3]["parameters"]},
    handler=TOOLS[3]["handler"],
)
registry.register(
    name="daily_report",
    toolset="real_estate",
    schema={"name": "daily_report", "description": "生成每日早报", "parameters": TOOLS[4]["parameters"]},
    handler=TOOLS[4]["handler"],
)
registry.register(
    name="midday_check",
    toolset="real_estate",
    schema={"name": "midday_check", "description": "午间检查", "parameters": TOOLS[5]["parameters"]},
    handler=TOOLS[5]["handler"],
)
registry.register(
    name="stale_check",
    toolset="real_estate",
    schema={"name": "stale_check", "description": "流失预警检查：自动降级长期无互动客户（S级>5天→A，A级>10天→B，B级>30天→C）并返回预警列表", "parameters": TOOLS[6]["parameters"]},
    handler=TOOLS[6]["handler"],
)


def churn_warning(min_risk: int = 40, task_id: str = None) -> str:
    """流失预警：找出"快凉了但还能救"的客户，附挽回建议"""
    db = _get_db()
    rows = db.churn_risk_customers(min_risk=min_risk)
    if not rows:
        return json.dumps({"success": True, "message": "当前无流失风险客户，保持节奏", "customers": []}, ensure_ascii=False)
    high = [r for r in rows if r["risk_level"] == "高危"]
    lines = [f"⚠️ 流失预警：{len(rows)} 位客户有流失风险（高危 {len(high)} 位）"]
    for r in rows[:10]:
        lines.append(f"\n· {r['name']}（{r['tier']}级，风险{r['risk_score']}分[{r['risk_level']}]）")
        lines.append(f"  信号: {'、'.join(r['signals'])}")
        lines.append(f"  建议: 调用 use_template 模板 {r['winback_script']} 生成挽回话术")
    return json.dumps({
        "success": True,
        "summary": {"total": len(rows), "high_risk": len(high)},
        "customers": rows,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


registry.register(
    name="churn_warning",
    toolset="real_estate",
    schema={"name": "churn_warning", "description": "客户流失预警：综合最后跟进时间/带看后沉默/等级加权评分，点名高危客户并给挽回建议", "parameters": {
        "type": "object",
        "properties": {
            "min_risk": {"type": "integer", "description": "最低风险分（默认40，中危起步）"},
        },
    }},
    handler=lambda args, **kw: churn_warning(**args),
)
