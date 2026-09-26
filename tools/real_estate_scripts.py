"""
Coco 房产工具 - 话术库沉淀
经纪人可自定义话术并复用
"""
import json
from tools.registry import registry
from agent.real_estate_input import clean_text, clip_text, norm_id
from agent.real_estate_script import label_of, norm_scenario, type_word

# 话术库认的场景（顺序即提示里给经纪人念的清单顺序）—— 与内置话术同一套档位
SCRIPT_SCENARIOS = ["greeting", "objection_handling", "closing", "follow_up", "custom"]
SCRIPT_NAME_MAX = 100        # 与 re_scripts.name 的列宽一致（PostgreSQL 上超长会让整次保存失败）


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def _script_field(value, label, hint):
    """文本项归一 → (文本 或 None, 中文提示 或 None)

    非文字（列表/字典）不许落到数据库层：那是 sqlite/PG 的绑定错误，报错里连表名列名
    与要写入的参数都会带出来，等于把内部结构念给模型（2026-09-26）。
    """
    if value is not None and not isinstance(value, str):
        return None, f"{label}要给{hint}。这次收到的是{type_word(value)}，我没法用。"
    return clean_text(value), None


def _truthy(value):
    """force 类开关：认 true/1/yes/是/覆盖（模型有时把布尔写成文字）"""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "是", "要", "覆盖"}


def save_script(name: str, content: str, scenario: str = "custom",
                force: bool = False, task_id: str = None) -> str:
    """保存自定义话术到话术库

    scenario: greeting(开场白) / objection_handling(异议处理) / closing(逼定成交) / follow_up(跟进维护) / custom(自定义)
    force: 同名时是否覆盖原来那条（不填＝不覆盖，先提醒）
    """
    name, problem = _script_field(name, "话术名称", "一个名字（如「议价话术」）")
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    if not name:
        return json.dumps({"success": False, "error": "话术名称不能为空，给一个名字就行（如「议价话术」）。"},
                          ensure_ascii=False)
    name, clip_hint = clip_text(name, SCRIPT_NAME_MAX)

    content, problem = _script_field(content, "话术内容", "一段文字")
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    if not content:
        return json.dumps({"success": False, "error": "话术内容不能为空，把要存的那段话发给我。"},
                          ensure_ascii=False)

    if isinstance(scenario, str):
        key, problem = (norm_scenario(scenario, SCRIPT_SCENARIOS) if scenario.strip() else ("custom", None))
    elif scenario is None:
        key, problem = "custom", None
    else:
        key, problem = None, f"话术场景要给一个说法（如「开场白」）。这次收到的是{type_word(scenario)}，我没法用。"
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)

    db = _get_db()
    existing = db.get_script_by_name(name)
    if existing and not _truthy(force):
        return json.dumps({"success": False, "error": (
            f"话术库里已经有一份叫「{name}」的（编号 {existing['id']}）。"
            f"要我用这版覆盖它，就跟我说一声；要另存一份就把名字改一下。")}, ensure_ascii=False)

    if existing:                                  # 覆盖：还是同一条，编号不变
        result = db.update_script(existing["id"], content=content, scenario=key)
        updated = True
        message = f"已更新同名话术「{name}」（编号 {existing['id']}，场景：{label_of(key)}）。"
    else:
        result = db.add_script(name=name, content=content, scenario=key)
        updated = False
        message = f"话术已保存：「{name}」（编号 {result['id']}，场景：{label_of(key)}）。"
    result["scenario_label"] = label_of(key)

    payload = {"success": True, "script": result, "updated": updated, "message": message}
    if clip_hint:
        payload["truncated"] = True
        payload["note"] = f"名称{clip_hint}。"
    return json.dumps(payload, ensure_ascii=False)


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
    script_id, problem = norm_id(script_id, '话术编号', '，可在话术列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem}, ensure_ascii=False)
    db = _get_db()
    if db.delete_script(script_id):
        return json.dumps({"success": True, "message": "话术已删除"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "话术不存在"}, ensure_ascii=False)


registry.register(
    name="save_script",
    toolset="real_estate",
    schema={"name": "save_script", "description": "保存一条自定义话术到话术库（经纪人自己攒的话术，随时能按名字取回来）。同名会先提醒你 —— 要覆盖原来那条就说一声，要另存一份就改个名字；场景认中文说法；名称最长 100 字，超了会截断并告诉你。这是\"存话术\"，跟内置话术（get_script 那 12 条）不是一回事。", "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "话术名称（最长 100 字，如「议价话术」）。同名会先提醒你，不会静默覆盖"},
            "content": {"type": "string", "description": "话术内容（要发给客户的那段原话）"},
            "scenario": {"type": "string", "enum": ["greeting", "objection_handling", "closing", "follow_up", "custom"], "description": "话术场景：开场白 / 异议处理 / 逼定成交 / 跟进维护 / 自定义（认这几种中文说法，也认英文；不填按「自定义」）"},
            "force": {"type": "boolean", "description": "同名时是否覆盖原来那条：不填 = 不覆盖（先提醒你已有同名）；填 true = 用这次的内容覆盖它，编号不变"},
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
