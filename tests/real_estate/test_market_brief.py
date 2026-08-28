"""市场行情简报测试（功能10，批次七）——联网段 mock，不依赖外网"""
import json
from datetime import datetime, timedelta

from conftest import make_customer, make_property

from tools.real_estate_analytics import market_brief, weekly_market_report


class TestWeeklyReportRealStats:
    def test_new_listings_real_not_hardcoded(self, db, monkeypatch):
        """周报新增房源数来自真实统计（修掉原来的硬编码 5）"""
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        make_property(db)  # 今天录入 → 计入本周
        r = json.loads(weekly_market_report())
        assert r["report"]["新增房源"] == "1套"

    def test_empty_week_zero(self, db, monkeypatch):
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        r = json.loads(weekly_market_report())
        assert r["report"]["新增房源"] == "0套"


class TestMarketBrief:
    def test_own_stats_section(self, db, monkeypatch):
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        make_property(db)
        make_property(db, title="第二套")
        r = json.loads(market_brief())  # 不传 city → 跳过联网
        assert r["success"] is True
        assert r["stats"]["new_listings"] == 2
        assert "自家盘况" in r["message"]
        assert "网络检索" in r["message"]  # 声明来源

    def test_no_city_skips_web(self, db, monkeypatch):
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        r = json.loads(market_brief())
        assert "未指定城市" in r["message"]

    def test_web_failure_not_blocking(self, db, monkeypatch):
        """联网失败不阻塞简报生成"""
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        import builtins
        r = json.loads(market_brief(city="海口"))
        assert r["success"] is True
        assert "自家盘况" in r["message"]

    def test_advice_low_inventory(self, db, monkeypatch):
        """在售<10 套 → 建议补盘"""
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        make_property(db)
        r = json.loads(market_brief())
        assert "在售房源偏少" in r["message"]

    def test_advice_healthy(self, db, monkeypatch):
        """无异常 → 节奏健康（在售≥10 套才不提示补盘）"""
        monkeypatch.setattr("tools.real_estate_analytics._get_db", lambda: db)
        for i in range(10):
            make_property(db, title=f"在售房{i}", price=2_000_000 + i * 100_000, area=90.0)
        r = json.loads(market_brief())
        assert "节奏健康" in r["message"]
