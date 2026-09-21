"""房源判重（按身份要素）回归 —— 2026-09-21 重做

真实事故：同一套房换个写法再录一次就会重复建档。旧规则只比"标题归一化后是否一字不差"，
实测 9 种常见写法里 7 种漏判。本文件把两批用例固化：

* 批 A：同一套房的不同写法 → **必须**判重（旧规则下 7/9 漏判 → 改前必红）
* 批 B：不同房源 → **必须**放行（防误拦：同小区不同房号/楼栋/单元、面积差 2㎡、二期、不同小区）
* 疑似重复：同小区同面积但房号不全 → 照常录入 + 返回 suspected_duplicate 供 Coco 提示
* 批量扫描：deduplicate_properties 也要认出写法不同的同一套房
"""
import json

import pytest

from conftest import make_property

NEW_TITLE = "海口美兰区海甸岛恒大美丽沙 3 号楼 1 单元 1602"
NEW_AREA = 128.0

# (说明, 标题, 面积) —— 都是同一套房的写法差异
SAME_PROPERTY_VARIANTS = [
    ("完全相同", NEW_TITLE, 128),
    ("去掉片区词（海甸岛）", "海口美兰区恒大美丽沙 3 号楼 1 单元 1602", 128),
    ("只有小区+房号", "恒大美丽沙3号楼1单元1602", 128),
    ("小区简称「美丽沙」", "海甸岛美丽沙 3号楼1单元1602", 128),
    ("楼栋写成「3栋」", "海口美兰区海甸岛恒大美丽沙 3栋1单元1602", 128),
    ("房号带「室」", "海甸岛恒大美丽沙3号楼1单元1602室", 128),
    ("楼栋带「#」", "海甸岛恒大美丽沙 3#1单元1602", 128),
    ("标题里带楼层「16层1602」", "海甸岛恒大美丽沙 3号楼1单元16层1602", 128),
    ("面积口径差 0.5 ㎡", "海甸岛恒大美丽沙3号楼1单元1602", 128.5),
]

# (说明, 标题, 面积) —— 都是不同的房源，必须放行
DIFFERENT_PROPERTY_CASES = [
    ("同小区不同房号", "海甸岛恒大美丽沙 3号楼1单元1601", 128),
    ("同小区不同楼栋", "海甸岛恒大美丽沙 5号楼1单元1602", 128),
    ("同小区不同单元", "海甸岛恒大美丽沙 3号楼2单元1602", 128),
    ("同小区同房号、面积差 2 ㎡", "海甸岛恒大美丽沙 3号楼1单元1602", 130),
    ("同小区但属「二期」", "海甸岛恒大美丽沙二期3号楼1单元1602", 128),
    ("不同小区、房号与面积都相同", "保利中央海岸 3号楼1单元1602", 128),
    ("不同小区（名不相近）", "雅居乐金沙湾 8号楼2单元301", 128),
    ("房号带字母后缀（1602A ≠ 1602）", "海甸岛恒大美丽沙 3号楼1单元1602A", 128),
]


@pytest.mark.parametrize("label,old_title,old_area", SAME_PROPERTY_VARIANTS,
                         ids=[c[0] for c in SAME_PROPERTY_VARIANTS])
def test_same_property_different_wording_blocks(db, label, old_title, old_area):
    """同一套房换写法 → 判重（这是本次修的核心：旧规则漏判）"""
    make_property(db, title=old_title, area=old_area)
    dup = db.find_duplicate_property(title=NEW_TITLE, area=NEW_AREA)
    assert dup is not None, f"{label}：{old_title} 与 {NEW_TITLE} 应判为同一套"


@pytest.mark.parametrize("label,other_title,other_area", DIFFERENT_PROPERTY_CASES,
                         ids=[c[0] for c in DIFFERENT_PROPERTY_CASES])
def test_different_property_passes(db, label, other_title, other_area):
    """不同房源 → 放行（判重变严后最容易误拦的就是这些）"""
    make_property(db, title=other_title, area=other_area)
    dup = db.find_duplicate_property(title=NEW_TITLE, area=NEW_AREA)
    assert dup is None, f"{label}：{other_title} 是不同房源，不该被判重"


def test_tool_blocks_before_insert_and_force_still_works(db, monkeypatch):
    """工具层：判重命中 → 不落库；force=true 仍可强录（保留原行为）"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0, price=2_100_000)
    before = db.get_stats().get("available_properties", 0)

    out = json.loads(t.add_property(title=NEW_TITLE, price=2_200_000, area=128.0))
    assert out["success"] is False and out["duplicate"] is True, out
    assert out["existing_property"]["title"] == "恒大美丽沙3号楼1单元1602"
    assert db.get_stats().get("available_properties", 0) == before, "命中重复不得落库"

    forced = json.loads(t.add_property(title=NEW_TITLE, price=2_200_000, area=128.0, force=True))
    assert forced["success"] is True


def test_sold_property_still_ignored(db):
    """已售房源不参与判重（只认在售，保留原行为）"""
    make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0, status="sold")
    assert db.find_duplicate_property(title=NEW_TITLE, area=128.0) is None


def test_exclude_id_keeps_update_path_clean(db):
    """更新场景排除自身 id（保留原行为）"""
    p = make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0)
    assert db.find_duplicate_property(title=NEW_TITLE, area=128.0, exclude_id=p["id"]) is None


def test_suspected_duplicate_hints_without_blocking(db, monkeypatch):
    """房号不全时只提示不拦：照常录入 + 返回 suspected_duplicate"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    # 库里这条没写房号 → 新的这条带房号，无法确定是不是同一套 → 只提示
    make_property(db, title="海甸岛恒大美丽沙", area=128.0, price=2_100_000)

    out = json.loads(t.add_property(title=NEW_TITLE, price=2_200_000, area=128.0))
    assert out["success"] is True, out
    assert out["suspected_duplicate"]["area"] == 128.0
    assert "hint" in out["suspected_duplicate"]


def test_suspected_not_triggered_for_different_area_or_community(db):
    """疑似判定的边界：面积不同 / 小区不同 → 不给提示（少打扰）"""
    make_property(db, title="海甸岛恒大美丽沙 3号楼1单元", area=128.0)
    assert db.find_suspected_property(title="海甸岛恒大美丽沙 5号楼2单元", area=130.0) is None
    assert db.find_suspected_property(title="保利中央海岸 5号楼2单元", area=128.0) is None


def test_batch_scan_finds_variation_duplicates(db):
    """批量扫描：写法不同的同一套房也要认出来（旧实现按标题+面积+价格完全相同，抓不到）"""
    make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0, price=2_100_000)
    make_property(db, title=NEW_TITLE, area=128.5, price=2_200_000)
    make_property(db, title="保利中央海岸 3号楼1单元1602", area=128.0, price=2_300_000)

    groups = db.find_duplicate_properties()
    assert len(groups) == 1, groups
    assert len(groups[0]) == 2, groups
    # 保留最早录入的那条
    assert groups[0][0] < groups[0][1]


def test_deduplicate_tool_reports_and_cleans(db, monkeypatch):
    """deduplicate_properties：dry_run 先报明细，确认后只删重复项、保留最早那条"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    keep = make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0)
    dup = make_property(db, title=NEW_TITLE, area=128.5)

    dry = json.loads(t.deduplicate_properties(dry_run=True))
    assert dry["result"]["duplicate_groups"] == 1, dry
    assert dry["result"]["groups"][0]["keep_id"] == keep["id"]
    assert dry["result"]["groups"][0]["duplicate_ids"] == [dup["id"]]
    assert db.get_stats().get("available_properties", 0) == 2, "dry_run 不得真的删"

    done = json.loads(t.deduplicate_properties(dry_run=False))
    assert done["result"]["removable"] == [dup["id"]]
    assert db.get_stats().get("available_properties", 0) == 1


def test_cleanup_protects_owner_info(db, monkeypatch):
    """保守规则：重复项带业主信息、而保留项没有 → 跳过并写明原因（留着人工拍板）"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0)
    dup = make_property(db, title=NEW_TITLE, area=128.5)
    db.link_owner_to_property(dup["id"], name="陈志强", phone="13800000000")

    out = json.loads(t.deduplicate_properties(dry_run=False))
    assert out["result"]["removable"] == [], out
    assert out["result"]["skipped"][0]["id"] == dup["id"]
    assert "业主" in out["result"]["skipped"][0]["reason"]
    assert db.get_stats().get("available_properties", 0) == 2, "被保护的重复项不得被删"


def test_cleanup_protects_images(db, monkeypatch):
    """保守规则：重复项带图片、而保留项没有 → 同样跳过"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0)
    dup = make_property(db, title=NEW_TITLE, area=128.5, images="/tmp/a.jpg")

    out = json.loads(t.deduplicate_properties(dry_run=False))
    assert out["result"]["removable"] == [], out
    assert "图片" in out["result"]["skipped"][0]["reason"]
    assert db.get_stats().get("available_properties", 0) == 2


def test_cleanup_still_removes_plain_duplicate(db, monkeypatch):
    """反向：保留项本身有业主、重复项没有 → 照常清理（保护不能变成一律不动）"""
    import tools.real_estate_property as t
    monkeypatch.setattr(t, "_get_db", lambda: db)
    keep = make_property(db, title="恒大美丽沙3号楼1单元1602", area=128.0)
    db.link_owner_to_property(keep["id"], name="陈志强", phone="13800000000")
    dup = make_property(db, title=NEW_TITLE, area=128.5)

    out = json.loads(t.deduplicate_properties(dry_run=False))
    assert out["result"]["removable"] == [dup["id"]], out
    assert db.get_stats().get("available_properties", 0) == 1
