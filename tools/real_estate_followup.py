"""
Coco 房产工具 - 跟进管理
"""
import json
import re
from datetime import datetime
from tools.registry import registry
from agent.real_estate_display import attach_key_warning, mask_contacts
from agent.real_estate_input import clamp_limit, clean_text, clip_text, norm_date, norm_id

# 列表分页口径（与 list_customers/list_owners 同一套：默认 20、上限 200、≤0 与非数字按默认）
_LIST_LIMIT_DEFAULT = 20
_LIST_LIMIT_MAX = 200

# re_followups 的列宽：PostgreSQL 上 varchar 超长会让整单失败（sqlite 只是照存）
AGENT_ID_MAX = 100

# 逾期清单：默认在对话里列 50 条；limit 不设上限（老板 2026-09-25：要看全部走文档，别塞对话）
OVERDUE_LIMIT_DEFAULT = 50


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


# 跟进类型：内部存英文枚举（schema 里那 5 档），对外一律说中文
FOLLOWUP_TYPE_LABELS = {
    'call': '电话', 'visit': '带看', 'deal': '成交', 'note': '备注', 'reminder': '提醒',
}
_TYPE_ALIASES = {
    '电话': 'call', '打电话': 'call', '去电': 'call', '回访': 'call', 'phone': 'call',
    '带看': 'visit', '看房': 'visit', '到访': 'visit',
    '成交': 'deal', '签约': 'deal',
    '备注': 'note', '记录': 'note', '其他': 'note',
    '提醒': 'reminder', '待办': 'reminder',
}


def norm_followup_type(value):
    """跟进类型归一 → (枚举值, 提示或 None)。认英文枚举与常见中文说法，认不出不猜"""
    if value is None or str(value).strip() == '':
        return 'note', None
    text = str(value).strip().lower()
    if text in FOLLOWUP_TYPE_LABELS:
        return text, None
    if text in _TYPE_ALIASES:
        return _TYPE_ALIASES[text], None
    options = "、".join(f"{k}（{v}）" for k, v in FOLLOWUP_TYPE_LABELS.items())
    return None, f"跟进类型没能识别：收到的是「{value}」。可用：{options}"


def norm_followup_time(value):
    """跟进时间归一 → ('HH:MM' 或 None, 提示或 None)。认 9:00 / 09:00 / 9点30 / 9点 / 0930 / 09:30:00"""
    if value is None:
        return None, None
    text = str(value).strip().replace('：', ':').replace('点', ':').replace('分', '').rstrip(':')
    if not text:
        return None, None
    if text.isdigit() and len(text) == 4:
        text = text[:2] + ':' + text[2:]
    if text.isdigit():
        text = text + ':00'
    matched = re.match(r'^(\d{1,2})(?::(\d{1,2}))?', text)
    if not matched or (':' in text and not matched.group(2)):
        return None, _time_problem(value)
    hour, minute = int(matched.group(1)), int(matched.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, _time_problem(value)
    return f"{hour:02d}:{minute:02d}", None


def _time_problem(value):
    return f"下次跟进时间没能识别：收到的是「{value}」。请用 09:30 这类写法"


def _split_time_part(value):
    """从日期参数里拆出可能夹带的时刻 → (日期部分, 时刻部分或 None)

    模型常把整个 datetime 塞进 next_date（2026-09-28T14:30:00 / 2026-09-28 14:30），
    原先走 fromisoformat 能认，归一后必须照样认，不然后退成"日期格式错误"。
    """
    if value is None:
        return None, None
    if isinstance(value, datetime):
        has_time = bool(value.hour or value.minute)
        return value.date().isoformat(), (value.strftime('%H:%M:%S') if has_time else None)
    text = str(value).strip()
    for sep in ('T', 't', ' '):
        head, found, tail = text.partition(sep)
        if found and tail.strip():
            return head, tail
    return text, None


def norm_followup_when(date_value, time_value):
    """下次跟进时间归一 → (datetime 或 None, 'HH:MM' 或 None, 提示或 None)

    日期认 2026-12-31 / 2026/12/31 / 2026.12.31 / 2026年12月31日 / 12月31日，
    也认日期里夹带时刻的写法；显式传的 time 优先于日期里带的时刻。
    给了时刻就并进 datetime —— 与「设置提醒」「带看后自动提醒」同一口径。
    """
    date_part, embedded = _split_time_part(date_value)
    day, problem = norm_date(date_part, '下次跟进日期')
    if problem:
        return None, None, problem
    time_text, problem = norm_followup_time(
        time_value if str(time_value or '').strip() else embedded)
    if problem:
        return None, None, problem
    if day and time_text:
        hour, minute = (int(part) for part in time_text.split(':'))
        day = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return day, time_text, None


def add_followup(
    customer_id: int, content: str, property_id: int = None,
    type: str = 'note', next_date: str = None, next_time: str = None,
    agent_id: str = None, task_id: str = None,
) -> str:
    """添加客户跟进记录

    写入前先认人认房：客户或房源不存在就如实说明，不写孤儿记录（孤儿跟进会被
    逾期列表/午间检查当成真客户报出来，经纪人只看到一个查不到的编号）。
    下次跟进日期支持 2026-12-31 / 2026/12/31 / 2026年12月31日 / 12月31日 等写法；
    给了时间就把时刻并进 next_date（与设置提醒、带看后自动提醒同一口径）。
    """
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    if property_id is not None:
        property_id, problem = norm_id(property_id, '房源编号')
        if problem:
            return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    content = clean_text(content)
    if not content:
        return json.dumps({"success": False, "error": "跟进内容不能为空，请写一句这次沟通的情况"}, ensure_ascii=False)
    type_value, problem = norm_followup_type(type)
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    next_date_dt, next_time_text, problem = norm_followup_when(next_date, next_time)
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    warnings = []
    agent_id, clipped = clip_text(clean_text(agent_id), AGENT_ID_MAX)
    if clipped:
        warnings.append("经纪人编号" + clipped + "。")

    db = _get_db()
    customer = db.get_customer(customer_id)
    if not customer:
        return json.dumps({"success": False, "error": "客户不存在，请先在客户列表里核对编号"}, ensure_ascii=False)
    if property_id is not None and not db.get_property(property_id):
        return json.dumps({"success": False, "error": "房源不存在，请核对房源编号"}, ensure_ascii=False)
    result = db.add_followup(
        customer_id=customer_id, property_id=property_id, type=type_value,
        content=content, next_date=next_date_dt, next_time=next_time_text,
        agent_id=agent_id,
    )
    label = FOLLOWUP_TYPE_LABELS.get(type_value, '跟进')
    tail = ""
    if next_date_dt:
        when = next_date_dt.strftime('%Y-%m-%d %H:%M') if next_time_text else next_date_dt.strftime('%Y-%m-%d')
        tail = f"，下次跟进 {when}"
    payload = {"success": True,
               "message": f"已记录「{customer.get('name')}」的{label}跟进{tail}",
               "followup": result}
    if warnings:
        payload["warnings"] = warnings
    return json.dumps(payload, ensure_ascii=False)


def get_followups(customer_id: int, limit: int = _LIST_LIMIT_DEFAULT, task_id: str = None) -> str:
    """查看某位客户的跟进历史（最新的在前；默认 20 条、最多 200）

    返回 total=该客户跟进总条数、count=本次返回条数、truncated；被截断时给一句说明。
    "客户不存在"与"客户存在但没有跟进"分开说 —— 前者多半是编号打错了。
    每条带 type_label 中文类型与 property_title 关联房源标题（房源已删则给可读标注）。
    """
    limit = clamp_limit(limit, _LIST_LIMIT_DEFAULT, _LIST_LIMIT_MAX)
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    if not db.get_customer(customer_id):
        return json.dumps({"success": False, "error": "客户不存在，请先在客户列表里核对编号"},
                          ensure_ascii=False)
    result, total = db.get_followups(customer_id, limit=limit, with_total=True)
    titles = db.get_property_titles([f.get('property_id') for f in result])
    items = []
    for row in result:
        item = dict(row)
        item['type_label'] = FOLLOWUP_TYPE_LABELS.get(row.get('type'), row.get('type'))
        pid = row.get('property_id')
        if pid is not None:
            item['property_title'] = titles.get(pid) or f"已删除房源（id={pid}）"
        items.append(item)
    payload = {"success": True, "followups": items, "count": len(items), "total": total,
               "truncated": bool(total and total > len(items))}
    if not total:
        payload["message"] = "这位客户还没有跟进记录"
    elif payload["truncated"]:
        payload["message"] = (f"共 {total} 条跟进，本次返回最近 {len(items)} 条（最新在前）。"
                              f"要看得更全就把 limit 调大（最多 {_LIST_LIMIT_MAX}）")
    return json.dumps(payload, ensure_ascii=False)


def get_overdue(limit: int = OVERDUE_LIMIT_DEFAULT, task_id: str = None) -> str:
    """查看逾期跟进清单（按"每位客户最新一条跟进"的下次跟进时间是否已过判定）

    逾期最久在前；默认在对话里列 50 条，`limit` 不设上限（要看全部走文档，别把大 limit 塞进对话）。
    返回 total=逾期总条数、count=本次返回条数、truncated。每条带客户名与中文类型；
    客户已被删（存量孤儿）给"已删除客户（id=N）"标注而不是裸编号。
    本工具还会顺手把长期无互动的客户**自动降一级**（S→A→B→C，同一天最多降一次），
    降级名单在 downgrades 字段里如实说明。
    """
    limit = clamp_limit(limit, OVERDUE_LIMIT_DEFAULT, None)
    db = _get_db()
    rows = db.get_overdue()
    total = len(rows)
    # 流失预警：先取一次快照，降级复用同一份（原先这里全库扫描两遍）
    stale = db.get_stale_customers()
    downgrade = db.auto_downgrade_stale_customers(stale=stale)
    labels = db.get_customer_labels([r.get('customer_id') for r in rows[:limit]])
    page = []
    for row in rows[:limit]:
        item = dict(row)
        item['type_label'] = FOLLOWUP_TYPE_LABELS.get(row.get('type'), row.get('type'))
        cid = row.get('customer_id')
        label = labels.get(cid)
        if label:
            item['customer_name'] = label['name']
            item['customer_tier'] = label['tier']
        else:
            item['customer_name'] = f"已删除客户（id={cid}）"
            item['customer_missing'] = True
        page.append(item)
    if total:
        message = f"有 {total} 条跟进已逾期（逾期最久在前）"
    elif db.count_customers():
        message = "暂无逾期跟进"
    else:
        message = "库里还没有客户，先登记客户再设跟进"
    response = {"success": True, "overdue": page, "count": len(page), "total": total,
                "truncated": bool(total > len(page)), "message": message}
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
    customer_id, problem = norm_id(customer_id, '客户编号', '，可在客户列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
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
    {"name": "add_followup", "description": "添加客户跟进记录（电话/带看/成交/备注/提醒），可关联房源、设下次跟进日期与时间；写入前会核对客户与房源是否存在", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "content": {"type": "string", "description": "跟进内容"},
            "property_id": {"type": "integer", "description": "关联房源ID"},
            "type": {"type": "string", "enum": ["call", "visit", "deal", "note", "reminder"],
                     "description": "跟进类型（call 电话 / visit 带看 / deal 成交 / note 备注 / reminder 提醒，也认中文写法）"},
            "next_date": {"type": "string",
                          "description": "下次跟进日期（2026-12-31 / 2026/12/31 / 2026年12月31日 都认；给了时间会并到这一刻）"},
            "next_time": {"type": "string", "description": "下次跟进时间，如 09:30（也认 9点30 / 0930）"},
        }, "required": ["customer_id", "content"],
    }, "handler": lambda args, **kw: add_followup(**args)},
    {"name": "get_followups", "description": "查看某位客户的跟进历史（最新的在前；默认返回 20 条、最多 200）。返回 total=该客户跟进总条数、count=本次返回条数、truncated；客户不存在会如实说明", "parameters": {
        "type": "object", "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "limit": {"type": "integer", "description": "本次返回条数（默认 20，最多 200；传 0/负数/非数字按默认 20）"},
        }, "required": ["customer_id"],
    }, "handler": lambda args, **kw: get_followups(**args)},
    {"name": "get_overdue", "description": "获取逾期跟进列表", "parameters": {
        "type": "object", "properties": {
            "limit": {"type": "integer", "description": "本次返回条数（默认 50，不设上限；传 0/负数/非数字按默认 50）"},
        },
    }, "handler": lambda args, **kw: get_overdue(**args)},
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
    schema={"name": "add_followup", "description": "添加客户跟进记录（电话/带看/成交/备注/提醒），可关联房源、设下次跟进日期与时间；写入前会核对客户与房源是否存在", "parameters": TOOLS[0]["parameters"]},
    handler=TOOLS[0]["handler"],
)
registry.register(
    name="get_followups",
    toolset="real_estate",
    schema={"name": "get_followups", "description": "查看某位客户的跟进历史（最新的在前；默认返回 20 条、最多 200）。返回 total=该客户跟进总条数、count=本次返回条数、truncated；客户不存在会如实说明", "parameters": TOOLS[1]["parameters"]},
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


# 挽回话术模板的中文说法（对外只说人话，内部模板键留在 customers[] 里给 Coco 用）
_WINBACK_LABELS = {"winback_long_absence": "长期未联系", "winback_after_viewing": "看房后没下文"}


def churn_warning(min_risk: int = 40, task_id: str = None) -> str:
    """流失预警：找出"快凉了但还能救"的客户，附挽回建议"""
    db = _get_db()
    rows = db.churn_risk_customers(min_risk=min_risk)
    if not rows:
        return json.dumps({"success": True, "message": "当前无流失风险客户，保持节奏", "customers": []}, ensure_ascii=False)
    # 联系方式展示防御（2026-09-25）：customers[] 里带着 phone，密钥不一致时是密文（原先直出）
    masked_fields = []
    for r in rows:
        _, m = mask_contacts(r)
        masked_fields.extend(m)
    high = [r for r in rows if r["risk_level"] == "高危"]
    lines = [f"⚠️ 流失预警：{len(rows)} 位客户有流失风险（高危 {len(high)} 位）"]
    for r in rows[:10]:
        lines.append(f"\n· {r['name']}（{r['tier']}级，风险{r['risk_score']}分[{r['risk_level']}]）")
        lines.append(f"  信号: {'、'.join(r['signals'])}")
        label = _WINBACK_LABELS.get(r["winback_script"], "挽回")
        lines.append(f"  建议: 用「{label}」挽回模板生成话术")
    return json.dumps(attach_key_warning({
        "success": True,
        "summary": {"total": len(rows), "high_risk": len(high)},
        "customers": rows,
        "message": "\n".join(lines),
    }, masked_fields), ensure_ascii=False)


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


def stage_stagnation(task_id: str = None) -> str:
    """阶段滞留清单：强意向/已看房/谈判阶段停留超时的客户"""
    db = _get_db()
    alerts = db.stage_stagnation_report()
    if not alerts:
        return json.dumps({"success": True, "message": "无阶段滞留客户，节奏健康", "alerts": []}, ensure_ascii=False)
    lines = [f"⏰ 阶段滞留提醒：{len(alerts)} 位客户停留超时"]
    for a in alerts:
        lines.append(f"\n· {a['name']}（{a['tier']}级）在「{a['stage']}」已停留 {a['days_in_stage']} 天")
        lines.append(f"  建议: {a['hint']}")
    return json.dumps({"success": True, "alerts": alerts, "message": "\n".join(lines)}, ensure_ascii=False)


registry.register(
    name="stage_stagnation",
    toolset="real_estate",
    schema={"name": "stage_stagnation", "description": "阶段滞留清单：强意向超7天/已看房超14天/谈判超7天无推进的客户", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: stage_stagnation(**args),
)
