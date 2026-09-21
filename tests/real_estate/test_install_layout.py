"""安装布局变更的回归测试（老板 2026-09-21 拍板 ①+②）：

  ① `hermes` 命令不再对外暴露（统一用 coco）——install.sh 不建软链、update.sh 每次清理；
  ② 安装目录 ~/hermes-agent → ~/coco，脚本自定位（按自身位置推导），老实例可 `coco migrate-path` 搬迁。

全部用临时假环境，不动真机器。
"""
import os
import re
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO_ROOT, env=env)


class TestInstallLayout:
    def test_install_sh_uses_coco_dir(self):
        t = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        assert 'INSTALL_DIR="${COCO_INSTALL_DIR:-$HOME/coco}"' in t, "默认安装目录应为 ~/coco"
        assert 'INSTALL_DIR="$HOME/hermes-agent"' not in t, "不应再默认装到 ~/hermes-agent"

    def test_install_sh_no_longer_exposes_hermes(self):
        t = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        assert "COCO_EXPOSE_HERMES" in t, "应保留显式开关"
        # 无条件创建 hermes 软链的代码必须消失：所有创建动作都要落在这个开关分支里
        for m in re.finditer(r'ln -sf "\$HERMES_BIN" /usr/local/bin/hermes', t):
            head = t[max(0, m.start() - 900):m.start()]
            assert "COCO_EXPOSE_HERMES" in head, "存在未受开关保护的 hermes 软链创建"

    def test_update_sh_removes_hermes_symlink(self):
        t = (SCRIPTS / "update.sh").read_text(encoding="utf-8")
        assert "已移除 hermes 命令入口" in t, "更新时应清掉旧的 hermes 软链"
        assert 'readlink -f "$_hlink"' in t, "只应删除指向本安装目录的软链"

    def test_uninstall_cleans_both_symlinks(self):
        t = (SCRIPTS / "uninstall.sh").read_text(encoding="utf-8")
        assert "/usr/local/bin/hermes" in t and "/usr/local/bin/coco" in t, "卸载应同时清理两个命令入口"


class TestSelfLocating:
    """脚本自定位：不再写死安装目录（以后改目录名不用改代码）"""

    def test_no_hardcoded_install_dir_in_our_scripts(self):
        for rel in ("scripts/healthcheck.py", "scripts/backup_db.py", "tools/real_estate_update_guard.py"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert 'expanduser("~/hermes-agent")' not in t, f"{rel} 仍写死旧安装目录"

    def test_derive_repo_root_from_file(self):
        for rel in ("scripts/healthcheck.py", "scripts/backup_db.py", "tools/real_estate_update_guard.py"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "Path(__file__).resolve()" in t, f"{rel} 未按自身位置推导仓库根"

    def test_backup_db_finds_env_db_relative_to_repo(self, tmp_path):
        """把仓库根换成一个临时目录，备份工具应去那里找 .env.db（证明不是写死路径）"""
        import importlib.util
        import shutil

        fake = tmp_path / "fake-coco"
        (fake / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPTS / "backup_db.py", fake / "scripts" / "backup_db.py")
        (fake / ".env.db").write_text("DATABASE_URL=postgresql://u:p@localhost:5432/db\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("bd_fake", fake / "scripts" / "backup_db.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert Path(mod._REPO_ROOT) == fake, f"仓库根推导错误：{mod._REPO_ROOT}"
        assert (Path(mod._REPO_ROOT) / ".env.db").exists(), "应在临时目录里找到 .env.db"


class TestMigrateScript:
    def _repo(self, tmp_path, dirty=False):
        work = tmp_path / "hermes-agent"
        (work / "scripts").mkdir(parents=True)
        for name in ("migrate_install_dir.sh", "healthcheck.py"):
            src = SCRIPTS / name
            if src.exists():
                (work / "scripts" / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "master", str(work)], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", str(work), "config", k, v], check=True)
        (work / "VERSION").write_text("0.0.0-1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True)
        if dirty:
            (work / "VERSION").write_text("dirty\n", encoding="utf-8")
        return work

    def test_dry_run_prints_plan_and_changes_nothing(self, tmp_path):
        work = self._repo(tmp_path)
        target = tmp_path / "coco"
        r = subprocess.run(["bash", str(work / "scripts" / "migrate_install_dir.sh"),
                            "--to", str(target), "--dry-run"], capture_output=True, text=True)
        out = r.stdout
        assert r.returncode == 0, out + r.stderr
        assert "干跑" in out and "移动目录" in out, out
        assert work.exists(), "干跑不应移动目录"
        assert not target.exists(), "干跑不应创建目标目录"

    def test_refuses_when_target_exists(self, tmp_path):
        work = self._repo(tmp_path)
        target = tmp_path / "coco"
        target.mkdir()
        r = subprocess.run(["bash", str(work / "scripts" / "migrate_install_dir.sh"),
                            "--to", str(target), "--yes"], capture_output=True, text=True)
        assert r.returncode != 0
        assert "已存在" in (r.stdout + r.stderr), r.stdout + r.stderr
        assert work.exists(), "拒绝时不应移动目录"

    def test_refuses_on_dirty_worktree(self, tmp_path):
        work = self._repo(tmp_path, dirty=True)
        r = subprocess.run(["bash", str(work / "scripts" / "migrate_install_dir.sh"),
                            "--to", str(tmp_path / "coco"), "--yes"], capture_output=True, text=True)
        assert r.returncode != 0
        assert "未提交" in (r.stdout + r.stderr), r.stdout + r.stderr

    def test_refuses_when_already_migrated(self, tmp_path):
        work = self._repo(tmp_path)
        r = subprocess.run(["bash", str(work / "scripts" / "migrate_install_dir.sh"),
                            "--to", str(work), "--yes"], capture_output=True, text=True)
        assert "无需迁移" in (r.stdout + r.stderr), r.stdout + r.stderr

    def test_help_lists_options(self, tmp_path):
        work = self._repo(tmp_path)
        r = subprocess.run(["bash", str(work / "scripts" / "migrate_install_dir.sh"), "--help"],
                           capture_output=True, text=True)
        assert r.returncode == 0 and "--dry-run" in r.stdout, r.stdout


class TestDocsUseNewLayout:
    def test_readmes_use_coco_dir(self):
        for rel in ("README.md", "README.zh-CN.md"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "~/coco" in t, f"{rel} 未使用新安装目录"
            # 旧路径只允许出现在"老实例迁移说明"里
            for line in t.split("\n"):
                if "~/hermes-agent" in line:
                    assert "migrate_install_dir" in line or "老实例" in line, f"{rel} 残留旧路径：{line.strip()[:80]}"

    def test_equivalent_update_command_uses_new_dir(self):
        for rel in ("README.md", "README.zh-CN.md"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "git -C ~/coco pull" in t, f"{rel} 的等价更新写法未换到新目录"

    def test_migration_notice_present(self):
        for rel in ("README.md", "README.zh-CN.md"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "migrate_install_dir.sh" in t, f"{rel} 未说明老实例如何迁移"
