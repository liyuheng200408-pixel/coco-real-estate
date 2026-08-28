"""客户管理测试：敏感字段加密、等级约束、变更历史、生日查询"""
import base64

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import make_customer, make_property


def _fernet_key() -> str:
    raw = b"coco-test-enc-key-32bytes-fixed-xyz!"
    return base64.urlsafe_b64encode(raw).decode()


# ==================== 敏感字段加密 ====================

class TestEncryptedFields:
    def test_phone_stored_encrypted(self, enc_db, tmp_path, monkeypatch):
        """配置密钥时，手机号在库里必须是密文"""
        c = make_customer(enc_db, phone="13800008001")
        # 绕过 ORM，直接读 sqlite 原始字节
        import sqlite3
        raw_path = str(tmp_path / "re_test_enc.db")
        conn = sqlite3.connect(raw_path)
        stored = conn.execute(
            "SELECT phone FROM re_customers WHERE id=?", (c["id"],)
        ).fetchone()[0]
        conn.close()
        assert stored != "13800008001"      # 不是明文
        assert "13800008001" not in stored

    def test_phone_roundtrip_decrypted(self, enc_db):
        """加密存储后读取自动解密回明文"""
        c = make_customer(enc_db, phone="13800008001", wechat="wx_abc123")
        got = enc_db.get_customer(c["id"])
        assert got["phone"] == "13800008001"
        assert got["wechat"] == "wx_abc123"

    def test_plaintext_mode_without_key(self, db):
        """无密钥时明文存取（兼容旧部署）"""
        c = make_customer(db, phone="13900009002")
        got = db.get_customer(c["id"])
        assert got["phone"] == "13900009002"

    def test_legacy_plaintext_data_still_readable(self, tmp_path, monkeypatch):
        """历史明文数据 + 现在配置了密钥 → 读取不崩溃，原样返回"""
        import sqlite3
        raw_path = str(tmp_path / "re_legacy.db")
        # 第一步：无密钥写入明文
        from agent.real_estate_db import RealEstateDB
        legacy_db = RealEstateDB(f"sqlite:///{raw_path}")
        c = legacy_db.add_customer(name="旧客户", phone="13700007003")
        assert legacy_db.get_customer(c["id"])["phone"] == "13700007003"

        # 第二步：同一库，配置密钥后读取（模拟生产升级场景）
        monkeypatch.setenv("COCO_ENC_KEY", _fernet_key())
        upgraded_db = RealEstateDB(f"sqlite:///{raw_path}")
        got = upgraded_db.get_customer(c["id"])
        assert got["phone"] == "13700007003"  # 解密失败回退原值，不崩溃

    def test_wrong_key_falls_back_not_crash(self, enc_db, monkeypatch):
        """密钥错误时读取返回密文原值而非抛异常"""
        c = enc_db.get_customer(make_customer(enc_db, phone="13600006004")["id"])
        assert c["phone"] == "13600006004"
        # 换一把错误密钥
        wrong = base64.urlsafe_b64encode(b"other-key-32bytes-fixed-abcd5678!").decode()
        monkeypatch.setenv("COCO_ENC_KEY", wrong)
        got = enc_db.get_customer(c["id"])
        assert isinstance(got["phone"], str)  # 不抛异常


# ==================== 等级与约束 ====================

class TestTier:
    def test_default_tier_c(self, db):
        c = db.add_customer(name="新客")
        assert c["tier"] == "C"

    def test_valid_tiers(self, db):
        for tier in ("S", "A", "B", "C"):
            c = make_customer(db, name=f"客户{tier}", tier=tier)
            assert c["tier"] == tier

    def test_invalid_tier_rejected(self, db):
        """数据库层 CheckConstraint 挡住非法等级"""
        with pytest.raises(IntegrityError):
            db.add_customer(name="坏等级", tier="X")

    def test_update_tier(self, db):
        c = make_customer(db, tier="C")
        db.update_customer(c["id"], tier="S")
        assert db.get_customer(c["id"])["tier"] == "S"


# ==================== 变更历史 ====================

class TestChangeHistory:
    def test_budget_change_recorded(self, db):
        c = make_customer(db, budget_max=5_000_000)
        db.update_customer(c["id"], budget_max=6_000_000)
        changes = db.get_customer_changes(c["id"])
        assert len(changes) == 1
        assert changes[0]["field"] == "budget_max"
        assert changes[0]["old_value"] == "5000000"
        assert changes[0]["new_value"] == "6000000"

    def test_no_change_no_record(self, db):
        c = make_customer(db, tier="C")
        db.update_customer(c["id"], tier="C")  # 同值不改
        assert db.get_customer_changes(c["id"]) == []

    def test_history_desc_order(self, db):
        c = make_customer(db)
        db.update_customer(c["id"], tier="B")
        db.update_customer(c["id"], tier="A")
        changes = db.get_customer_changes(c["id"])
        assert [ch["field"] for ch in changes] == ["tier", "tier"]
        assert changes[0]["new_value"] == "A"  # 最新在前


# ==================== 生日查询 ====================

class TestBirthday:
    def test_birthday_filter(self, db):
        make_customer(db, name="八月寿星", birthday="1990-08-15")
        make_customer(db, name="九月寿星", birthday="1985-09-20")
        result = db.get_birthday_customers(month=8)
        assert len(result) == 1
        assert result[0]["name"] == "八月寿星"

    def test_month_day_filter(self, db):
        make_customer(db, name="今天生日", birthday="1990-08-15")
        make_customer(db, name="同月不同日", birthday="1985-08-20")
        result = db.get_birthday_customers(month=8, day=15)
        assert [c["name"] for c in result] == ["今天生日"]

    def test_no_birthday_excluded(self, db):
        make_customer(db, name="没填生日")
        assert db.get_birthday_customers(month=8) == []


# ==================== 基础增删查 ====================

class TestCustomerCRUD:
    def test_add_and_get(self, db):
        c = make_customer(db, name="张三")
        got = db.get_customer(c["id"])
        assert got["name"] == "张三"
        assert got["status"] == "active"

    def test_get_nonexistent(self, db):
        assert db.get_customer(99999) is None

    def test_list_filter_by_tier(self, db):
        make_customer(db, name="S客户", tier="S")
        make_customer(db, name="C客户", tier="C")
        s_list = db.list_customers(tier="S")
        assert [c["name"] for c in s_list] == ["S客户"]

    def test_list_filter_by_type(self, db):
        make_customer(db, name="租客", customer_type="rent")
        make_customer(db, name="买家", customer_type="buy_second_hand")
        renters = db.list_customers(customer_type="rent")
        assert [c["name"] for c in renters] == ["租客"]
