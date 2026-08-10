"""
Coco 房产工具 - 房源图片管理
"""
import json
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def add_property_images(property_id: int, images: str, task_id: str = None) -> str:
    """为房源添加图片（多个用逗号分隔）"""
    db = _get_db()
    properties = db.search_properties()
    p = None
    for item in properties:
        if item.get('id') == property_id:
            p = item
            break
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)
    existing = (p.get('images') or '').strip()
    new_images = [img.strip() for img in images.split(',') if img.strip()]
    merged = []
    if existing:
        merged.extend([x.strip() for x in existing.split(',') if x.strip()])
    for img in new_images:
        if img not in merged:
            merged.append(img)
    result = db.update_property(property_id, images=','.join(merged))
    return json.dumps({
        "success": True, "property": result,
        "message": f"已添加 {len(new_images)} 张图片，共 {len(merged)} 张"
    }, ensure_ascii=False)


def list_property_images(property_id: int, task_id: str = None) -> str:
    """查看房源图片列表"""
    db = _get_db()
    properties = db.search_properties()
    p = None
    for item in properties:
        if item.get('id') == property_id:
            p = item
            break
    if p is None:
        return json.dumps({"success": False, "error": "房源不存在或不在售"}, ensure_ascii=False)
    images = [x.strip() for x in (p.get('images') or '').split(',') if x.strip()]
    return json.dumps({"success": True, "property_id": property_id, "images": images, "count": len(images)}, ensure_ascii=False)


registry.register(
    name="add_property_images",
    toolset="real_estate",
    schema={"name": "add_property_images", "description": "为房源添加图片（多个用逗号分隔）", "parameters": {
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "房源ID"},
            "images": {"type": "string", "description": "图片URL或路径，多个用逗号分隔"},
        },
        "required": ["property_id", "images"],
    }},
    handler=lambda args, **kw: add_property_images(**args),
)

registry.register(
    name="list_property_images",
    toolset="real_estate",
    schema={"name": "list_property_images", "description": "查看房源图片列表", "parameters": {
        "type": "object",
        "properties": {"property_id": {"type": "integer", "description": "房源ID"}},
        "required": ["property_id"],
    }},
    handler=lambda args, **kw: list_property_images(**args),
)
