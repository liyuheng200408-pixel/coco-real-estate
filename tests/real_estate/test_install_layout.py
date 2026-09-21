"""安装布局变更的回归测试（老板 2026-09-21 拍板 ①+②）：

  ① `hermes` 命令不再对外暴露（统一用 coco）——install.sh 不建软链、update.sh 每次清理；
  ② 安装目录 ~/hermes-agent → ~/coco，脚本自定位（按自身位置推导）。

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


class TestDocsUseNewLayout:
    def test_readmes_use_coco_dir(self):
        for rel in ("README.md", "README.zh-CN.md"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "~/coco" in t, f"{rel} 未使用新安装目录"
            assert "~/hermes-agent" not in t, f"{rel} 残留旧安装目录（老板要求不写老实例迁移说明）"

    def test_equivalent_update_command_uses_new_dir(self):
        for rel in ("README.md", "README.zh-CN.md"):
            t = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert "git -C ~/coco pull" in t, f"{rel} 的等价更新写法未换到新目录"



class TestInstallScriptSymlinkPolicyBehaviour:
    """真跑一遍 install.sh 里的软链逻辑（属功能级核验，不是看字符串）：

    · 默认（不设 COCO_EXPOSE_HERMES）：清掉指向本安装目录的旧 hermes 软链；
    · COCO_EXPOSE_HERMES=1：创建 hermes 软链；
    · 指向别处的同名软链一律不动。
    """

    def _run_block(self, tmp_path, expose_hermes=None):
        import os

        src = (REPO_ROOT / "install.sh").read_text(encoding="utf-8").split("\n")
        start = next(i for i, l in enumerate(src) if l.strip().startswith("# hermes 命令（2026-09-21"))
        # 到该块的收尾 fi（下一处与 start 同缩进的 fi）
        indent = len(src[start]) - len(src[start].lstrip())
        end = next(i for i in range(start + 1, len(src))
                   if src[i].strip() == "fi" and (len(src[i]) - len(src[i].lstrip())) == indent)
        block = "\n".join(src[start:end + 1])

        install_dir = tmp_path / "coco-install"
        (install_dir / "venv" / "bin").mkdir(parents=True)
        (install_dir / "venv" / "bin" / "hermes").write_text("#!/bin/sh\n", encoding="utf-8")
        (install_dir / "venv" / "bin" / "hermes").chmod(0o755)

        fake_bin = tmp_path / "usr-local-bin"
        fake_bin.mkdir()
        fake_home = tmp_path / "home"
        (fake_home / ".local" / "bin").mkdir(parents=True)
        ours = fake_bin / "hermes"
        ours.symlink_to(install_dir / "venv" / "bin" / "hermes")
        theirs = fake_bin / "other-hermes"
        theirs.symlink_to("/bin/true")

        script = tmp_path / "block.sh"
        script.write_text(
            "set -uo pipefail\n"
            'INSTALL_DIR="' + str(install_dir) + '"\n'
            'HOME="' + str(fake_home) + '"\n'
            'ok() { echo "  OK $*"; }\n'
            'warn() { echo "  WARN $*"; }\n'
            + block.replace("/usr/local/bin/hermes", str(ours)).replace("$HOME/.local/bin/hermes", str(fake_home / ".local" / "bin" / "hermes"))
            + "\n",
            encoding="utf-8")
        env = dict(os.environ)
        if expose_hermes is not None:
            env["COCO_EXPOSE_HERMES"] = expose_hermes
        else:
            env.pop("COCO_EXPOSE_HERMES", None)
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
        return r, ours, theirs

    def test_default_removes_our_symlink(self, tmp_path):
        r, ours, theirs = self._run_block(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not ours.is_symlink(), "默认应当清掉我们自己的 hermes 软链"
        assert theirs.is_symlink(), "指向别处的同名软链不能动"

    def test_expose_flag_creates_symlink(self, tmp_path):
        r, ours, _ = self._run_block(tmp_path, expose_hermes="1")
        assert r.returncode == 0, r.stdout + r.stderr
        assert ours.is_symlink(), "COCO_EXPOSE_HERMES=1 时应创建 hermes 软链"


class TestSelfLocatingBehaviour:
    def test_healthcheck_install_dir_follows_file_location(self, tmp_path):
        import importlib.util
        import shutil

        fake = tmp_path / "renamed-coco"
        (fake / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPTS / "healthcheck.py", fake / "scripts" / "healthcheck.py")
        spec = importlib.util.spec_from_file_location("hc_fake", fake / "scripts" / "healthcheck.py")
        mod = importlib.util.module_from_spec(spec)
        # 只执行到读取常量即可：捕获导入期异常（该模块导入时会定义常量）
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
        assert str(mod.INSTALL_DIR).startswith(str(fake)), f"安装目录未跟随文件位置：{mod.INSTALL_DIR}"


class TestDocsCommandsExist:
    """文档里出现的每个 coco 子命令都必须真实存在（防文档写了不存在的命令）"""

    def test_every_documented_coco_command_exists(self):
        import re

        coco = (SCRIPTS / "coco.sh").read_text(encoding="utf-8")
        # 解析 case 分支标签（如 `version|--version|-v|"")`、`model|setup)`），只保留像命令的 token
        known = set()
        for group in re.findall(r"^\s{2}([^)\n]+)\)", coco, re.M):
            for token in group.split("|"):
                token = token.strip().strip('"')
                if re.fullmatch(r"[a-z][a-z\-]*", token):
                    known.add(token)
        assert {"version", "check", "backup", "update", "uninstall", "model", "setup"} <= known, known
        assert known, "未从 coco.sh 解析出子命令"
        for rel in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            # 只认"命令位置"的 coco（行首/空白/&&/;/|/反引号之后），避免把 `git -C ~/coco pull` 误判
            for cmd in set(re.findall(r"(?:^|[\s;&|`])coco\s+([a-z][a-z\-]{2,})", text, re.M)):
                assert cmd in known, f"{rel} 写了不存在的命令：coco {cmd}（已知：{sorted(known)}）"
