"""
Coco 房产工具 - 沟通工具
话术库、消息模板
"""
import json
from tools.registry import registry


# 话术库
SCRIPTS = {
    "greeting": {
        "first_contact": "您好，我是XX房产的置业顾问。看到您在关注房产信息，不知道您是想买房还是租房呢？我可以根据您的需求帮您推荐合适的房源。",
        "follow_up": "您好，之前您看过的那套房子，现在有个好消息想告诉您。不知道您方便聊聊吗？",
        "after_viewing": "您好，上次带您看的房子感觉怎么样？有什么想法可以跟我说说，我帮您分析分析。",
    },
    "objection_handling": {
        "price_too_high": "理解您的顾虑。这套房子的价格确实是同区域较高的，但它的优势在于：1. 学区对口XX小学；2. 楼层好、采光佳；3. 装修保养好，拎包入住。如果您诚心想要，我可以帮您跟业主谈谈价格。",
        "need_to_consider": "买房确实是大事，您考虑清楚是对的。不过这套房子在同户型里性价比很高，最近看的人也不少。我建议您可以先做个对比，看看其他类似房源的价格和条件，这样心里更有数。",
        "location_not_satisfied": "这个位置确实不是您首选的区域，但您知道吗，这个片区未来有地铁规划，而且现在价格比您理想的区域低了20%左右。从投资角度看，增值空间更大。",
    },
    "closing": {
        "create_urgency": "跟您说实话，这套房子已经有两组客户在谈了。如果您真的喜欢，建议尽快定下来，不然可能就被别人抢先了。",
        "offer_incentive": "如果您今天能定下来，我可以帮您跟公司申请一个额外优惠，比如免一部分中介费或者赠送家电。您看怎么样？",
        "final_reminder": "您考虑得怎么样了？这套房子业主那边也在等回复，如果今天能给个准信，我好帮您争取最好的条件。",
    },
    "follow_up": {
        "weekly_check": "您好，好久没联系了。最近房产市场有些新变化，不知道您还在关注买房的事吗？有什么需要随时跟我说。",
        "holiday_greeting": "XX节快乐！感谢您一直以来的信任。最近有几套不错的房源，要不要我发给您看看？",
        "price_drop": "好消息！您之前关注的那套房子降价了，现在价格更合适了。要不要再去看一看？",
    },
}


def get_script(
    scenario: str,
    sub_scenario: str = None,
    task_id: str = None,
) -> str:
    """
    获取话术
    
    参数:
        scenario: 场景 (greeting/objection_handling/closing/follow_up)
        sub_scenario: 子场景
    """
    if scenario not in SCRIPTS:
        return json.dumps({"success": False, "error": f"未知场景: {scenario}，可用场景: {list(SCRIPTS.keys())}"}, ensure_ascii=False)
    
    scripts = SCRIPTS[scenario]
    
    if sub_scenario:
        if sub_scenario in scripts:
            return json.dumps({"success": True, "scenario": scenario, "sub_scenario": sub_scenario, "script": scripts[sub_scenario]}, ensure_ascii=False)
        else:
            return json.dumps({"success": False, "error": f"未知子场景: {sub_scenario}，可用: {list(scripts.keys())}"}, ensure_ascii=False)
    
    return json.dumps({"success": True, "scenario": scenario, "scripts": scripts}, ensure_ascii=False)


# 消息模板
TEMPLATES = {
    "property_recommend": "【房源推荐】\n小区：{community}\n价格：{price}万\n户型：{rooms}室{halls}厅\n面积：{area}㎡\n亮点：{highlights}",
    "viewing_reminder": "【看房提醒】\n时间：{time}\n地址：{address}\n联系人：{contact}",
    "follow_up": "【跟进提醒】\n客户：{customer}\n上次沟通：{last_contact}\n待办：{todo}",
    "price_change": "【价格变动】\n房源：{title}\n原价：{old_price}万\n现价：{new_price}万\n变动：{change}",
    "market_report": "【市场周报】\n区域：{district}\n新增房源：{new_listings}套\n成交：{deals}套\n均价：{avg_price}万",
}


def use_template(
    template_name: str,
    variables: dict = None,
    task_id: str = None,
) -> str:
    """
    使用消息模板
    
    参数:
        template_name: 模板名称
        variables: 模板变量
    """
    if template_name not in TEMPLATES:
        return json.dumps({"success": False, "error": f"未知模板: {template_name}，可用模板: {list(TEMPLATES.keys())}"}, ensure_ascii=False)
    
    template = TEMPLATES[template_name]
    
    if variables:
        try:
            message = template.format(**variables)
        except KeyError as e:
            return json.dumps({"success": False, "error": f"缺少变量: {e}"}, ensure_ascii=False)
    else:
        message = template
    
    return json.dumps({"success": True, "template": template_name, "message": message}, ensure_ascii=False)


# 注册工具
registry.register(
    name="get_script",
    toolset="real_estate",
    schema={"name": "get_script", "description": "获取话术（销售场景标准话术）", "parameters": {
        "type": "object",
        "properties": {
            "scenario": {"type": "string", "enum": ["greeting", "objection_handling", "closing", "follow_up"], "description": "场景"},
            "sub_scenario": {"type": "string", "description": "子场景"},
        },
        "required": ["scenario"],
    }},
    handler=lambda args, **kw: get_script(**args),
)

registry.register(
    name="use_template",
    toolset="real_estate",
    schema={"name": "use_template", "description": "使用消息模板", "parameters": {
        "type": "object",
        "properties": {
            "template_name": {"type": "string", "enum": ["property_recommend", "viewing_reminder", "follow_up", "price_change", "market_report"], "description": "模板名称"},
            "variables": {"type": "object", "description": "模板变量"},
        },
        "required": ["template_name"],
    }},
    handler=lambda args, **kw: use_template(**args),
)
