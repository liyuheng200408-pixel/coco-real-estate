"""migrate.py 迁移机制测试：幂等、失败回滚、安全检查、状态查询"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE = REPO_ROOT / "scripts" / "migrate.py"


def run_migrate(db_url, *extra):
    return subprocess.run(
        [sys.executable, str(MIGRATE), "--database-url", db_url, *extra],
        capture_output=True, text=True, timeout=60,
    )


@pytest.fixture
def sqlite_db(tmp_path):
    """预建迁移会用到的表（003 需要 re_properties、011 需要 re_customer_changes）"""
    db_path = tmp_path / "mig_test.db"
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE re_customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE re_properties (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE re_deals (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE re_customer_changes (id INTEGER PRIMARY KEY, customer_id INTEGER,"
                 " field TEXT, old_value TEXT, new_value TEXT)")
    conn.commit()
    conn.close()
    return f"sqlite:///{db_path}"


def write_migration(tmp_path, name, sql):
    """往临时 migrations 目录写迁移文件"""
    migrations_dir = REPO_ROOT / "migrations"
    f = migrations_dir / name
    f.write_text(sql, encoding="utf-8")
    return f


class TestMigrate:
    def test_executes_pending_migration(self, sqlite_db, tmp_path):
        f = write_migration(tmp_path, "901_test_add_col.sql",
                            "ALTER TABLE re_customers ADD COLUMN phone VARCHAR(20);")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 0
            assert "901_test_add_col.sql" in r.stdout
            # 列真的加上了
            import sqlite3
            db_path = sqlite_db.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(re_customers)")]
            conn.close()
            assert "phone" in cols
        finally:
            f.unlink(missing_ok=True)

    def test_idempotent_second_run_skips(self, sqlite_db, tmp_path):
        """跑第二遍：已执行的跳过，不重复执行（幂等）"""
        f = write_migration(tmp_path, "902_test_skip.sql",
                            "ALTER TABLE re_customers ADD COLUMN tag VARCHAR(20);")
        try:
            assert run_migrate(sqlite_db).returncode == 0
            r2 = run_migrate(sqlite_db)
            assert r2.returncode == 0
            assert "数据库已是最新" in r2.stdout
        finally:
            f.unlink(missing_ok=True)

    def test_failure_stops_further_migrations(self, sqlite_db, tmp_path):
        """迁移失败：立即中止，后续迁移不再执行（sqlite 的 DDL 隐式提交
        无法回滚 ALTER；PostgreSQL 生产机上同一机制会整体回滚，事务语义不变）"""
        f_bad = write_migration(
            tmp_path, "903_test_bad.sql",
            "ALTER TABLE nonexistent_table ADD COLUMN x INT;")
        f_after = write_migration(
            tmp_path, "904_test_never_runs.sql",
            "ALTER TABLE re_customers ADD COLUMN never_col VARCHAR(10);")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 2
            assert "迁移中止" in r.stderr
            import sqlite3
            conn = sqlite3.connect(sqlite_db.replace("sqlite:///", ""))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(re_customers)")]
            hist = conn.execute("SELECT COUNT(*) FROM migrations_history").fetchone()[0]
            conn.close()
            assert "never_col" not in cols   # 后续迁移没有跑
            # 002_price_history.sql（真实迁移）会先成功执行并记账，
            # 所以只断言"失败的 903 没有记账"（904 因中止也没跑）
            conn = sqlite3.connect(sqlite_db.replace("sqlite:///", ""))
            bad_recorded = conn.execute(
                "SELECT COUNT(*) FROM migrations_history WHERE seq >= 903"
            ).fetchone()[0]
            conn.close()
            assert bad_recorded == 0
        finally:
            f_bad.unlink(missing_ok=True)
            f_after.unlink(missing_ok=True)

    def test_forbidden_drop_table_rejected(self, sqlite_db, tmp_path):
        """DROP TABLE 被安全检查拒绝，不执行"""
        f = write_migration(tmp_path, "904_test_drop.sql",
                            "DROP TABLE re_customers;")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 2
            assert "DROP TABLE" in r.stderr
        finally:
            f.unlink(missing_ok=True)

    def test_drop_column_rejected_without_optin(self, sqlite_db, tmp_path):
        """未声明 -- migrate:allow-drop-column 的删列语句仍被拒绝（护栏不开口子）"""
        f = write_migration(tmp_path, "906_test_drop_col.sql",
                            "ALTER TABLE re_properties DROP COLUMN name;")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 2
            assert "DROP COLUMN" in r.stderr or "ALTER ... DROP" in r.stderr
            import sqlite3
            conn = sqlite3.connect(sqlite_db.replace("sqlite:///", ""))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(re_properties)")]
            conn.close()
            assert "name" in cols  # 列还在，没被删
        finally:
            f.unlink(missing_ok=True)

    def test_drop_column_allowed_with_optin(self, sqlite_db, tmp_path):
        """显式声明后允许删列（清理用不上的遗留列）"""
        f = write_migration(tmp_path, "907_test_drop_col_ok.sql",
                            "-- migrate:allow-drop-column\n"
                            "ALTER TABLE re_properties DROP COLUMN name;")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 0
            import sqlite3
            conn = sqlite3.connect(sqlite_db.replace("sqlite:///", ""))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(re_properties)")]
            conn.close()
            assert "name" not in cols  # 列真的删了
        finally:
            f.unlink(missing_ok=True)

    def test_drop_column_idempotent_when_missing(self, sqlite_db, tmp_path):
        """列已不存在时跳过（重跑安全；SQLite 没有 DROP COLUMN IF EXISTS）"""
        f = write_migration(tmp_path, "908_test_drop_col_missing.sql",
                            "-- migrate:allow-drop-column\n"
                            "ALTER TABLE re_properties DROP COLUMN never_existed;")
        try:
            r = run_migrate(sqlite_db)
            assert r.returncode == 0
            assert "不存在" in r.stdout
        finally:
            f.unlink(missing_ok=True)

    def test_status_only(self, sqlite_db, tmp_path):
        """--status 只看状态不执行"""
        f = write_migration(tmp_path, "905_test_status.sql",
                            "ALTER TABLE re_customers ADD COLUMN s VARCHAR(5);")
        try:
            r = run_migrate(sqlite_db, "--status")
            assert r.returncode == 0
            assert "待执行" in r.stdout
            # status 模式不实际执行
            import sqlite3
            conn = sqlite3.connect(sqlite_db.replace("sqlite:///", ""))
            # migrations_history 可能已建，但迁移未跑
            hist = conn.execute("SELECT COUNT(*) FROM migrations_history").fetchone()[0]
            conn.close()
            assert hist == 0
        finally:
            f.unlink(missing_ok=True)

    def test_011_masks_plaintext_contacts_in_change_history(self, sqlite_db):
        """011 迁移：变更历史里的明文手机号/微信换成掩码，非加密字段不动，重跑安全"""
        import sqlite3
        db_path = sqlite_db.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO re_customer_changes (customer_id, field, old_value, new_value)"
                     " VALUES (1, 'phone', '13922220001', '13922220002')")
        conn.execute("INSERT INTO re_customer_changes (customer_id, field, old_value, new_value)"
                     " VALUES (1, 'wechat', 'mm_wx', 'mm_wx2')")
        conn.execute("INSERT INTO re_customer_changes (customer_id, field, old_value, new_value)"
                     " VALUES (1, 'budget_max', '3000000', '5000000')")
        conn.commit()
        conn.close()

        assert run_migrate(sqlite_db).returncode == 0
        assert run_migrate(sqlite_db).returncode == 0      # 再跑一遍：幂等

        conn = sqlite3.connect(db_path)
        rows = {f: (o, n) for f, o, n in conn.execute(
            "SELECT field, old_value, new_value FROM re_customer_changes")}
        conn.close()
        assert rows["phone"] == ("139****0001", "139****0002"), rows
        assert rows["wechat"] == ("mm****", "mm****"), rows
        assert rows["budget_max"] == ("3000000", "5000000"), rows   # 非加密字段不被改
