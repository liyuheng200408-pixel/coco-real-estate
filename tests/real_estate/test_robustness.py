"""健壮性契约：模型漏传参数要得到可读提示；工具内部失败不能静默吞掉。

2026-09-18 加：①网关层必填参数校验（原先 handler 直接抛 TypeError，模型看到
"Tool execution failed" 转而自己编答案）；②add_property/update_property 里
"业主登记失败""自动匹配失败"原先静默吞掉，经纪人会以为登记好了。
"""
import json

from conftest import make_property


class TestRequiredParamValidation:
    def test_missing_required_returns_readable_error(self, db, monkeypatch):
        """漏传必填参数 → 返回"缺少必填参数：X"，而不是 TypeError 崩到模型面前"""
        import tools.real_estate_customer  # noqa: F401 —— 触发注册
        from tools.registry import registry
        out = json.loads(registry.dispatch("add_customer", {}))
        assert "error" in out
        assert "缺少必填参数" in out["error"]
        assert "name" in out["error"]
        assert "TypeError" not in out["error"]

    def test_no_validation_when_params_present(self, db, monkeypatch):
        """参数给全时正常执行（校验不误伤）"""
        import tools.real_estate_customer  # noqa: F401
        from tools.registry import registry
        monkeypatch.setattr("tools.real_estate_customer._get_db", lambda: db)
        out = json.loads(registry.dispatch("add_customer", {"name": "校验用客户"}))
        assert out.get("success") is True, out


class TestFailuresAreNotSwallowed:
    def test_owner_link_failure_is_surfaced(self, db, monkeypatch):
        """业主登记失败必须在返回里带 warning_owner（原先是静默吞掉）"""
        import tools.real_estate_property as tp
        monkeypatch.setattr(tp, "_get_db", lambda: db)
        def boom(*a, **kw):
            raise RuntimeError("模拟业主库写入失败")
        monkeypatch.setattr(db, "link_owner_to_property", boom)
        out = json.loads(tp.add_property(title="健壮性房源", price=1_000_000, area=90.0,
                                         owner_name="某业主", owner_phone="13800138000"))
        assert out["success"] is True
        assert "warning_owner" in out, out
        assert "业主信息登记失败" in out["warning_owner"]

    def test_match_failure_is_surfaced(self, db, monkeypatch):
        """自动匹配失败也要带 warning_match，而不是悄悄返回"无客户" """
        import tools.real_estate_property as tp
        monkeypatch.setattr(tp, "_get_db", lambda: db)
        def boom(*a, **kw):
            raise RuntimeError("模拟匹配失败")
        monkeypatch.setattr(db, "match_customers_for_property", boom)
        out = json.loads(tp.add_property(title="健壮性房源2", price=1_000_000, area=90.0))
        assert out["success"] is True
        assert "warning_match" in out, out
        assert "自动匹配客户失败" in out["warning_match"]

    def test_update_property_owner_failure_surfaced(self, db, monkeypatch):
        """更新房源时业主登记失败同样要带 warning_owner"""
        import tools.real_estate_property as tp
        monkeypatch.setattr(tp, "_get_db", lambda: db)
        p = make_property(db, title="待更新房源", price=1_000_000, area=90.0)
        def boom(*a, **kw):
            raise RuntimeError("模拟业主库写入失败")
        monkeypatch.setattr(db, "link_owner_to_property", boom)
        out = json.loads(tp.update_property(property_id=p["id"], owner_name="某业主"))
        assert out["success"] is True
        assert "warning_owner" in out, out
