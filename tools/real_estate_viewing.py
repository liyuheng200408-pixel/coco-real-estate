"""
Coco 房产工具 - 带看管理
"""
import json
from datetime import datetime
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def _parse_time(viewing_time: str):
    """解析带看时间，支持 2026-08-15 10:00 或 ISO 格式"""
    viewing_time = viewing_time.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(viewing_time, fmt)
        except ValueError:
            continue
    # 纯日期，默认 10:00
    try:
        return datetime.strptime(viewing_time, "%Y-%m-%d").replace(hour=10)
    except ValueError:
        raise ValueError(f"时间格式错误: {viewing_time}，请用 YYYY-MM-DD HH:MM 格式")


def schedule_viewing(customer_id: int, property_id: int, viewing_time: str, task_id: str = None) -> str:
    """预约带看：为指定客户安排指定房源的带看时间"""
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)
    try:
        dt = _parse_time(viewing_time)
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    result = db.add_viewing(customer_id=customer_id, property_id=property_id, viewing_time=dt)
    return json.dumps({
        "success": True,
        "viewing": result,
        "message": f"已预约 {viewing_time} 带看，客户: {customer.get('name')}，房源: {result.get('property_title')}"
    }, ensure_ascii=False)


def record_viewing(viewing_id: int, status: str = None, result: str = None, feedback: str = None, task_id: str = None) -> str:
    """记录带看结果：status(scheduled/done/cancelled)、result(interested/not_interested/pending)、feedback(客户反馈)"""
    db = _get_db()
    kwargs = {}
    if status:
        if status not in ('scheduled', 'done', 'cancelled'):
            return json.dumps({"success": False, "error": "status 必须是 scheduled/done/cancelled"}, ensure_ascii=False)
        kwargs['status'] = status
    if result:
        if result not in ('interested', 'not_interested', 'pending'):
            return json.dumps({"success": False, "error": "result 必须是 interested/not_interested/pending"}, ensure_ascii=False)
        kwargs['result'] = result
    if feedback is not None:
        kwargs['feedback'] = feedback
    updated = db.update_viewing(viewing_id, **kwargs)
    if not updated:
        return json.dumps({"success": False, "error": "带看记录不存在"}, ensure_ascii=False)

    # 带看完成 → 自动安排 1 小时后回访提醒
    reminder_added = False
    if kwargs.get('status') == 'done':
        try:
            from datetime import timedelta
            now = datetime.now()
            remind_time = now + timedelta(hours=1)
            customer = db.get_customer(updated['customer_id'])
            customer_name = customer.get('name') if customer else '客户'
            db.add_followup(
                customer_id=updated['customer_id'],
                type='reminder',
                content=f"带看后回访：{customer_name} 看完 {updated.get('property_title')} 已 1 小时，主动跟进了解意向",
                next_date=remind_time,
                next_time=remind_time.strftime('%H:%M'),
            )
            reminder_added = True
        except Exception:
            reminder_added = False

    # 缺陷标签反哺（2026-08-28 功能3）：记录带看结果后自动重扫该房缺陷
    defect_refreshed = None
    if updated.get('property_id') and (feedback or updated.get('result') == 'not_interested'):
        try:
            defects = db.refresh_defect_tags(updated['property_id'])
            defect_refreshed = defects
        except Exception:
            defect_refreshed = None

    response = {"success": True, "viewing": updated}
    if defect_refreshed:
        response["defect_tags_updated"] = defect_refreshed
        response["message"] = f"带看已记录；检测到共性差评，已更新房源缺陷标签: {','.join(defect_refreshed)}"
    elif reminder_added:
        response["message"] = "带看已记录，已自动安排 1 小时后回访提醒"
    return json.dumps(response, ensure_ascii=False)


def get_viewing(viewing_id: int, task_id: str = None) -> str:
    """查看带看详情"""
    db = _get_db()
    result = db.get_viewing(viewing_id)
    if result:
        return json.dumps({"success": True, "viewing": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "带看记录不存在"}, ensure_ascii=False)


def list_viewings(customer_id: int = None, property_id: int = None, status: str = None, limit: int = 20, task_id: str = None) -> str:
    """列出带看记录，可按客户/房源/状态筛选"""
    db = _get_db()
    result = db.list_viewings(customer_id=customer_id, property_id=property_id, status=status, limit=limit)
    return json.dumps({"success": True, "viewings": result, "count": len(result)}, ensure_ascii=False)


def viewing_stats(task_id: str = None) -> str:
    """带看统计：总数、已看、取消、客户感兴趣比例"""
    db = _get_db()
    stats = db.viewing_stats()
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


# 注册工具
registry.register(
    name="schedule_viewing",
    toolset="real_estate",
    schema={"name": "schedule_viewing", "description": "预约带看：为指定客户安排指定房源的带看时间", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "property_id": {"type": "integer", "description": "房源ID"},
            "viewing_time": {"type": "string", "description": "带看时间，如 2026-08-15 10:00"},
        },
        "required": ["customer_id", "property_id", "viewing_time"],
    }},
    handler=lambda args, **kw: schedule_viewing(**args),
)

registry.register(
    name="record_viewing",
    toolset="real_estate",
    schema={"name": "record_viewing", "description": "记录带看结果：状态和客户反馈", "parameters": {
        "type": "object",
        "properties": {
            "viewing_id": {"type": "integer", "description": "带看记录ID"},
            "status": {"type": "string", "enum": ["scheduled", "done", "cancelled"], "description": "带看状态"},
            "result": {"type": "string", "enum": ["interested", "not_interested", "pending"], "description": "客户意向"},
            "feedback": {"type": "string", "description": "客户反馈"},
        },
        "required": ["viewing_id"],
    }},
    handler=lambda args, **kw: record_viewing(**args),
)

registry.register(
    name="get_viewing",
    toolset="real_estate",
    schema={"name": "get_viewing", "description": "查看带看详情", "parameters": {
        "type": "object",
        "properties": {"viewing_id": {"type": "integer"}},
        "required": ["viewing_id"],
    }},
    handler=lambda args, **kw: get_viewing(**args),
)

registry.register(
    name="list_viewings",
    toolset="real_estate",
    schema={"name": "list_viewings", "description": "列出带看记录，可按客户/房源/状态筛选", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer"},
            "property_id": {"type": "integer"},
            "status": {"type": "string", "enum": ["scheduled", "done", "cancelled"]},
            "limit": {"type": "integer"},
        },
    }},
    handler=lambda args, **kw: list_viewings(**args),
)

registry.register(
    name="viewing_stats",
    toolset="real_estate",
    schema={"name": "viewing_stats", "description": "带看统计：总数、已看、取消、客户感兴趣比例", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: viewing_stats(),
)


def clear_defect_tag(property_id: int, tag: str, task_id: str = None) -> str:
    """房东整改后，经纪人手动清除某缺陷标签"""
    db = _get_db()
    ok = db.clear_defect_tag(property_id, tag)
    if ok:
        return json.dumps({"success": True, "message": f"已清除缺陷标签: {tag}"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": f"清除失败：该房源没有标签 {tag}"}, ensure_ascii=False)


registry.register(
    name="clear_defect_tag",
    toolset="real_estate",
    schema={"name": "clear_defect_tag", "description": "清除房源缺陷标签（房东整改后由经纪人手动操作，不自动清除）", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "tag": {"type": "string", "description": "要清除的标签名（如 采光差）"},
        },
        "required": ["property_id", "tag"],
    }},
    handler=lambda args, **kw: clear_defect_tag(**args),
)
