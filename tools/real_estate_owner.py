"""
Coco 房产工具 - 房东（业主）委托管理
房东登记、名下房源组合、独家委托到期提醒
隐私原则：身份证号只存脱敏后文本，全套信息不落库
"""
import json
from datetime import datetime

from tools.registry import registry


def _get_db():
    import os
    from agent.real_estate_db import RealEstateDB
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise RuntimeError("未配置 DATABASE_URL 环境变量，拒绝初始化数据库。")
    return RealEstateDB(database_url)


def _mask_id(id_number: str) -> str:
    """身份证脱敏：保留前4后4，中间打星"""
    id_number = (id_number or '').strip()
    if len(id_number) < 8:
        return '*' * len(id_number)
    return id_number[:4] + '*' * (len(id_number) - 8) + id_number[-4:]


def _mask_phone(phone) -> str:
    """手机号脱敏（2026-08-30 老板定：业主电话脱敏展示）：保留前3后4，中间打星。

    老板决策：对外/经纪人展示业主联系方式要脱敏，与"房源公开营销、联系方式敏感"的口径一致。
    仅对展示层做脱敏，库内仍存密文（EncryptedString），不影响比对/关联。
    """
    if not phone:
        return None
    phone = str(phone).strip()
    if len(phone) < 7:
        return phone
    return phone[:3] + '*' * (len(phone) - 7) + phone[-4:]


def get_property_owners(property_ids: list = None, task_id: str = None) -> str:
    """按房源 ID 批量查询业主信息（房源→业主反向查询，最多 3 套）。

    老板实测现象：让 Coco "把这套/几套房源的业主信息给我"，Coco 只能做模糊工具搜索，
    找不到就兜底报"均未录入业主信息"。本工具补上反向能力：给房源ID → 返回该房源关联业主
    的姓名/电话(脱敏)/微信/看房方式；房源未关联业主则 owner=None，如实说明。
    """
    db = _get_db()
    if not property_ids:
        return json.dumps({"success": False, "error": "请提供房源 ID 列表（property_ids）"},
                          ensure_ascii=False)
    if not isinstance(property_ids, list):
        property_ids = [property_ids]
    if len(property_ids) > 3:
        return json.dumps({"success": False,
                           "error": "一次最多查询 3 套房源，请分批查询"},
                          ensure_ascii=False)
    rows = db.get_property_owners(property_ids)
    lines = []
    for r in rows:
        o = r.get('owner')
        if not o:
            lines.append(f"· {r['title']}（ID:{r['id']}）：未录入业主信息")
            continue
        masked_phone = _mask_phone(o.get('phone'))
        wechat = o.get('wechat')
        view = f"，看房方式: {r.get('viewing_note')}" if r.get('viewing_note') else ""
        lines.append(
            f"· {r['title']}（ID:{r['id']}）：业主 {o.get('name')}，"
            f"电话 {masked_phone or '未录'}"
            + (f"，微信 {wechat}" if wechat else "")
            + view)
    return json.dumps({
        "success": True,
        "count": len(rows),
        "properties": rows,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


def add_owner(name: str, phone: str = None, wechat: str = None,
              id_number: str = None, trust_note: str = None,
              notes: str = None, task_id: str = None) -> str:
    """登记房东（业主）。身份证号只存脱敏版本，原号不落库。"""
    name = (name or '').strip()
    if not name:
        return json.dumps({"success": False, "error": "房东姓名不能为空"}, ensure_ascii=False)
    db = _get_db()
    owner = db.add_owner(
        name=name, phone=phone, wechat=wechat,
        id_masked=_mask_id(id_number) if id_number else None,
        trust_note=trust_note, notes=notes,
    )
    privacy = "（身份证已脱敏存储，原号未落库）" if id_number else ""
    return json.dumps({
        "success": True,
        "message": f"房东 {name} 已登记{privacy}",
        "owner": owner,
    }, ensure_ascii=False)


def get_owner(owner_id: int, task_id: str = None) -> str:
    """查询房东信息"""
    db = _get_db()
    owner = db.get_owner(owner_id)
    if not owner:
        return json.dumps({"success": False, "error": "房东不存在"}, ensure_ascii=False)
    return json.dumps({"success": True, "owner": owner}, ensure_ascii=False)


def list_owners(limit: int = 50, task_id: str = None) -> str:
    """房东列表"""
    db = _get_db()
    owners = db.list_owners(limit)
    return json.dumps({"success": True, "total": len(owners), "owners": owners}, ensure_ascii=False)


def owner_portfolio(owner_id: int, task_id: str = None) -> str:
    """房东名下房源组合：房源列表 + 在售/成交统计"""
    db = _get_db()
    result = db.owner_portfolio(owner_id)
    if not result:
        return json.dumps({"success": False, "error": "房东不存在"}, ensure_ascii=False)
    stats = result["stats"]
    lines = [
        f"房东 {result['owner']['name']} 名下 {stats['total']} 套房"
        f"（在售 {stats['available']} / 已成交 {stats['dealed']}）"
    ]
    for p in result["properties"]:
        viewing = f"，看房方式: {p['viewing_note']}" if p.get("viewing_note") else ""
        lines.append(f"\n· {p['title']}（ID:{p['id']}）{p['price']/10000:.0f}万 [{p['status']}]{viewing}")
    return json.dumps({
        "success": True, **result,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


def exclusive_expiring(days: int = 30, task_id: str = None) -> str:
    """独家委托到期清单：到期是重新谈委托或谈降价的天然时机"""
    db = _get_db()
    items = db.exclusive_expiring(days)
    if not items:
        return json.dumps({"success": True,
                           "message": f"未来 {days} 天内无独家委托到期", "items": []},
                          ensure_ascii=False)
    lines = [f"📌 独家委托到期提醒（{days}天内 {len(items)} 套）"]
    for it in items:
        lines.append(f"\n· {it['title']}（ID:{it['id']}）{it['price']/10000:.0f}万 — {it['urgency']}到期")
        lines.append("  时机提示: 到期前是重新谈委托条件或建议调价的窗口")
    return json.dumps({
        "success": True, "items": items,
        "message": "\n".join(lines),
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "add_owner",
        "description": "登记房东（业主）。身份证号自动脱敏存储，原号不落库",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "房东姓名"},
                "phone": {"type": "string", "description": "手机号（加密存储）"},
                "wechat": {"type": "string", "description": "微信号（加密存储）"},
                "id_number": {"type": "string", "description": "身份证号（只存脱敏版本，原号不落库）"},
                "trust_note": {"type": "string", "description": "信任度备注（如 配合带看/价格坚挺）"},
                "notes": {"type": "string", "description": "备注"},
            },
            "required": ["name"],
        },
        "handler": lambda args, **kw: add_owner(**args),
    },
    {
        "name": "get_owner",
        "description": "查询房东信息",
        "parameters": {
            "type": "object",
            "properties": {"owner_id": {"type": "integer", "description": "房东ID"}},
            "required": ["owner_id"],
        },
        "handler": lambda args, **kw: get_owner(**args),
    },
    {
        "name": "list_owners",
        "description": "房东列表",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回条数（默认50）"}},
        },
        "handler": lambda args, **kw: list_owners(**args),
    },
    {
        "name": "owner_portfolio",
        "description": "房东名下房源组合：房源列表 + 在售/成交统计 + 看房方式",
        "parameters": {
            "type": "object",
            "properties": {"owner_id": {"type": "integer", "description": "房东ID"}},
            "required": ["owner_id"],
        },
        "handler": lambda args, **kw: owner_portfolio(**args),
    },
    {
        "name": "get_property_owners",
        "description": "按房源ID批量查业主信息（房源→业主反向查询，最多3套）。返回每套房源关联业主的姓名/电话(脱敏)/微信/看房方式；房源未关联业主则如实说明。用于经纪人问'这套/这几套房源的业主是谁/业主联系方式'",
        "parameters": {
            "type": "object",
            "properties": {"property_ids": {"type": "array", "items": {"type": "integer"},
                                            "description": "房源ID列表（最多3个）"}},
            "required": ["property_ids"],
        },
        "handler": lambda args, **kw: get_property_owners(**args),
    },
    {
        "name": "exclusive_expiring",
        "description": "独家委托到期清单：到期前是重新谈委托条件或建议调价的窗口",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "未来几天内到期（默认30）"}},
        },
        "handler": lambda args, **kw: exclusive_expiring(**args),
    },
]

for tool in TOOLS:
    registry.register(
        name=tool["name"],
        toolset="real_estate",
        schema={"name": tool["name"], "description": tool["description"], "parameters": tool["parameters"]},
        handler=tool["handler"],
    )
