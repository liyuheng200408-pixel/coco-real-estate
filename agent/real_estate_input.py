"""
房产助理 - 录入写法归一

模型常把经纪人的原话直接传下来（价格「185万」「一百五十万」、手机号「139 1111 2222」、
客户类型「买二手房」），统一在这里换算成系统口径；认不出返回 None，由调用方给中文提示，
**绝不静默存错**。
"""
import re
from datetime import datetime

# ==================== 金额 ====================

_CN_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
              '六': 6, '七': 7, '八': 8, '九': 9}
_CN_UNITS = {'十': 10, '百': 100, '千': 1000, '万': 10000, '亿': 100000000}


def cn_number(text):
    """把「一百五十」「三千二」这类中文数字转成数值；认不出返回 None"""
    total = section = number = 0
    seen = False
    for ch in text:
        if ch in _CN_DIGITS:
            number = _CN_DIGITS[ch]
            seen = True
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            seen = True
            if unit >= 10000:
                section = (section + number) * unit
                total += section
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            return None
    return (total + section + number) if seen else None


def norm_money(value):
    """把「185万 / 一百五十万 / 1,850,000 元 / 2200」这类写法换算成元（int）；认不出返回 None。

    只清"价格尾巴"；单价类写法（3000/平米）不允许被当成总价，宁可认不出让模型回头问。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(',', '').replace('，', '').replace(' ', '')
    for junk in ('人民币', '元整', '元', '万整', '块', '¥', '￥', '/月', '／月', '每月', '/套'):
        text = text.replace(junk, '')
    if not text:
        return None
    multiplier = 1
    if '亿' in text:
        multiplier, text = 100000000, text.replace('亿', '')
    elif '万' in text:
        multiplier, text = 10000, text.replace('万', '')
    try:
        num = float(text)
    except ValueError:
        num = cn_number(text)
        if num is None:
            return None
    return int(round(num * multiplier))


# ==================== 手机号 ====================

def norm_phone(value):
    """手机号写法归一：去空格/横线/括号/点、去 +86 与 0086 前缀。

    归一只为"认出同一个人"，改不了写法时退回去掉首尾空白的原值（手机号不是必填，
    认不出也不该拦住建档）。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace('＋', '+').replace('－', '-').replace('　', '')
    text = re.sub(r'[\s\-()（）\.]', '', text)
    if text.startswith('+86'):
        text = text[3:]
    elif text.startswith('0086'):
        text = text[4:]
    elif len(text) == 13 and text.startswith('86'):
        text = text[2:]
    return text


# ==================== 客户类型 / 等级 ====================

CUSTOMER_TYPES = ("buy_new", "buy_second_hand", "rent")
# 未细分（经纪人没说买新房还是买二手房）：匹配时不限类型，但必须能在筛选中被找到
CUSTOMER_TYPE_UNSPECIFIED = "unspecified"

_CUSTOMER_TYPE_ALIASES = {
    "buy_new": "buy_new", "buynew": "buy_new", "new": "buy_new",
    "一手房": "buy_new", "新房": "buy_new", "买一手": "buy_new", "买一手房": "buy_new", "买新房": "buy_new",
    "buy_second_hand": "buy_second_hand", "buysecondhand": "buy_second_hand",
    "buy_secondhand": "buy_second_hand", "second_hand": "buy_second_hand", "secondhand": "buy_second_hand",
    "二手房": "buy_second_hand", "买二手": "buy_second_hand", "买二手房": "buy_second_hand",
    "rent": "rent", "rental": "rent", "租房": "rent", "租": "rent", "出租": "rent",
    "unspecified": CUSTOMER_TYPE_UNSPECIFIED, "unknown": CUSTOMER_TYPE_UNSPECIFIED,
    "buy": CUSTOMER_TYPE_UNSPECIFIED, "未细分": CUSTOMER_TYPE_UNSPECIFIED, "不限": CUSTOMER_TYPE_UNSPECIFIED,
}


def norm_customer_type(value):
    """客户类型归一 → (规范值或 None, 是否认得)。

    未传/未细分 → CUSTOMER_TYPE_UNSPECIFIED（不猜成"买二手房"，也不留空字符串）。
    """
    if value is None:
        return CUSTOMER_TYPE_UNSPECIFIED, True
    if not isinstance(value, str):
        return None, False
    key = value.strip().lower().replace('-', '_').replace(' ', '')
    if key in _CUSTOMER_TYPE_ALIASES:
        return _CUSTOMER_TYPE_ALIASES[key], True
    return None, False


def customer_type_filter(value):
    """筛选口径 → 库内应匹配的取值集合（含历史值）；值非法返回 None。

    历史遗留：早期默认值是 'buy'、空字符串也有落库过，都归到"未细分"这一档，
    否则这些客户按类型筛就永远找不到（等于凭空消失）。
    """
    canonical, ok = norm_customer_type(value)
    if not ok:
        return None
    if canonical == CUSTOMER_TYPE_UNSPECIFIED:
        return (CUSTOMER_TYPE_UNSPECIFIED, "buy", "", None)
    return (canonical,)


TIERS = ("S", "A", "B", "C")

# ==================== 客户生命周期阶段 ====================

STAGES = ("lead", "interested", "strong", "viewed", "negotiating", "dealing", "maintain", "lost")
STAGE_LABELS = {
    "lead": "潜在", "interested": "意向", "strong": "强意向", "viewed": "已看房",
    "negotiating": "谈判", "dealing": "成交中", "maintain": "售后维护", "lost": "流失",
}
_STAGE_ALIASES = {label: key for key, label in STAGE_LABELS.items()}


def norm_stage(value):
    """客户阶段归一 → (规范值或 None, 是否认得)。

    接受英文键（大小写/空格不敏感）与中文说法（潜在/意向/强意向/已看房/谈判/成交中/售后维护/流失）。
    """
    if value is None:
        return None, True
    if not isinstance(value, str):
        return None, False
    key = value.strip().lower()
    if key in STAGES:
        return key, True
    alias = _STAGE_ALIASES.get(value.strip())
    return (alias, True) if alias else (None, False)


def stage_options_text():
    """给上层看的可用阶段（中文名 + 英文键），用于提示语"""
    return " / ".join(f"{STAGE_LABELS[k]}({k})" for k in STAGES)


def norm_tier(value):
    """客户等级归一 → (规范值或 None, 是否认得)"""
    if value is None:
        return None, True
    if not isinstance(value, str):
        return None, False
    key = value.strip().upper()
    return (key, True) if key in TIERS else (None, False)


# ==================== 生日 ====================

def norm_birthday(value):
    """生日归一 → (规范值或 None, 是否认得)。

    接受 YYYY-MM-DD / YYYY/M/D / MM-DD / M-D / M月D日；统一存成 YYYY-MM-DD 或 MM-DD。
    认不出返回 (None, False) —— 生日提醒只认这两种写法，乱值入库会让提醒静默漏人。
    """
    if value is None:
        return None, True
    if not isinstance(value, str):
        return None, False
    text = value.strip().replace('/', '-').replace('.', '-').replace('年', '-').replace('月', '-').replace('日', '')
    text = re.sub(r'\s', '', text)
    parts = [p for p in text.split('-') if p != '']
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None, False
    if len(nums) == 3:
        year, month, day = nums
        if not (1900 <= year <= 2100):
            return None, False
    elif len(nums) == 2:
        month, day = nums
        year = None
    else:
        return None, False
    try:
        datetime(year or 2000, month, day)
    except ValueError:
        return None, False
    return (f"{year:04d}-{month:02d}-{day:02d}" if year else f"{month:02d}-{day:02d}"), True


def birthday_matches_month_day(stored, month=None, day=None):
    """判断库里存的生日（YYYY-MM-DD 或 MM-DD）是否落在给定月/日上"""
    if not isinstance(stored, str):
        return False
    parts = stored.strip().split('-')
    try:
        if len(parts) == 3:
            return (month is None or int(parts[1]) == month) and (day is None or int(parts[2]) == day)
        if len(parts) == 2:
            return (month is None or int(parts[0]) == month) and (day is None or int(parts[1]) == day)
    except ValueError:
        return False
    return False


# ==================== 条数（limit） ====================

def clamp_limit(value, default, maximum=200):
    """条数归一 → 正整数：非数字/≤0 按**该工具自己的默认值**、超过上限按上限。

    口径（老板 2026-09-24 定，契约 5）：`limit` 传 0/负数/非数字一律按默认，
    **负数绝不能变成"拉全量"**（列表类工具最容易把上下文撑爆）。默认值各工具不同
    （客户列表 20、房东列表 50、竞品对比 5…），所以默认值由调用方传入。
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


# ==================== 编号 ====================

def norm_id(value, label="编号", hint=""):
    """编号写法归一 → (整数或 None, 提示或 None)。

    上层把编号传成文本/布尔时（`"12"`、`true`、`abc`），宁可给一句中文提示，
    也不要静默走到"对象不存在"：编号形态认不出 ≠ 库里没有这条记录（2026-09-25 加）。
    框架层已经拦掉整数参数收到 bool/数字串的形态，这里给"以编号为入口"的工具兜底，
    并让提示说清"编号是数字"。
    """
    if isinstance(value, bool):
        return None, f"{label}没能识别：收到的是 {'true' if value else 'false'}。{label}是数字（如 12）{hint}"
    if isinstance(value, int):
        return value, None
    text = str(value).strip()
    if text.lstrip('+').isdigit():
        return int(text), None
    return None, f"{label}没能识别：收到的是「{value}」。{label}是数字（如 12）{hint}"


# ==================== 日期 ====================

def norm_date(value, label="日期"):
    """日期归一 → (datetime 或 None, 提示或 None)。

    接受 `2026-12-31` / `2026/12/31` / `2026.12.31` / `2026年12月31日`；
    只有月日（`12月31日` / `12-31`）时按**当年**算，若当年那天已过按**次年**（到期日总是指未来）。
    认不出返回 (None, 中文提示) —— 不猜、也不静默存错。
    """
    from datetime import datetime as _dt
    if value is None:
        return None, None
    if isinstance(value, _dt):
        return value, None
    text = str(value).strip()
    if not text:
        return None, None
    text = (text.replace('年', '-').replace('月', '-').replace('日', '')
                .replace('/', '-').replace('.', '-'))
    parts = [p for p in text.split('-') if p != '']
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None, f"{label}没能识别：收到的是「{value}」。请用 2026-12-31 这类写法"
    try:
        if len(nums) == 3:
            return _dt(nums[0], nums[1], nums[2]), None
        if len(nums) == 2:
            month, day = nums
            year = _dt.now().year
            candidate = _dt(year, month, day)
            if candidate.date() < _dt.now().date():
                candidate = _dt(year + 1, month, day)
            return candidate, None
    except ValueError:
        return None, f"{label}没能识别：收到的是「{value}」。请用 2026-12-31 这类写法"
    return None, f"{label}没能识别：收到的是「{value}」。请用 2026-12-31 这类写法"


# ==================== 客户标签 ====================

TAG_MAX_LEN = 20
_TAG_SEPARATORS = re.compile(r"[,，、;；/／|｜]+")


def norm_tags(value, max_len=TAG_MAX_LEN):
    """标签写法归一 → (标签列表, 问题说明或 None)。

    规则（2026-09-24 加，标签三件套共用）：
    - 去首尾空白（含全角空格）；
    - 按中英文逗号/顿号/分号/斜杠/竖线**拆成多个标签** —— 存储层用逗号分隔，含逗号的标签本身不合法；
    - 丢掉空元素、按出现顺序去重；
    - 单个标签超过 max_len 个字 → 拒绝（不截断，避免造出一个用户没说的标签）。
    """
    if value is None:
        return [], "标签不能为空"
    text = str(value).replace("\u3000", " ").strip()
    if not text:
        return [], "标签不能为空"
    tags, seen = [], set()
    for part in _TAG_SEPARATORS.split(text):
        tag = part.strip()
        if not tag:
            continue
        if len(tag) > max_len:
            return [], f"标签「{tag[:12]}…」太长了（每个标签最多 {max_len} 个字）"
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    if not tags:
        return [], "标签不能为空"
    return tags, None


def clean_tags(value):
    """把库里存的标签串读成干净的列表（去空元素/去首尾空白/去重，不改动库存值）。

    用**与写入侧同一套分隔符**拆分：存量数据里可能有 "A, A"、"A,,"、"学区房，地铁房"（全角）、
    "急售、钥匙在我这"（顿号）这些没归一的写法 —— 读路径统一兜住，否则整串会被当成"一个标签"，
    按标签筛选会漏、删也删不掉（2026-09-24 修：写入侧归一了、读取侧漏了）。
    """
    if not value:
        return []
    out, seen = [], set()
    for part in _TAG_SEPARATORS.split(str(value)):
        tag = part.strip()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out
