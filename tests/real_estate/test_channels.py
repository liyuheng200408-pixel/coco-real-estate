"""稳定版 / 测试版双通道（2026-09-21 老板要求）。

老板的原话："我发的版本只有我能拉下来测试，其他人还是拉之前测试通过的版本，
等我测试没问题了再正式发布。" 方案 = 双分支双通道，**默认分支不动**：

  · master = 稳定版 —— 别人照文档安装/更新的就是它（零迁移）
  · next   = 测试版 —— 只有老板的测试机切到这个分支

关键机制：`git pull` 不带分支名 = 拉"当前分支对应的线上分支"，所以老板机器切到 next
之后，`git pull && bash scripts/update.sh` 这条老命令**一个字都不用改**就自动拉测试版。

本文件钉住三件事：① 通道标签与切换（含"工作区脏就拒绝"）；② 版本输出里能看到通道；
③ 晋升脚本只做快进（master 不是 next 的祖先时必须拒绝，否则会破坏 --ff-only 更新）。
"""
import json
import os
import shutil
import subprocess
import sys

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO_ROOT)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _init_repo(path, branch="master"):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(path), "config", k, v], check=True)
    (path / "VERSION").write_text("0.0.0-1\n", encoding="utf-8")
    return path


def _commit_all(repo, msg):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", msg], check=True)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


class TestChannelTool:
    """scripts/coco_channel.sh：通道标签 / 当前通道 / 期望通道 / 切换"""

    def test_labels(self):
        for branch, label in (("master", "稳定通道"), ("next", "测试通道"), ("feat/x", "自定义通道")):
            r = _run(["bash", str(SCRIPTS / "coco_channel.sh"), "label", branch])
            assert r.stdout.strip() == label, r.stdout

    def test_show_reports_current_channel(self, tmp_path):
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        shutil.copy(SCRIPTS / "coco_channel.sh", work / "scripts" / "coco_channel.sh")
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        r = _run(["bash", str(work / "scripts" / "coco_channel.sh"), "show"], cwd=work)
        assert "测试通道" in r.stdout and "next" in r.stdout, r.stdout

    def test_want_priority_env_then_file_then_current(self, tmp_path):
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        shutil.copy(SCRIPTS / "coco_channel.sh", work / "scripts" / "coco_channel.sh")
        assert _run(["bash", str(work / "scripts" / "coco_channel.sh"), "want"], cwd=work).stdout.strip() == "master"
        (work / ".coco-channel").write_text("next\n", encoding="utf-8")
        assert _run(["bash", str(work / "scripts" / "coco_channel.sh"), "want"], cwd=work).stdout.strip() == "next"
        env = {**os.environ, "COCO_CHANNEL": "custom"}
        assert subprocess.run(["bash", str(work / "scripts" / "coco_channel.sh"), "want"], cwd=work,
                              capture_output=True, text=True, env=env).stdout.strip() == "custom"

    def test_switch_moves_branch(self, tmp_path):
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        shutil.copy(SCRIPTS / "coco_channel.sh", work / "scripts" / "coco_channel.sh")
        _commit_all(work, "init")
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        (work / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(work, "next work")
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "master"], check=True)

        r = _run(["bash", str(work / "scripts" / "coco_channel.sh"), "switch", "next"], cwd=work)
        assert r.returncode == 0, r.stdout + r.stderr
        assert _git(work, "branch", "--show-current").stdout.strip() == "next"

    def test_switch_refuses_dirty_worktree(self, tmp_path):
        """绝不覆盖本地改动：工作区脏时必须拒绝切换"""
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        shutil.copy(SCRIPTS / "coco_channel.sh", work / "scripts" / "coco_channel.sh")
        _commit_all(work, "init")
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        (work / "VERSION").write_text("dirty\n", encoding="utf-8")      # 制造已跟踪文件的未提交改动

        r = _run(["bash", str(work / "scripts" / "coco_channel.sh"), "switch", "next"], cwd=work)
        assert r.returncode != 0
        assert "未提交的代码改动" in (r.stdout + r.stderr)
        assert _git(work, "branch", "--show-current").stdout.strip() == "master", "拒绝切换后不应换分支"


class TestChannelVisible:
    """通道要能看见 —— 否则老板不知道自己在测哪条线"""

    def test_coco_version_shows_channel(self):
        r = _run(["bash", "scripts/coco.sh", "version"])
        assert r.returncode == 0, r.stderr
        assert any(x in r.stdout for x in ("稳定通道", "测试通道")), r.stdout

    def test_version_tool_reports_channel(self):
        sys.path.insert(0, str(REPO_ROOT))
        from tools.real_estate_version import get_coco_version

        data = json.loads(get_coco_version())
        assert data["channel"] in ("稳定通道", "测试通道", "自定义通道", "未知通道")
        assert data["channel"] in data["message"]

    def test_update_script_prints_channel_and_supports_switch(self):
        text = (SCRIPTS / "update.sh").read_text(encoding="utf-8")
        assert "通道" in text and "coco_channel.sh" in text, "更新脚本没有显示/处理通道"
        assert ".coco-channel" in (SCRIPTS / "coco_channel.sh").read_text(encoding="utf-8")

    def test_install_script_supports_channel(self):
        text = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        assert "COCO_CHANNEL" in text
        assert 'git clone --branch "$COCO_CHANNEL"' in text, "安装脚本没有按通道克隆"


class TestPromoteRelease:
    """scripts/promote_release.sh：把测试版(next)晋升为稳定版(master)，只做快进"""

    def _setup(self, tmp_path, diverge=False):
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        for name in ("coco_channel.sh", "promote_release.sh"):
            shutil.copy(SCRIPTS / name, work / "scripts" / name)
        _commit_all(work, "init")
        for name in ("gitee.git", "github.git"):
            subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / name)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(tmp_path / "gitee.git")], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "github", str(tmp_path / "github.git")], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "github", "master"], check=True)
        # 造一个"测试版"：master 之上加提交
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        if diverge:
            # 让两条线分叉（稳定线有测试线没有的提交）→ 必须拒绝晋升
            subprocess.run(["git", "-C", str(work), "checkout", "-q", "master"], check=True)
            (work / "hotfix.txt").write_text("hotfix", encoding="utf-8")
            _commit_all(work, "hotfix on master")
            subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
            subprocess.run(["git", "-C", str(work), "push", "-q", "github", "master"], check=True)
            subprocess.run(["git", "-C", str(work), "checkout", "-q", "next"], check=True)
        (work / "feature.txt").write_text("feature", encoding="utf-8")
        next_tip = _commit_all(work, "feature on next")
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "github", "next"], check=True)
        return work, next_tip

    def _remote_master(self, tmp_path, which):
        return subprocess.run(["git", "-C", str(tmp_path / which), "rev-parse", "master"],
                              capture_output=True, text=True).stdout.strip()

    def test_dry_run_changes_nothing(self, tmp_path):
        work, next_tip = self._setup(tmp_path)
        before = self._remote_master(tmp_path, "gitee.git")
        r = _run(["bash", "scripts/promote_release.sh", "--dry-run"], cwd=work)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "dry-run" in r.stdout
        assert self._remote_master(tmp_path, "gitee.git") == before, "dry-run 不应改动远程"
        assert next_tip not in r.stdout

    def test_promotes_next_to_master_on_both_remotes(self, tmp_path):
        work, next_tip = self._setup(tmp_path)
        r = _run(["bash", "scripts/promote_release.sh"], cwd=work)
        assert r.returncode == 0, r.stdout + r.stderr
        assert self._remote_master(tmp_path, "gitee.git") == next_tip
        assert self._remote_master(tmp_path, "github.git") == next_tip
        assert "晋升完成" in r.stdout

    def test_refuses_when_master_is_not_ancestor(self, tmp_path):
        """稳定线有测试线没有的提交（分叉）时必须拒绝 —— 否则会破坏 --ff-only 更新"""
        work, next_tip = self._setup(tmp_path, diverge=True)
        before = self._remote_master(tmp_path, "gitee.git")
        r = _run(["bash", "scripts/promote_release.sh"], cwd=work)
        assert r.returncode != 0
        assert "无法快进" in (r.stdout + r.stderr)
        assert self._remote_master(tmp_path, "gitee.git") == before, "拒绝时不应改动 master"

    def test_tag_option_creates_and_pushes_tag(self, tmp_path):
        work, next_tip = self._setup(tmp_path)
        r = _run(["bash", "scripts/promote_release.sh", "--tag", "v0.0.0-99"], cwd=work)
        assert r.returncode == 0, r.stdout + r.stderr
        tags = subprocess.run(["git", "-C", str(tmp_path / "gitee.git"), "tag"], capture_output=True, text=True).stdout
        assert "v0.0.0-99" in tags


class TestUpdateScriptStartsCleanly:
    """更新脚本自身必须能正常启动 —— 这一条是被真事逼出来的：

    曾经把通道代码写在 info()/fail() 定义**之前**，脚本一启动就 "command not found"
    直接中断（还调了一个根本不存在的 fail）。所以这里真跑一次脚本，钉住：
    ① 不出现 command not found；② 能打印当前通道；③ 能走到 venv 前提检查（说明前面全过了）。
    """

    def _fake_repo(self, tmp_path, branch="master"):
        work = tmp_path / "work"
        (work / "scripts").mkdir(parents=True)
        for name in ("update.sh", "coco_channel.sh"):
            shutil.copy(SCRIPTS / name, work / "scripts" / name)
        subprocess.run(["git", "init", "-q", "-b", branch, str(work)], check=True)
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", str(work), "config", k, v], check=True)
        (work / "VERSION").write_text("0.0.0-1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True)
        return work

    def test_script_starts_and_reaches_preflight(self, tmp_path):
        work = self._fake_repo(tmp_path)
        r = _run(["bash", str(work / "scripts" / "update.sh")], cwd=work)
        out = r.stdout + r.stderr
        assert "command not found" not in out, out
        assert "当前通道" in out, out
        assert r.returncode != 0 and "虚拟环境" in out, "应当停在 venv 前提检查（本临时仓库不是真实安装）"

    def test_test_flag_switches_to_test_channel(self, tmp_path):
        """老板命令：update.sh --test → 自动切到测试通道"""
        work = self._fake_repo(tmp_path)
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        (work / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-qm", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "master"], check=True)

        r = _run(["bash", str(work / "scripts" / "update.sh"), "--test"], cwd=work)
        out = r.stdout + r.stderr
        assert "command not found" not in out, out
        assert "测试通道" in out, out
        assert _git(work, "branch", "--show-current").stdout.strip() == "next", "没有切到测试通道"

    def test_stable_flag_switches_back(self, tmp_path):
        work = self._fake_repo(tmp_path, branch="next")
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "next"], check=True)

        r = _run(["bash", str(work / "scripts" / "update.sh"), "--stable"], cwd=work)
        out = r.stdout + r.stderr
        assert "稳定通道" in out, out
        assert _git(work, "branch", "--show-current").stdout.strip() == "master", "没有切回稳定通道"

    def test_flag_refuses_to_switch_with_dirty_tree(self, tmp_path):
        work = self._fake_repo(tmp_path)
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "master"], check=True)
        (work / "VERSION").write_text("dirty\n", encoding="utf-8")     # 已跟踪文件的未提交改动

        r = _run(["bash", str(work / "scripts" / "update.sh"), "--test"], cwd=work)
        out = r.stdout + r.stderr
        assert "未提交改动" in out, out
        assert _git(work, "branch", "--show-current").stdout.strip() == "master", "脏工作区不应换分支"

    def test_unknown_flag_is_rejected(self, tmp_path):
        work = self._fake_repo(tmp_path)
        r = _run(["bash", str(work / "scripts" / "update.sh"), "--nonsense"], cwd=work)
        assert r.returncode != 0 and "未知参数" in (r.stdout + r.stderr)


class TestRuntimeFilesDoNotBlockSwitch:
    """运行时文件（更新锁 / 通道标记 / .env.db / 密钥）是未跟踪的，不该挡住切通道。

    真缺陷记录：更新脚本自己会创建 .coco-update.lock，若切通道的干净检查把未跟踪文件
    也算进去，老板的机器就会永远切不动通道（第一次更新后就再也切不了）。
    """

    def test_lock_file_does_not_block_switch(self, tmp_path):
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        shutil.copy(SCRIPTS / "coco_channel.sh", work / "scripts" / "coco_channel.sh")
        _commit_all(work, "init")
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "next"], check=True)
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "master"], check=True)
        # 模拟更新脚本留下的运行时文件
        (work / ".coco-update.lock").write_text("", encoding="utf-8")
        (work / ".coco-channel").write_text("next\n", encoding="utf-8")
        (work / ".env.db").write_text("secret", encoding="utf-8")

        r = _run(["bash", str(work / "scripts" / "coco_channel.sh"), "switch", "next"], cwd=work)
        assert r.returncode == 0, r.stdout + r.stderr
        assert _git(work, "branch", "--show-current").stdout.strip() == "next"


class TestPromoteSyncsTestChannelFirst:
    """晋升前必须先让测试通道与远程一致 —— 真缺陷记录：

    本地 next 有未推送提交时，旧脚本按 origin/next（旧 SHA）校验，结果**误报失败**
    （远程其实已更新），并且把标签打到了旧提交上。所以现在先推齐测试分支，再按远程 SHA 晋升。
    """

    def test_promote_pushes_test_channel_before_promoting(self, tmp_path):
        work = _init_repo(tmp_path / "work")
        (work / "scripts").mkdir(exist_ok=True)
        for name in ("coco_channel.sh", "promote_release.sh"):
            shutil.copy(SCRIPTS / name, work / "scripts" / name)
        _commit_all(work, "init")
        for name in ("gitee.git", "github.git"):
            subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / name)], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(tmp_path / "gitee.git")], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "github", str(tmp_path / "github.git")], check=True)
        for r in ("origin", "github"):
            subprocess.run(["git", "-C", str(work), "push", "-q", r, "master"], check=True)
        # 测试分支：推一版旧的，然后在本地再加一个"未推送"的提交
        subprocess.run(["git", "-C", str(work), "checkout", "-q", "-b", "next"], check=True)
        (work / "old.txt").write_text("old", encoding="utf-8")
        _commit_all(work, "pushed to test channel")
        for r in ("origin", "github"):
            subprocess.run(["git", "-C", str(work), "push", "-q", r, "next"], check=True)
        (work / "new.txt").write_text("new", encoding="utf-8")
        tip = _commit_all(work, "not pushed yet")

        r = _run(["bash", "scripts/promote_release.sh"], cwd=work)
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        assert "推齐" in out, out
        assert subprocess.run(["git", "-C", str(tmp_path / "gitee.git"), "rev-parse", "master"],
                              capture_output=True, text=True).stdout.strip() == tip
        assert subprocess.run(["git", "-C", str(tmp_path / "gitee.git"), "rev-parse", "next"],
                              capture_output=True, text=True).stdout.strip() == tip, "测试通道也应被推齐"
