"""带看反馈反哺房源缺陷标签测试（功能3，批次四）"""
import json

from conftest import make_customer, make_property


def _view_and_feedback(db, customer_name, property_id, feedback, result="not_interested"):
    from datetime import datetime
    c = make_customer(db, name=customer_name)
    v = db.add_viewing(
        customer_id=c["id"], property_id=property_id,
        viewing_time=datetime(2026, 8, 20, 10, 0), status="scheduled",
    )
    db.update_viewing(v["id"], status="done", result=result, feedback=feedback)


# ==================== 缺陷标签生成 ====================

class TestDefectTags:
    def test_two_mentions_tagged(self, db):
        """同一缺陷被 2 组客户提及 → 打标签"""
        p = make_property(db)
        _view_and_feedback(db, "客户甲", p["id"], "采光太差了，白天都要开灯")
        _view_and_feedback(db, "客户乙", p["id"], "屋里暗，采光不好")
        defects = db.refresh_defect_tags(p["id"])
        assert "采光差" in defects

    def test_single_mention_not_tagged(self, db):
        """只有 1 组客户提及 → 不打标签（阈值=2）"""
        p = make_property(db)
        _view_and_feedback(db, "客户甲", p["id"], "有点吵，临街")
        assert db.refresh_defect_tags(p["id"]) == []

    def test_same_customer_counted_once(self, db):
        """同一客户一条反馈里重复说"吵"，只算1组"""
        p = make_property(db)
        _view_and_feedback(db, "客户甲", p["id"], "很吵，临街噪音太吵了")
        assert db.refresh_defect_tags(p["id"]) == []

    def test_multiple_defects(self, db):
        """多个缺陷同时命中"""
        p = make_property(db)
        _view_and_feedback(db, "客户甲", p["id"], "采光差，而且临街很吵")
        _view_and_feedback(db, "客户乙", p["id"], "又暗又吵，楼下有漏水痕迹")
        _view_and_feedback(db, "客户丙", p["id"], "卫生间漏水")
        defects = db.refresh_defect_tags(p["id"])
        assert "采光差" in defects
        assert "临街吵" in defects
        assert "漏水" in defects   # 2次提及（乙丙）达标

    def test_cancelled_viewing_not_counted(self, db):
        """取消的带看不计入"""
        p = make_property(db)
        from datetime import datetime
        c = make_customer(db, name="没去的")
        v = db.add_viewing(customer_id=c["id"], property_id=p["id"],
                           viewing_time=datetime(2026, 8, 20, 10, 0), status="cancelled",
                           )
        db.update_viewing(v["id"], status="cancelled", feedback="听朋友说采光差")
        assert db.refresh_defect_tags(p["id"]) == []


# ==================== 匹配降权 ====================

class TestDefectDownweight:
    def test_defect_property_downweighted(self, db):
        """有缺陷标签的房源评分×0.8，且理由里透明标注"""
        c = make_customer(db, budget_min=3_000_000, budget_max=5_000_000,
                          area_pref="90-120", layout_pref="3室2厅",
                          location="美兰区", customer_type="buy_second_hand")
        make_property(db)  # 干净房
        dirty = make_property(db, title="有缺陷的", community="缺陷小区",
                              price=3_800_000)
        import json as _json
        db.update_property(dirty["id"], **{})  # 触发一次空更新确保无副作用
        # 手动打标签
        from agent.real_estate_db import Property
        with db.get_session() as s:
            prop = s.query(Property).get(dirty["id"])
            prop.defect_tags = _json.dumps({"采光差": 3, "临街吵": 2}, ensure_ascii=False)
            s.commit()

        matches = db.match_property(c["id"])
        clean = [m for m in matches if m["title"].startswith("测试房源")]
        dirty_m = [m for m in matches if m["title"] == "有缺陷的"]
        if clean and dirty_m:
            assert clean[0]["score"] > dirty_m[0]["score"]
        if dirty_m:
            reasons = " ".join(dirty_m[0]["match_reasons"])
            assert "客户反馈" in reasons
            assert "采光差" in reasons


# ==================== 清除标签 ====================

class TestClearDefect:
    def test_clear_tag(self, db):
        p = make_property(db)
        with db.get_session() as s:
            from agent.real_estate_db import Property
            prop = s.query(Property).get(p["id"])
            import json as _json
            prop.defect_tags = _json.dumps({"采光差": 3}, ensure_ascii=False)
            s.commit()
        assert db.clear_defect_tag(p["id"], "采光差") is True
        props = db.search_properties(limit=100)
        target = [x for x in props if x["id"] == p["id"]][0]
        assert not target["defect_tags"]  # None 或空均算已清空

    def test_clear_nonexistent_tag(self, db):
        p = make_property(db)
        assert db.clear_defect_tag(p["id"], "不存在的") is False


# ==================== 工具层 ====================

class TestDefectTools:
    def test_record_viewing_triggers_refresh(self, db, monkeypatch):
        """record_viewing 带 feedback → 自动刷新缺陷标签"""
        import tools.real_estate_viewing as vmod
        monkeypatch.setattr(vmod, "_get_db", lambda: db)
        from datetime import datetime
        c = make_customer(db, name="带看客户")
        p = make_property(db, price=2_000_000, area=80.0)
        v = db.add_viewing(customer_id=c["id"], property_id=p["id"],
                           viewing_time=datetime(2026, 8, 20, 10, 0), status="scheduled")
        # 两个客户都吐槽采光
        _view_and_feedback(db, "另一位", p["id"], "采光差")
        r = json.loads(vmod.record_viewing(viewing_id=v["id"], status="done",
                                           result="not_interested", feedback="屋里太暗采光差"))
        assert r["success"] is True
        assert r.get("defect_tags_updated") == ["采光差"]
