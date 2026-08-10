"""
Coco 房产工具 - 经营报告导出
周报/月报：客户、房源、带看、成交全维度汇总
"""
import json
from datetime import datetime, timedelta
from tools.registry import registry


def _get_db():
    from agent.real_estate_db import get_real_estate_db
    return get_real_estate_db()


def generate_report(period: str = "week", task_id: str = None) -> str:
    """生成经营报告（周报/月报），Markdown 格式

    period: week(周报) / month(月报)
    """
    if period not in ("week", "month"):
        return json.dumps({"success": False, "error": "period 必须是 week/month"}, ensure_ascii=False)

    db = _get_db()
    now = datetime.now()
    if period == "week":
        start = now - timedelta(days=7)
        title = f"周报（{start.strftime('%m-%d')} ~ {now.strftime('%m-%d')}）"
    else:
        start = now - timedelta(days=30)
        title = f"月报（{start.strftime('%Y-%m')}）"

    # 客户统计
    stats = db.get_stats()
    # 带看统计
    try:
        viewing_stats = db.viewing_stats()
    except Exception:
        viewing_stats = {}
    # 成交统计
    try:
        deal_stats = db.deal_stats()
    except Exception:
        deal_stats = {}
    # 逾期
    overdue = db.get_overdue()

    lines = []
    lines.append(f"# Coco 经营{title}")
    lines.append("")
    lines.append("## 客户概况")
    lines.append("")
    lines.append(f"- 客户总数：{stats.get('total_customers', 0)}")
    tier_counts = stats.get('tier_counts', {})
    lines.append(f"- S级：{tier_counts.get('S', 0)} | A级：{tier_counts.get('A', 0)} | "
                 f"B级：{tier_counts.get('B', 0)} | C级：{tier_counts.get('C', 0)}")
    lines.append(f"- 在售房源：{stats.get('available_properties', 0)}")
    lines.append("")
    lines.append("## 带看情况")
    lines.append("")
    lines.append(f"- 总带看：{viewing_stats.get('total_viewings', 0)} 次")
    lines.append(f"- 已完成：{viewing_stats.get('done', 0)} 次 | 待带看：{viewing_stats.get('scheduled', 0)} 次")
    lines.append(f"- 客户感兴趣：{viewing_stats.get('interested', 0)} 位")
    lines.append(f"- 带看兴趣率：{viewing_stats.get('interest_rate', 0)}%")
    lines.append("")
    lines.append("## 成交进展")
    lines.append("")
    lines.append(f"- 成交总数：{deal_stats.get('total_deals', 0)}")
    stages = deal_stats.get('stages', {})
    lines.append(f"- 定金：{stages.get('deposit', 0)} | 签约：{stages.get('signing', 0)} | "
                 f"贷款：{stages.get('loan', 0)} | 过户：{stages.get('transfer', 0)} | 交房：{stages.get('finalized', 0)}")
    lines.append("")
    lines.append("## 逾期跟进")
    lines.append("")
    if overdue:
        lines.append(f"- 逾期客户 {len(overdue)} 位，请尽快跟进：")
        for f in overdue[:10]:
            customer_name = f.get('customer_name') or f"客户#{f.get('customer_id')}"
            next_date = (f.get('next_date') or '')[:10]
            lines.append(f"  - {customer_name}（原定 {next_date}）")
    else:
        lines.append("- 无逾期客户，跟进情况良好")
    lines.append("")
    lines.append("## 总结")
    lines.append("")
    lines.append(f"本{period}共管理 {stats.get('total_customers', 0)} 位客户，"
                 f"完成 {viewing_stats.get('done', 0)} 次带看，"
                 f"成交推进 {deal_stats.get('total_deals', 0)} 单。")
    if viewing_stats.get('interest_rate', 0) < 30:
        lines.append("提示：带看兴趣率偏低，建议复盘带看房源匹配度和客户需求沟通。")
    if tier_counts.get('S', 0) > 0 and len(overdue) > 0:
        lines.append("注意：存在逾期跟进，S级客户务必 2 天内完成跟进。")

    report = "\n".join(lines)
    return json.dumps({"success": True, "period": period, "title": title, "report": report}, ensure_ascii=False)


registry.register(
    name="generate_report",
    toolset="real_estate",
    schema={"name": "generate_report", "description": "生成经营报告（周报/月报）：客户、带看、成交、逾期全维度", "parameters": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["week", "month"], "description": "报告周期"},
        },
    }},
    handler=lambda args, **kw: generate_report(**args),
)
