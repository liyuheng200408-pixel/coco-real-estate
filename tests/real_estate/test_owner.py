"""房东委托管理测试（功能7，批次六）"""
import json
from datetime import datetime, timedelta

from conftest import make_customer, make_property


def _add_owner(db, name="房东王五", **kw):
    return db.add_owner(name=name, **kw)


# ==================== 房东增查 ====================

class TestOwnerCRUD:
    def test_add_and_get(self, db):
        o = _add_owner(db, phone="13800001111")
        got = db.get_owner(o["id"])
        assert got["name"] == "房东王五"
        assert got["phone"] == "13800001111"  # EncryptedString 读取自动解密

    def test_get_nonexistent(self, db):
        assert db.get_owner(99999) is None

    def test_id_masking(self, db):
        """身份证只存脱敏版本（脱敏在工具层 _mask_id 完成）"""
        from tools.real_estate_owner import _mask_id
        o = _add_owner(db, id_masked=_mask_id("460005199001011234"))
        assert o["id_masked"] == "4600**********1234"
        assert "199001011234" not in (o["id_masked"] or "")

    def test_list(self, db):
        _add_owner(db, name="房东A")
        _add_owner(db, name="房东B")
        owners = db.list_owners()
        assert {o["name"] for o in owners} >= {"房东A", "房东B"}


# ==================== 组合查询 ====================

class TestOwnerPortfolio:
    def test_portfolio_with_stats(self, db):
        o = _add_owner(db)
        p1 = make_property(db, title="在售房", price=3_000_000, area=100.0)
        p2 = make_property(db, title="已售房", price=4_000_000, area=120.0, status="sold")
        db.update_property(p1["id"], owner_id=o["id"])
        db.update_property(p2["id"], owner_id=o["id"])
        result = db.owner_portfolio(o["id"])
        assert result["stats"]["total"] == 2
        assert result["stats"]["available"] == 1
        assert result["stats"]["dealed"] == 1

    def test_portfolio_nonexistent(self, db):
        assert db.owner_portfolio(99999) is None


# ==================== 独家委托到期 ====================

class TestExclusiveExpiring:
    def test_expiring_within_window(self, db):
        o = _add_owner(db)
        p = make_property(db, title="快到期独家")
        deadline = datetime.now() + timedelta(days=15)
        db.update_property(p["id"], owner_id=o["id"], exclusive_until=deadline)
        items = db.exclusive_expiring(days=30)
        assert len(items) == 1
        assert "天" in items[0]["urgency"] and "已过期" not in items[0]["urgency"]

    def test_expired_flagged(self, db):
        o = _add_owner(db)
        p = make_property(db, title="已过期独家")
        db.update_property(p["id"], owner_id=o["id"],
                           exclusive_until=datetime.now() - timedelta(days=5))
        items = db.exclusive_expiring(days=30)
        assert items[0]["urgency"] == "已过期"

    def test_far_future_not_listed(self, db):
        o = _add_owner(db)
        p = make_property(db)
        db.update_property(p["id"], owner_id=o["id"],
                           exclusive_until=datetime.now() + timedelta(days=90))
        assert db.exclusive_expiring(days=30) == []

    def test_none_exclusive_excluded(self, db):
        o = _add_owner(db)
        make_property(db, owner_id=None)
        assert db.exclusive_expiring(days=30) == []


# ==================== 工具层 ====================

class TestOwnerTools:
    def test_add_owner_tool_masks_id(self, db, monkeypatch):
        import tools.real_estate_owner as omod
        monkeypatch.setattr(omod, "_get_db", lambda: db)
        r = json.loads(omod.add_owner(name="房东赵六", id_number="110101200001015678",
                                      phone="13900002222"))
        assert r["success"] is True
        assert r["owner"]["id_masked"].startswith("1101")
        assert "20000101" not in r["owner"]["id_masked"]  # 原生日不出现

    def test_portfolio_tool(self, db, monkeypatch):
        import tools.real_estate_owner as omod
        monkeypatch.setattr(omod, "_get_db", lambda: db)
        o = _add_owner(db)
        p = make_property(db, price=3_000_000, area=100.0)
        db.update_property(p["id"], owner_id=o["id"],
                           viewing_note="钥匙在门店，随时可看")
        r = json.loads(omod.owner_portfolio(owner_id=o["id"]))
        assert r["success"] is True
        assert "钥匙在门店" in r["message"]


# ==================== 按房源反查业主（2026-08-30 加） ====================

class TestPropertyOwnerLookup:
    def test_property_owner_linked(self, db):
        """房源关联业主后，get_property_owners 反向查得业主姓名/电话/微信"""
        o = _add_owner(db, name="房东张三", phone="13800138000", wechat="zs_wx")
        p = make_property(db, price=3_000_000, area=100.0)
        db.update_property(p["id"], owner_id=o["id"])
        rows = db.get_property_owners([p["id"]])
        assert len(rows) == 1
        assert rows[0]["id"] == p["id"]
        assert rows[0]["owner"]["name"] == "房东张三"
        assert rows[0]["owner"]["phone"] == "13800138000"  # EncryptedString 读出即明文

    def test_property_owner_not_linked(self, db):
        """房源未关联业主时，get_property_owners 返回 owner=None（不报错不编造）"""
        p = make_property(db, price=3_000_000, area=100.0)  # 无 owner
        rows = db.get_property_owners([p["id"]])
        assert len(rows) == 1
        assert rows[0]["owner"] is None

    def test_property_owner_multiple_truncated(self, db):
        """一次传超过 3 套，db 层截断只返回前 3 套（工具层另有 3 套上限提示）"""
        o = _add_owner(db, name="房东A")
        ps = [make_property(db, title=f"房{i}", price=2_000_000 + i, area=80.0 + i)
              for i in range(5)]
        for p in ps:
            db.update_property(p["id"], owner_id=o["id"])
        rows = db.get_property_owners([p["id"] for p in ps])
        assert len(rows) == 3  # 截断到 3

    def test_property_owner_tool_masks_phone(self, db, monkeypatch):
        """工具层：业主电话按老板要求脱敏展示（前3后4打星）"""
        import tools.real_estate_owner as omod
        monkeypatch.setattr(omod, "_get_db", lambda: db)
        assert omod._mask_phone("13800138000") == "138****8000"
        assert omod._mask_phone(None) is None
