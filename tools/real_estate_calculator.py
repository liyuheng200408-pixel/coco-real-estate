"""
Coco 房产工具 - 金融计算器
贷款计算、税费计算、投资回报计算、贷款方案对比、税费明细单
"""
import json
import re
from tools.registry import registry


def mortgage_calculator(
    price: float,
    down_payment_ratio: float = 0.3,
    loan_years: int = 30,
    interest_rate: float = 4.5,
    method: str = "equal_installment",
    task_id: str = None,
) -> str:
    """
    贷款计算器
    
    参数:
        price: 房价（元，如 400万=4000000）
        down_payment_ratio: 首付比例（默认30%）
        loan_years: 贷款年限（默认30年）
        interest_rate: 年利率（默认4.5%）
        method: 还款方式 equal_installment(等额本息) / equal_principal(等额本金)
    """
    # 转换为元
    price_yuan = price  # 系统价格单位为元（如 400万 = 4000000）
    down_payment = price_yuan * down_payment_ratio
    loan_amount = price_yuan - down_payment
    
    # 月利率
    monthly_rate = interest_rate / 100 / 12
    total_months = loan_years * 12
    
    if method == "equal_installment":
        # 等额本息
        monthly_payment = loan_amount * monthly_rate * (1 + monthly_rate) ** total_months / ((1 + monthly_rate) ** total_months - 1)
        total_payment = monthly_payment * total_months
        total_interest = total_payment - loan_amount
    else:
        # 等额本金
        monthly_principal = loan_amount / total_months
        first_month_payment = monthly_principal + loan_amount * monthly_rate
        last_month_payment = monthly_principal + monthly_principal * monthly_rate
        total_payment = (first_month_payment + last_month_payment) * total_months / 2
        total_interest = total_payment - loan_amount
        monthly_payment = f"{first_month_payment:.2f} - {last_month_payment:.2f}"
    
    result = {
        "房价": f"{price/10000:.0f}万元",
        "首付比例": f"{down_payment_ratio*100}%",
        "首付金额": f"{down_payment/10000:.2f}万元",
        "贷款金额": f"{loan_amount/10000:.2f}万元",
        "贷款年限": f"{loan_years}年",
        "年利率": f"{interest_rate}%",
        "还款方式": "等额本息" if method == "equal_installment" else "等额本金",
        "月供": f"{monthly_payment:.2f}元" if isinstance(monthly_payment, float) else monthly_payment,
        "总还款额": f"{total_payment/10000:.2f}万元",
        "总利息": f"{total_interest/10000:.2f}万元",
    }
    
    return json.dumps({"success": True, "calculator": result}, ensure_ascii=False)


def tax_calculator(
    price: float,
    area: float,
    is_first_home: bool = True,
    hold_years: int = 2,
    task_id: str = None,
) -> str:
    """
    税费计算器
    
    参数:
        price: 房价（元，如 400万=4000000）
        area: 面积（㎡）
        is_first_home: 是否首套房
        hold_years: 持有年限
    """
    price_yuan = price  # 系统价格单位为元（如 400万 = 4000000）
    
    # 契税
    if is_first_home:
        if area <= 90:
            deed_tax_rate = 0.01  # 1%
        else:
            deed_tax_rate = 0.015  # 1.5%
    else:
        deed_tax_rate = 0.03  # 3%
    deed_tax = price_yuan * deed_tax_rate
    
    # 增值税（卖方缴纳，但可能转嫁给买方）
    if hold_years >= 2:
        vat = 0  # 满2年免征
    else:
        vat = price_yuan * 0.056  # 5.6%
    
    # 个人所得税（卖方缴纳）
    if hold_years >= 5 and is_first_home:
        personal_tax = 0  # 满5年且唯一免征
    else:
        personal_tax = price_yuan * 0.01  # 1%或差额20%
    
    total_tax = deed_tax + vat + personal_tax
    
    result = {
        "房价": f"{price/10000:.0f}万元",
        "面积": f"{area}㎡",
        "是否首套": "是" if is_first_home else "否",
        "持有年限": f"{hold_years}年",
        "契税": f"{deed_tax/10000:.2f}万元 ({deed_tax_rate*100}%)",
        "增值税": f"{vat/10000:.2f}万元" if vat > 0 else "免征（满2年）",
        "个人所得税": f"{personal_tax/10000:.2f}万元" if personal_tax > 0 else "免征（满5年唯一）",
        "税费合计": f"{total_tax/10000:.2f}万元",
    }
    
    return json.dumps({"success": True, "calculator": result}, ensure_ascii=False)


def loan_compare(
    price: float,
    down_payment_ratio: float = 0.3,
    loan_years_list: str = "20,30",
    commercial_rate: float = None,
    provident_fund_rate: float = 2.85,
    provident_fund_loan_amount: float = None,
    city: str = None,
    task_id: str = None,
) -> str:
    """
    贷款方案对比器：一次输出 商贷/组合贷/等额本金 多方案对比表

    参数:
        price: 房价（元，如 400万=4000000）
        down_payment_ratio: 首付比例（默认0.3）
        loan_years_list: 商贷年限列表，逗号分隔（默认"20,30"）
        commercial_rate: 商贷年利率%（不传则按 city 查政策库，查不到用 3.6%）
        provident_fund_rate: 公积金年利率%（默认2.85%）
        provident_fund_loan_amount: 公积金贷款额度（元），传了才出组合贷方案
        city: 城市名（用于查询当地政策利率）
    """
    price_yuan = price
    if price_yuan <= 0 or down_payment_ratio <= 0 or down_payment_ratio >= 1:
        return json.dumps({"success": False, "error": "房价需>0且首付比例需在(0,1)之间"}, ensure_ascii=False)

    down_payment = price_yuan * down_payment_ratio
    loan_amount = price_yuan - down_payment

    # 利率：显式传入 > 政策库查询 > 默认值
    if commercial_rate is None:
        commercial_rate = 3.6
        if city:
            try:
                from tools.real_estate_policy import get_loan_policy
                raw = get_loan_policy(city=city, policy_type="贷款利率")
                data = json.loads(raw)
                text = json.dumps(data, ensure_ascii=False)
                m = re.search(r"(\d+\.?\d*)\s*%", text.replace("：", ":"))
                if m:
                    commercial_rate = float(m.group(1))
            except Exception:
                pass

    years = []
    for y in str(loan_years_list).split(","):
        y = y.strip()
        if y and y.isdigit():
            years.append(int(y))
    if not years:
        years = [20, 30]

    def installment_monthly(amount, annual_rate, months):
        mr = annual_rate / 100 / 12
        return amount * mr * (1 + mr) ** months / ((1 + mr) ** months - 1)

    def principal_monthly_first(amount, annual_rate, months):
        mr = annual_rate / 100 / 12
        return amount / months + amount * mr

    plans = []
    # 方案1..N：等额本息 各年限
    for y in sorted(years):
        months = y * 12
        mp = installment_monthly(loan_amount, commercial_rate, months)
        total_interest = mp * months - loan_amount
        plans.append({
            "方案": f"纯商贷 {y}年 等额本息",
            "贷款额": f"{loan_amount/10000:.1f}万",
            "年利率": f"{commercial_rate}%",
            "月供": f"{mp:,.0f}元",
            "总利息": f"{total_interest/10000:.1f}万",
            "适合人群": f"月供压力要小、打算长期还款" if y >= 30 else "利息总额与月供的平衡",
        })

    # 组合贷方案（按最长年限算）
    if provident_fund_loan_amount and provident_fund_loan_amount > 0:
        gf = min(provident_fund_loan_amount, loan_amount)
        comm = loan_amount - gf
        y = max(years)
        months = y * 12
        mp_gf = installment_monthly(gf, provident_fund_rate, months)
        mp_comm = installment_monthly(comm, commercial_rate, months)
        mp = mp_gf + mp_comm
        total_interest = (mp * months) - loan_amount
        plans.insert(0, {
            "方案": f"组合贷(公积金{gf/10000:.0f}万+商贷{comm/10000:.0f}万) {y}年 等额本息",
            "贷款额": f"{loan_amount/10000:.1f}万",
            "年利率": f"公积金{provident_fund_rate}%+商贷{commercial_rate}%",
            "月供": f"{mp:,.0f}元",
            "总利息": f"{total_interest/10000:.1f}万",
            "适合人群": "有公积金额度，想省利息",
        })

    # 等额本金方案（按最长年限）
    y = max(years)
    months = y * 12
    first_mp = principal_monthly_first(loan_amount, commercial_rate, months)
    total_interest_principal = loan_amount * commercial_rate / 100 * (months + 1) / 2 / 12
    plans.append({
        "方案": f"纯商贷 {y}年 等额本金",
        "贷款额": f"{loan_amount/10000:.1f}万",
        "年利率": f"{commercial_rate}%",
        "月供": f"首月{first_mp:,.0f}元逐月递减",
        "总利息": f"{total_interest_principal/10000:.1f}万",
        "适合人群": "前期还款能力强、打算提前还款",
    })

    tips = [
        "提前还款：多数银行放款满1年后才允许，部分有违约金，签字前确认",
        "利率重定价：LPR浮动利率每年1月1日或放款日重定价，降息月供会变",
        "公积金贷款：额度上限、缴存年限要求各城市不同，建议先查当地政策",
    ]

    result = {
        "房价": f"{price_yuan/10000:.0f}万元",
        "首付": f"{down_payment_ratio*100:.0f}% = {down_payment/10000:.1f}万",
        "贷款总额": f"{loan_amount/10000:.1f}万",
        "商贷利率来源": f"{city}政策库" if (city and commercial_rate != 3.6) else ("手动指定" if commercial_rate else "默认值"),
        "方案对比": plans,
        "温馨提示": tips,
    }
    return json.dumps({"success": True, "loan_compare": result}, ensure_ascii=False)


def tax_breakdown_report(
    price: float,
    area: float,
    hold_years: float = 2,
    is_first_home: bool = True,
    is_only_home: bool = True,
    property_class: str = "ordinary",
    original_price: float = None,
    city: str = None,
    task_id: str = None,
) -> str:
    """
    客户版税费明细单：满二/满五唯一、首套/二套、普宅/非普宅联动判定

    参数:
        price: 成交价（元）
        area: 面积（㎡）
        hold_years: 房产证持有年限（可传小数，如1.5）
        is_first_home: 买方是否首套
        is_only_home: 卖方是否唯一住房（满五唯一免个税的关键）
        property_class: ordinary(普通住宅)/non_ordinary(非普通住宅)
        original_price: 卖方原购入价（元），非普宅/满二差额计税用
        city: 城市（展示政策依据用）
    """
    price_yuan = price
    if price_yuan <= 0 or area <= 0:
        return json.dumps({"success": False, "error": "房价和面积需>0"}, ensure_ascii=False)

    full_two = hold_years >= 2
    full_five_only = hold_years >= 5 and is_only_home
    ordinary = (property_class == "ordinary")

    items = []

    # 1. 契税（买方）
    if is_first_home:
        deed_rate = 0.01 if area <= 90 else (0.015 if ordinary else 0.03)
    else:
        deed_rate = 0.03
    deed = price_yuan * deed_rate
    items.append({
        "税目": "契税", "承担": "买方",
        "金额": f"{deed/10000:.2f}万 ({deed_rate*100:.1f}%)",
        "依据": f"{'首套' if is_first_home else '二套'}+{area}㎡ → 税率{deed_rate*100:.1f}%",
    })

    # 2. 增值税（卖方，常转嫁买方）
    if full_two:
        if ordinary:
            vat, vat_note = 0, "满2年普通住宅免征"
        else:
            # 非普宅满2年差额计税
            base = price_yuan - (original_price or 0)
            vat, vat_note = base * 0.05 / 1.05, f"满2年非普宅按差额(现价-原价{original_price/10000 if original_price else 0:.0f}万)5%" if original_price else "非普宅需提供原购入价按差额计税"
    else:
        vat, vat_note = price_yuan / 1.05 * 0.05, "未满2年全额5%（增值税及附加约5.6%口径内）"
    items.append({
        "税目": "增值税及附加", "承担": "卖方(常转嫁)",
        "金额": f"{vat/10000:.2f}万" if vat > 0 else "免征",
        "依据": vat_note,
    })

    # 3. 个人所得税（卖方）
    if full_five_only:
        pt, pt_note = 0, "满五唯一免征"
    elif hold_years >= 5:
        pt, pt_note = price_yuan * 0.01, "满五不唯一 → 差额20%或核定1%（本单按1%）"
    else:
        pt, pt_note = price_yuan * 0.01, "未满五年 → 差额20%或核定1%（本单按1%）"
    items.append({
        "税目": "个人所得税", "承担": "卖方(常转嫁)",
        "金额": f"{pt/10000:.2f}万" if pt > 0 else "免征",
        "依据": pt_note,
    })

    total = deed + vat + pt
    lines = ["📋 税费明细单（客户版）", "=" * 32,
             f"成交价: {price_yuan/10000:.0f}万元 | {area}㎡ | {city or ''}{'（普宅）' if ordinary else '（非普宅）'}",
             f"房本: 满{hold_years:.0f}年{'且唯一' if is_only_home else '非唯一'} | 买方{'首套' if is_first_home else '二套'}",
             "-" * 32]
    for it in items:
        lines.append(f"{it['税目']}（{it['承担']}）: {it['金额']}")
        lines.append(f"  └ {it['依据']}")
    lines.append("-" * 32)
    lines.append(f"税费合计: {total/10000:.2f}万元（实际以税务局核定为准）")
    lines.append("⚠️ 各地政策有差异且随时调整，本清单仅供参考，签约前请以当地最新政策为准。")

    return json.dumps({
        "success": True,
        "tax_breakdown": {
            "city": city, "items": items,
            "total_tax_yuan": round(total, 2),
            "report_text": "\n".join(lines),
        },
    }, ensure_ascii=False)


def roi_calculator(
    price: float,
    monthly_rent: float,
    hold_years: int = 5,
    expected_appreciation: float = 0.05,
    task_id: str = None,
) -> str:
    """
    投资回报率计算器
    
    参数:
        price: 购入价（元，如 400万=4000000）
        monthly_rent: 月租金（元）
        hold_years: 持有年限
        expected_appreciation: 预期年增值率（默认5%）
    """
    price_yuan = price  # 系统价格单位为元（如 400万 = 4000000）
    
    # 租金回报
    annual_rent = monthly_rent * 12
    gross_rental_yield = annual_rent / price_yuan * 100
    
    # 升值收益
    future_price = price_yuan * (1 + expected_appreciation) ** hold_years
    appreciation_gain = future_price - price_yuan
    appreciation_rate = ((1 + expected_appreciation) ** hold_years - 1) * 100
    
    # 总收益
    total_gain = annual_rent * hold_years + appreciation_gain
    total_roi = total_gain / price_yuan * 100
    
    # 年化收益
    annual_roi = ((1 + total_roi / 100) ** (1 / hold_years) - 1) * 100
    
    result = {
        "购入价": f"{price/10000:.0f}万元",
        "月租金": f"{monthly_rent}元",
        "持有年限": f"{hold_years}年",
        "预期年增值率": f"{expected_appreciation*100}%",
        "年租金收入": f"{annual_rent}元",
        "毛租金回报率": f"{gross_rental_yield:.2f}%",
        "预期卖出价": f"{future_price/10000:.2f}万元",
        "升值收益": f"{appreciation_gain/10000:.2f}万元",
        "总收益": f"{total_gain/10000:.2f}万元",
        "总回报率": f"{total_roi:.2f}%",
        "年化回报率": f"{annual_roi:.2f}%",
    }
    
    return json.dumps({"success": True, "calculator": result}, ensure_ascii=False)


# 工具注册
TOOLS = [
    {
        "name": "mortgage_calculator",
        "description": "贷款计算器 - 计算月供、总利息、还款计划",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "房价（元，如 400万=4000000）"},
                "down_payment_ratio": {"type": "number", "description": "首付比例（默认0.3）"},
                "loan_years": {"type": "integer", "description": "贷款年限（默认30年）"},
                "interest_rate": {"type": "number", "description": "年利率（默认4.5%）"},
                "method": {"type": "string", "enum": ["equal_installment", "equal_principal"], "description": "还款方式"},
            },
            "required": ["price"],
        },
        "handler": lambda args, **kw: mortgage_calculator(**args),
    },
    {
        "name": "tax_calculator",
        "description": "税费计算器 - 计算契税、增值税、个税",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "房价（元，如 400万=4000000）"},
                "area": {"type": "number", "description": "面积（㎡）"},
                "is_first_home": {"type": "boolean", "description": "是否首套房"},
                "hold_years": {"type": "integer", "description": "持有年限"},
            },
            "required": ["price", "area"],
        },
        "handler": lambda args, **kw: tax_calculator(**args),
    },
    {
        "name": "loan_compare",
        "description": "贷款方案对比器 - 一次输出纯商贷/组合贷/等额本金多方案对比表（月供、总利息、适合人群），可直接转发客户",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "房价（元，如 400万=4000000）"},
                "down_payment_ratio": {"type": "number", "description": "首付比例（默认0.3）"},
                "loan_years_list": {"type": "string", "description": "商贷年限列表，逗号分隔（默认'20,30'）"},
                "commercial_rate": {"type": "number", "description": "商贷年利率%（不传则按城市查政策，查不到用默认）"},
                "provident_fund_rate": {"type": "number", "description": "公积金年利率%（默认2.85）"},
                "provident_fund_loan_amount": {"type": "number", "description": "公积金贷款额度（元），传了才出组合贷方案"},
                "city": {"type": "string", "description": "城市名（查询当地政策利率用）"},
            },
            "required": ["price"],
        },
        "handler": lambda args, **kw: loan_compare(**args),
    },
    {
        "name": "tax_breakdown_report",
        "description": "税费明细单（客户版）- 满二/满五唯一/首套二套/普宅非普宅联动判定，生成可直接转发客户的税费清单",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "成交价（元）"},
                "area": {"type": "number", "description": "面积（㎡）"},
                "hold_years": {"type": "number", "description": "房本持有年限（可传小数如1.5）"},
                "is_first_home": {"type": "boolean", "description": "买方是否首套"},
                "is_only_home": {"type": "boolean", "description": "卖方是否唯一住房"},
                "property_class": {"type": "string", "enum": ["ordinary", "non_ordinary"], "description": "普通/非普通住宅"},
                "original_price": {"type": "number", "description": "卖方原购入价（元），非普宅差额计税用"},
                "city": {"type": "string", "description": "城市"},
            },
            "required": ["price", "area"],
        },
        "handler": lambda args, **kw: tax_breakdown_report(**args),
    },
    {
        "name": "roi_calculator",
        "description": "投资回报率计算器 - 租金回报、升值收益",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "购入价（元，如 400万=4000000）"},
                "monthly_rent": {"type": "number", "description": "月租金（元）"},
                "hold_years": {"type": "integer", "description": "持有年限"},
                "expected_appreciation": {"type": "number", "description": "预期年增值率"},
            },
            "required": ["price", "monthly_rent"],
        },
        "handler": lambda args, **kw: roi_calculator(**args),
    },
]

for tool in TOOLS:
    registry.register(
        name=tool["name"],
        toolset="real_estate",
        schema={"name": tool["name"], "description": tool["description"], "parameters": tool["parameters"]},
        handler=tool["handler"],
    )
