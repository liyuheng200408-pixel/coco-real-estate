"""
Coco 房产工具 - 话术库沉淀
经纪人可自定义话术并复用
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def save_script(name: str, content: str, scenario: str = "custom", task_id: str = None) -> str:
    """保存自定义话术到话术库

    scenario: greeting(开场) / objection_handling(异议处理) / closing(逼定) / follow_up(跟进) / custom(自定义)
    """
    if not name or not content:
        return json.dumps({"success": False, "error": "话术名称和内容不能为空"}, ensure_ascii=False)
    db = _get_db()
    result = db.add_script(name=name, content=content, scenario=scenario)
    return json.dumps({"success": True, "script": result, "message": f"话术已保存: {name}"}, ensure_ascii=False)


def get_script_by_name(name: str, task_id: str = None) -> str:
    """按名称获取话术"""
    db = _get_db()
    result = db.get_script_by_name(name)
    if result:
        return json.dumps({"success": True, "script": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": f"话术不存在: {name}"}, ensure_ascii=False)


def list_scripts(scenario: str = None, task_id: str = None) -> str:
    """列出话术库（可按场景筛选）"""
    db = _get_db()
    result = db.list_scripts(scenario=scenario)
    return json.dumps({"success": True, "scripts": result, "count": len(result)}, ensure_ascii=False)


def delete_script(script_id: int, task_id: str = None) -> str:
    """删除话术"""
    db = _get_db()
    if db.delete_script(script_id):
        return json.dumps({"success": True, "message": "话术已删除"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "话术不存在"}, ensure_ascii=False)


registry.register(
    name="save_script",
    toolset="real_estate",
    schema={"name": "save_script", "description": "保存自定义话术到话术库", "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "话术名称"},
            "content": {"type": "string", "description": "话术内容"},
            "scenario": {"type": "string", "enum": ["greeting", "objection_handling", "closing", "follow_up", "custom"], "description": "话术场景"},
        },
        "required": ["name", "content"],
    }},
    handler=lambda args, **kw: save_script(**args),
)

registry.register(
    name="get_script_by_name",
    toolset="real_estate",
    schema={"name": "get_script_by_name", "description": "按名称获取话术", "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "话术名称"}},
        "required": ["name"],
    }},
    handler=lambda args, **kw: get_script_by_name(**args),
)

registry.register(
    name="list_scripts",
    toolset="real_estate",
    schema={"name": "list_scripts", "description": "列出话术库（可按场景筛选）", "parameters": {
        "type": "object",
        "properties": {
            "scenario": {"type": "string", "enum": ["greeting", "objection_handling", "closing", "follow_up", "custom"]},
        },
    }},
    handler=lambda args, **kw: list_scripts(**args),
)

registry.register(
    name="delete_script",
    toolset="real_estate",
    schema={"name": "delete_script", "description": "删除话术", "parameters": {
        "type": "object",
        "properties": {"script_id": {"type": "integer", "description": "话术ID"}},
        "required": ["script_id"],
    }},
    handler=lambda args, **kw: delete_script(**args),
)
