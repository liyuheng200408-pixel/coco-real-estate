"""
Coco 房产工具 - 生日/节日提醒
"""
import json
from datetime import datetime
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def birthday_check(task_id: str = None) -> str:
    """检查今天/明天过生日的客户（供定时任务调用）"""
    db = _get_db()
    now = datetime.now()
    today = db.get_birthday_customers(month=now.month, day=now.day)
    # 明天生日（提前提醒）
    tomorrow = now.replace(day=now.day + 1) if now.day < 28 else now
    from datetime import timedelta
    tmr = now + timedelta(days=1)
    upcoming = db.get_birthday_customers(month=tmr.month, day=tmr.day)

    result = {
        "success": True,
        "today_birthdays": today,
        "tomorrow_birthdays": upcoming,
    }
    return json.dumps(result, ensure_ascii=False)


def update_birthday(customer_id: int, birthday: str, task_id: str = None) -> str:
    """设置客户生日（YYYY-MM-DD）"""
    from datetime import datetime as _dt
    try:
        _dt.strptime(birthday.strip(), "%Y-%m-%d")
    except ValueError:
        return json.dumps({"success": False, "error": "生日格式错误，请用 YYYY-MM-DD"}, ensure_ascii=False)
    db = _get_db()
    result = db.update_customer(customer_id, birthday=birthday.strip())
    if result:
        return json.dumps({"success": True, "customer": result, "message": f"已设置客户生日 {birthday}"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "客户不存在"}, ensure_ascii=False)


registry.register(
    name="birthday_check",
    toolset="real_estate",
    schema={"name": "birthday_check", "description": "检查今天和明天过生日的客户（定时任务用）", "parameters": {
        "type": "object", "properties": {},
    }},
    handler=lambda args, **kw: birthday_check(),
)

registry.register(
    name="update_birthday",
    toolset="real_estate",
    schema={"name": "update_birthday", "description": "设置客户生日（YYYY-MM-DD）", "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer", "description": "客户ID"},
            "birthday": {"type": "string", "description": "生日 YYYY-MM-DD"},
        },
        "required": ["customer_id", "birthday"],
    }},
    handler=lambda args, **kw: update_birthday(**args),
)
