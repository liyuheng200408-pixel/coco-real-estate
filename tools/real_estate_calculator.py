"""
Coco 房产工具 - 金融计算器
贷款计算、税费计算、投资回报计算
"""
import json
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
        price: 房价（万元）
        down_payment_ratio: 首付比例（默认30%）
        loan_years: 贷款年限（默认30年）
        interest_rate: 年利率（默认4.5%）
        method: 还款方式 equal_installment(等额本息) / equal_principal(等额本金)
    """
    # 转换为元
    price_yuan = price * 10000
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
        "房价": f"{price}万元",
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
        price: 房价（万元）
        area: 面积（㎡）
        is_first_home: 是否首套房
        hold_years: 持有年限
    """
    price_yuan = price * 10000
    
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
        "房价": f"{price}万元",
        "面积": f"{area}㎡",
        "是否首套": "是" if is_first_home else "否",
        "持有年限": f"{hold_years}年",
        "契税": f"{deed_tax/10000:.2f}万元 ({deed_tax_rate*100}%)",
        "增值税": f"{vat/10000:.2f}万元" if vat > 0 else "免征（满2年）",
        "个人所得税": f"{personal_tax/10000:.2f}万元" if personal_tax > 0 else "免征（满5年唯一）",
        "税费合计": f"{total_tax/10000:.2f}万元",
    }
    
    return json.dumps({"success": True, "calculator": result}, ensure_ascii=False)


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
        price: 购入价（万元）
        monthly_rent: 月租金（元）
        hold_years: 持有年限
        expected_appreciation: 预期年增值率（默认5%）
    """
    price_yuan = price * 10000
    
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
        "购入价": f"{price}万元",
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
                "price": {"type": "number", "description": "房价（万元）"},
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
                "price": {"type": "number", "description": "房价（万元）"},
                "area": {"type": "number", "description": "面积（㎡）"},
                "is_first_home": {"type": "boolean", "description": "是否首套房"},
                "hold_years": {"type": "integer", "description": "持有年限"},
            },
            "required": ["price", "area"],
        },
        "handler": lambda args, **kw: tax_calculator(**args),
    },
    {
        "name": "roi_calculator",
        "description": "投资回报率计算器 - 租金回报、升值收益",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {"type": "number", "description": "购入价（万元）"},
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
