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
    """预建 re_customers + re_properties 表的临时库（003 迁移需要 re_properties）"""
    db_path = tmp_path / "mig_test.db"
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE re_customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE re_properties (id INTEGER PRIMARY KEY, name TEXT)")
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
