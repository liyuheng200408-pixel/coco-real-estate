"""房源建档去重测试（2026-08-29 加：按 小区名称(标题含房号)+面积 判重，录入前拦截）"""
import json

from conftest import make_property


class TestPropertyDedup:
    def test_duplicate_property_detected(self, db):
        """同名同面积在售房源 → 视为重复"""
        make_property(db, title="海阔天空国瑞城 15号楼1单元1703", area=138.0)
        dup = db.find_duplicate_property(title="海阔天空国瑞城 15号楼1单元1703", area=138.0)
        assert dup is not None
        assert dup["title"] == "海阔天空国瑞城 15号楼1单元1703"

    def test_different_area_not_duplicate(self, db):
        """同名但不同面积 → 不同期数/楼栋，不判重"""
        make_property(db, title="国瑞城 1号楼1单元1703", area=138.0)
        dup = db.find_duplicate_property(title="国瑞城 1号楼1单元1703", area=120.0)
        assert dup is None

    def test_sold_property_not_counted(self, db):
        """已售房源不参与判重（只认在售）"""
        make_property(db, title="国瑞城 15号楼1单元1703", area=138.0, status="sold")
        dup = db.find_duplicate_property(title="国瑞城 15号楼1单元1703", area=138.0)
        assert dup is None

    def test_exclude_id(self, db):
        """更新场景：排除自身 id"""
        p = make_property(db, title="国瑞城 15号楼1单元1703", area=138.0)
        dup = db.find_duplicate_property(title="国瑞城 15号楼1单元1703", area=138.0, exclude_id=p["id"])
        assert dup is None

    def test_tool_duplicate_blocks_before_insert(self, db, monkeypatch):
        """工具层：录入前命中重复 → duplicate=true 不落库；force=true 强制新增"""
        import tools.real_estate_property as t
        monkeypatch.setattr(t, "_get_db", lambda: db)
        # 先造一条在售
        make_property(db, title="国瑞城 15号楼1单元1703", area=138.0, price=2_550_000)
        count_before = db.get_stats().get("available_properties", 0)
        # 重复录入 → 应被拦
        out1 = json.loads(t.add_property(title="国瑞城 15号楼1单元1703", price=2_600_000, area=138.0))
        assert out1["success"] is False
        assert out1["duplicate"] is True
        assert out1["existing_property"]["title"] == "国瑞城 15号楼1单元1703"
        # 未新增（在售数不变）
        assert db.get_stats().get("available_properties", 0) == count_before
        # force=True → 强制新增
        out2 = json.loads(t.add_property(title="国瑞城 15号楼1单元1703", price=2_600_000, area=138.0, force=True))
        assert out2["success"] is True

    def test_duplicate_detected_title_variation(self, db):
        """标题格式不同(区名前缀/空格/逗号)也能判重（归一化后一致）"""
        make_property(db, title="海口美兰区桂林洋海阔天空, 7号楼2单元301", area=88.0)
        dup = db.find_duplicate_property(title="桂林洋海阔天空 7号楼2单元301", area=88.0)
        assert dup is not None
        assert dup["area"] == 88.0

    def test_different_unit_not_duplicate(self, db):
        """不同单元号 → 按归一化后仍不同，不判重"""
        make_property(db, title="海口美兰区桂林洋海阔天空, 7号楼2单元301", area=88.0)
        dup = db.find_duplicate_property(title="桂林洋海阔天空 8号楼2单元302", area=88.0)
        assert dup is None

    def test_normalize_title_unit(self):
        from agent.real_estate_db import _normalize_title
        a = _normalize_title("海口美兰区桂林洋海阔天空, 7号楼2单元301")
        b = _normalize_title("美兰区桂林洋海阔天空 7号楼2单元301")
        c = _normalize_title("海口市龙华区XX花园 1号楼1单元101")
        assert a == b == "海阔天空7号楼2单元301"
        assert c == "XX花园1号楼1单元101"
        assert a != _normalize_title("桂林洋海阔天空 8号楼2单元302")
