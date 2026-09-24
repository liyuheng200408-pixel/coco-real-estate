"""
Coco 房产工具 - 房东（业主）委托管理
房东登记、名下房源组合、独家委托到期提醒
隐私原则：身份证号只存脱敏后文本，全套信息不落库
"""
import json
from datetime import datetime

from agent.real_estate_input import norm_id, norm_phone
from tools.real_estate_property import _STATUS_LABELS, _fmt_price
from tools.registry import registry


def _get_db():
    import os
    from agent.real_estate_db import RealEstateDB
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise RuntimeError("未配置 DATABASE_URL 环境变量，拒绝初始化数据库。")
    return RealEstateDB(database_url)


def _safe_contact(value):
    """联系方式展示：空 → None；疑似密钥不一致的密文 → 可读提示（绝不把乱码丢给经纪人）"""
    if not value:
        return None
    from agent.real_estate_db import KEY_MISMATCH_HINT, looks_like_ciphertext
    return KEY_MISMATCH_HINT if looks_like_ciphertext(value) else value


OWNER_KEY_MISMATCH_WARNING = (
    "房东联系方式读不出来：库里的加密内容用当前密钥解不开"
    "（常见于换了机器、或恢复备份时没带上密钥文件）。先用备份里的密钥文件恢复，"
    "在此之前不要把这条联系方式给客户。")


def _mask_owner_contacts(row):
    """把房东行里的联系方式做展示防御，返回 (row, 被掩码的字段列表)。

    密钥不一致时 EncryptedString 会把密文原样返回 —— 所有会把房东数据交给上层的路径都要过这里
    （2026-09-25 加：原先读路径直接把 gAAAA… 当电话交出去，get_property_owners 是唯一做了的）。
    """
    masked = []
    for key in ("phone", "wechat"):
        before = row.get(key)
        if before is None:
            continue
        after = _safe_contact(before)
        if after != before:
            masked.append(key)
        row[key] = after
    return row, masked


def _attach_key_warning(payload, masked):
    """命中密文时给返回体补 warning 与 cipher_fields（让 Coco 如实转述，不静默）"""
    if masked:
        payload["warning_key_mismatch"] = OWNER_KEY_MISMATCH_WARNING
        payload["cipher_fields"] = sorted(set(masked))
    return payload


def _mask_id(id_number: str) -> str:
    """身份证脱敏：保留前4后4，中间打星"""
    id_number = (id_number or '').strip()
    if len(id_number) < 8:
        return '*' * len(id_number)
    return id_number[:4] + '*' * (len(id_number) - 8) + id_number[-4:]


# re_owners 的列宽：PostgreSQL 上 varchar 超长会让整次登记失败（sqlite 不拦），入库前按列宽截断
NAME_MAX = 100
TRUST_NOTE_MAX = 200
# 列表分页口径（与客户侧 list_customers 同一套：默认 50、上限 200、≤0 与非数字按默认）
_LIST_LIMIT_DEFAULT = 50
_LIST_LIMIT_MAX = 200


def _clamp_limit(value, default=_LIST_LIMIT_DEFAULT, maximum=_LIST_LIMIT_MAX):
    """条数归一 → 正整数：非数字/≤0 按默认、超过上限按上限（与客户侧 list_customers 同一套口径）"""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


def _clip(value, max_len):
    """按列宽截断文本 → (截断后的值, 提示或 None)。截断必须告知，不静默丢内容"""
    if not isinstance(value, str) or len(value) <= max_len:
        return value, None
    return value[:max_len], f"超过 {max_len} 字，只保留了前 {max_len} 字"


def _clean_text(value):
    """文本参数去首尾空白；空串按"未填"（None），避免库里空串与未填两种形态并存"""
    if value is None:
        return None
    return str(value).strip() or None


def add_owner(name: str, phone: str = None, wechat: str = None,
              id_number: str = None, trust_note: str = None,
              notes: str = None, force: bool = False, task_id: str = None) -> str:
    """登记房东（业主）。身份证号只存脱敏版本，原号不落库。

    登记前按手机号查重（没给手机号时按微信号），命中给出已有房东、不重复建档；
    确认是另一个人（或同一个人的另一个号）时用 force=True 跳过查重。
    姓名不参与判重：同名不同号是两个人，都要能建。
    """
    name = (name or '').strip()
    if not name:
        return json.dumps({"success": False, "error": "房东姓名不能为空"}, ensure_ascii=False)
    warnings = []
    name, _clipped = _clip(name, NAME_MAX)
    if _clipped:
        warnings.append("房东姓名" + _clipped + "。")
    trust_note, _clipped = _clip(_clean_text(trust_note), TRUST_NOTE_MAX)
    if _clipped:
        warnings.append("信任度备注" + _clipped + "（其余内容可放进备注里）。")
    phone = norm_phone(phone)
    wechat = _clean_text(wechat)
    notes = _clean_text(notes)
    db = _get_db()

    if not force and (phone or wechat):
        dup, warn = db.find_duplicate_owner(phone=phone, wechat=wechat)
        if warn:
            # 密钥不一致防御：不强行判重，提示先检查密钥
            return json.dumps({
                "success": False, "duplicate": False, "warning": warn,
                "error": "检测到房东字段可能因密钥不一致无法安全判重，请先检查 COCO_ENC_KEY 再操作。",
            }, ensure_ascii=False)
        if dup:
            identical = (dup.get('name') == name
                         and all(_clean_text(dup.get(k)) == v for k, v in
                                 (('phone', phone), ('wechat', wechat),
                                  ('trust_note', trust_note), ('notes', notes)) if v is not None))
            tail = ("同号同名，不用重复登记。" if identical else
                    "如果其实是另一个人（或同一个人的另一个号），用 force=true 再登记一次。")
            return json.dumps({
                "success": False, "duplicate": True, "identical": identical,
                "existing_owner": dup,
                "error": (f"该房东已在库里（id={dup.get('id')} {dup.get('name')}，"
                          f"电话 {_safe_contact(dup.get('phone')) or '未填'}）。" + tail),
            }, ensure_ascii=False)

    owner = db.add_owner(
        name=name, phone=phone, wechat=wechat,
        id_masked=_mask_id(id_number) if id_number else None,
        trust_note=trust_note, notes=notes,
    )
    privacy = "（身份证已脱敏存储，原号未落库）" if id_number else ""
    payload = {"success": True, "message": f"房东 {name} 已登记{privacy}", "owner": owner}
    if warnings:
        payload["warnings"] = warnings
    return json.dumps(payload, ensure_ascii=False)


def get_property_owners(property_ids: list = None, task_id: str = None) -> str:
    """按房源 ID 批量查询业主信息（房源→业主反向查询，最多 3 套）。

    老板实测现象：让 Coco "把这套/几套房源的业主信息给我"，Coco 只能做模糊工具搜索，
    找不到就兜底报"均未录入业主信息"。本工具补上反向能力：给房源ID → 返回该房源关联业主
    的姓名/电话/微信/看房方式；房源未关联业主则 owner=None，如实说明。
    联系方式给完整号码（经纪人本人是唯一接收方，脱敏只会挡住他自己）。
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
        phone = _safe_contact(o.get('phone'))
        wechat = _safe_contact(o.get('wechat'))
        view = f"，看房方式: {r.get('viewing_note')}" if r.get('viewing_note') else ""
        lines.append(
            f"· {r['title']}（ID:{r['id']}）：业主 {o.get('name')}，"
            f"电话 {phone or '未录'}"
            + (f"，微信 {wechat}" if wechat else "")
            + view)
    payload = {
        "success": True,
        "count": len(rows),
        "properties": rows,
        "message": "\n".join(lines),
    }
    if any('读取失败' in ln for ln in lines):
        payload["warning_key_mismatch"] = ("有业主的联系方式读不出来：库里的加密内容用当前密钥解不开"
                                           "（常见于换了机器、或恢复备份时没带上密钥文件）。"
                                           "先用备份里的密钥文件恢复，在此之前不要把这条联系方式给客户。")
    return json.dumps(payload, ensure_ascii=False)


def find_person_by_name(name: str = None, task_id: str = None) -> str:
    """按姓名同时查客户和业主（两边都给），电话/微信给完整号码。

    老板实测：问"某人详细信息"（如"欧阳先生"），Coco 默认只查客户，找不到就报"库内无此客户"，
    实际对方可能是业主（房东）。本工具一次覆盖 客户(买家/租客) + 业主(房源主人)两类，
    按姓名模糊匹配，找到哪类报哪类；同名两边都有则分别列出。
    """
    db = _get_db()
    if not (name or '').strip():
        return json.dumps({"success": False, "error": "请提供要查询的姓名（name）"},
                          ensure_ascii=False)
    result = db.find_person_by_name(name)
    customers = result.get('customers', [])
    owners = result.get('owners', [])
    lines = [f"按姓名「{name}」检索到 客户 {len(customers)} 人 / 业主 {len(owners)} 人："]
    for c in customers:
        phone = _safe_contact(c.get('phone'))
        _wechat_c = _safe_contact(c.get('wechat'))
        lines.append(f"\n【客户】{c.get('name')}（ID:{c.get('id')}）"
                     f"电话 {phone or '未录'} | 微信 {_wechat_c or '未录'} | 等级 {c.get('tier') or '-'} | "
                     f"类型 {c.get('customer_type') or '-'} | 预算 {'-'.join(filter(None,[str(c.get('budget_min') or ''),str(c.get('budget_max') or '')])) or '-'}万 | "
                     f"意向 {c.get('location') or '-'} {c.get('layout_pref') or ''}")
    for o in owners:
        phone = _safe_contact(o.get('phone'))
        wechat = _safe_contact(o.get('wechat'))
        lines.append(f"\n【业主】{o.get('name')}（ID:{o.get('id')}）"
                     f"电话 {phone or '未录'} | 微信 {wechat or '未录'} | "
                     f"脱敏证件 {o.get('id_masked') or '-'} | 信任度 {o.get('trust_note') or '-'}")
    if not customers and not owners:
        lines.append("\n客户表和业主表均无此人。可能未登记；如需新建客户请提供电话及需求，业主可先登记。")
    return json.dumps({
        "success": True,
        "name": name,
        "customers": customers,
        "owners": owners,
        "count_customers": len(customers),
        "count_owners": len(owners),
        "message": "\n".join(lines),
    }, ensure_ascii=False)


def get_owner(owner_id: int, task_id: str = None) -> str:
    """查询房东详情"""
    oid, problem = norm_id(owner_id, '房东编号', '，可在房东列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem + "。"}, ensure_ascii=False)
    db = _get_db()
    owner = db.get_owner(oid)
    if not owner:
        return json.dumps({"success": False, "error": "房东不存在"}, ensure_ascii=False)
    # 联系方式展示防御（2026-09-25 加，与客户详情 F46 同口径）：密钥不一致时读出来是密文，
    # 绝不能把 gAAAA… 当房东电话说给经纪人，也不能默默咽掉（给 warning 让 Coco 如实转述）。
    owner, masked = _mask_owner_contacts(owner)
    return json.dumps(_attach_key_warning({"success": True, "owner": owner}, masked),
                      ensure_ascii=False)


def list_owners(limit: int = 50, task_id: str = None) -> str:
    """房东列表（默认最新登记优先）

    limit: 返回条数（默认 50，最多 200；传 0/负数/非数字按默认 50 处理）。
    返回 count=本次条数、total=房东总数、truncated=是否被截断（被截断时给一句说明）。
    """
    limit = _clamp_limit(limit)
    db = _get_db()
    owners, total = db.list_owners(limit=limit, with_total=True)
    # 联系方式展示防御（2026-09-25 加，与 get_owner / 客户列表 F53 同口径）
    masked_fields = []
    for row in owners:
        _, row_masked = _mask_owner_contacts(row)
        masked_fields.extend(row_masked)
    payload = {"success": True, "owners": owners, "count": len(owners), "total": total,
               "truncated": bool(total > len(owners))}
    if payload["truncated"]:
        payload["message"] = (f"共 {total} 位房东，本次返回 {len(owners)} 位（最新登记优先）。"
                              f"要看得更全就把 limit 调大（最多 {_LIST_LIMIT_MAX}）")
    return json.dumps(_attach_key_warning(payload, masked_fields), ensure_ascii=False)


def owner_portfolio(owner_id: int, limit: int = None, task_id: str = None) -> str:
    """房东名下房源组合：房源明细（默认最新登记优先）+ 在售/成交统计（统计按名下全部房源算）

    limit: 返回条数（默认 50，最多 200；传 0/负数/非数字按默认 50）。
    """
    oid, problem = norm_id(owner_id, '房东编号', '，可在房东列表里查')
    if problem:
        return json.dumps({"success": False, "error": problem + "。"}, ensure_ascii=False)
    limit = _clamp_limit(limit)
    db = _get_db()
    result = db.owner_portfolio(oid, limit=limit)
    if not result:
        return json.dumps({"success": False, "error": "房东不存在"}, ensure_ascii=False)
    # 联系方式展示防御（2026-09-25 加，与 get_owner / list_owners 同口径）
    result['owner'], masked = _mask_owner_contacts(result['owner'])
    stats = result['stats']
    shown = result['properties']
    truncated = stats['total'] > len(shown)
    if stats['total']:
        lines = [f"房东 {result['owner']['name']} 名下 {stats['total']} 套房"
                 f"（在售 {stats['available']} / 已成交 {stats['dealed']}）"]
    else:
        lines = [f"房东 {result['owner']['name']} 名下暂无房源"]
    if truncated:
        lines.append(f"共 {stats['total']} 套房源，这里列出最新登记的 {len(shown)} 套（最新登记优先）。"
                     f"要看得更全就把 limit 调大（最多 {_LIST_LIMIT_MAX}）")
    for p in shown:
        # 展示口径复用房源侧：_fmt_price（出租 → 元/月）/ _STATUS_LABELS（在售/已售/已租）
        viewing = f"，看房方式: {p['viewing_note']}" if p.get("viewing_note") else ""
        status = _STATUS_LABELS.get(p.get('status'), p.get('status') or '未录入')
        lines.append(f"\n· {p['title']}（ID:{p['id']}）{_fmt_price(p)} [{status}]{viewing}")
    payload = {
        "success": True, **result,
        "count": len(shown), "truncated": truncated,
        "message": "\n".join(lines),
    }
    return json.dumps(_attach_key_warning(payload, masked), ensure_ascii=False)


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
        "description": "登记房东（业主）。可登记姓名、手机号、微信号、身份证号（自动脱敏存储，原号不落库）、信任度备注、备注。登记前按手机号查重，号已在库里会提示已有房东、不重复建档（确认是另一个人时用 force=true）。手机号写法不限（138 0013 8000 / +86 138-0013-8000 都会归一）",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "房东姓名"},
                "phone": {"type": "string", "description": "手机号（加密存储，写法不限，会自动归一）"},
                "wechat": {"type": "string", "description": "微信号（加密存储）"},
                "id_number": {"type": "string", "description": "身份证号（只存脱敏版本，原号不落库）"},
                "trust_note": {"type": "string", "description": "信任度备注（如 配合带看/价格坚挺，最多 200 字）"},
                "notes": {"type": "string", "description": "备注"},
                "force": {"type": "boolean", "description": "默认 false。true=跳过房东查重强制新增（同一个人的另一个号、或确认是另一个人时用）"},
            },
            "required": ["name"],
        },
        "handler": lambda args, **kw: add_owner(**args),
    },
    {
        "name": "get_owner",
        "description": "查房东详情：姓名、手机号、微信号、脱敏身份证号、信任度备注、备注、登记时间；联系方式给完整号码（经纪人本人是唯一接收方）。房东不存在或编号写错会如实说明。用于经纪人问\"这位房东的详细资料/电话号码\"",
        "parameters": {
            "type": "object",
            "properties": {"owner_id": {"type": "integer", "description": "房东ID（数字，如 12；不确定就先列房东列表查）"}},
            "required": ["owner_id"],
        },
        "handler": lambda args, **kw: get_owner(**args),
    },
    {
        "name": "list_owners",
        "description": "房东列表（默认最新登记优先）：姓名、手机号、微信号、脱敏身份证号、信任度备注、备注、登记时间；联系方式给完整号码。返回 count=本次条数、total=房东总数、truncated=是否被截断。用于经纪人问\"有哪些房东/给我房东名单\"",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回条数（默认 50，最多 200；传 0/负数/非数字按默认 50）"}},
        },
        "handler": lambda args, **kw: list_owners(**args),
    },
    {
        "name": "owner_portfolio",
        "description": "房东名下房源组合（默认最新登记优先）：名下房源明细（标题/价格/状态/看房方式，出租按月租说）+ 在售·成交统计（统计按名下全部房源算）。房东不存在或编号写错会如实说明。用于经纪人问\"这位房东名下有哪些房/在售几套\"",
        "parameters": {
            "type": "object",
            "properties": {
                "owner_id": {"type": "integer", "description": "房东ID（数字，如 12；不确定就先列房东列表查）"},
                "limit": {"type": "integer", "description": "返回条数（默认 50，最多 200；传 0/负数/非数字按默认 50）—— 统计数字始终按名下全部房源计算"},
            },
            "required": ["owner_id"],
        },
        "handler": lambda args, **kw: owner_portfolio(**args),
    },
    {
        "name": "get_property_owners",
        "description": "按房源ID批量查业主信息（房源→业主反向查询，最多3套）。返回每套房源关联业主的姓名/电话（完整号码）/微信/看房方式；房源未关联业主则如实说明。用于经纪人问'这套/这几套房源的业主是谁/业主联系方式'",
        "parameters": {
            "type": "object",
            "properties": {"property_ids": {"type": "array", "items": {"type": "integer"},
                                            "description": "房源ID列表（最多3个）"}},
            "required": ["property_ids"],
        },
        "handler": lambda args, **kw: get_property_owners(**args),
    },
    {
        "name": "find_person_by_name",
        "description": "按姓名同时查客户和业主（两边都给），电话/微信给完整号码。用于经纪人问'某人/某先生/某女士的详细信息'（对方可能是客户=买家租客，也可能是业主=房东），按姓名模糊匹配，找到哪类报哪类，同名两边都有则分别列出；两表都无则如实说明。严禁用psql直接连库",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "姓名（支持模糊匹配，子串命中即返回）"}},
            "required": ["name"],
        },
        "handler": lambda args, **kw: find_person_by_name(**args),
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
