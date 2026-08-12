"""
Coco 房产工具 - 经纪人配置（品牌/公司名）
2026-08-12 加：海报品牌必须来自经纪人真实告知的公司名，禁止用默认值硬凑。
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def save_agent_brand(brand_name: str, task_id: str = None) -> str:
    """保存经纪人公司/门店品牌名（海报展示用），返回保存结果"""
    brand_name = (brand_name or '').strip()
    if not brand_name:
        return json.dumps({"success": False, "error": "品牌名称不能为空"}, ensure_ascii=False)
    db = _get_db()
    db.set_setting('brand_name', brand_name)
    return json.dumps({
        "success": True,
        "brand_name": brand_name,
        "message": f"品牌名称已保存：{brand_name}（海报将展示该名称）",
    }, ensure_ascii=False)


def get_agent_brand(task_id: str = None) -> str:
    """获取经纪人已保存的品牌名；未配置返回 None"""
    db = _get_db()
    brand = db.get_setting('brand_name')
    if not brand:
        return json.dumps({"success": False, "error": "品牌未配置，需要先询问经纪人公司名称"}, ensure_ascii=False)
    return json.dumps({"success": True, "brand_name": brand}, ensure_ascii=False)


def get_brand_or_none() -> str:
    """供海报工具内部调用：返回品牌名或空字符串（不输出 JSON）"""
    try:
        db = _get_db()
        return db.get_setting('brand_name') or ''
    except Exception:
        return ''


registry.register(
    name="save_agent_brand",
    toolset="real_estate",
    schema={"name": "save_agent_brand", "description": "保存经纪人公司/门店品牌名（用于海报等展示），经纪人明确告知公司名称后调用", "parameters": {
        "type": "object",
        "properties": {
            "brand_name": {"type": "string", "description": "公司/门店品牌名，如 宇恒房产"},
        },
        "required": ["brand_name"],
    }},
    handler=lambda args, **kw: save_agent_brand(**args),
)

registry.register(
    name="get_agent_brand",
    toolset="real_estate",
    schema={"name": "get_agent_brand", "description": "获取经纪人已保存的品牌名（生成海报前确认品牌是否已配置）", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: get_agent_brand(**args),
)
