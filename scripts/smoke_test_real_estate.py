"""Coco real_estate 工具全量冒烟测试 —— 在 sqlite 上真实调用每个工具的注册 handler

用法（在服务器或本地）:
    cd ~/hermes-agent && source venv/bin/activate && python3 scripts/smoke_test_real_estate.py

覆盖: 工具集静态清单全部 62 个工具 + 出租房附加用例。
输出: 每个工具的 OK/ERR/EXC 汇总 + 未注册/遗漏提示。
"""
import os, sys, json, glob, importlib, traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# ---------- 环境（独立测试库，不碰真实数据） ----------
TEST_DB = '/tmp/coco_smoke_test.db'
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
# 用真实 Fernet 密钥走加密路径（服务器上 install.sh 会生成 COCO_ENC_KEY）
from cryptography.fernet import Fernet
os.environ['COCO_ENC_KEY'] = Fernet.generate_key().decode()
os.environ.setdefault('COCO_IMG_DIR', '/tmp/coco_smoke_imgs')

from agent.real_estate_db import init_real_estate_db
init_real_estate_db()

# ---------- 导入全部 real_estate 工具模块（自注册） ----------
import tools.registry as registry_mod
for f in sorted(glob.glob(os.path.join(REPO_ROOT, 'tools', 'real_estate_*.py'))):
    mod = os.path.basename(f)[:-3]
    importlib.import_module(f'tools.{mod}')
registry = registry_mod.registry

# ---------- 静态工具清单（与 toolsets.py 一致） ----------
STATIC_TOOLS = [
    "add_customer","update_customer","get_customer","list_customers","update_tier","customer_stats",
    "add_customer_tag","remove_customer_tag","list_customer_tags","get_customer_form","customer_change_history",
    "add_property","update_property","search_property","match_property","property_stats","get_property_form","deduplicate_properties",
    "add_followup","get_followups","get_overdue","schedule_reminder","daily_report","midday_check","stale_check",
    "mortgage_calculator","tax_calculator","roi_calculator",
    "get_script","use_template",
    "performance_dashboard","conversion_funnel","weekly_market_report","get_loan_policy","list_policy_cities","channel_stats",
    "schedule_viewing","record_viewing","get_viewing","list_viewings","viewing_stats",
    "start_deal","advance_deal","get_deal","list_deals","deal_stats",
    "birthday_check","update_birthday",
    "generate_listing_copy","generate_short_video_script",
    "add_property_images","list_property_images",
    "compare_property","intent_score","list_intent_scores",
    "save_script","get_script_by_name","list_scripts","delete_script",
    "generate_report",
    "generate_property_poster","generate_poster_grid",
]

# ---------- 造一张测试图片 ----------
from PIL import Image
os.makedirs('/tmp/coco_smoke_imgs', exist_ok=True)
TEST_IMG = '/tmp/coco_smoke_imgs/test_house.jpg'
Image.new('RGB', (400, 300), (200, 180, 160)).save(TEST_IMG)


def call(tool, args=None):
    entry = registry.get_entry(tool)
    if entry is None:
        return ('NO_ENTRY', None)
    try:
        raw = entry.handler(args or {})
    except Exception:
        return ('EXC', traceback.format_exc(limit=3))
    try:
        data = json.loads(raw)
        ok = bool(data.get('success'))
        return ('OK' if ok else 'ERR', data)
    except Exception:
        return ('RAW', str(raw)[:120])


results = {}

# ---------- 1. 播种 ----------
r = call('add_customer', {"name":"测试客户张先生","phone":"13800138000","wechat":"zhang138","tier":"S",
    "budget_min":3000000,"budget_max":5000000,"area_pref":"朝阳","layout_pref":"3室2厅","location":"北京朝阳",
    "renovation":"精装","notes":"测试客户","source":"转介绍","customer_type":"buy_second_hand","birthday":"1990-01-01"})
cid = r[1]['customer']['id']; results['add_customer'] = r

r = call('add_property', {"title":"测试小区三居","price":1280000,"area":89.5,"community":"测试小区","district":"朝阳",
    "address":"朝阳路1号","rooms":3,"halls":2,"bathrooms":1,"floor":"5/18","orientation":"南北","renovation":"精装",
    "year_built":2018,"has_elevator":1,"parking":1,"property_type":"second_hand","tags":"地铁房,南北通透"})
pid = r[1]['property']['id']; results['add_property'] = r

# 出租房:月租 1000 元(验证小金额直接存元)
r = call('add_property', {"title":"测试小区单间出租","price":1000,"area":45.0,"community":"测试小区","district":"朝阳",
    "rooms":1,"halls":1,"bathrooms":1,"property_type":"rental","tags":"拎包入住"})
rental_pid = r[1]['property']['id']; results['add_property_rental'] = r

r = call('save_script', {"name":"议价话术","content":"理解您的预算考虑，这套房可以谈","scenario":"objection_handling"})
sid = r[1]['script']['id']; results['save_script'] = r

r = call('schedule_viewing', {"customer_id":cid,"property_id":pid,"viewing_time":"2026-08-16 14:00"})
vid = r[1]['viewing']['id']; results['schedule_viewing'] = r

r = call('start_deal', {"customer_id":cid,"property_id":pid,"price":1250000,"deposit_amount":20000,
    "deposit_date":"2026-08-15","notes":"测试成交"})
did = r[1]['deal']['id']; results['start_deal'] = r

# ---------- 2. 全部工具按序调用 ----------
CASES = [
    ("update_customer", {"customer_id":cid,"budget_max":900000}),                  # 500万→90万 触发预算漂移预警
    ("get_customer", {"customer_id":cid}),
    ("list_customers", {}),
    ("update_tier", {"customer_id":cid,"tier":"A"}),
    ("customer_stats", {}),
    ("add_customer_tag", {"customer_id":cid,"tag":"刚需"}),
    ("remove_customer_tag", {"customer_id":cid,"tag":"刚需"}),
    ("list_customer_tags", {"customer_id":cid}),
    ("get_customer_form", {}),
    ("customer_change_history", {"customer_id":cid}),
    ("update_property", {"property_id":pid,"price":1250000}),
    ("search_property", {"district":"朝阳","max_price":1500000,"limit":10}),
    ("match_property", {"customer_id":cid,"top_n":5}),
    ("property_stats", {}),
    ("get_property_form", {}),
    ("deduplicate_properties", {"dry_run":True}),
    ("add_followup", {"customer_id":cid,"content":"电话沟通，客户周末来看房","type":"call",
        "next_date":"2026-08-15","next_time":"10:00"}),
    ("get_followups", {"customer_id":cid}),
    ("get_overdue", {}),
    ("schedule_reminder", {"customer_id":cid,"date":"2026-08-16","time":"09:30","content":"跟进客户意向"}),
    ("daily_report", {}),
    ("midday_check", {}),
    ("stale_check", {}),
    ("mortgage_calculator", {"price":3000000,"down_payment_ratio":0.3,"loan_years":30,"interest_rate":4.5}),
    ("tax_calculator", {"price":3000000,"area":100,"is_first_home":True,"hold_years":2}),
    ("roi_calculator", {"price":2000000,"monthly_rent":5000,"hold_years":5,"expected_appreciation":0.03}),
    ("get_script", {"scenario":"greeting"}),
    ("use_template", {"template_name":"property_recommend",
        "variables":{"community":"测试小区","price":"128","rooms":3,"halls":2,"area":"89.5","highlights":"南北通透"}}),
    ("performance_dashboard", {"period":"week"}),
    ("conversion_funnel", {"period":"week"}),
    ("weekly_market_report", {"district":"朝阳"}),
    ("get_loan_policy", {"city":"北京","policy_type":"首付比例"}),
    ("list_policy_cities", {}),
    ("channel_stats", {}),
    ("record_viewing", {"viewing_id":vid,"status":"done","result":"interested","feedback":"客户觉得价格合适"}),
    ("get_viewing", {"viewing_id":vid}),
    ("list_viewings", {}),
    ("viewing_stats", {}),
    ("advance_deal", {"deal_id":did,"stage":"signing","date":"2026-08-20"}),
    ("get_deal", {"deal_id":did}),
    ("list_deals", {}),
    ("deal_stats", {}),
    ("birthday_check", {}),
    ("update_birthday", {"customer_id":cid,"birthday":"1990-01-01"}),
    ("generate_listing_copy", {"property_id":pid,"platform":"friends"}),
    ("generate_listing_copy", {"property_id":rental_pid,"platform":"beike"}),      # 出租文案应显示"1000元/月"
    ("generate_short_video_script", {"property_id":pid,"platform":"douyin"}),
    ("add_property_images", {"property_id":pid,"images":TEST_IMG}),
    ("list_property_images", {"property_id":pid}),
    ("compare_property", {"property_id":pid}),
    ("intent_score", {"customer_id":cid}),
    ("list_intent_scores", {}),
    ("get_script_by_name", {"name":"议价话术"}),
    ("list_scripts", {}),
    ("delete_script", {"script_id":sid}),
    ("generate_report", {"period":"week"}),
    ("generate_property_poster", {"property_id":pid}),
    ("generate_poster_grid", {"property_ids":str(pid)}),
]

for name, args in CASES:
    results[name] = call(name, args)

# ---------- 3. 汇总 ----------
covered = set(results.keys())
missing = [t for t in STATIC_TOOLS if t not in covered]
orphan  = [t for t in covered if t not in STATIC_TOOLS]
unregistered = [t for t in STATIC_TOOLS if registry.get_entry(t) is None]

print("=" * 70)
print(f"工具总数(静态清单): {len(STATIC_TOOLS)}  实际调用: {len(covered)}")
if missing: print(f"!! 静态清单里有但未测试: {missing}")
if orphan:  print(f"!! 测试了但不在静态清单: {orphan}")
if unregistered: print(f"!! 静态清单里无注册条目(模型看不到): {unregistered}")
print("-" * 70)
ok = err = exc = 0
for name in STATIC_TOOLS:
    if name not in results: continue
    status, payload = results[name]
    if status == 'OK': ok += 1
    elif status == 'ERR': err += 1; print(f"[{status}] {name} -> success=False: {json.dumps(payload, ensure_ascii=False)[:160]}")
    elif status == 'EXC': exc += 1; print(f"[EXC ] {name} -> 异常:\n{payload}")
    elif status == 'NO_ENTRY': print(f"[MISS] {name} 未注册")
    else: print(f"[RAW ] {name} -> {payload}")
print("-" * 70)
print(f"✅ 正常返回 success=true : {ok}")
print(f"⚠️  返回 success=false   : {err}（工具跑了但业务上没走通，需看原因）")
print(f"❌ 抛异常崩溃            : {exc}")
print(f"✅ 合计通过(OK+ERR 无崩溃): {ok+err}/{len(STATIC_TOOLS)}")
