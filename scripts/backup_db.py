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
        """从 URL 提取连接串（去掉密码、保留用户名，pg_dump 用 PGPASSWORD 传密码）"""
        url = self.database_url
        if "@" in url:
            prefix, rest = url.split("@", 1)
            # prefix 形如 postgresql://user:password 或 postgresql://user
            if "://" in prefix:
                scheme, cred = prefix.split("://", 1)
                if ":" in cred:
                    user = cred.split(":", 1)[0]
                    return f"{scheme}://{user}@{rest}"
                return f"{scheme}://{cred}@{rest}"
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

            # 备份房源图片目录（tar.gz，与数据库备份同名）
            image_tar = self._backup_images(timestamp)
            if image_tar:
                file_size = backup_path.stat().st_size
                self._log(f"备份成功: {backup_filename} ({file_size} bytes) + 图片 {image_tar}")
            else:
                file_size = backup_path.stat().st_size
                self._log(f"备份成功: {backup_filename} ({file_size} bytes)")
            return True

        except Exception as e:
            self._log(f"备份失败: {str(e)}")
            return False

    def _backup_images(self, timestamp: str) -> str:
        """打包房源图片缓存目录到备份目录，返回 tar 文件名（无图片返回空字符串）"""
        import tarfile
        cache_candidates = [
            Path.home() / ".hermes" / "image_cache",          # 房源图片实际位置（海报/上传）
            Path.home() / ".hermes" / "cache" / "images",
            Path.home() / "hermes-agent" / ".hermes" / "cache" / "images",
        ]
        image_dir = None
        for cand in cache_candidates:
            if cand.exists() and any(cand.iterdir()):
                image_dir = cand
                break
        if image_dir is None:
            return ""
        tar_name = f"real_estate_images_{timestamp}.tar.gz"
        tar_path = self.backup_dir / tar_name
        try:
            with tarfile.open(tar_path, "w:gz") as tar:
                for img in image_dir.iterdir():
                    if img.is_file():
                        tar.add(img, arcname=f"images/{img.name}")
            os.chmod(tar_path, 0o600)
            return tar_name
        except Exception as e:
            self._log(f"图片备份失败: {e}")
            return ""

    def restore_images(self, image_tar_filename: str) -> bool:
        """恢复房源图片备份（tar.gz 解包到图片缓存目录）"""
        import tarfile
        tar_path = self.backup_dir / image_tar_filename
        if not tar_path.exists():
            self._log(f"错误: 图片备份不存在: {image_tar_filename}")
            return False
        cache_candidates = [
            Path.home() / ".hermes" / "image_cache",          # 房源图片实际位置（海报/上传）
            Path.home() / ".hermes" / "cache" / "images",
            Path.home() / "hermes-agent" / ".hermes" / "cache" / "images",
        ]
        target_dir = None
        for cand in cache_candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                if os.access(cand, os.W_OK):
                    target_dir = cand
                    break
            except Exception:
                continue
        if target_dir is None:
            self._log("错误: 找不到可写的图片缓存目录")
            return False
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        f = tar.extractfile(member)
                        if f:
                            data = f.read()
                            (target_dir / member.name.split("/")[-1]).write_bytes(data)
            count = len([p for p in target_dir.iterdir() if p.is_file()])
            self._log(f"图片恢复成功: {image_tar_filename} -> {target_dir} ({count} 张图片)")
            return True
        except Exception as e:
            self._log(f"图片恢复失败: {e}")
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

    def _restore_enc_key(self) -> bool:
        """从备份目录的 enc_key.txt 恢复加密密钥到 .env.db（已有则替换，无则追加）"""
        enc_key_file = self.backup_dir / "enc_key.txt"
        if not enc_key_file.exists():
            self._log("错误: 加密密钥备份不存在: enc_key.txt")
            return False

        new_key_line = None
        for line in enc_key_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("COCO_ENC_KEY=") and len(line.split("=", 1)[1].strip()) > 0:
                new_key_line = line
                break
        if not new_key_line:
            self._log("错误: enc_key.txt 中未找到有效的 COCO_ENC_KEY")
            return False

        env_db_candidates = [
            Path.home() / "hermes-agent" / ".env.db",
            Path.cwd() / ".env.db",
        ]
        env_db = None
        for cand in env_db_candidates:
            if cand.exists():
                env_db = cand
                break
        if env_db is None:
            self._log("错误: 未找到 .env.db，无法合并加密密钥")
            return False

        lines = env_db.read_text(encoding="utf-8").splitlines()
        replaced = False
        for i, line in enumerate(lines):
            if line.strip().startswith("COCO_ENC_KEY="):
                lines[i] = new_key_line
                replaced = True
                break
        if not replaced:
            lines.append(new_key_line)
        env_db.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            os.chmod(env_db, 0o600)
        except OSError:
            pass
        self._log(f"加密密钥已恢复并写入 {env_db}（{'替换' if replaced else '追加'}）")
        return True

    def restore_migration(self, backup_filename: str = None, images_filename: str = None,
                          migration_tar: str = None) -> bool:
        """迁移恢复：一条命令完成 数据库 + 图片 + 加密密钥 恢复

        Args:
            backup_filename: 数据库备份文件名（默认取备份目录最新 dump）
            images_filename: 图片备份文件名（默认取备份目录最新 images tar.gz）
            migration_tar: 迁移打包文件（coco_migration.tar.gz），若指定先解包到备份目录
        """
        if migration_tar:
            import tarfile
            tar_path = Path(migration_tar)
            if not tar_path.exists():
                self._log(f"错误: 迁移打包文件不存在: {migration_tar}")
                return False
            try:
                with tarfile.open(tar_path, "r:gz") as tar:
                    try:
                        tar.extractall(self.backup_dir, filter="data")
                    except TypeError:
                        # Python < 3.12 无 filter 参数，回退（迁移包为自产文件，风险可控）
                        tar.extractall(self.backup_dir)
                self._log(f"迁移包已解包到 {self.backup_dir}: {migration_tar}")
            except Exception as e:
                self._log(f"迁移包解包失败: {e}")
                return False

        if backup_filename is None:
            dumps = sorted(self.backup_dir.glob("real_estate_*.dump"))
            if not dumps:
                self._log("错误: 备份目录没有数据库备份文件")
                return False
            backup_filename = dumps[-1].name
        if images_filename is None:
            images = sorted(self.backup_dir.glob("real_estate_images_*.tar.gz"))
            if images:
                images_filename = images[-1].name

        self._log(f"迁移恢复开始: 数据库={backup_filename} 图片={images_filename or '无'}")

        # 顺序: 先恢复数据库, 再恢复图片, 最后恢复密钥
        if not self.restore(backup_filename):
            self._log("迁移恢复中止: 数据库恢复失败")
            return False

        if images_filename:
            if not self.restore_images(images_filename):
                self._log("迁移恢复中止: 图片恢复失败")
                return False
        else:
            self._log("提示: 未找到图片备份，跳过图片恢复")

        if not self._restore_enc_key():
            self._log("迁移恢复中止: 加密密钥恢复失败")
            return False

        self._log("迁移恢复完成: 数据库 + 图片 + 加密密钥 全部成功")
        print("============================================")
        print("迁移恢复完成！请执行以下步骤：")
        print("  1. sudo systemctl restart hermes-agent")
        print("  2. 给机器人发送\"你好\"，定时任务会自动注册")
        print("============================================")
        return True

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
    parser.add_argument("action", choices=["backup", "restore", "restore_migration", "list", "status"], help="操作类型")
    parser.add_argument("--db-url", default=None, help="PostgreSQL 连接串（默认读 .env.db）")
    parser.add_argument("--backup-dir", default=None, help="备份目录")
    parser.add_argument("--force", action="store_true", help="强制备份（忽略数据变化）")
    parser.add_argument("--restore-file", help="恢复指定备份文件")
    parser.add_argument("--images-file", help="迁移恢复时指定图片备份文件")
    parser.add_argument("--migration-tar", help="迁移打包文件路径（coco_migration.tar.gz），restore_migration 先解包再恢复")

    args = parser.parse_args()

    backup_mgr = DatabaseBackup(args.db_url, args.backup_dir)

    if args.action == "backup":
        exit(0 if backup_mgr.backup(force=args.force) else 1)
    elif args.action == "restore":
        if not args.restore_file:
            print("错误: 请指定 --restore-file 参数")
            exit(1)
        exit(0 if backup_mgr.restore(args.restore_file) else 1)
    elif args.action == "restore_migration":
        exit(0 if backup_mgr.restore_migration(
            backup_filename=args.restore_file,
            images_filename=args.images_file,
            migration_tar=args.migration_tar,
        ) else 1)
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
