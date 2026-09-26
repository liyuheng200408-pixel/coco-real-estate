"""
Coco 房产工具 - 数据分析
业绩看板、渠道统计、市场简报
"""
import json
from datetime import datetime, timedelta

from agent.real_estate_period import norm_period, period_window
from tools.registry import registry

# 业绩看板的四个档（口径与经营报告同一处：`agent/real_estate_period.py` 的滚动窗口）
_DASH_PERIOD_ALLOWED = ("week", "month", "quarter", "year")
_DASH_PERIOD_NAMES = {"week": "本周", "month": "本月", "quarter": "本季度", "year": "今年"}
_DASH_PERIOD_HINT = "周期只认「本周」「本月」「本季度」「今年」（也可以说 近 7 天 / 近 30 天 / 近 90 天 / 近 365 天）"
OVERDUE_SHOW = 5        # 看板里最多列 5 位逾期客户，超出要说清共几位


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def performance_dashboard(
    period: str = "month",
    task_id: str = None,
) -> str:
    """业绩看板：客户/房源的时点数据 + 本期（近 N 天）进展 + 逾期跟进

    2026-09-26 改（F346–F349）：`period` 此前**只被原样回显**、数字全是累计值（传 week 与传 year
    的结果一模一样），经纪人传「本季度」会以为拿到季度业绩 → 现在四个档**真的统计**
    （滚动窗口：近 7 / 30 / 90 / 365 天，口径在 `agent/real_estate_period.py` 一处），
    并在 `本周期` 里写明区间；逾期客户给**客户名与等级**、只列最急的 5 位并说清共几位；
    空库给空态说法；补一句中文 `message`（键名沿用中文，见 HANDOFF 第 35 条「能中文就中文」）。
    """
    key, hint = norm_period(period, allowed=_DASH_PERIOD_ALLOWED, hint=_DASH_PERIOD_HINT)
    if hint:
        return json.dumps({"success": False, "error": hint}, ensure_ascii=False)
    period_name = _DASH_PERIOD_NAMES[key]
    start, range_text, span_label = period_window(key)

    db = _get_db()
    stats = db.get_stats()

    # 获取各等级客户数
    tier_counts = stats.get('tier_counts', {})

    # 获取逾期跟进（每客户只看最新一条人为跟进是否过期；本工具只读，不降级）
    overdue = db.get_overdue()
    labels = db.get_customer_labels([f.get('customer_id') for f in overdue])

    warnings = []
    try:
        period_stats = db.period_stats(start)
    except Exception as exc:
        period_stats = {}
        warnings.append(f"本期数据这次没取到（{type(exc).__name__}）")

    total_customers = stats.get('total_customers', 0)
    closed_customers = stats.get('closed_customers', 0)
    no_customers = total_customers + closed_customers == 0

    shown = overdue[:OVERDUE_SHOW]
    overdue_rows = []
    for f in shown:
        cid = f.get('customer_id')
        label = labels.get(cid) or {}
        who = label.get('name') or f"已删除客户（id={cid}）"
        tier = f"{label.get('tier')}级" if label.get('tier') else ''
        overdue_rows.append(f"{who}（{tier}）" if tier else who)

    result = {
        "统计周期": period_name,
        "本周期": f"{span_label}（{range_text}）",
        "客户总数": total_customers,
        "各等级客户": {
            "S级（高意向）": tier_counts.get('S', 0),
            "A级（有需求）": tier_counts.get('A', 0),
            "B级（培养中）": tier_counts.get('B', 0),
            "C级（初步接触）": tier_counts.get('C', 0),
        },
        "在售房源": stats.get('available_properties', 0),
        "逾期跟进": len(overdue),
        "逾期客户": overdue_rows,
    }
    if period_stats:
        result["本期新增客户"] = period_stats.get('new_customers', 0)
        result["本期新增房源"] = period_stats.get('new_properties', 0)
        result["本期完成带看"] = period_stats.get('viewings_done', 0)
        result["本期新开成交单"] = period_stats.get('new_deals', 0)

    # 给经纪人看的那句话：全中文，替他把口径与"这里只列了几位"说清
    if no_customers:
        result["说明"] = "库里还没有客户，先登记客户再看数据"
        message = "库里还没有客户，先登记客户再看数据"
    else:
        parts = [f"{period_name}（{span_label}：{range_text}）",
                 f"在跟客户 {total_customers} 位（S级 {tier_counts.get('S', 0)} / "
                 f"A级 {tier_counts.get('A', 0)} / B级 {tier_counts.get('B', 0)} / "
                 f"C级 {tier_counts.get('C', 0)}），在售房源 {stats.get('available_properties', 0)} 套"]
        if period_stats:
            parts.append(f"本期新增客户 {period_stats.get('new_customers', 0)} 位、"
                         f"新增房源 {period_stats.get('new_properties', 0)} 套、"
                         f"完成带看 {period_stats.get('viewings_done', 0)} 次、"
                         f"新开成交单 {period_stats.get('new_deals', 0)} 单")
        if not overdue:
            result["逾期客户说明"] = "暂无逾期跟进"
            parts.append("暂无逾期跟进")
        elif len(overdue) > OVERDUE_SHOW:
            result["逾期客户说明"] = f"这里列逾期最久的 {OVERDUE_SHOW} 位，共 {len(overdue)} 位"
            parts.append(f"逾期跟进 {len(overdue)} 位（这里列逾期最久的 {OVERDUE_SHOW} 位）")
        else:
            result["逾期客户说明"] = f"共 {len(overdue)} 位逾期，已全部列出"
            parts.append(f"逾期跟进 {len(overdue)} 位")
        message = "；".join(parts) + "。"

    out = {"success": True, "dashboard": result, "message": message}
    if warnings:
        out["warnings"] = warnings
        out["message"] = message + "（本期数据这次没取到，稍后我可以再试一次）"
    return json.dumps(out, ensure_ascii=False)


registry.register(
    name="performance_dashboard",
    toolset="real_estate",
    schema={"name": "performance_dashboard",
            "description": "业绩看板：客户与房源的时点数据（在跟客户、各等级、在售房源）+ 本期（近 N 天）新增客户/新增房源/完成带看/新开成交单 + 逾期跟进数与最急的几条",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["week", "month", "quarter", "year"],
                               "description": "统计周期：本周（近 7 天）/本月（近 30 天）/本季度（近 90 天）/今年（近 365 天），默认本月"},
                },
            }},
    handler=lambda args, **kw: performance_dashboard(**args),
)

def channel_stats(task_id: str = None) -> str:
    """渠道线索统计：按客户来源分组统计客户数、S/A/B/C分级、成交数、成交率

    来源为固定选项：安居客/贝壳/抖音/转介绍/门店/58/其他（未填写归入"未填写"）。
    """
    db = _get_db()
    channels = db.get_channel_stats()
    return json.dumps({
        "success": True,
        "channels": channels,
        "total_channels": len(channels),
        "message": "各渠道线索量与成交率一览，可据此判断广告投放性价比",
    }, ensure_ascii=False)


registry.register(
    name="channel_stats",
    toolset="real_estate",
    schema={"name": "channel_stats", "description": "渠道线索统计：按客户来源分组统计客户数、分级、成交数、成交率（客户数只算在跟客户，已关闭单列 closed），判断哪个渠道来客多、成交率高", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: channel_stats(**args),
)


def market_brief(city: str = None, district: str = None, task_id: str = None) -> str:
    """市场行情简报：自家真实盘况 + 联网行情（标注来源）+ 行动建议"""
    db = _get_db()
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)

    # ① 自家盘况（真实统计）
    _brief_warning = None
    try:
        with db.get_session() as s:
            from agent.real_estate_db import Property, Viewing, Deal
            new_props = s.query(Property).filter(Property.created_at >= week_ago).count()
            avail = s.query(Property).filter(Property.status == 'available').count()
            viewings_week = s.query(Viewing).filter(Viewing.viewing_time >= week_ago).count()
            deals_week = s.query(Deal).filter(Deal.created_at >= week_ago).count()
    except Exception as exc:
        # 同上：失败要标出来，不能假装是 0
        new_props = avail = viewings_week = deals_week = None
        _brief_warning = f"自家盘况统计失败（{type(exc).__name__}: {exc}），下面的数字不可信"

    conversion = f"{deals_week / viewings_week * 100:.0f}%" if viewings_week else "暂无数据"
    _d = lambda v: "统计失败" if v is None else v      # 失败时显示“统计失败”，不显示 None 也不假装 0

    own_section = [
        "一、自家盘况（系统数据）",
        f"· 本周新增房源: {_d(new_props)} 套",
        f"· 当前在售: {_d(avail)} 套",
        f"· 本周带看: {_d(viewings_week)} 次",
        f"· 本周成交: {_d(deals_week)} 单（带看转化率 {conversion}）",
    ]

    # ② 联网行情（标注来源；失败不阻塞）
    news_section = ["\n二、市场动态（来源: 网络检索，仅供参考）"]
    news_items = []
    if city:
        try:
            from hermes_tools import web_search
            query = f"{city} 楼市 最新政策 房价" + (f" {district}" if district else "")
            res = web_search(query, limit=5)
            items = (res.get("data") or {}).get("web") or []
            for it in items[:3]:
                title = (it.get("title") or "").strip()
                if title:
                    news_items.append(f"· {title}")
                    news_items.append(f"  {it.get('url', '')}")
        except Exception as e:
            news_items.append(f"· 联网检索暂不可用（{str(e)[:50]}），建议稍后重试")
    else:
        news_items.append("· 未指定城市，这次跳过联网行情（告诉我城市名就能查）")
    news_section.extend(news_items or ["· 无结果"])

    # ③ 行动建议（基于自家数据生成）
    advice = ["\n三、本周行动建议"]
    if _brief_warning:
        advice.append("· 自家盘况统计这次没取到，本周建议先按人工判断（我稍后再试一次）")
    elif deals_week == 0 and viewings_week > 0:
        advice.append("· 有带看无成交：回访本周带看客户，优先推进最接近成交的")
    if avail is not None and avail < 10:
        advice.append("· 在售房源偏少：联系房东补盘，优先谈委托快到期的房东续期")
    high = db.churn_risk_customers(min_risk=60)
    if high:
        advice.append(f"· {len(high)} 位客户流失风险高危，建议优先挽回（要我拉名单就说一声）")
    if len(advice) == 1:
        advice.append("· 节奏健康，按日常跟进计划执行即可")

    report = "\n".join(own_section + news_section + advice)
    out = {
        "success": True,
        "city": city, "district": district,
        "stats": {"new_listings": new_props, "available": avail,
                  "viewings": viewings_week, "deals": deals_week},
        "message": report,
    }
    if _brief_warning:
        out["warning_stats"] = _brief_warning
    return json.dumps(out, ensure_ascii=False)


registry.register(
    name="market_brief",
    toolset="real_estate",
    schema={"name": "market_brief", "description": "市场行情简报：自家盘况+联网行情（标注来源）+本周行动建议，可直接转发朋友圈/客户群", "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市（启用联网行情检索）"},
            "district": {"type": "string", "description": "区域（可选）"},
        },
    }},
    handler=lambda args, **kw: market_brief(**args),
)
