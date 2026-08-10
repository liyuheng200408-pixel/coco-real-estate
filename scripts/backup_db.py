#!/usr/bin/env python3
"""
Coco 房产助理 - 数据库备份脚本
支持定时自动备份、保留30天、数据变化检查、备份日志
"""
import os
import shutil
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path


class DatabaseBackup:
    """数据库备份管理器"""
    
    def __init__(self, db_path: str, backup_dir: str = None):
        """
        初始化备份管理器
        
        Args:
            db_path: 数据库文件路径
            backup_dir: 备份目录（默认 ~/backups/real_estate/）
        """
        self.db_path = Path(db_path)
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            self.backup_dir = Path.home() / "backups" / "real_estate"
        
        # 创建备份目录
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 备份日志
        self.log_file = self.backup_dir / "backup.log"
        
        # 数据哈希文件（用于检测变化）
        self.hash_file = self.backup_dir / ".last_hash"
    
    def _log(self, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)
        
        print(log_line.strip())
    
    def _get_file_hash(self) -> str:
        """计算文件哈希"""
        if not self.db_path.exists():
            return ""
        
        hash_md5 = hashlib.md5()
        with open(self.db_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _has_changed(self) -> bool:
        """检查数据是否变化"""
        current_hash = self._get_file_hash()
        
        if not self.hash_file.exists():
            return True
        
        last_hash = self.hash_file.read_text().strip()
        return current_hash != last_hash
    
    def _save_hash(self):
        """保存当前哈希"""
        current_hash = self._get_file_hash()
        self.hash_file.write_text(current_hash)
    
    def _cleanup_old_backups(self, keep_days: int = 30):
        """清理旧备份"""
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        for backup_file in self.backup_dir.glob("real_estate_*.db"):
            # 从文件名提取日期
            try:
                date_str = backup_file.stem.replace("real_estate_", "")
                file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                
                if file_date < cutoff_date:
                    backup_file.unlink()
                    self._log(f"删除旧备份: {backup_file.name}")
            except ValueError:
                continue
    
    def backup(self, force: bool = False) -> bool:
        """
        执行备份
        
        Args:
            force: 强制备份（忽略数据变化检查）
        
        Returns:
            bool: 是否成功
        """
        self._log("=" * 50)
        self._log("开始数据库备份")
        
        # 检查数据库文件
        if not self.db_path.exists():
            self._log(f"错误: 数据库文件不存在: {self.db_path}")
            return False
        
        # 检查数据变化
        if not force and not self._has_changed():
            self._log("数据无变化，跳过备份")
            return True
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"real_estate_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename
        
        try:
            # 执行备份
            shutil.copy2(self.db_path, backup_path)
            
            # 设置权限
            os.chmod(backup_path, 0o600)
            
            # 保存哈希
            self._save_hash()
            
            # 清理旧备份
            self._cleanup_old_backups()
            
            # 记录日志
            file_size = backup_path.stat().st_size
            self._log(f"备份成功: {backup_filename} ({file_size} bytes)")
            
            return True
            
        except Exception as e:
            self._log(f"备份失败: {str(e)}")
            return False
    
    def restore(self, backup_filename: str) -> bool:
        """
        恢复备份
        
        Args:
            backup_filename: 备份文件名
        
        Returns:
            bool: 是否成功
        """
        backup_path = self.backup_dir / backup_filename
        
        if not backup_path.exists():
            self._log(f"错误: 备份文件不存在: {backup_filename}")
            return False
        
        try:
            # 备份当前数据库
            current_backup = self.db_path.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
            if self.db_path.exists():
                shutil.copy2(self.db_path, current_backup)
                self._log(f"当前数据库已备份到: {current_backup.name}")
            
            # 恢复备份
            shutil.copy2(backup_path, self.db_path)
            os.chmod(self.db_path, 0o600)
            
            self._log(f"恢复成功: {backup_filename}")
            return True
            
        except Exception as e:
            self._log(f"恢复失败: {str(e)}")
            return False
    
    def list_backups(self) -> list:
        """列出所有备份"""
        backups = []
        for backup_file in sorted(self.backup_dir.glob("real_estate_*.db"), reverse=True):
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
            "database_path": str(self.db_path),
            "database_exists": self.db_path.exists(),
            "backup_dir": str(self.backup_dir),
            "total_backups": len(backups),
            "latest_backup": backups[0] if backups else None,
            "log_file": str(self.log_file),
        }


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Coco 房产助理 - 数据库备份工具")
    parser.add_argument("action", choices=["backup", "restore", "list", "status"], help="操作类型")
    parser.add_argument("--db-path", default=os.path.expanduser("~/hermes-agent/real_estate.db"), help="数据库路径")
    parser.add_argument("--backup-dir", default=None, help="备份目录")
    parser.add_argument("--force", action="store_true", help="强制备份（忽略数据变化）")
    parser.add_argument("--restore-file", help="恢复指定备份文件")
    
    args = parser.parse_args()
    
    # 初始化备份管理器
    backup_mgr = DatabaseBackup(args.db_path, args.backup_dir)
    
    if args.action == "backup":
        success = backup_mgr.backup(force=args.force)
        exit(0 if success else 1)
    
    elif args.action == "restore":
        if not args.restore_file:
            print("错误: 请指定 --restore-file 参数")
            exit(1)
        success = backup_mgr.restore(args.restore_file)
        exit(0 if success else 1)
    
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
