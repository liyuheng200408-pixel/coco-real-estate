"""
Coco 房产工具 - 带看管理
"""
import json
from datetime import datetime
from tools.registry import registry
from agent.real_estate_input import clamp_limit, norm_date, norm_id
from tools.real_estate_followup import norm_followup_time, split_time_part
from tools.real_estate_property import _STATUS_LABELS

# 列表分页口径（与 list_customers/list_owners 同一套：默认 20、上限 200、≤0 与非数字按默认）
_LIST_LIMIT_DEFAULT = 20
_LIST_LIMIT_MAX = 200

# 只给日期、没说时刻时按上午 10:00 记（回执必须说明这是默认值，别让经纪人以为他说过）
_DEFAULT_VIEWING_HOUR = 10


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def norm_viewing_when(value, label='带看时间', sample='2026-12-31 10:00'):
    """带看时间归一 → (datetime 或 None, 是否用了默认时刻, 提示或 None)

    认 `2026-12-31 10:00` / `2026-12-31`（按 10:00）/ `2026/12/31 10:00` / `2026年12月31日 10:00` /
    `9点30` / `明天 10:00` / `周三 10:00` / `3天后 10:00` / 夹带时刻的 `2026-12-31T10:00` ——
    日期与时刻复用跟进侧同一套归一（`norm_date` / `norm_followup_time` / `split_time_part`），
    别再各写一份解析器（原先只认 `YYYY-MM-DD HH:MM`，经纪人怎么说都被拒）。
    提示文案按"日期+时刻挤在一个参数里"的场景自己给：认不出时引的是**经纪人原话**，不是拆出来的半截。
    """
    date_part, embedded = split_time_part(value)
    if not str(date_part or '').strip():
        return None, False, f"{label}不能为空，请说一下哪天几点（如 {sample}、明天 10:00）"
    day, problem = norm_date(date_part, label, sample)
    if problem:
        return None, False, f"{label}没能识别：收到的是「{value}」。可以说 {sample}，也可以说 明天 10:00"
    time_text = None
    if embedded:
        time_text, problem = norm_followup_time(embedded, label)
        if problem:
            return None, False, f"{label}没能识别：收到的是「{value}」。时间请用 9:30 或 9点30 这类写法"
    if not time_text:
        return day.replace(hour=_DEFAULT_VIEWING_HOUR, minute=0), True, None
    hour, minute = (int(part) for part in time_text.split(':'))
    return day.replace(hour=hour, minute=minute), False, None


def schedule_viewing(customer_id: int, property_id: int, viewing_time: str, task_id: str = None) -> str:
    """预约带看：为指定客户安排指定房源的带看时间

    写入前先认人认房（客户或房源不存在就如实说明，不写孤儿带看 —— 孤儿会在带看列表、
    统计里冒出来，经纪人只看到一个查不到的编号）。同一客户同一房源同一时间已有未完成的
    带看时不再重复登记，返回既有那条。已售/已租的房源、已关闭的客户、已经过去的时间都只给
    提醒不拦（补录历史带看是真实需求）。回执里给带看编号，记结果、查详情都用它。
    """
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    property_id, problem = norm_id(property_id, '房源编号')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    dt, used_default, problem = norm_viewing_when(viewing_time)
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在，请先在客户列表里核对编号"},
                          ensure_ascii=False)
    prop = db.get_property(property_id)
    if not prop:
        return json.dumps({"success": False, "error": "房源不存在，请核对房源编号"}, ensure_ascii=False)

    stamped = dt.strftime('%Y-%m-%d %H:%M')
    existing = db.find_scheduled_viewing(customer_id, property_id, dt)
    if existing:
        return json.dumps({
            "success": True, "viewing": existing, "already_scheduled": True,
            "message": f"这位客户已经约了这个房源 {stamped} 的带看（带看编号 {existing['id']}），没有重复登记",
        }, ensure_ascii=False)

    warnings = []
    if dt < datetime.now():
        warnings.append(f"这个时间已经过去了（{stamped}）。我按补录记下了；"
                        f"如果是要新约带看，请给我一个将来的时间")
    if (prop.get('status') or '') in ('sold', 'rented'):
        warnings.append(f"该房源状态是{_STATUS_LABELS.get(prop['status'], prop['status'])}，"
                        f"约带看前先确认一下")
    if (customer.get('status') or '') == 'closed':
        warnings.append("这位客户已经标记为已关闭，确认还要约带看吗")

    result = db.add_viewing(customer_id=customer_id, property_id=property_id, viewing_time=dt)
    note = f"；你没说具体时间，我按 {_DEFAULT_VIEWING_HOUR:02d}:00 记的" if used_default else ""
    payload = {
        "success": True,
        "viewing": result,
        "message": (f"已预约 {stamped} 带看（带看编号 {result['id']}{note}），"
                    f"客户: {customer.get('name')}，房源: {result.get('property_title')}"),
    }
    if warnings:
        payload["warnings"] = warnings
    return json.dumps(payload, ensure_ascii=False)


def record_viewing(viewing_id: int, status: str = None, result: str = None, feedback: str = None, task_id: str = None) -> str:
    """记录带看结果：status(scheduled/done/cancelled)、result(interested/not_interested/pending)、feedback(客户反馈)"""
    viewing_id, problem = norm_id(viewing_id, '带看编号', '，可在带看记录列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
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
    viewing_id, problem = norm_id(viewing_id, '带看编号', '，可在带看记录列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    result = db.get_viewing(viewing_id)
    if result:
        return json.dumps({"success": True, "viewing": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "带看记录不存在"}, ensure_ascii=False)


def list_viewings(customer_id: int = None, property_id: int = None, status: str = None,
                  limit: int = _LIST_LIMIT_DEFAULT, task_id: str = None) -> str:
    """列出带看记录，可按客户/房源/状态筛选"""
    limit = clamp_limit(limit, _LIST_LIMIT_DEFAULT, _LIST_LIMIT_MAX)
    if customer_id is not None:
        customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
        if problem:
            return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    if property_id is not None:
        property_id, problem = norm_id(property_id, '房源编号')
        if problem:
            return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    result = db.list_viewings(customer_id=customer_id, property_id=property_id, status=status, limit=limit)
    return json.dumps({"success": True, "viewings": result, "count": len(result)}, ensure_ascii=False)


def viewing_stats(task_id: str = None) -> str:
    """带看统计：总数、已看、取消、客户感兴趣比例"""
    db = _get_db()
    stats = db.viewing_stats()
    return json.dumps({"success": True, "stats": stats}, ensure_ascii=False)


registry.register(
    name="schedule_viewing",
    toolset="real_estate",
    schema={"name": "schedule_viewing", "description":
            "预约带看：给指定客户安排看某个房源的带看时间，时间支持 2026-12-31 10:00、明天 10:00、周三 10:00、"
            "3天后 10:00（只给日期就按当天 10:00 记，回执会说明）。返回带看编号（记结果、查详情都用它）；"
            "客户或房源编号查不到会如实说明，不建空记录；同一客户同一房源同一时间不会重复登记。"
            "已售/已租的房源、已关闭的客户、已经过去的时间只给提醒不拦。", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户编号（数字，来自建档或客户列表）"},
            "property_id": {"type": "integer", "description": "房源编号（数字，来自建档或房源列表）"},
            "viewing_time": {"type": "string", "description":
                             "带看时间：2026-12-31 10:00 / 2026/12/31 10:00 / 2026年12月31日 10:00 / "
                             "明天 10:00 / 周三 10:00 / 3天后 10:00；只给日期（如 2026-12-31）就按 10:00 记"},
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
            "limit": {"type": "integer", "description": "返回条数（默认 20，最多 200；传 0/负数/非数字按默认 20）"},
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
    property_id, problem = norm_id(property_id, '房源编号')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
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
