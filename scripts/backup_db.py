#!/usr/bin/env python3
"""
Coco 房产助理 - 数据库备份脚本（PostgreSQL 版）
支持定时自动备份、保留30天、数据变化检查、备份日志
使用 pg_dump 导出，恢复用 pg_restore
"""
import os
import subprocess
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path


def _load_db_config():
    """
    从 .env.db 或环境变量读取数据库配置
    优先级: 环境变量 DATABASE_URL > .env.db 文件
    """
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        return database_url

    # 尝试从 .env.db 读取
    candidates = [
        Path.home() / "hermes-agent" / ".env.db",
        Path.cwd() / ".env.db",
    ]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip()
    return ""


class DatabaseBackup:
    """PostgreSQL 数据库备份管理器"""

    def __init__(self, database_url: str = None, backup_dir: str = None):
        """
        初始化备份管理器

        Args:
            database_url: PostgreSQL 连接串（默认从 .env.db 读取）
            backup_dir: 备份目录（默认 ~/backups/real_estate/）
        """
        self.database_url = database_url or _load_db_config()
        if not self.database_url:
            raise RuntimeError("无法获取 DATABASE_URL，请检查 .env.db 或环境变量")

        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            self.backup_dir = Path.home() / "backups" / "real_estate"

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.backup_dir / "backup.log"
        self.hash_file = self.backup_dir / ".last_hash"

    def _log(self, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
        print(log_line)

    def _run_pg_dump(self, out_path: Path) -> bool:
        """执行 pg_dump 导出到文件"""
        env = os.environ.copy()
        env["PGPASSWORD"] = self._extract_password()
        cmd = [
            "pg_dump",
            "-Fc",  # 自定义格式，便于 pg_restore
            "--no-owner",
            "--no-privileges",
            "-f", str(out_path),
            self._extract_conn(),
        ]
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self._log(f"pg_dump 失败: {result.stderr.strip()[:500]}")
                return False
            return True
        except FileNotFoundError:
            self._log("错误: 未找到 pg_dump，请确认 postgresql-client 已安装")
            return False
        except subprocess.TimeoutExpired:
            self._log("错误: pg_dump 超时")
            return False

    def _extract_conn(self) -> str:
        """从 URL 提取连接串（去掉密码，pg_dump 用 PGPASSWORD）"""
        url = self.database_url
        if "@" in url:
            prefix, rest = url.split("@", 1)
            if ":" in prefix:
                scheme = prefix.split(":", 1)[0]
                return f"{scheme}://{rest}"
        return url

    def _extract_password(self) -> str:
        """从 URL 提取密码"""
        url = self.database_url
        if "@" in url:
            prefix = url.split("@", 1)[0]
            if ":" in prefix:
                parts = prefix.split(":", 2)
                if len(parts) == 3:
                    return parts[2]
        return ""

    def _get_db_snapshot(self) -> str:
        """计算数据库变化指纹（表行数 + 最大更新时间）"""
        env = os.environ.copy()
        env["PGPASSWORD"] = self._extract_password()
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
        try:
            result = subprocess.run(
                ["psql", self._extract_conn(), "-t", "-A", "-c", sql],
                env=env, capture_output=True, text=True, timeout=60,
            )
            tables = [t.strip() for t in result.stdout.splitlines() if t.strip()]
            if not tables:
                return "empty"
            # 每张表行数
            parts = []
            for t in tables:
                r = subprocess.run(
                    ["psql", self._extract_conn(), "-t", "-A", "-c",
                     f'SELECT count(*) FROM "{t}"'],
                    env=env, capture_output=True, text=True, timeout=60,
                )
                parts.append(f"{t}={r.stdout.strip()}")
            return "|".join(parts)
        except Exception as e:
            return f"error:{e}"

    def _has_changed(self) -> bool:
        """检查数据是否变化"""
        current = self._get_db_snapshot()
        if not self.hash_file.exists():
            return True
        last = self.hash_file.read_text(encoding="utf-8").strip()
        return current != last

    def _save_hash(self):
        """保存当前数据指纹"""
        self.hash_file.write_text(self._get_db_snapshot(), encoding="utf-8")

    def _cleanup_old_backups(self, keep_days: int = 30):
        """清理旧备份"""
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        for backup_file in self.backup_dir.glob("real_estate_*.dump"):
            try:
                date_str = backup_file.stem.replace("real_estate_", "")
                file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                if file_date < cutoff_date:
                    backup_file.unlink()
                    self._log(f"删除旧备份: {backup_file.name}")
            except ValueError:
                continue

    def backup(self, force: bool = False) -> bool:
        """执行备份"""
        self._log("=" * 50)
        self._log("开始数据库备份")

        # 检查数据变化
        if not force and not self._has_changed():
            self._log("数据无变化，跳过备份")
            return True

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"real_estate_{timestamp}.dump"
        backup_path = self.backup_dir / backup_filename

        try:
            if not self._run_pg_dump(backup_path):
                return False

            os.chmod(backup_path, 0o600)
            self._save_hash()
            self._cleanup_old_backups()

            file_size = backup_path.stat().st_size
            self._log(f"备份成功: {backup_filename} ({file_size} bytes)")
            return True

        except Exception as e:
            self._log(f"备份失败: {str(e)}")
            return False

    def restore(self, backup_filename: str) -> bool:
        """恢复备份"""
        backup_path = self.backup_dir / backup_filename
        if not backup_path.exists():
            self._log(f"错误: 备份文件不存在: {backup_filename}")
            return False

        env = os.environ.copy()
        env["PGPASSWORD"] = self._extract_password()

        # 先删除并重建数据库对象（用 --clean）
        cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-d", self._extract_conn(),
            str(backup_path),
        ]
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                self._log(f"恢复失败: {result.stderr.strip()[:500]}")
                return False
            self._save_hash()
            self._log(f"恢复成功: {backup_filename}")
            return True
        except FileNotFoundError:
            self._log("错误: 未找到 pg_restore，请确认 postgresql-client 已安装")
            return False
        except subprocess.TimeoutExpired:
            self._log("错误: pg_restore 超时")
            return False

    def list_backups(self) -> list:
        """列出所有备份"""
        backups = []
        for backup_file in sorted(self.backup_dir.glob("real_estate_*.dump"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return backups

    def get_status(self) -> dict:
        """获取备份状态"""
        backups = self.list_backups()
        return {
            "database_url": self._extract_conn(),
            "backup_dir": str(self.backup_dir),
            "total_backups": len(backups),
            "latest_backup": backups[0] if backups else None,
            "log_file": str(self.log_file),
        }


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Coco 房产助理 - PostgreSQL 数据库备份工具")
    parser.add_argument("action", choices=["backup", "restore", "list", "status"], help="操作类型")
    parser.add_argument("--db-url", default=None, help="PostgreSQL 连接串（默认读 .env.db）")
    parser.add_argument("--backup-dir", default=None, help="备份目录")
    parser.add_argument("--force", action="store_true", help="强制备份（忽略数据变化）")
    parser.add_argument("--restore-file", help="恢复指定备份文件")

    args = parser.parse_args()

    backup_mgr = DatabaseBackup(args.db_url, args.backup_dir)

    if args.action == "backup":
        exit(0 if backup_mgr.backup(force=args.force) else 1)
    elif args.action == "restore":
        if not args.restore_file:
            print("错误: 请指定 --restore-file 参数")
            exit(1)
        exit(0 if backup_mgr.restore(args.restore_file) else 1)
    elif args.action == "list":
        backups = backup_mgr.list_backups()
        if not backups:
            print("暂无备份")
        else:
            print(f"共 {len(backups)} 个备份：")
            for b in backups:
                print(f"  {b['filename']} ({b['size']} bytes) - {b['created']}")
    elif args.action == "status":
        status = backup_mgr.get_status()
        print("备份状态：")
        for k, v in status.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
